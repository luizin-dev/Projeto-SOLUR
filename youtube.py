# -*- coding: utf-8 -*-
"""Kit YouTube gerado localmente: thumbnails 1280x720, capitulos e pacote de
upload (titulo/descricao/tags). 100% gratuito — so PIL + timeline.json."""
import json
import os

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageStat

from presets import FONTS, THEMES

TW, TH = 1280, 720


def _font(size, bold=True):
    f = ImageFont.truetype(os.path.join(FONTS, "Cinzel.ttf"), size)
    try:
        f.set_variation_by_name("Bold" if bold else "Regular")
    except Exception:
        pass
    return f


def _fmt(ts):
    ts = max(0, int(round(ts)))
    h, m, s = ts // 3600, (ts % 3600) // 60, ts % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fit(draw, text, max_w, start=130, floor=44):
    size = start
    while size > floor:
        f = _font(size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 6
    return _font(floor)


def _title_lines(draw, title, max_w=TW - 200):
    """Titulo em 1 linha, ou 2 linhas equilibradas se for longo."""
    t = title.upper()
    f = _fit(draw, t, max_w)
    if draw.textlength(t, font=f) <= max_w or len(t.split()) < 2:
        return [(t, f)]
    words = t.split()
    best, spread = [(t, _font(44))], 1e9
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        fa, fb = _fit(draw, a, max_w, 100), _fit(draw, b, max_w, 100)
        d = abs(draw.textlength(a, font=fa) - draw.textlength(b, font=fb))
        if d < spread:
            spread, best = d, [(a, fa), (b, fb)]
    return best


def _thumb(img_path, title, out_path, accent):
    """Thumbnail YouTube: melhor imagem + gradiente + titulo grande em Cinzel."""
    base = Image.open(img_path).convert("RGB")
    w, h = base.size
    tr = TW / TH
    if w / h > tr:
        nw = int(h * tr)
        x0 = (w - nw) // 2
        base = base.crop((x0, 0, x0 + nw, h))
    else:
        nh = int(w / tr)
        y0 = (h - nh) // 2
        base = base.crop((0, y0, w, y0 + nh))
    base = base.resize((TW, TH), Image.LANCZOS)
    base = ImageEnhance.Color(base).enhance(1.12)
    base = ImageEnhance.Contrast(base).enhance(1.05)
    # gradiente inferior escuro para o titulo saltar
    grad = Image.new("L", (1, TH))
    for y in range(TH):
        v = int(max(0.0, y / TH - 0.34) * 2.4 * 255)
        grad.putpixel((0, y), min(v, 215))
    grad = grad.resize((TW, TH))
    base = Image.composite(Image.new("RGB", (TW, TH), (5, 6, 9)), base, grad)
    d = ImageDraw.Draw(base)
    lines = _title_lines(d, title)
    heights = []
    for txt, f in lines:
        bb = d.textbbox((0, 0), txt, font=f)
        heights.append(bb[3] - bb[1])
    total_h = sum(heights) + 26 * (len(lines) - 1)
    y = TH - total_h - 96
    for (txt, f), hh in zip(lines, heights):
        bb = d.textbbox((0, 0), txt, font=f)
        x = (TW - (bb[2] - bb[0])) / 2 - bb[0]
        for dx in (-3, 0, 3):
            for dy in (-3, 0, 3):
                if dx or dy:
                    d.text((x + dx, y - bb[1] + dy), txt, font=f, fill=(0, 0, 0))
        d.text((x, y - bb[1]), txt, font=f, fill=(246, 244, 238))
        y += hh + 26
    d.rectangle([TW / 2 - 150, y + 14, TW / 2 + 150, y + 21], fill=accent)
    base.save(out_path, "PNG")


def _chapters(tl, doc):
    """Capitulos prontos p/ YouTube (1o em 0:00, intervalos >= 10s)."""
    names = {sc.get("idx"): (sc.get("title") or None) for sc in doc.get("scenes", [])}
    chs = []
    for sc in tl["scenes"]:
        chs.append([sc["start"], names.get(sc["idx"]) or f"Parte {sc['idx']}"])
    if tl.get("quote"):
        chs.append([tl["quote"]["start"], "Citacao final"])
    if tl.get("final"):
        chs.append([tl["final"]["start"], "Final"])
    if not chs:
        return []
    if chs[0][0] >= 10:
        chs.insert(0, [0.0, "Abertura"])
    else:
        chs[0][0] = 0.0
    out = [chs[0]]
    for c in chs[1:]:
        if c[0] - out[-1][0] >= 10:
            out.append(c)
    return [(_fmt(t), x) for t, x in out]


def make_kit(project_dir, doc, tl, accent, log=print):
    """Gera thumb_1..3.png, upload_kit.json e upload_kit.txt no projeto."""
    root = project_dir
    imgdir = os.path.join(root, "images")
    # candidatos: imagens reais ordenadas por contraste (as mais "punchy")
    cands = []
    if os.path.isdir(imgdir):
        for fn in os.listdir(imgdir):
            if not fn.endswith(".png"):
                continue
            p = os.path.join(imgdir, fn)
            if os.path.exists(p + ".placeholder") or os.path.getsize(p) < 30000:
                continue
            try:
                st = ImageStat.Stat(Image.open(p).convert("L")).stddev[0]
                cands.append((st, p))
            except Exception:
                continue
    cands.sort(reverse=True)
    picks = [p for _, p in cands[:3]]
    if not picks:
        p = os.path.join(root, "cards", "title.png")
        if os.path.exists(p):
            picks = [p]

    title = doc.get("title") or "Meu Video"
    thumbs = []
    for k, src in enumerate(picks, 1):
        out = os.path.join(root, f"thumb_{k}.png")
        try:
            _thumb(src, title, out, accent)
            thumbs.append(out)
            log(f"      thumbnail {k} ok (base: {os.path.basename(src)})")
        except Exception as e:
            log(f"      AVISO: thumbnail {k} falhou ({e})")

    chapters = _chapters(tl, doc)
    theme = (tl.get("meta", {}) or {}).get("theme", "noir")
    label = THEMES.get(theme, {}).get("label", "")
    hook = ""
    for sc in doc.get("scenes", []):
        if sc.get("narration"):
            hook = sc["narration"][0][:160]
            break
    desc = []
    if hook:
        desc.append(hook)
        desc.append("")
    if chapters:
        desc.append("CAPITULOS:")
        desc.extend(f"{ts} {t}" for ts, t in chapters)
        desc.append("")
    desc.append("Video gerado com Video Factory (narracao, imagens, trilha e "
                "montagem automaticas).")
    tags = []
    if label:
        tags.append(label.lower())
    tags += [w.lower() for w in title.split() if len(w) > 3][:6]
    tags += ["storytelling", "video narrado", "curta"]
    kit = {"title": title, "description": "\n".join(desc),
           "chapters": chapters, "tags": tags, "thumbnails": thumbs,
           "duration": tl.get("total"), "theme": theme}
    with open(os.path.join(root, "upload_kit.json"), "w", encoding="utf-8") as f:
        json.dump(kit, f, ensure_ascii=False, indent=1)
    with open(os.path.join(root, "upload_kit.txt"), "w", encoding="utf-8") as f:
        f.write(f"TITULO\n{title}\n\n")
        f.write(f"DESCRICAO\n{kit['description']}\n\n")
        f.write(f"TAGS (separadas por virgula)\n{', '.join(tags)}\n")
    log("      kit de upload: upload_kit.json / upload_kit.txt")
    return kit
