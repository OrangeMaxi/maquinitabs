"""Barre los umbrales del armado de notas de la app (transcribir.armar) contra GuitarSet y EGDB.

    python umbrales.py <carpeta guitarset> <carpeta egdb>

Mide lo que importa en la app: si cada nota cae en la semicorchea correcta. La referencia y lo transcripto se
llevan a la misma grilla de semicorcheas (pulsos anotados en GuitarSet; en EGDB, pulsos de librosa) y una nota
es correcta si coinciden la altura y la casilla donde empieza.
"""
import itertools
import json
import os
import sys

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(AQUI)), "acordes"))
sys.path.insert(0, AQUI)
import transcribir  # noqa: E402
from evaluar_notas import referencia, yourmt3  # noqa: E402

RANGO = (40, 88)      # el de la guitarra en la app


def activ(wav, cache):
    import librosa
    if os.path.exists(cache):
        z = np.load(cache)
        return z["nota"], z["ataque"], float(z["dur"])
    y, _ = librosa.load(wav, sr=transcribir.SR, mono=True)
    n, a = transcribir.activaciones(y)
    np.savez_compressed(cache, nota=n, ataque=a, dur=len(y) / transcribir.SR)
    return n, a, len(y) / transcribir.SR


def grilla(pulsos, dur):
    """Pulsos -> bordes de semicorcheas que cubren todo el audio."""
    p = np.asarray(sorted(pulsos))
    paso = np.median(np.diff(p))
    antes = np.arange(p[0] - paso, -paso, -paso)[::-1]
    despues = np.arange(p[-1] + paso, dur + 2 * paso, paso)
    p = np.concatenate([antes, p, despues])
    return np.concatenate([np.linspace(a, b, 4, endpoint=False) for a, b in zip(p[:-1], p[1:])] + [[p[-1]]])


def a_casillas(notas, bordes):
    """Notas (ini, fin, midi) en segundos -> {(casilla, midi)}."""
    centros = (bordes[:-1] + bordes[1:]) / 2
    out = set()
    for ini, fin, m in notas:
        if RANGO[0] <= m <= RANGO[1]:
            out.add((int(np.argmin(np.abs(bordes[:-1] - ini))), int(m)))
    return out


def cargar(gs, egdb):
    import librosa
    clips = []
    cg = os.path.join(gs, "_bp2")
    os.makedirs(cg, exist_ok=True)
    for f in sorted(os.listdir(os.path.join(gs, "annotation"))):
        if not f.startswith("05_"):
            continue
        c = f[:-5]
        d = json.load(open(os.path.join(gs, "annotation", f), encoding="utf-8"))
        pulsos = [o["time"] for a in d["annotations"] if a["namespace"] == "beat_position" for o in a["data"]]
        n, a, dur = activ(os.path.join(gs, "audio_mono-mic", c + "_mic.wav"), os.path.join(cg, c + ".npz"))
        b = grilla(pulsos, dur)
        clips.append(("guitarset", n, a, b, a_casillas(referencia(os.path.join(gs, "annotation", f)), b)))
    ce = os.path.join(egdb, "_bp2")
    os.makedirs(ce, exist_ok=True)
    for nombre, audio, etiqueta, ext in (("plexi", "audio_Plexi", "audio_label", ".midi"),
                                         ("real", "RealData/Audio", "RealData/Label", ".mid")):
        for f in sorted(os.listdir(os.path.join(egdb, audio))):
            if not f.endswith(".wav"):
                continue
            c = f[:-4]
            wav = os.path.join(egdb, audio, f)
            n, a, dur = activ(wav, os.path.join(ce, nombre + "_" + c + ".npz"))
            y, sr = librosa.load(wav, sr=22050, mono=True)
            _, pulsos = librosa.beat.beat_track(y=y, sr=sr, units="time")
            if len(pulsos) < 4:
                continue
            b = grilla(pulsos, dur)
            clips.append((nombre, n, a, b, a_casillas(yourmt3(os.path.join(egdb, etiqueta, c + ext)), b)))
    return clips


def medir(clips, **u):
    por = {}
    for grupo, n, a, b, ref in clips:
        est = {(x["i"], x["m"]) for x in transcribir.armar(n, a, b, RANGO, **u)}
        ok = len(est & ref)
        p = ok / len(est) if est else 0
        r = ok / len(ref) if ref else 0
        por.setdefault(grupo, []).append((p, r, 2 * p * r / (p + r) if p + r else 0))
    return {g: tuple(100 * np.mean(v, axis=0)) for g, v in por.items()}


def linea(res):
    return "  ".join(f"{g} P{p:4.1f} R{r:4.1f} F{f:4.1f}" for g, (p, r, f) in res.items())


def main():
    clips = cargar(sys.argv[1], sys.argv[2])
    base = medir(clips)
    print("actual           ", linea(base), flush=True)
    filas = []
    for un, ua, us, mg, fa in itertools.product((0.3, 0.32, 0.36, 0.4, 0.45, 0.5), (0.4, 0.5, 0.6, 0.7),
                                               (0.5, 0.6, 0.7), (0.05, 0.1, 0.2), (1.6, 2.5)):
        u = dict(u_nota=un, u_ataque=ua, u_suelta=us, margen=mg, f_armonico=fa)
        res = medir(clips, **u)
        # se elige por el promedio de las dos eléctricas (lo que más se parece a la banda); GuitarSet acompaña
        filas.append(((res["plexi"][2] + res["real"][2]) / 2, res["guitarset"][2], u, res))
    filas.sort(key=lambda x: -x[0])
    for e, g, u, res in filas[:12]:
        print(json.dumps(u), linea(res), flush=True)


if __name__ == "__main__":
    main()
