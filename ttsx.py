# -*- coding: utf-8 -*-
"""Narracao com edge-tts (voz neural gratuita da Microsoft, sem chave de API).
Gera MP3 + legendas sincronizadas (SRT salvo com extensao .json, lido pelo parser)."""
import os
import subprocess

from presets import PYTHON, VOICE_FALLBACK

CHARS_TO_STRIP = "*_`#<>\"|"


def _sanitize(text):
    """Remove marcas que o TTS leria em voz alta; preserva paragrafos (pausas naturais)."""
    out = []
    for para in text.split("\n"):
        for c in CHARS_TO_STRIP:
            para = para.replace(c, " ")
        para = " ".join(para.split())
        if para:
            out.append(para)
    return "\n\n".join(out)


def _tts_once(voice, rate, tmp_txt, out_mp3, out_sub):
    r = subprocess.run(
        [PYTHON, "-m", "edge_tts",
         f"--voice={voice}",
         f"--rate={rate}",
         f"--file={tmp_txt}",
         f"--write-media={out_mp3}",
         f"--write-subtitles={out_sub}"],
        capture_output=True, text=True, timeout=300)
    ok = os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 8000
    return ok, (r.stderr or r.stdout or "").strip()


def synth(text, out_mp3, voice, rate="-8%", log=print):
    """Gera narracao + cues de legenda. Retorna True em caso de sucesso.

    Se a voz pedida falhar (ex.: removida do catalogo da Microsoft), tenta
    automaticamente vozes alternativas do mesmo idioma."""
    text = _sanitize(text)
    if not text:
        return False
    out_sub = os.path.splitext(out_mp3)[0] + ".json"
    if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 8000:
        return True  # cache de execucao anterior
    tmp_txt = os.path.splitext(out_mp3)[0] + ".txt"
    with open(tmp_txt, "w", encoding="utf-8") as f:
        f.write(text)
    if not rate.startswith(("+", "-")):
        rate = f"-{rate}"

    lang = voice.split("-")[0] if "-" in voice else "en"
    order = [voice] + [v for v in VOICE_FALLBACK.get(lang, []) if v != voice]
    for k, cand in enumerate(order):
        for attempt in range(2 if k == 0 else 1):
            try:
                ok, err = _tts_once(cand, rate, tmp_txt, out_mp3, out_sub)
                if ok:
                    if cand != voice:
                        log(f"    AVISO: voz {voice} indisponivel; "
                            f"narrando com {cand}")
                    log(f"    tts ok: {os.path.basename(out_mp3)} "
                        f"({cand}, {os.path.getsize(out_mp3) // 1024} kB)")
                    return True
                log(f"    tts falhou ({cand}, tentativa {attempt + 1}): {err[:120]}")
            except Exception as e:
                log(f"    tts erro ({cand}): {e}")
    return False
