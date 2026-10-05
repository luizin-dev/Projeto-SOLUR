# -*- coding: utf-8 -*-
"""Orquestrador do Video Factory: roteiro -> video completo.

Etapas: parse -> TTS -> timeline/legendas -> imagens -> musica -> cartoes -> montagem.
Cada etapa atualiza status.json (usado pela interface web) e aceita retomada
(arquivos existentes sao reaproveitados)."""
import argparse
import hashlib
import json
import os
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import images as images_mod
import parser as parser_mod
import translate as translate_mod
import youtube as youtube_mod
from cards import title_card, quote_card
from music import build_score
from presets import IMG_SIZE, THEMES, normalize_theme, voice_lang
from ttsx import synth

STAGES = [
    ("parse", "Lendo roteiro", 2),
    ("tts", "Gerando narracao", 15),
    ("timeline", "Planejando timeline e legendas", 3),
    ("images", "Gerando imagens", 46),
    ("music", "Compondo trilha sonora", 8),
    ("cards", "Renderizando cartoes", 3),
    ("assemble", "Montando video (Ken Burns, mixagem, legendas)", 19),
    ("youtube", "Kit YouTube (thumbnail, capitulos)", 4),
]

SHOT_SHOTS = [
    "cinematic wide establishing shot of",
    "medium shot of",
    "dramatic close-up of",
    "over-the-shoulder shot of",
    "low angle shot of",
    "silhouette shot of",
    "profile shot of",
    "intimate detail shot of",
]

# shots neutros p/ cartoon: a palavra "cinematic"/"dramatic" puxa o modelo
# para pintura fotorrealista e mata o estilo flat (validado em teste A/B)
CARTOON_SHOTS = [
    "wide view of",
    "medium view of",
    "close-up of",
    "full-body view of",
    "profile view of",
    "detail view of",
]


class Status:
    def __init__(self, project_dir):
        self.path = os.path.join(project_dir, "status.json")
        self.log = []
        self._lk = threading.Lock()
        self.state = {"stage": "", "step": 0, "total": 0, "pct": 0, "msg": "",
                      "done": False, "error": None, "output": None, "log": self.log}

    def say(self, msg):
        with self._lk:
            self.log.append(msg)
            if len(self.log) > 400:
                del self.log[:200]
            self.state["msg"] = msg
            self._flush()
        try:
            print(msg, flush=True)
        except UnicodeEncodeError:
            print(msg.encode("ascii", "replace").decode(), flush=True)

    def stage(self, key, step, total):
        with self._lk:
            for i, (k, label, w) in enumerate(STAGES):
                if k == key:
                    base = sum(x[2] for x in STAGES[:i])
                    self.state["stage"] = label
                    self.state["pct"] = base + int(w * (step / max(total, 1)))
                    break
            self.state["step"] = step
            self.state["total"] = total
            self._flush()

    def finish(self, output):
        with self._lk:
            self.state.update(done=True, pct=100, stage="Concluido", output=output)
            self._flush()

    def fail(self, err):
        with self._lk:
            self.state.update(error=str(err)[:800])
            self._flush()

    def _flush(self):
        self.state["log"] = self.log[-120:]
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False)
        except OSError:
            pass


def _narration_excerpt(narration, k, chunk_words=16):
    words = " ".join(narration).split()
    if not words:
        return "abstract atmospheric scene"
    chunks = max(1, len(words) // chunk_words)
    i = k % chunks
    return " ".join(words[i * chunk_words:(i + 1) * chunk_words])


def _seed(prompt):
    return int(hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:8], 16) % 1_000_000


def new_project_dir(title):
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects")
    os.makedirs(base, exist_ok=True)
    slug = re.sub(r"[^\w-]", "", re.sub(r"\s+", "_", title.strip()))[:40] or "projeto"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    d = os.path.join(base, f"{slug}-{stamp}")
    os.makedirs(d, exist_ok=True)
    return d


def run_project(script_text, project_dir, title=None, theme="noir", voice=None,
                status=None, log=None):
    """Executa o pipeline completo. status/log opcionais p/ interface web."""
    theme = normalize_theme(theme)
    th = THEMES[theme]
    voice = voice or th["voice"]
    rate = th["rate"]
    mood = th["mood"]
    accent = tuple(th["accent"])
    lang = voice_lang(voice)
    say = (status.say if status else log) or print
    os.makedirs(os.path.join(project_dir, "audio"), exist_ok=True)
    os.makedirs(os.path.join(project_dir, "images"), exist_ok=True)
    os.makedirs(os.path.join(project_dir, "cards"), exist_ok=True)
    os.makedirs(os.path.join(project_dir, "subs"), exist_ok=True)
    audio_dir = os.path.join(project_dir, "audio")

    # guarda os insumos: a interface usa isto para "refazer imagem"
    # (rodar de novo o mesmo projeto sem redigitar o roteiro)
    try:
        with open(os.path.join(project_dir, "config.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"script": script_text, "title": title, "theme": theme,
                       "voice": voice}, f, ensure_ascii=False)
    except OSError:
        pass

    # 1. parse ------------------------------------------------------------
    status and status.stage("parse", 1, 1)
    doc = parser_mod.parse_script(script_text)
    if title:
        doc["title"] = title
    say(f"[1/8] Roteiro lido: {len(doc['scenes'])} cenas, titulo '{doc['title']}'")
    if not doc["scenes"]:
        raise RuntimeError("Nenhuma cena encontrada no roteiro.")
    with open(os.path.join(project_dir, "roteiro_processado.json"), "w",
              encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)

    # 2. TTS --------------------------------------------------------------
    status and status.stage("tts", 0, len(doc["scenes"]) + 1)
    say(f"[2/8] Narracao ({voice})...")
    for k, sc in enumerate(doc["scenes"]):
        status and status.stage("tts", k, len(doc["scenes"]) + 1)
        out = os.path.join(audio_dir, f"narr_s{sc['idx']:02d}.mp3")
        text = "\n\n".join(sc["narration"]).strip()
        if text and not os.path.exists(out):
            if not synth(text, out, voice, rate, say):
                say(f"    AVISO: narracao da cena {sc['idx']} falhou "
                    f"(cena ficara so com musica)")
    fq = doc.get("final_question")
    if fq:
        status and status.stage("tts", len(doc["scenes"]), len(doc["scenes"]) + 1)
        out = os.path.join(audio_dir, "narr_final.mp3")
        if not os.path.exists(out):
            synth(fq, out, voice, rate, say)

    # 3. timeline + legendas ----------------------------------------------
    status and status.stage("timeline", 1, 1)
    tl = parser_mod.build_timeline(doc, audio_dir, th.get("img_every", 8.0))
    tl["meta"] = {"title": doc["title"], "theme": theme, "voice": voice}
    with open(os.path.join(project_dir, "timeline.json"), "w", encoding="utf-8") as f:
        json.dump(tl, f, ensure_ascii=False, indent=1)
    n_cues = parser_mod.build_ass(tl, audio_dir, os.path.join(project_dir, "subs", "subs.ass"))
    total_min = tl["total"] / 60
    say(f"[3/8] Timeline: {total_min:.1f} min, {n_cues} legendas")

    # 4. imagens (3 downloads em paralelo; shots selecionados ganham uma
    #    variacao "b" da mesma descricao -> dissolve longo = shot animado) ----
    chars = doc.get("characters") or []

    # prompts visuais em portugues viram ingles (os modelos de imagem seguem
    # o contexto muito melhor); cache em disco por projeto, quota-free fallback
    tcache = os.path.join(project_dir, "translation.json")
    for d in doc["scenes"]:
        if d.get("visuals"):
            d["visuals"] = [translate_mod.to_en(v, tcache, say) for v in d["visuals"]]
        elif d.get("narration"):
            # sem VISUAL PROMPT: trecho da narracao vira a descricao da
            # imagem — traduz tambem (TTS/legendas ja sairam, mutacao segura)
            d["narration"] = [translate_mod.to_en(l, tcache, say)
                              for l in d["narration"]]
    chars = [[n, translate_mod.to_en(ds, tcache, say)] for n, ds in chars]

    def _prompt_for(idx, i):
        dsc = next((d for d in doc["scenes"] if d["idx"] == idx), None)
        visuals = (dsc["visuals"] if dsc else []) or []
        if visuals:
            base = visuals[(i - 1) % len(visuals)]
        else:
            base = _narration_excerpt(dsc["narration"] if dsc else [], i - 1)
        if chars and th.get("char_focus"):
            # cartoon flat (formula validada em ~15 testes A/B/C/D/E/F/G):
            # - estilo PRIMEIRO + shot neutro ("cinematic" puxa p/ pintura);
            # - descricao do personagem UMA vez: repetida, o modelo colapsa
            #   a imagem num close de retrato e perde a cena;
            # - "the main character of a modern animated series" ancora o
            #   personagem; ~60% de acerto na especie (o botao "refazer"
            #   da interface resolve os sorteios ruins sem perder o resto).
            name, desc = chars[0]
            shot = CARTOON_SHOTS[(i - 1) % len(CARTOON_SHOTS)]
            return (f"{th['style']}: {shot} {name} ({desc}), "
                    f"the main character of a modern animated series, in {base}")
        shot = SHOT_SHOTS[(i - 1) % len(SHOT_SHOTS)]
        prompt = f"{shot} {base}"
        if chars and i % 2 == 0:
            name, desc = chars[(i // 2) % len(chars)]
            prompt += f", featuring {name} ({desc})"
        return prompt + f", {th['style']}"

    jobs = []
    for sc in tl["scenes"]:
        idx = sc["idx"]
        for i in range(1, sc["n_images"] + 1):
            out = os.path.join(project_dir, "images", f"s{idx}_{i:02d}.png")
            # ".reroll" (botao refazer da interface): regera mesmo com a
            # imagem atual saudavel
            if os.path.exists(out + ".reroll") or not (
                    os.path.exists(out) and os.path.getsize(out) > 30000
                    and not os.path.exists(out + ".placeholder")):
                jobs.append((idx, i, 0, out))
            if i % 4 == 1:  # shot "animado": 2a versao da mesma cena p/ morph
                vout = out[:-4] + "b.png"
                if os.path.exists(vout + ".reroll") or not (
                        os.path.exists(vout) and os.path.getsize(vout) > 30000):
                    jobs.append((idx, i, 1, vout))

    n_total = len(jobs)
    status and status.stage("images", 0, max(n_total, 1))
    if jobs:
        say(f"[4/8] Baixando {n_total} imagens (3 em paralelo, Pollinations)...")
        lk = threading.Lock()
        done = [0]

        def _work(job):
            idx, i, variant, out = job
            _prompt = _prompt_for(idx, i)
            try:  # salva o prompt junto a imagem: recovery/re-do sem rederiv
                with open(out + ".prompt", "w", encoding="utf-8") as f:
                    f.write(_prompt)
            except OSError:
                pass
            # "refazer": mesma prompt+seed daria exatamente a mesma imagem,
            # entao o re-do usa um nonce no seed e guarda a antiga ate dar
            # certo (se falhar, a antiga volta = nunca fica pior que antes)
            seed_extra = variant
            backup = None
            if os.path.exists(out + ".reroll"):
                try:
                    os.remove(out + ".reroll")
                except OSError:
                    pass
                seed_extra = variant + 1000 + int(time.time() * 1000) % 900000
                if os.path.exists(out):
                    backup = out + ".old"
                    try:
                        os.replace(out, backup)
                    except OSError:
                        backup = None
            st = images_mod.fetch(_prompt, out, say,
                                  seed_extra=seed_extra, prefer=th.get("img_model"))
            if backup is not None:
                good = (os.path.exists(out) and os.path.getsize(out) > 30000
                        and not os.path.exists(out + ".placeholder"))
                if good:
                    try:
                        os.remove(backup)
                    except OSError:
                        pass
                else:  # refazer falhou: devolve a imagem antiga
                    try:
                        os.remove(out + ".placeholder")
                    except OSError:
                        pass
                    try:
                        os.replace(backup, out)
                        st = "mantida"
                    except OSError:
                        pass
            tag = f"s{idx}_{i:02d}" + ("b" if variant else "")
            if "(" in st:
                say(f"    imagem {tag} baixada ({st})")
            elif st == "placeholder":
                say(f"    AVISO: imagem {tag} indisponivel; usando placeholder")
            elif st == "mantida":
                say(f"    imagem {tag}: refazer falhou; mantida a versao anterior")
            with lk:
                done[0] += 1
                status and status.stage("images", done[0], n_total)

        with ThreadPoolExecutor(max_workers=3) as ex:
            list(ex.map(_work, jobs))

        # varredura final: a roleta 402 do tier gratuito muda de minuto a
        # minuto; imagens que viraram placeholder ganham uma 2a rodada agora
        ph = [j for j in jobs if os.path.exists(j[3] + ".placeholder")]
        if ph:
            say(f"    varredura final: retentando {len(ph)} imagem(ns) que falharam...")
            done[0] = n_total - len(ph)   # retrabalha a barra de progresso
            with ThreadPoolExecutor(max_workers=3) as ex:
                list(ex.map(_work, ph))
    else:
        say("[4/8] Imagens: todas ja estavam em cache")
    status and status.stage("images", max(n_total, 1), max(n_total, 1))

    # 5. musica ------------------------------------------------------------
    status and status.stage("music", 1, 1)
    say("[5/8] Compondo trilha sonora...")
    build_score(project_dir, tl, doc, mood, say)

    # 6. cartoes -------------------------------------------------------------
    status and status.stage("cards", 1, 2)
    title_card(doc["title"], os.path.join(project_dir, "cards", "title.png"),
               accent, voice)
    say("[6/8] Cartao de titulo ok")
    if doc.get("final_text"):
        status and status.stage("cards", 2, 2)
        quote_card(doc["final_text"],
                   os.path.join(project_dir, "cards", "quote.png"), accent)
        say("      Cartao de citacao ok")

    # 7. montagem ---------------------------------------------------------
    status and status.stage("assemble", 0, 1)
    say("[7/8] Montando video final (pode levar varios minutos)...")
    import assembly
    out_mp4 = assembly.assemble(project_dir, say)

    # 8. kit youtube ---------------------------------------------------------
    status and status.stage("youtube", 1, 1)
    say("[8/8] Kit YouTube (thumbnails, capitulos, pacote de upload)...")
    try:
        youtube_mod.make_kit(project_dir, doc, tl, accent, say)
    except Exception as e:  # o video ja esta pronto; kit nunca derruba a entrega
        say(f"    AVISO: kit youtube falhou ({e})")

    status and status.finish(out_mp4)
    say(f"PRONTO -> {out_mp4}")
    return out_mp4


def main():
    ap = argparse.ArgumentParser(description="Video Factory: roteiro -> video")
    ap.add_argument("--script", required=True, help="arquivo .txt com o roteiro")
    ap.add_argument("--title", default=None)
    ap.add_argument("--theme", default="noir")
    ap.add_argument("--voice", default=None)
    ap.add_argument("--out", default=None, help="diretorio do projeto (opcional)")
    args = ap.parse_args()
    with open(args.script, encoding="utf-8-sig") as f:
        text = f.read()
    title = args.title
    pdir = args.out or new_project_dir(title or "cli")
    st = Status(pdir)
    print(f"Projeto: {pdir}")
    try:
        run_project(text, pdir, title, args.theme, args.voice, status=st)
    except Exception as e:
        st.fail(e)
        print(f"ERRO: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
