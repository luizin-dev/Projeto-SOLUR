# -*- coding: utf-8 -*-
"""Servidor local do Video Factory (stdlib puro, sem dependencias).

  GET  /              -> interface web
  GET  /api/presets   -> temas e vozes disponiveis
  GET  /api/status    -> progresso do projeto atual
  GET  /api/projects  -> projetos anteriores
  GET  /api/images?dir= -> imagens de um projeto (galeria/refazer)
  GET  /api/img?p=    -> serve uma imagem PNG do projeto
  GET  /api/video?p=  -> stream do MP4 com suporte a Range (seek)
  POST /api/start     -> inicia geracao {script, title, theme, voice}
  POST /api/redo      -> refaz UMA imagem {dir, name} com seed novo
"""
import json
import os
import re
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pipeline as pipeline_mod
from presets import BASE, FONTS, PORT, PROJECTS, THEMES, VOICES, WEB

CURRENT_FILE = os.path.join(PROJECTS, "_current.json")
_lock = threading.Lock()
_state = {"project_dir": None, "thread": None}


def _read_current():
    try:
        with open(CURRENT_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_current(d):
    try:
        with open(CURRENT_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except OSError:
        pass


def _read_status(project_dir):
    if not project_dir:
        return {"idle": True}
    p = os.path.join(project_dir, "status.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"idle": True, "msg": "aguardando..."}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # silencia log no console
        pass

    # ---------------- helpers ----------------
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, ctype, range_ok=False):
        try:
            size = os.path.getsize(path)
        except OSError:
            self._send(404, '{"error":"not found"}')
            return
        rng = self.headers.get("Range")
        if range_ok and rng:
            try:
                start = int(rng.replace("bytes=", "").split("-")[0])
            except ValueError:
                start = 0
            start = max(0, min(start, size - 1))
            end = size - 1
            with open(path, "rb") as f:
                f.seek(start)
                data = f.read(end - start + 1)
            self.send_response(206)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        with open(path, "rb") as f:
            data = f.read()
        self._send(200, data, ctype)

    # ---------------- GET ----------------
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(url.query)

        if url.path == "/":
            return self._file(os.path.join(WEB, "index.html"), "text/html; charset=utf-8")
        if url.path.startswith("/fonts/"):
            name = os.path.basename(url.path)
            return self._file(os.path.join(FONTS, name), "font/ttf")
        if url.path == "/api/presets":
            themes = [{"id": k, **{kk: vv for kk, vv in v.items()}}
                      for k, v in THEMES.items()]
            for t in themes:
                t["accent"] = "#%02x%02x%02x" % tuple(t["accent"])
            return self._send(200, json.dumps({"themes": themes, "voices": VOICES},
                                              ensure_ascii=False))
        if url.path == "/api/status":
            cur = _read_current()
            st = _read_status(cur.get("dir"))
            busy = bool(_state["thread"] and _state["thread"].is_alive())
            st["busy"] = busy
            st["dir"] = cur.get("dir")
            return self._send(200, json.dumps(st, ensure_ascii=False))
        if url.path == "/api/projects":
            out = []
            try:
                for name in sorted(os.listdir(PROJECTS), reverse=True):
                    d = os.path.join(PROJECTS, name)
                    if not os.path.isdir(d) or name.startswith("_"):
                        continue
                    mp4s = [f for f in os.listdir(d) if f.endswith(".mp4")
                            and not f.startswith("full_")]
                    out.append({"name": name,
                                "status": _read_status(d).get("stage", "?"),
                                "video": mp4s[0] if mp4s else None})
            except OSError:
                pass
            return self._send(200, json.dumps(out, ensure_ascii=False))
        if url.path == "/api/images":
            d = os.path.abspath((q.get("dir") or [""])[0])
            if not (d.startswith(os.path.abspath(PROJECTS) + os.sep)
                    and os.path.isdir(d)):
                return self._send(404, '{"error":"projeto invalido"}')
            imgs = []
            idir = os.path.join(d, "images")
            try:
                for name in sorted(os.listdir(idir)):
                    if not name.endswith(".png"):
                        continue
                    p = os.path.join(idir, name)
                    sz = os.path.getsize(p)
                    ph = os.path.exists(p + ".placeholder")
                    imgs.append({"name": name, "size": sz,
                                 "ok": sz > 30000 and not ph})
            except OSError:
                pass
            return self._send(200, json.dumps({"images": imgs}, ensure_ascii=False))
        if url.path == "/api/img":
            rel = (q.get("p") or [""])[0]
            p = os.path.abspath(os.path.join(BASE, rel))
            if (not p.lower().endswith(".png") or not os.path.isfile(p)
                    or not p.startswith(os.path.abspath(PROJECTS) + os.sep)):
                return self._send(404, '{"error":"not found"}')
            return self._file(p, "image/png")
        if url.path == "/api/video":
            rel = (q.get("p") or [""])[0]
            if rel:
                p = os.path.abspath(os.path.join(BASE, rel))
            else:
                p = _read_current().get("output") or ""
            if (not p or not os.path.exists(p)
                    or not os.path.abspath(p).startswith(os.path.abspath(BASE))
                    or not p.lower().endswith(".mp4")):
                return self._send(404, '{"error":"sem video"}')
            return self._file(p, "video/mp4", range_ok=True)
        return self._send(404, '{"error":"not found"}')

    # ---------------- POST ----------------
    def do_POST(self):
        if self.path == "/api/start":
            return self._post_start()
        if self.path == "/api/redo":
            return self._post_redo()
        return self._send(404, '{"error":"not found"}')

    def _post_start(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return self._send(400, '{"error":"json invalido"}')
        script = (body.get("script") or "").strip()
        if len(script) < 40:
            return self._send(400, '{"error":"roteiro muito curto"}')
        with _lock:
            if _state["thread"] and _state["thread"].is_alive():
                return self._send(409, '{"error":"ja existe uma geracao em andamento"}')
            pdir = pipeline_mod.new_project_dir(body.get("title") or "video")
            st = pipeline_mod.Status(pdir)
            t = threading.Thread(
                target=self._run, daemon=True,
                args=(script, pdir, body.get("title"), body.get("theme") or "noir",
                      body.get("voice"), st))
            _state["project_dir"] = pdir
            _state["thread"] = t
            _write_current({"dir": pdir, "output": None})
            t.start()
        return self._send(200, json.dumps({"ok": True, "dir": pdir}))

    def _post_redo(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return self._send(400, '{"error":"json invalido"}')
        d = os.path.abspath(body.get("dir") or "")
        name = os.path.basename(body.get("name") or "")
        if not re.match(r"^s\d+_\d+b?\.png$", name):
            return self._send(400, '{"error":"nome de imagem invalido"}')
        if not (d.startswith(os.path.abspath(PROJECTS) + os.sep)
                and os.path.isdir(d)):
            return self._send(400, '{"error":"projeto invalido"}')
        img = os.path.join(d, "images", name)
        if not os.path.exists(img):
            return self._send(404, '{"error":"imagem nao existe"}')
        cfgp = os.path.join(d, "config.json")
        try:
            with open(cfgp, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            return self._send(409, '{"error":"projeto antigo sem config.json; gere de novo pelo botao principal"}')
        with _lock:
            if _state["thread"] and _state["thread"].is_alive():
                return self._send(409, '{"error":"ja existe uma geracao em andamento"}')
            try:  # marcador: o pipeline regera SO esta imagem, com seed novo
                with open(img + ".reroll", "w", encoding="utf-8") as f:
                    f.write("1")
            except OSError:
                return self._send(500, '{"error":"nao consegui marcar a imagem"}')
            st = pipeline_mod.Status(d)
            t = threading.Thread(
                target=self._run, daemon=True,
                args=(cfg.get("script") or "", d, cfg.get("title"),
                      cfg.get("theme") or "noir", cfg.get("voice"), st))
            _state["project_dir"] = d
            _state["thread"] = t
            cur = _read_current()
            if cur.get("dir") != d:
                cur["output"] = None
            cur["dir"] = d
            _write_current(cur)
            t.start()
        return self._send(200, '{"ok": true}')

    @staticmethod
    def _run(script, pdir, title, theme, voice, st):
        try:
            pipeline_mod.run_project(script, pdir, title, theme, voice, status=st)
            cur = _read_current()
            if cur.get("dir") == pdir:
                cur["output"] = st.state.get("output")
                _write_current(cur)
        except Exception as e:
            st.fail(e)


def main():
    os.makedirs(PROJECTS, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Video Factory rodando em http://localhost:{PORT}  (Ctrl+C para sair)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
