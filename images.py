# -*- coding: utf-8 -*-
"""Geracao de imagens via Pollinations (gratuito, sem chave) + tratamento local."""
import hashlib
import os
import time
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from presets import IMG_SIZE, IMG_OUT, FONTS


def _seed(prompt, path):
    h = hashlib.sha1((prompt + path).encode("utf-8")).hexdigest()
    return int(h[:8], 16) % 999983


def _postprocess(im, out_path):
    """Remove so a faixa da marca d'agua (4.3% medidos + margem), recorta 16:9
    e realca a nitidez pos-upscale (LANCZOS + UnsharpMask)."""
    im = im.convert("RGB")
    w, h = im.size
    im = im.crop((0, 0, w, h - int(h * 0.05)))
    w, h = im.size
    th = int(w * 9 / 16)
    if h > th:
        y0 = (h - th) // 2
        im = im.crop((0, y0, w, y0 + th))
    elif h < th:
        tw = int(h * 16 / 9)
        x0 = (w - tw) // 2
        im = im.crop((x0, 0, x0 + tw, h))
    im = im.resize(IMG_OUT, Image.LANCZOS)
    im = im.filter(ImageFilter.UnsharpMask(radius=2.2, percent=130, threshold=2))
    im.save(out_path, "PNG")


def _placeholder(out_path, prompt):
    """Fallback offline: card escuro com o prompt (o filme continua montando)."""
    W, H = IMG_OUT
    img = Image.new("RGB", (W, H), (8, 9, 12))
    glow = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(glow)
    d.ellipse([W/2 - 800, H/2 - 420, W/2 + 800, H/2 + 420], fill=30)
    glow = glow.filter(ImageFilter.GaussianBlur(220))
    img = Image.composite(Image.new("RGB", (W, H), (22, 24, 30)), img, glow)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(os.path.join(FONTS, "Cormorant-Italic.ttf"), 44)
    except Exception:
        font = ImageFont.load_default()
    words = prompt.split()
    lines, cur = [], ""
    for wd in words:
        if len(cur) + len(wd) > 46:
            lines.append(cur); cur = wd
        else:
            cur = (cur + " " + wd).strip()
    if cur:
        lines.append(cur)
    y = H / 2 - len(lines) * 30
    for ln in lines[:14]:
        bb = d.textbbox((0, 0), ln, font=font)
        d.text((W/2 - (bb[2]-bb[0])/2, y), ln, font=font, fill=(140, 142, 150))
        y += 60
    img.save(out_path, "PNG")


# Nos nodes gratuitos do pollinations o sucesso e intermitente: parte dos
# requests cai em nodes pagos (HTTP 402, round-robin). A resposta certa e
# tentar de novo LOGO (outro node responde), nao esperar muito — por isso
# 16 tentativas com esperas curtas + rotacao de modelo entre tentativas.
# (O endpoint POST devolve imagem fixa de marketing — inutil; so o GET gera.)
RETRY_WAITS = (0, 1, 2, 3, 4, 6, 8, 11, 14, 18, 23, 30, 40, 55, 70, 90)
MODELS = ("", "turbo", "sana")   # "" = modelo padrao do node


def _mark_placeholder(out_path, prompt):
    try:
        with open(out_path + ".placeholder", "w", encoding="utf-8") as f:
            f.write(prompt)
    except OSError:
        pass


def fetch(prompt, out_path, log=print, seed_extra=0, prefer=None):
    """Baixa 1 imagem com retry agressivo; nunca falha (placeholder no pior caso).
    seed_extra > 0 gera uma variacao da mesma descricao (shots animados/morph).
    prefer: fixa o modelo em TODAS as tentativas ('' = modelo padrao do
    node; 'turbo'; etc). O 402 do Pollinations e saturacao global (todos
    os modelos falham juntos), entao rotacao nao aumenta a chance de
    sucesso — mas deixar 'sana'/'padrao' entrar no meio produz imagem
    off-style que e aceita como se fosse boa. Pin e' o correto.
    """
    if os.path.exists(out_path + ".placeholder"):
        try:
            os.remove(out_path + ".placeholder")
        except OSError:
            pass  # retentativa abaixo vai sobrescrever o placeholder
    elif os.path.exists(out_path) and os.path.getsize(out_path) > 30000:
        return "cache"
    q = urllib.parse.quote(prompt[:1400], safe="")
    seed = _seed(prompt + f"#{seed_extra}", out_path)
    for attempt, wait in enumerate(RETRY_WAITS, 1):
        if wait:
            time.sleep(wait)
        if prefer is not None:
            model = prefer
        else:
            model = MODELS[attempt % len(MODELS)]
        url = (f"https://image.pollinations.ai/prompt/{q}"
               f"?width={IMG_SIZE[0]}&height={IMG_SIZE[1]}&nologo=true&seed={seed}")
        if model:
            url += f"&model={model}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 VideoFactory"})
            tmp = out_path + ".tmp"
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                f.write(r.read())
            im = Image.open(tmp)
            im.load()
            if im.size[0] < 512:   # resposta truncada/lixo
                raise ValueError(f"imagem muito pequena: {im.size}")
            _postprocess(im, out_path)
            os.remove(tmp)
            return "ok" if attempt == 1 else f"ok(tentativa {attempt})"
        except Exception as e:  # noqa: BLE001
            log(f"    imagem falhou (tentativa {attempt}"
                f"{'/' + model if model else ''}): {type(e).__name__}: {e}")
    _placeholder(out_path, prompt)
    _mark_placeholder(out_path, prompt)
    return "placeholder"
