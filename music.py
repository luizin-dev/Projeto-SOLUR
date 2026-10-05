# -*- coding: utf-8 -*-
"""Trilha sonora sintetizada (numpy, zero dependencias externas de audio).
Portado do filme Loan Shark: pads de cordas, drone, chuva, pulsos, piano de feltro,
boom cinematico e pre-ducking automatico sob a narracao. Parametrizado por mood."""
import json
import os
import wave

import numpy as np

from parser import _parse_srt

SR = 44100

# acordes (Hz)
DM  = [146.8, 174.6, 220.0]    # Dm
BB  = [116.5, 146.8, 174.6]    # Bb
FM2 = [87.3, 110.0, 130.8]     # Fm baixo
C   = [130.8, 164.8, 196.0]    # C
FM  = [174.6, 220.0, 261.6]    # F
GM  = [98.0, 123.5, 196.0]     # G
AM  = [110.0, 138.6, 164.8]    # Am
EM  = [82.4, 123.5, 164.8]     # Em
DMAJ = [146.8, 185.0, 220.0]   # D maior

# ---------------- paletas por mood ----------------
MOODS = {
    "noir":    {"prog": [DM, BB, FM2, C],  "drone": 0.085, "pad": 0.062, "rain": 0.07,
                "pulse": 0.0,   "lp": 6500, "boom_every": 0, "piano": False},
    "tense":   {"prog": [DM, BB, EM, DM],  "drone": 0.105, "pad": 0.055, "rain": 0.0,
                "pulse": 0.05,  "lp": 6000, "boom_every": 0, "piano": False},
    "sad":     {"prog": [FM2, DM, BB, FM2],"drone": 0.060, "pad": 0.055, "rain": 0.03,
                "pulse": 0.0,   "lp": 5500, "boom_every": 0, "piano": True},
    "hopeful": {"prog": [C, GM, AM, FM],   "drone": 0.060, "pad": 0.068, "rain": 0.02,
                "pulse": 0.0,   "lp": 9000, "boom_every": 0, "piano": True},
    "epic":    {"prog": [AM, FM, C, GM],   "drone": 0.090, "pad": 0.060, "rain": 0.0,
                "pulse": 0.028, "lp": 7500, "boom_every": 2, "piano": False},
    "playful": {"prog": [C, GM, DMAJ, FM], "drone": 0.050, "pad": 0.075, "rain": 0.0,
                "pulse": 0.045, "lp": 11000, "boom_every": 0, "piano": True},
}


# ---------------- sintese ----------------
def t_axis(dur):
    return np.arange(int(dur * SR)) / SR


def lowpass_fft(x, cutoff_hz, softness=0.5):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    mask = 1.0 / (1.0 + np.exp(np.clip((f - cutoff_hz) / (cutoff_hz * softness + 1e-9), -50, 50)))
    return np.fft.irfft(X * mask, n=len(x))


def highpass_fft(x, cutoff_hz, softness=0.5):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    mask = 1.0 / (1.0 + np.exp(-(f - cutoff_hz) / (cutoff_hz * softness + 1e-9)))
    return np.fft.irfft(X * mask, n=len(x))


def smooth_noise(dur, smooth_hz=2.0, seed=0):
    rng = np.random.default_rng(seed)
    n = int(dur * SR) + 1
    x = rng.standard_normal(n)
    x = lowpass_fft(x, smooth_hz, 0.35)
    x -= x.min(); x /= (x.max() + 1e-9)
    return x[:n - 1]


def pad_chord(freqs, dur, level, attack=3.0, release=3.5, seed=0):
    t = t_axis(dur)
    out = np.zeros_like(t)
    rng = np.random.default_rng(seed)
    for f in freqs:
        for det in (-0.0012, 0.0009):
            ff = f * (1 + det)
            ph = rng.uniform(0, 2 * np.pi)
            for k, a in ((1, 1.0), (2, 0.32), (3, 0.12), (4, 0.05)):
                out += a * np.sin(2 * np.pi * ff * k * t + ph + k) / (1 + 0.15 * k)
    out /= (len(freqs) * 2 * 1.6)
    attack = min(attack, dur * 0.45); release = min(release, dur * 0.45)
    env = np.ones_like(t)
    na = int(attack * SR); nr = int(release * SR)
    env[:na] = np.linspace(0, 1, na) ** 2
    env[-nr:] = np.linspace(1, 0, nr) ** 2
    env *= (0.85 + 0.15 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.07 * t + seed)))
    return out * env * level


def drone(dur, level, root=36.71, fifth=55.0):
    t = t_axis(dur)
    lfo = 0.8 + 0.2 * np.sin(2 * np.pi * 0.045 * t)
    x = (np.sin(2 * np.pi * root * 1.0015 * t) + np.sin(2 * np.pi * root * 0.999 * t)
         + 0.7 * np.sin(2 * np.pi * fifth * t) + 0.35 * np.sin(2 * np.pi * root * 2 * 1.002 * t))
    x = lowpass_fft(x / 3.05, 300)
    return x * lfo * level


def rain(dur, level, seed=1):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    x = rng.standard_normal(n)
    x = highpass_fft(lowpass_fft(x, 5200, 0.4), 350, 0.45)
    patter = 0.55 + 0.45 * smooth_noise(dur, 3.2, seed + 7)
    slow = 0.75 + 0.25 * smooth_noise(dur, 0.12, seed + 13)
    return x * patter * slow * level


def pulse(dur, level, period=2.56, f=41.2):
    t = t_axis(dur)
    x = np.zeros_like(t)
    k = 0
    while k * period < dur:
        s = int(k * period * SR)
        seg_dur = min(1.6, dur - k * period)
        n = int(seg_dur * SR)
        if n <= 0:
            break
        tt = np.arange(n) / SR
        env = np.exp(-tt * 3.2) * np.minimum(tt / 0.12, 1.0)
        x[s:s + n] += np.sin(2 * np.pi * f * tt) * env
        k += 1
    return x * level


def piano_note(f, dur=5.0, level=1.0):
    t = t_axis(dur)
    x = np.zeros_like(t)
    for k, a in ((1, 1.0), (2, 0.38), (3, 0.14), (4, 0.05)):
        x += a * np.sin(2 * np.pi * f * (1 + 0.0004 * k) * k * t + 0.3 * k)
    env = np.minimum(t / 0.012, 1.0) * np.exp(-t * 1.5)
    return x * env * level


def add_note(buf, f, t0, level):
    s = int(t0 * SR)
    note = piano_note(f, min(5.0, max(0.5, len(buf) / SR - t0)), level)
    e = min(s + len(note), len(buf))
    if e > s:
        buf[s:e] += note[:e - s]


def boom(level=1.0, dur=2.8):
    t = t_axis(dur)
    env = np.exp(-t * 2.0) * np.minimum(t / 0.006, 1.0)
    x = np.sin(2 * np.pi * 46 * t * (1 - 0.25 * np.minimum(t / dur, 1))) + 0.3 * np.sin(2 * np.pi * 92 * t)
    x = lowpass_fft(x * env, 400)
    return x * level


def duck_envelope(dur, cues, floor=0.38, attack=0.25, release=0.85):
    env = np.ones(int(dur * SR))
    for s, e in cues:
        a = max(0, int(s * SR)); b = min(int(e * SR), len(env))
        na = int(attack * SR); nr = int(release * SR)
        if b > a:
            env[a:b] = np.minimum(env[a:b], floor)
            for k in range(na):
                if a - 1 - k >= 0:
                    env[a - 1 - k] = np.minimum(env[a - 1 - k], floor + (1 - floor) * (k / na))
            for k in range(nr):
                if b + k < len(env):
                    env[b + k] = np.minimum(env[b + k], floor + (1 - floor) * (k / nr))
    return env


def write_wav(path, left, right=None):
    if right is None:
        right = left
    peak = max(np.abs(left).max(), np.abs(right).max(), 1e-9)
    if peak > 0.97:
        left = left / peak * 0.97; right = right / peak * 0.97
    data = np.empty((len(left), 2))
    data[:, 0] = left; data[:, 1] = right
    pcm = (np.clip(data, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ---------------- construcao ----------------
def _cues(audio_dir, narr_name, lead):
    p = os.path.join(audio_dir, narr_name)
    if not os.path.exists(p):
        return []
    return [(s + lead, e + lead) for s, e, _ in _parse_srt(p)]


def _scene_bed(dur, mood, scene_seed, cues):
    m = MOODS.get(mood, MOODS["noir"])
    t = t_axis(dur)
    bed = drone(dur, m["drone"])
    pos, bar = 0.0, 0
    while pos < dur - 0.5:
        d = min(17.0, dur - pos)
        p = pad_chord(m["prog"][bar % 4], d, m["pad"], attack=4.0, release=4.5,
                      seed=scene_seed + bar)
        s0 = int(pos * SR)
        bed[s0:s0 + len(p)] += p
        pos += 16.0; bar += 1
        if m["boom_every"] and bar % m["boom_every"] == 0:
            b = boom(0.16)
            bed[s0:s0 + len(b)] += b[:max(0, len(bed) - s0)]
    if m["rain"] > 0:
        r = rain(dur, m["rain"], seed=40 + scene_seed % 500)
        bed += r
        bed += np.roll(r, int(0.011 * SR)) * 0.6
    if m["pulse"] > 0:
        bed += pulse(dur, m["pulse"])
    if m["piano"]:
        for k in range(max(2, int(dur / 14))):
            add_note(bed, m["prog"][k % 4][0] * 2, 1.5 + k * (dur / max(2, int(dur / 14))), 0.05)
    bed = lowpass_fft(bed, m["lp"])
    if cues:
        bed *= duck_envelope(dur, cues)
    return bed


def build_score(project_dir, timeline, doc, global_mood="noir", log=print):
    """Gera bed_title, bed_sXX, bed_quote, bed_final em <projeto>/audio/."""
    audio_dir = os.path.join(project_dir, "audio")
    os.makedirs(audio_dir, exist_ok=True)

    # title
    dur = timeline["title"]["dur"]
    m = MOODS.get(global_mood, MOODS["noir"])
    t = t_axis(dur)
    x = drone(dur, m["drone"] + 0.02) * np.minimum(t / 1.2, 1.0)
    x += pad_chord(m["prog"][0], dur, 0.045, attack=2.5, release=2.0, seed=101)
    b = boom(0.20); x[:len(b)] += b
    x = lowpass_fft(x, 3200)
    write_wav(os.path.join(audio_dir, "bed_title.wav"), x, x * 0.96)
    log("  bed_title ok")

    for sc in timeline["scenes"]:
        out = os.path.join(audio_dir, f"bed_s{sc['idx']:02d}.wav")
        if os.path.exists(out):
            continue
        # mood por cena (campo MOOD: no roteiro) tem prioridade sobre o global
        scene_mood = None
        for dsc in doc["scenes"]:
            if dsc["idx"] == sc["idx"]:
                scene_mood = (dsc.get("mood") or "").strip().lower() or None
        use = scene_mood if scene_mood in MOODS else global_mood
        bed = _scene_bed(sc["dur"], use, 100 * sc["idx"],
                         _cues(audio_dir, f"narr_s{sc['idx']:02d}.json", sc["lead"]))
        write_wav(out, bed, bed * 0.97)
        log(f"  bed_s{sc['idx']:02d} ok ({use})")

    # quote
    if timeline.get("quote"):
        dur = timeline["quote"]["dur"]
        q = pad_chord([116.5, 146.8, 174.6, 220.0], dur, 0.055, attack=3.5, release=4.0, seed=55)
        add_note(q, 293.7, 0.8, 0.10)
        add_note(q, 220.0, 3.2, 0.085)
        add_note(q, 174.6, 5.6, 0.08)
        q = lowpass_fft(q, 5200)
        write_wav(os.path.join(audio_dir, "bed_quote.wav"), q, q * 0.97)
        log("  bed_quote ok")

    # final
    if timeline.get("final"):
        dur = timeline["final"]["dur"]
        t = t_axis(dur)
        f = drone(dur, 0.05) * np.exp(-t / (dur * 0.55))
        add_note(f, 146.8, 1.0, 0.07)
        f = lowpass_fft(f, 3000)
        write_wav(os.path.join(audio_dir, "bed_final.wav"), f, f)
        log("  bed_final ok")


if __name__ == "__main__":
    import sys
    proj = sys.argv[1] if len(sys.argv) > 1 else "."
    T = json.load(open(os.path.join(proj, "timeline.json")))
    build_score(proj, T, {"scenes": []}, "noir")
    print("MUSIC DONE")
