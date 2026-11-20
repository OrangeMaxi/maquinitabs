"""Compara modelos de transcripción (audio -> notas) contra GuitarSet, nota por nota.

    python evaluar_notas.py <carpeta guitarset> [jugador=05]

- Referencia: las notas anotadas de GuitarSet (archivos .jams, una capa "note_midi" por cuerda).
- Basic Pitch (lo que usa hoy la app): el mismo modelo ONNX de acordes/transcribir.py; las notas se arman
  como en el paquete oficial de Basic Pitch (umbral de ataque 0,5, de nota 0,3, nota mínima ~128 ms).
- YourMT3: los MIDI que deja yourmt3_guitarset.py en <guitarset>/yourmt3/ (si están).

Métricas (mir_eval, las del concurso MIREX), en % y promediadas sobre las grabaciones:
- ataque: la nota es correcta si coincide la altura y el ataque cae a menos de 50 ms;
- ataque+fin: además el final cae cerca (20 % de la duración o 50 ms);
- clase: como «ataque» pero sin mirar la octava (sirve para acordes y digitación).
"""
import json
import os
import sys

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(AQUI)), "acordes"))
import transcribir  # noqa: E402


def referencia(ruta_jams):
    d = json.load(open(ruta_jams, encoding="utf-8"))
    notas = []
    for a in d["annotations"]:
        if a["namespace"] == "note_midi":
            for o in a["data"]:
                notas.append((o["time"], o["time"] + o["duration"], round(o["value"])))
    return sorted(notas)


def basic_pitch(ruta_wav, cache):
    import librosa
    if os.path.exists(cache):
        z = np.load(cache)
        nota, ataque = z["nota"], z["ataque"]
    else:
        y, _ = librosa.load(ruta_wav, sr=transcribir.SR, mono=True)
        nota, ataque = transcribir.activaciones(y)
        np.savez_compressed(cache, nota=nota, ataque=ataque)
    return notas_bp(nota, ataque)


def notas_bp(frames, onsets, u_ataque=0.5, u_nota=0.3, min_largo=11, tolerancia=11):
    """Armado de notas como output_to_notes_polyphonic de Basic Pitch (sin el paso de «melodía»)."""
    n = frames.shape[0]
    # ataques inferidos de los saltos de energía de las notas (infer_onsets=True en Basic Pitch)
    dif = np.zeros_like(frames)
    for k in (1, 2):
        d = np.zeros_like(frames)
        d[k:] = frames[k:] - frames[:-k]
        dif = d if k == 1 else np.minimum(dif, d)
    dif = np.maximum(dif, 0)
    dif[:2] = 0
    if dif.max() > 0:
        onsets = np.maximum(onsets, dif * onsets.max() / dif.max())
    picos = (onsets > u_ataque)
    picos[1:-1] &= (onsets[1:-1] >= onsets[:-2]) & (onsets[1:-1] >= onsets[2:])
    resto = frames.copy()
    notas = []
    for t, f in sorted(zip(*np.nonzero(picos)), key=lambda x: -x[0]):
        if t >= n - 1:
            continue
        i, k = t + 1, 0
        while i < n - 1 and k < tolerancia:
            k = k + 1 if resto[i, f] < u_nota else 0
            i += 1
        i -= k
        if i - t <= min_largo:
            continue
        resto[t:i, max(f - 1, 0):f + 2] = 0
        notas.append((t / transcribir.FPS, i / transcribir.FPS, f + transcribir.MIDI_BASE))
    return sorted(notas)


def yourmt3(ruta_mid):
    import mido
    m = mido.MidiFile(ruta_mid)
    notas, abiertas, t = [], {}, 0.0
    for msg in m:                                  # iterar el archivo da tiempos en segundos
        t += msg.time
        if getattr(msg, "channel", None) == 9:     # batería: no son notas de altura
            continue
        if msg.type == "note_on" and msg.velocity > 0:
            abiertas.setdefault(msg.note, []).append(t)
        elif msg.type in ("note_off", "note_on") and abiertas.get(msg.note):
            ini = abiertas[msg.note].pop(0)
            if t > ini:
                notas.append((ini, t, msg.note))
    return sorted(notas)


def medir(ref, est):
    import mir_eval
    ri = np.array([[a, b] for a, b, _ in ref]) if ref else np.zeros((0, 2))
    rp = np.array([mir_eval.util.midi_to_hz(m) for _, _, m in ref])
    if not est:
        return {"ataque": 0.0, "ataque+fin": 0.0, "clase": 0.0, "precision": 0.0, "recall": 0.0}
    ei = np.array([[a, max(b, a + 0.01)] for a, b, _ in est])
    ep = np.array([mir_eval.util.midi_to_hz(m) for _, _, m in est])
    p, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep, offset_ratio=None)
    _, _, f2, _ = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep)
    # clase de altura: todas las notas a la misma octava
    a_pc = lambda ps: np.array([mir_eval.util.midi_to_hz(60 + (round(mir_eval.util.hz_to_midi(x)) % 12)) for x in ps])
    _, _, f3, _ = mir_eval.transcription.precision_recall_f1_overlap(ri, a_pc(rp), ei, a_pc(ep), offset_ratio=None)
    return {"ataque": 100 * f, "ataque+fin": 100 * f2, "clase": 100 * f3, "precision": 100 * p, "recall": 100 * r}


def promedio(res, cs):
    for modelo, r in res.items():
        if cs and all(c in r for c in cs):
            prom = {k: np.mean([r[c][k] for c in cs]) for k in ("ataque", "ataque+fin", "clase", "precision", "recall")}
            print(f"  {modelo:12s} " + "  ".join(f"{k} {v:5.1f}" for k, v in prom.items()))


def egdb(carpeta):
    """EGDB (guitarra eléctrica): las tabs con el amplificador Plexi (con distorsión) y las 5 grabaciones
    reales anotadas por un músico. El fin de nota de EGDB es estimado: mirar sobre todo «ataque»."""
    cache = os.path.join(carpeta, "_bp")
    os.makedirs(cache, exist_ok=True)
    for nombre, audio, etiqueta, ymt3, ext in (("EGDB, amplificador Plexi (distorsión)", "audio_Plexi", "audio_label", "yourmt3_plexi", ".midi"),
                                                ("EGDB, grabaciones reales (RealData)", "RealData/Audio", "RealData/Label", "yourmt3_real", ".mid")):
        claves = sorted(os.path.splitext(f)[0] for f in os.listdir(os.path.join(carpeta, audio)) if f.endswith(".wav"))
        res = {"Basic Pitch": {}, "YourMT3": {}}
        for c in claves:
            ref = yourmt3(os.path.join(carpeta, etiqueta, c + ext))
            res["Basic Pitch"][c] = medir(ref, basic_pitch(os.path.join(carpeta, audio, c + ".wav"),
                                                           os.path.join(cache, audio.replace("/", "_") + c + ".npz")))
            mid = os.path.join(carpeta, ymt3, c + ".mid")
            if os.path.exists(mid):
                res["YourMT3"][c] = medir(ref, yourmt3(mid))
        comunes = [c for c in claves if c in res["YourMT3"]] or claves
        print(f"{nombre}: {len(comunes)} de {len(claves)}")
        promedio(res, comunes)
        print()


def main():
    if sys.argv[1] == "egdb":
        egdb(sys.argv[2])
        return
    gs = sys.argv[1]
    jugador = sys.argv[2] if len(sys.argv) > 2 else "05"
    cache = os.path.join(gs, "_bp")
    os.makedirs(cache, exist_ok=True)
    claves = sorted(f[:-5] for f in os.listdir(os.path.join(gs, "annotation")) if f.startswith(jugador + "_"))
    res = {"Basic Pitch": {}, "YourMT3": {}}
    for c in claves:
        ref = referencia(os.path.join(gs, "annotation", c + ".jams"))
        res["Basic Pitch"][c] = medir(ref, basic_pitch(os.path.join(gs, "audio_mono-mic", c + "_mic.wav"),
                                                       os.path.join(cache, c + ".npz")))
        mid = os.path.join(gs, "yourmt3", c + ".mid")
        if os.path.exists(mid):
            res["YourMT3"][c] = medir(ref, yourmt3(mid))
    comunes = [c for c in claves if c in res["YourMT3"]] or claves
    print(f"GuitarSet, guitarrista {jugador}: {len(comunes)} grabaciones (de {len(claves)})\n")
    for estilo, filtro in (("todo", ""), ("comping (acordes)", "_comp"), ("solos", "_solo")):
        cs = [c for c in comunes if filtro in c]
        print(f"{estilo} ({len(cs)})")
        for modelo, r in res.items():
            if not all(c in r for c in cs) or not cs:
                continue
            prom = {k: np.mean([r[c][k] for c in cs]) for k in ("ataque", "ataque+fin", "clase", "precision", "recall")}
            print(f"  {modelo:12s} " + "  ".join(f"{k} {v:5.1f}" for k, v in prom.items()))
        print()


if __name__ == "__main__":
    main()
