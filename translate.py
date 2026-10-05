# -*- coding: utf-8 -*-
"""Traducao pt->en de prompts visuais via MyMemory (gratuito, sem chave).

Os modelos de imagem do Pollinations entendem ingles muito melhor que
portugues; roteiros em PT ganham fidelidade de contexto com a traducao.
Regras: detecta portugues por palavras-marco, traduz online 1x (cache em
disco por projeto) e NUNCA falha — pior caso devolve o texto original."""
import json
import os
import re
import urllib.parse
import urllib.request

# palavras comuns suficiente para suspeitar de portugues (evita gastar
# quota traduzindo prompts que ja estao em ingles)
_PT_MARKERS = re.compile(
    r"\b(uma|um|uns|umas|de|da|do|das|dos|na|no|nas|nos|com|entre|para|que|"
    r"sobre|ao|aos|atrav[eé]s|rua|cidade|noite|manh[ãa]|amanhecer|entardecer|"
    r"casa|homem|mulher|menino|menina|cachorro|gato|cavalo|carro|floresta|"
    r"escuro|colorid[oa]s?|grande|pequen[oa]s?|velho|velha|novo|nova)\b",
    re.IGNORECASE)

_API = "https://api.mymemory.translated.net/get"

# termos de roteiro que a MT traduz literal demais (luneta de detetive =
# monocle, nao spyglass); aplicado no texto JA traduzido, por palavra inteira
_GLOSSARY = {
    "spyglass": "monocle",
    "spyglasses": "monocle",
    "overcoat": "trench coat",
    "waistcoat": "vest",
    "cafeteria": "diner",
}


def _gloss(text):
    for k, v in _GLOSSARY.items():
        text = re.sub(rf"\b{re.escape(k)}\b", v, text, flags=re.IGNORECASE)
    return text


def looks_pt(text):
    return len(_PT_MARKERS.findall(text or "")) >= 2


def _online(text, log):
    q = urllib.parse.quote(text[:450], safe="")
    url = f"{_API}?q={q}&langpair=pt|en"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 VideoFactory"})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        if data.get("quotaFinished"):
            log("    traducao: quota diario da MyMemory esgotado, "
                "seguindo com texto original")
            return None
        out = (data.get("responseData") or {}).get("translatedText", "")
        if out and "MYMEMORY WARNING" not in out.upper() \
                and "INVALID" not in (out[:60]).upper() \
                and len(out) < len(text) * 4 + 120:
            return " ".join(_gloss(out).split())
    except Exception as e:  # noqa: BLE001
        log(f"    traducao falhou ({type(e).__name__}), usando texto original")
    return None


def to_en(text, cache_path=None, log=print):
    """Traduz se parecer portugues. Cache por projeto; nunca falha."""
    if not text or not looks_pt(text):
        return text
    cache = {}
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}
    key = " ".join(text.split()).lower()
    if key in cache:
        return cache[key]
    out = _online(text, log) or text
    if cache_path and out != text:
        cache[key] = out
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=1)
        except OSError:
            pass
    return out
