# -*- coding: utf-8 -*-
"""Configuracao global: caminhos, temas e vozes do Video Factory."""
import os

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECTS = os.path.join(BASE, "projects")
FONTS = os.path.join(BASE, "fonts")
WEB = os.path.join(BASE, "web")

# ferramentas reaproveitadas do projeto do filme
PYTHON = r"D:\video_loan_shark\python\python.exe"
_BIN = r"D:\video_loan_shark\bin\ffmpeg-9.0.2-essentials_build\bin"
FFMPEG = os.path.join(_BIN, "ffmpeg.exe")
FFPROBE = os.path.join(_BIN, "ffprobe.exe")

PORT = 8765
IMG_SIZE = (1024, 576)      # tier gratuito do pollinations entrega isso
IMG_OUT = (1792, 1008)      # pos-corte da marca d'agua, 16:9

# ---------------------------------------------------------------- vozes
VOICES = [
    {"id": "pt-BR-AntonioNeural",   "label": "Antonio  (pt-BR, masculino)"},
    {"id": "pt-BR-ThalitaNeural",   "label": "Thalita  (pt-BR, feminino)"},
    {"id": "pt-BR-FranciscaNeural", "label": "Francisca (pt-BR, feminina)"},
    {"id": "pt-BR-ThalitaMultilingualNeural", "label": "Thalita ML (pt-BR, feminina)"},
    {"id": "en-US-AndrewNeural",    "label": "Andrew   (en-US, masculino)"},
    {"id": "en-US-GuyNeural",       "label": "Guy      (en-US, masculino)"},
    {"id": "en-US-JennyNeural",     "label": "Jenny    (en-US, feminino)"},
    {"id": "en-US-AriaNeural",      "label": "Aria     (en-US, feminino)"},
    {"id": "en-GB-RyanNeural",      "label": "Ryan     (en-GB, masculino)"},
]

# fallback caso a Microsoft remova uma voz do catalogo (aconteceu com
# FranciscoNeural/BrendaNeural em 10/2026): tentamos outras do mesmo idioma
VOICE_FALLBACK = {
    "pt": ["pt-BR-AntonioNeural", "pt-BR-FranciscaNeural",
           "pt-BR-ThalitaMultilingualNeural", "pt-BR-ThalitaNeural"],
    "en": ["en-US-AndrewNeural", "en-US-GuyNeural", "en-US-JennyNeural",
           "en-US-AriaNeural", "en-GB-RyanNeural"],
}

# ---------------------------------------------------------------- temas
STYLE_SUFFIX = ("cinematic film still, photorealistic, ultra detailed, "
                "shallow depth of field, subtle 35mm film grain, 16:9 widescreen")

THEMES = {
    "noir": {
        "label": "Crime Noir",
        "desc": "Drama sombrio, luz baixa, teal & amber (estilo Loan Shark)",
        "style": ("cinematic film still from a dark crime drama, moody film noir lighting, "
                  "teal and amber color grade, deep shadows, anamorphic lens, " + STYLE_SUFFIX),
        "mood": "noir",
        "accent": (120, 22, 26),
        "voice": "en-US-AndrewNeural",
        "rate": "-8%",
        "img_every": 9.0,
    },
    "documentario": {
        "label": "Documentario",
        "desc": "Fotografia realista, luz natural, narrativa calma",
        "style": ("photorealistic documentary photography, natural lighting, "
                  "candid composition, realistic colors, " + STYLE_SUFFIX),
        "mood": "hopeful",
        "accent": (170, 138, 80),
        "voice": "pt-BR-AntonioNeural",
        "rate": "-4%",
        "img_every": 8.0,
    },
    "terror": {
        "label": "Terror / Suspense",
        "desc": "Claustrofobico, sombras densas, tensao constante",
        "style": ("cinematic horror film still, dim moonlight, dense shadows, "
                  "desaturated cold color grade, fog, " + STYLE_SUFFIX),
        "mood": "tense",
        "accent": (110, 24, 24),
        "voice": "en-US-GuyNeural",
        "rate": "-10%",
        "img_every": 9.5,
    },
    "motivacional": {
        "label": "Motivacional",
        "desc": "Epic grandioso, golden hour, superacao",
        "style": ("epic cinematic film still, golden hour lighting, heroic composition, "
                  "warm inspiring color grade, lens flare, " + STYLE_SUFFIX),
        "mood": "epic",
        "accent": (196, 152, 64),
        "voice": "pt-BR-FranciscaNeural",
        "rate": "-6%",
        "img_every": 8.0,
    },
    "scifi": {
        "label": "Sci-Fi",
        "desc": "Futurista, neon, atmosferas artificiais",
        "style": ("cinematic science fiction film still, neon lighting, rain-slick futuristic "
                  "city, volumetric light, cyberpunk color grade, " + STYLE_SUFFIX),
        "mood": "tense",
        "accent": (40, 150, 190),
        "voice": "en-US-AriaNeural",
        "rate": "-6%",
        "img_every": 8.0,
    },
    "historico": {
        "label": "Historia / Epoca",
        "desc": "Classico, cores de epoca, ar solene",
        "style": ("classical historical film still, period-accurate sets and costumes, "
                  "candlelight and warm sepia tones, painterly composition, " + STYLE_SUFFIX),
        "mood": "sad",
        "accent": (150, 120, 70),
        "voice": "en-GB-RyanNeural",
        "rate": "-8%",
        "img_every": 9.0,
    },
    "cartoon": {
        "label": "Cartoon / Animacao",
        "desc": "Vetorial flat: contornos pretos grossos, cores chapadas",
        "style": ("2D flat vector illustration, thick bold black outlines, solid "
                  "flat colors, no gradients, no shading, clean simple shapes, "
                  "modern flat design cartoon, professional illustration, "
                  "16:9 widescreen"),
        "mood": "playful",
        "accent": (240, 130, 32),
        "voice": "pt-BR-FranciscaNeural",
        "rate": "-2%",
        "img_every": 7.0,
        "char_focus": True,   # protagonista em TODOS os shots (nao alternados)
        "img_model": "",      # flux (padrao do node): turbo/sana deformavam a
                              # especie (urso no lugar do bulldog) - testes A/B/C
    },
}

# frases do cartao de creditos conforme idioma da voz
CARD_CREDIT = {"pt": "UM  CURTA-METRAGEM", "en": "A  SHORT  FILM"}


def voice_lang(voice_id):
    return voice_id.split("-")[0] if "-" in voice_id else "en"


def normalize_theme(name):
    return name if name in THEMES else "noir"
