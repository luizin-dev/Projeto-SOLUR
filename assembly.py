# -*- coding: utf-8 -*-
"""Montagem do video final: Ken Burns, fades, mixagem, concat e queima de legendas.
Portado do build_video.py do filme Loan Shark, parametrizado por projeto."""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from presets import FFMPEG

FPS = 30
W, H = 1920, 1080
SUPER = 3840  # supersampling p/ zoompan suave

VENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", str(FPS)]
AENC = ["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2"]

MOTIONS = ["in", "out", "right", "left", "up", "down", "in_right", "out_left"]
CF_SHOT = 0.7    # crossfade curto entre shots da mesma cena
CF_MORPH = 2.2   # dissolve longo entre variacoes da mesma cena (morph "pintura viva")


def slugify(text):
    s = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip()
    return re.sub(r"[\s_]+", "_", s)[:60] or "video"


def assemble(project_dir, log=print):
    root = Path(project_dir)
    segdir = root / "segments"
    segdir.mkdir(exist_ok=True)
    tl = json.loads((root / "timeline.json").read_text(encoding="utf-8"))

    # invalida segments/MP4s antigos se a timeline mudou (evita montagem stale)
    sig = hashlib.md5(json.dumps(tl, sort_keys=True).encode("utf-8")).hexdigest()
    stamp = segdir / "build.json"
    try:
        old = json.loads(stamp.read_text(encoding="utf-8")) if stamp.exists() else {}
    except Exception:
        old = {}
    if old.get("sig") != sig:
        for f in list(segdir.glob("*.mp4")):
            f.unlink()
        for f in list(root.glob("*.mp4")):
            f.unlink()
        stamp.write_text(json.dumps({"sig": sig}), encoding="utf-8")

    def run(args, tag, skip_if=None, deps=()):
        if skip_if is not None and skip_if.exists() and skip_if.stat().st_size > 0:
            # cache consciente de mtime: se alguma fonte (imagem recuperada,
            # legenda, clipe) for mais nova que o resultado, refaz a etapa.
            if any(p.exists() and p.stat().st_mtime > skip_if.stat().st_mtime
                   for p in deps):
                log(f"  [refaz] {tag} (fonte mais nova)")
            else:
                log(f"  [skip] {tag}")
                return
        t0 = time.time()
        p = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y"] + args,
                           capture_output=True, text=True, cwd=str(root))
        dt = time.time() - t0
        if p.returncode != 0:
            log(f"  [FALHA] {tag} ({dt:.1f}s): {p.stderr[-600:]}")
            raise RuntimeError(f"ffmpeg falhou em {tag}: {p.stderr[-400:]}")
        log(f"  [ok] {tag} ({dt:.1f}s)")

    def kb_chain(frames, motion):
        f = max(frames - 1, 1)
        cx = "x='iw/2-(iw/zoom/2)'"
        cy = "y='ih/2-(ih/zoom/2)'"
        if motion == "in":
            z = f"z='1.0+0.10*on/{f}'"
        elif motion == "out":
            z = f"z='1.10-0.10*on/{f}'"
        elif motion == "right":
            z = "z='1.06'"
            cx = f"x='(iw-iw/zoom)*on/{f}'"
        elif motion == "left":
            z = "z='1.06'"
            cx = f"x='(iw-iw/zoom)*(1-on/{f})'"
        elif motion == "up":
            z = "z='1.06'"
            cy = f"y='(ih-ih/zoom)*on/{f}'"
        elif motion == "down":
            z = "z='1.06'"
            cy = f"y='(ih-ih/zoom)*(1-on/{f})'"
        elif motion == "in_right":
            z = f"z='1.0+0.08*on/{f}'"
            cx = f"x='(iw-iw/zoom)*on/{f}'"
        else:  # out_left
            z = f"z='1.08-0.08*on/{f}'"
            cx = f"x='(iw-iw/zoom)*(1-on/{f})'"
        return (f"scale={SUPER}:2160:force_original_aspect_ratio=increase,"
                f"crop={SUPER}:2160,"
                f"zoompan={z}:{cx}:{cy}:d={frames}:s={W}x{H}:fps={FPS},"
                f"format=yuv420p,settb=AVTB")

    def encode_scene(sc):
        idx = sc["idx"]
        dur = sc["dur"]
        total_frames = round(dur * FPS)
        n = sc["n_images"]
        imgs = [root / "images" / f"s{idx}_{i:02d}.png" for i in range(1, n + 1)]
        missing = [p for p in imgs if not p.exists()]
        if missing:
            raise RuntimeError(f"cena {idx}: faltam {len(missing)} imagens "
                               f"(ex.: {os.path.basename(str(missing[0]))})")

        alloc = [round(d * FPS) for d in sc["imgs"]]
        alloc[-1] = max(total_frames - sum(alloc[:-1]), 1)

        # cada imagem vira um clipe Ken Burns; shots com variante 'b' viram
        # 2 cliques ligados por dissolve longo (a imagem "respira"/morph).
        # O dissolve e adaptativo ao tamanho do slot para nao sobrepor o
        # crossfade seguinte (regra: morph termina antes do fim do slot).
        clips = []   # (img, base_frames, crossfade_ate_o_proximo_s)
        for i in range(1, n + 1):
            img = imgs[i - 1]
            var = root / "images" / f"s{idx}_{i:02d}b.png"
            bf = alloc[i - 1]
            var_ok = var.exists() and not os.path.exists(str(var) + ".placeholder")
            slot = bf / FPS
            if var_ok and slot >= 4.0:
                cf_m = min(CF_MORPH, slot * 0.30)
                fa = int(bf * 0.58)
                clips.append((img, fa, cf_m))
                clips.append((var, bf - fa, CF_SHOT))
            else:
                clips.append((img, bf, CF_SHOT))

        m = len(clips)
        cf_f = [int(round(c[2] * FPS)) for c in clips[:-1]]
        adj = [clips[j][1] + (cf_f[j] if j < m - 1 else 0) for j in range(m)]
        adj[-1] = max(total_frames + sum(cf_f) - sum(adj[:-1]), 1)

        cmd, fg = [], []
        for j in range(m):
            cmd += ["-i", str(clips[j][0])]
            fg.append(f"[{j}:v]{kb_chain(adj[j], MOTIONS[j % len(MOTIONS)])}[c{j}]")

        # encadeia com crossfades (em vez de cortes secos)
        cur, tacc = "[c0]", adj[0] / FPS
        for j in range(1, m):
            cf = clips[j - 1][2]
            fg.append(f"{cur}[c{j}]xfade=transition=fade:duration={cf:.3f}:"
                      f"offset={max(tacc - cf, 0.05):.3f}[x{j}]")
            tacc = tacc + adj[j] / FPS - cf
            cur = f"[x{j}]"

        fin = fout = 0.8
        fg.append(f"{cur}fade=t=in:st=0:d={fin},"
                  f"fade=t=out:st={tacc - fout:.3f}:d={fout},format=yuv420p[vout]")

        bed = root / "audio" / f"bed_s{idx:02d}.wav"
        narr = root / "audio" / f"narr_s{idx:02d}.mp3"
        cmd += ["-i", str(bed)]
        if narr.exists():
            cmd += ["-i", str(narr)]
            delay_ms = int(sc["lead"] * 1000)
            fg.append(f"[{m + 1}:a]aresample=44100,aformat=channel_layouts=stereo,"
                      f"adelay={delay_ms}:all=1[narr]")
            fg.append(f"[{m}:a][narr]amix=inputs=2:duration=first:normalize=0[aout]")
        else:
            fg.append(f"[{m}:a]aresample=44100,aformat=channel_layouts=stereo[aout]")

        out = segdir / f"seg_s{idx:02d}.mp4"
        cmd += ["-filter_complex", ";".join(fg),
                "-map", "[vout]", "-map", "[aout]",
                "-t", f"{total_frames / FPS:.3f}"] + VENC + AENC + \
               ["-movflags", "+faststart", str(out)]
        deps = imgs + [root / "images" / f"s{idx}_{i:02d}b.png"
                       for i in range(1, n + 1)] + [bed, narr]
        run(cmd, f"cena {idx:02d} ({dur:.1f}s, {m} cliques)", skip_if=out, deps=deps)

    def encode_card(name, img, bed, dur, zoom_to=1.05):
        frames = round(dur * FPS)
        f = max(frames - 1, 1)
        vsrc = (f"scale={SUPER}:2160:force_original_aspect_ratio=increase,"
                f"crop={SUPER}:2160,"
                f"zoompan=z='1.0+{zoom_to - 1:.4f}*on/{f}':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={frames}:s={W}x{H}:fps={FPS},"
                f"fade=t=in:st=0:d=0.5,fade=t=out:st={frames / FPS - 0.5:.3f}:d=0.5[vout]")
        out = segdir / f"seg_{name}.mp4"
        cmd = ["-i", str(img), "-i", str(bed),
               "-filter_complex", vsrc, "-map", "[vout]", "-map", "1:a",
               "-t", f"{frames / FPS:.3f}"] + VENC + AENC + \
              ["-movflags", "+faststart", str(out)]
        run(cmd, f"cartao {name} ({dur:.1f}s)", skip_if=out, deps=[img, bed])

    def encode_final(dur):
        frames = round(dur * FPS)
        narr = root / "audio" / "narr_final.mp3"
        bed = root / "audio" / "bed_final.wav"
        cmd = ["-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}:d={dur:.3f}",
               "-i", str(bed)]
        if narr.exists():
            cmd += ["-i", str(narr)]
            fg = (f"[2:a]aresample=44100,aformat=channel_layouts=stereo,"
                  f"adelay=1000:all=1[narr];"
                  f"[1:a][narr]amix=inputs=2:duration=first:normalize=0,"
                  f"afade=t=out:st={dur - 2.5:.3f}:d=2.5[aout]")
        else:
            fg = f"[1:a]aresample=44100,aformat=channel_layouts=stereo," \
                 f"afade=t=out:st={dur - 2.5:.3f}:d=2.5[aout]"
        out = segdir / "seg_final.mp4"
        cmd += ["-filter_complex", fg, "-map", "0:v", "-map", "[aout]",
                "-t", f"{frames / FPS:.3f}"] + VENC + AENC + \
               ["-movflags", "+faststart", str(out)]
        run(cmd, f"final preto ({dur:.1f}s)", skip_if=out, deps=[narr, bed])

    # ---------------- etapas ----------------
    encode_card("title", root / "cards" / "title.png",
                root / "audio" / "bed_title.wav", tl["title"]["dur"], 1.06)
    for sc in tl["scenes"]:
        encode_scene(sc)
    if tl.get("quote"):
        encode_card("quote", root / "cards" / "quote.png",
                    root / "audio" / "bed_quote.wav", tl["quote"]["dur"], 1.04)
    if tl.get("final"):
        encode_final(tl["final"]["dur"])

    # concat
    order = ["seg_title.mp4"] + [f"seg_s{sc['idx']:02d}.mp4" for sc in tl["scenes"]]
    if tl.get("quote"):
        order.append("seg_quote.mp4")
    if tl.get("final"):
        order.append("seg_final.mp4")
    lst = segdir / "list.txt"
    lst.write_text("".join(f"file '{segdir / n}'\n" for n in order), encoding="utf-8")
    run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
         str(root / "full_nosubs.mp4")], "concat",
        skip_if=root / "full_nosubs.mp4",
        deps=[segdir / n for n in order])

    # queima de legendas (caminho relativo ao cwd para evitar conflito do ':' no Windows)
    ass = root / "subs" / "subs.ass"
    title_slug = slugify(tl.get("meta", {}).get("title", "video"))
    out_mp4 = root / f"{title_slug}.mp4"
    burn = ["-i", "full_nosubs.mp4"]
    if ass.exists():
        burn += ["-vf", "ass=filename=subs/subs.ass"]
    burn += VENC + AENC + ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100",
                           "-movflags", "+faststart",
                           "-metadata", f"title={tl.get('meta', {}).get('title', 'Video Factory')}",
                           str(out_mp4)]
    run(burn, "queima de legendas", skip_if=out_mp4,
        deps=[root / "full_nosubs.mp4", ass])
    return str(out_mp4)


if __name__ == "__main__":
    p = assemble(sys.argv[1] if len(sys.argv) > 1 else ".")
    print("DONE ->", p)
