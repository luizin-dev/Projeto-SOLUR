# -*- coding: utf-8 -*-
"""Parser de roteiro (tolerante) + planejador de timeline + gerador de legendas ASS."""
import json
import os
import re
import subprocess

from presets import FFPROBE

# ---------------------------------------------------------------- parse
# Rotulos tolerantes: prefixo markdown (#, bullets) + separador (:-–—).
# Aceita tanto rotulo com conteudo na mesma linha ("VISUAL: rua molhada")
# quanto rotulo sozinho com conteudo nas linhas seguintes (formato YouTube:
# "VISUAL PROMPT:" / "NARRATION:" em linhas separadas) -> maquina de estados.
LABEL = r"^\s*(?:#{1,4}\s*)?(?:[-*+]\s+)?"
SEP = r"[:\-–—]"

SCENE_RE = re.compile(LABEL + r"(?:SCENES?|CENAS?|BLOCOS?|PARTES?|ATOS?|ACTOS?|"
                      r"SEQUENCIAS?|SEQUÊNCIAS?)\s*#?\s*(\d+)\s*([:.\-–—)\]]*)\s*(.*)$",
                      re.IGNORECASE)
HR_RE = re.compile(r"^\s*(?:-{3,}|={3,}|\*{3,}|_{3,})\s*$")
VISUAL_RE = re.compile(LABEL + r"(?:VISUALS?\s+PROMPTS?|VISUALS?|IMAGENS?|IMAGES?|"
                       r"SHOTS?|CENARIOS?|CENÁRIOS?|DESCRI[CÇ][ÃÕA]O(?:ES|\s+VISUAL)?|"
                       r"BACKGROUND|FUNDO)\s*" + SEP + r"\s*(.*)$", re.IGNORECASE)
NARR_RE = re.compile(LABEL + r"(?:NARRATIONS?|NARRADORA?|NARRATORS?|"
                     r"NARRA[CÇ][ÃÕA]O(?:ES)?|VOZ(?:\s+OFF)?|VOICEOVERS?|VOICE\s+OVER|"
                     r"VO|LOCU[CÇ][ÃÕA]O(?:ES)?|LOCUTORA?|LEITURA|TEXTO)\s*" + SEP +
                     r"\s*(.*)$", re.IGNORECASE)
META_RE = re.compile(LABEL + r"(?:DURA[CÇ][ÃÕA]O(?:ES)?|DURATIONS?|TIMECODES?|TIMING|"
                     r"TIMESTAMP|TEMPOS?|M[UÚ]SICA|MUSICAS?|MUSIC|SFX|SOUND\s+DESIGN|"
                     r"SOUNDS?|SOM|SONS|TRILHA|[AÁ]UDIO|AUDIOS?|NOTAS?|NOTES?|"
                     r"OBS(?:ERVA[CÇ][ÃÕA]O)?|LEGENDAS?|SUBTITLES?|CAPTIONS?|THUMBNAIL|"
                     r"CAPA|B-?ROLL|TRANSI[CÇ][ÃÕA]O(?:ES)?|EDIT(?:AR|AGEM|S?)?)\s*" + SEP +
                     r"\s*(.*)$", re.IGNORECASE)
TIME_RANGE_RE = re.compile(r"^\s*\d{1,2}[:.]\d{2}(?:\s*[–—-]\s*\d{1,2}[:.]\d{2})?\s*$")
MOOD_RE = re.compile(LABEL + r"(?:MOOD|ATMOSFERA|TOM|TENSÃO|TENSAO)\s*" + SEP +
                     r"\s*(.+)$", re.IGNORECASE)
TITLE_RE = re.compile(LABEL + r"(?:TITLE|TÍTULO|TITULO)\s*" + SEP + r"\s*(.+)$",
                      re.IGNORECASE)
CHARS_RE = re.compile(LABEL + r"(?:CHARACTERS?|PERSONAGENS?)\s*[:\-]?\s*$", re.IGNORECASE)
FINAL_TEXT_RE = re.compile(LABEL + r"(?:FINAL TEXT|TEXTO FINAL|FRASE FINAL|QUOTE|"
                           r"CITAÇÃO|CITACAO)\s*" + SEP + r"\s*(.+)$", re.IGNORECASE)
FINAL_Q_RE = re.compile(LABEL + r"(?:FINAL QUESTION|PERGUNTA FINAL|QUESTÃO FINAL|"
                        r"QUESTAO FINAL)\s*" + SEP + r"\s*(.+)$", re.IGNORECASE)
PAREN_RE = re.compile(r"^\s*[\[\(]\s*(.{25,})\s*[\]\)]\s*$")

MD_RE = re.compile(r"\*\*(.+?)\*\*|\*(.+?)\*|__(.+?)__|_(.+?)_")


def _clean(s):
    s = MD_RE.sub(lambda m: next(g for g in m.groups() if g), s)
    return s.strip().strip('"').strip()


def _md_strip(s):
    """Remove negrito/italico da linha inteira antes de casar rotulos."""
    return MD_RE.sub(lambda m: next(g for g in m.groups() if g), s)


def _scene_header_ok(m, raw):
    """"CENA 3" puro ou com separador/titulo curto; frases de narracao nao contam."""
    title = (m.group(3) or "").strip()
    if len(title) > 70:
        return False
    if not title:
        return True
    if raw.lstrip().startswith("#"):
        return True
    if m.group(2):          # separador logo apos o numero ("SCENE 1 — ...")
        return True
    letters = [c for c in title if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.7:
        return True         # "SCENE 1 BORN INTO NOTHING" (titulo em caps)
    return False


def parse_script(text):
    """Roteiro livre -> estrutura. Retorna dict com title, characters, scenes
    (cada cena: idx, title, visuals, narration, mood), final_text, final_question,
    auto(bool: sem marcadores de cena)."""
    lines = text.replace("\r\n", "\n").split("\n")
    doc = {"title": None, "characters": [], "scenes": [],
           "final_text": None, "final_question": None}

    # blocos: separados por marcador de cena ou linha horizontal
    blocks, cur = [], None
    numbered = False
    for ln in lines:
        m = SCENE_RE.match(_md_strip(ln))
        if m and _scene_header_ok(m, ln):
            numbered = True
            if cur:
                blocks.append(cur)
            cur = {"num": int(m.group(1)),
                   "title": _clean(m.group(3)) or None, "lines": []}
            continue
        if HR_RE.match(ln):
            if cur and cur["lines"]:
                blocks.append(cur)
            cur = {"num": None, "lines": []}
            continue
        if cur is None:
            cur = {"num": None, "lines": []}
        cur["lines"].append(ln)
    if cur:
        blocks.append(cur)

    # se nenhuma divisao funcionou, roteiro inteiro = 1 cena
    if len(blocks) == 1 and blocks[0]["num"] is None:
        blocks = [{"num": 1, "title": None, "lines": blocks[0]["lines"]}]

    # filtros globais (title/final) e montagem das cenas
    for bi, b in enumerate(blocks):
        scene = {"idx": b["num"] or (bi + 1), "title": b.get("title"),
                 "visuals": [], "narration": [], "mood": None}
        in_chars = False
        mode = "narration"   # rotulo pendente: linhas soltas seguem o modo atual

        for raw in b["lines"]:
            ln = _md_strip(raw)
            if not ln.strip():
                in_chars = False
                continue
            m = TITLE_RE.match(ln)
            if m and doc["title"] is None and bi == 0:
                doc["title"] = _clean(m.group(1))
                continue
            if CHARS_RE.match(ln):
                in_chars = True
                continue
            if in_chars:
                cm = re.match(r"^\s*[-*]?\s*([A-Za-z\u00c0-\u00ff][\w\u00c0-\u00ff' ]{1,30}?)\s*[:\-]\s*(.+)$", ln)
                if cm:
                    doc["characters"].append((cm.group(1).strip(), _clean(cm.group(2))))
                    continue
                in_chars = False
            m = FINAL_TEXT_RE.match(ln)
            if m:
                doc["final_text"] = _clean(m.group(1)); continue
            m = FINAL_Q_RE.match(ln)
            if m:
                doc["final_question"] = _clean(m.group(1)); continue
            m = MOOD_RE.match(ln)
            if m:
                scene["mood"] = _clean(m.group(1)).lower(); continue
            # metadados de producao (Duration/Music/SFX...) nunca viram narracao
            if META_RE.match(ln) or TIME_RANGE_RE.match(ln.strip()):
                continue
            m = VISUAL_RE.match(ln)
            if m:
                mode = "visual"
                rest = _clean(m.group(1))
                if rest:
                    scene["visuals"].append(rest)
                continue
            m = NARR_RE.match(ln)
            if m:
                mode = "narration"
                rest = _clean(m.group(1))
                if rest:
                    scene["narration"].append(rest)
                continue
            pm = PAREN_RE.match(ln)
            if pm:
                scene["visuals"].append(_clean(pm.group(1)))
                mode = "narration"   # direcao de cena pontual; volta ao padrao
                continue
            txt = _clean(ln)
            if not txt:
                continue
            if mode == "visual" and scene["visuals"]:
                # continuacao multilinha de uma mesma descricao visual
                scene["visuals"][-1] = (scene["visuals"][-1].rstrip(" ,;") + " " + txt).strip()
            elif mode == "visual":
                scene["visuals"].append(txt)
            else:
                scene["narration"].append(txt)

        if scene["narration"] or scene["visuals"]:
            doc["scenes"].append(scene)

    # renumera sequencialmente (evita idx duplicado em roteiros mistos)
    for i, sc in enumerate(doc["scenes"], 1):
        sc["idx"] = i

    # title fallback: primeira linha curta fora de cenas
    if doc["title"] is None:
        first = next((l.strip() for l in lines if l.strip()), "")
        if 0 < len(first) <= 60 and not SCENE_RE.match(first) and len(doc["scenes"]) > 1 \
                and not NARR_RE.match(first):
            doc["title"] = _clean(first)
    if doc["title"] is None:
        doc["title"] = "Meu Video"
    doc["auto"] = not numbered
    return doc


# ---------------------------------------------------------------- helpers
def dur_of(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", path],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def n_images_for(scene, dur, per=8.0):
    """~1 imagem a cada `per` segundos de video (ritmo dinamico, mais cortes)."""
    want = max(round(dur / per), len(scene["visuals"]))
    return int(min(max(want, 2), 14))


def build_timeline(doc, audio_dir, img_every=8.0):
    """Duracoes de TTS medidas -> timeline global (mesmo schema do filme)."""
    scenes = []
    t = 6.0
    title = {"start": 0.0, "dur": t}
    n = len(doc["scenes"])
    for k, sc in enumerate(doc["scenes"]):
        narr_path = os.path.join(audio_dir, f"narr_s{sc['idx']:02d}.mp3")
        nd = dur_of(narr_path) if os.path.exists(narr_path) else 0.0
        if nd <= 0.01:
            nd = 5.0 * n_images_for(sc, 55.0, img_every)  # cena muda: ~5s por imagem
        lead = 1.2 if k == 0 else 0.9
        tail = 2.0 if k == n - 1 else 1.6
        d = lead + nd + tail
        ni = n_images_for(sc, d, img_every)
        scenes.append({"idx": sc["idx"], "start": round(t, 3), "dur": round(d, 3),
                       "narr": round(nd, 3), "lead": lead, "tail": tail,
                       "n_images": ni, "imgs": [round(d / ni, 3)] * ni})
        t += d
    timeline = {"title": title, "scenes": scenes, "total": 0.0}
    if doc["final_text"]:
        timeline["quote"] = {"start": round(t, 3), "dur": 9.0}
        t += 9.0
    fq = doc["final_question"]
    if fq:
        fpath = os.path.join(audio_dir, "narr_final.mp3")
        fn = dur_of(fpath) if os.path.exists(fpath) else 0.0
        timeline["final"] = {"start": round(t, 3), "dur": round(1.0 + fn + 2.5, 3),
                             "narr": round(fn, 3)}
        t += timeline["final"]["dur"]
    timeline["total"] = round(t, 3)
    return timeline


# ---------------------------------------------------------------- legendas
def _parse_srt(path):
    with open(path, encoding="utf-8-sig") as f:
        txt = f.read().replace("\r\n", "\n")
    cues = []
    for block in re.split(r"\n\s*\n", txt.strip()):
        ls = [l for l in block.split("\n") if l.strip()]
        if len(ls) < 2:
            continue
        m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", ls[1])
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        cues.append([g[0]*3600 + g[1]*60 + g[2] + g[3]/1000.0,
                     g[4]*3600 + g[5]*60 + g[6] + g[7]/1000.0,
                     " ".join(ls[2:]).strip()])
    return cues


def _split_long(cue, maxlen=92):
    s, e, text = cue
    if len(text) <= maxlen:
        return [cue]
    cuts = [m.end() for m in re.finditer(r",", text)]
    for pat in (r"\bbut\s", r"\band\s", r"\bbecause\s", r"\bthat\s",
                r"\bmas\s", r"\be\s", r"\bporque\s", r"\bque\s"):
        cuts += [m.start() for m in re.finditer(pat, text)]
    cuts += [m.start() for m in re.finditer(r" ", text)]
    cuts = sorted(set(c for c in cuts if 30 < c < len(text) - 25),
                  key=lambda c: abs(c - len(text) / 2))
    if not cuts:
        return [cue]
    cut = cuts[0]
    a, b = text[:cut].strip(" ,"), text[cut:].strip(" ,")
    if not a or not b:
        return [cue]
    frac = len(a) / (len(a) + len(b))
    mid = s + (e - s) * frac
    return _split_long([s, mid, a], maxlen) + _split_long([mid, e, b], maxlen)


def _wrap(text, width=46):
    words, out, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            out.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        out.append(cur)
    return out


def _ass_time(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Narr,Georgia,50,&H00F5F5F5,&H000000FF,&H00141414,&HA0000000,0,0,0,0,100,100,0.4,0,1,2.1,1.8,2,90,90,56,1
Style: Final,Georgia,52,&H00F5F5F5,&H000000FF,&H00141414,&HA0000000,0,1,0,0,100,100,0.8,0,1,2.1,1.8,2,90,90,90,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def build_ass(timeline, audio_dir, out_path):
    events = []
    for sc in timeline["scenes"]:
        srt = os.path.join(audio_dir, f"narr_s{sc['idx']:02d}.json")
        if not os.path.exists(srt):
            continue
        cues = []
        for c in _parse_srt(srt):
            cues.extend(_split_long(c))
        off = sc["start"] + sc["lead"]
        for j, (s, e, text) in enumerate(cues):
            s2, e2 = off + s, off + e
            if j + 1 < len(cues):
                e2 = min(e2 + 0.30, off + cues[j + 1][0] - 0.06)
            else:
                e2 = min(e2 + 0.40, sc["start"] + sc["dur"] - 0.25)
            events.append((s2, e2, "Narr", "{\\fad(220,220)}" + "\\N".join(_wrap(text))))
    fin = timeline.get("final")
    if fin:
        srt = os.path.join(audio_dir, "narr_final.json")
        if os.path.exists(srt):
            off = fin["start"] + 1.0
            for s, e, text in _parse_srt(srt):
                events.append((off + s, off + e + 0.4, "Final",
                               "{\\fad(300,300)}" + " ".join(_wrap(text))))
    events.sort(key=lambda x: x[0])
    with open(out_path, "w", encoding="utf-8-sig") as f:
        f.write(ASS_HEADER)
        for s, e, style, body in events:
            f.write(f"Dialogue: 0,{_ass_time(s)},{_ass_time(e)},{style},,0,0,0,,{body}\n")
    return len(events)
