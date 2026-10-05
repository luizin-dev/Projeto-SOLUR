# -*- coding: utf-8 -*-
"""Cartoes de titulo e citacao (1920x1080) com PIL.
Portado do filme Loan Shark; cor de destaque e idioma do credito parametrizados."""
import os

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from presets import FONTS, CARD_CREDIT, voice_lang

W, H = 1920, 1080

_cinzel = lambda size: ImageFont.truetype(os.path.join(FONTS, "Cinzel.ttf"), size)
try:
    F_TITLE = _cinzel(200); F_TITLE.set_variation_by_name("Bold")
except Exception:
    F_TITLE = _cinzel(200)
F_SMALL = _cinzel(52)
F_CREDIT = _cinzel(34)
try:
    F_QUOTE = ImageFont.truetype(os.path.join(FONTS, "Cormorant-Italic.ttf"), 92)
    F_QUOTE.set_variation_by_name("Medium")
except Exception:
    F_QUOTE = ImageFont.truetype(os.path.join(FONTS, "Cormorant-Italic.ttf"), 92)


def _vignette():
    """Cartao preto com leve elevacao central."""
    img = Image.new("RGB", (W, H), (4, 4, 6))
    glow = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(glow)
    d.ellipse([W / 2 - 900, H / 2 - 500, W / 2 + 900, H / 2 + 500], fill=26)
    glow = glow.filter(ImageFilter.GaussianBlur(260))
    lift = Image.new("RGB", (W, H), (16, 18, 22))
    return Image.composite(lift, img, glow)


def _draw_spaced(draw, xy, text, font, fill, spacing=18):
    total = sum(draw.textlength(c, font=font) + spacing for c in text) - spacing
    x = xy[0] - total / 2
    y = xy[1]
    for c in text:
        draw.text((x, y), c, font=font, fill=fill)
        x += draw.textlength(c, font=font) + spacing
    return total


def _shrink_title(draw, text, max_w=1700):
    """Reduz a fonte ate o titulo caber na largura."""
    size = 200
    while size > 60:
        f = _cinzel(size)
        try:
            f.set_variation_by_name("Bold")
        except Exception:
            pass
        total = sum(draw.textlength(c, font=f) + 10 for c in text) - 10
        if total <= max_w:
            return f
        size -= 10
    return _cinzel(60)


def title_card(text, out_path, accent=(120, 22, 26), voice="pt"):
    img = _vignette()
    d = ImageDraw.Draw(img)
    # linha superior discreta
    over = "UM  FILME" if voice_lang(voice) == "pt" else "A  FILM"
    _draw_spaced(d, (W / 2, 300), over, F_SMALL, (168, 168, 172), spacing=26)
    f_t = _shrink_title(d, text.upper())
    _draw_spaced(d, (W / 2, 420), text.upper(), f_t, (222, 220, 214), spacing=10)
    d.rectangle([W / 2 - 330, 705, W / 2 + 330, 708], fill=accent)
    credit = CARD_CREDIT.get(voice_lang(voice), CARD_CREDIT["en"])
    _draw_spaced(d, (W / 2, 745), credit, F_CREDIT, (120, 120, 126), spacing=10)
    img.save(out_path)


def quote_card(text, out_path, accent=(120, 22, 26)):
    img = _vignette()
    d = ImageDraw.Draw(img)

    def layout(font, max_w, line_h):
        words = text.split()
        lines, cur = [], ""
        for w in words:
            cand = (cur + " " + w).strip()
            bb = d.textbbox((0, 0), cand, font=font)
            if cur and (bb[2] - bb[0]) > max_w:
                lines.append(cur); cur = w
            else:
                cur = cand
        if cur:
            lines.append(cur)
        return lines, line_h

    lines, line_h = layout(F_QUOTE, 1440, 130)
    font = F_QUOTE
    if len(lines) > 4:  # texto longo: fonte menor, mais compacto
        try:
            font = ImageFont.truetype(os.path.join(FONTS, "Cormorant-Italic.ttf"), 68)
            font.set_variation_by_name("Medium")
        except Exception:
            font = F_QUOTE
        lines, line_h = layout(font, 1500, 96)
    y = H / 2 - (len(lines) * line_h / 2)
    for ln in lines:
        bb = d.textbbox((0, 0), ln, font=font)
        d.text((W / 2 - (bb[2] - bb[0]) / 2 - bb[0], y - bb[1]), ln, font=font,
               fill=(210, 208, 202))
        y += line_h
    y += 20
    d.rectangle([W / 2 - 60, y, W / 2 + 60, y + 2], fill=accent)
    img.save(out_path)
