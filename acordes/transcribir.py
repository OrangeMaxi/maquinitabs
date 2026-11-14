"""Transcripción polifónica (guitarra, piano) con el modelo Basic Pitch de Spotify (ICASSP 2022, Apache 2.0).

Se usa solo el modelo ONNX (basic_pitch\\nmp.onnx) con onnxruntime; el armado de notas es propio porque acá
las notas van directo a una grilla de semicorcheas.

    notas(ruta_wav, cache_npz, bordes, rango) -> [{"i": casilla, "d": casillas, "m": midi}, ...]
"""
import os

import numpy as np

AQUI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "basic_pitch")
SR = 22050
HOP = 256
FPS = SR / HOP
N_MUESTRAS = SR * 2 - HOP            # ventana del modelo
SOLAPE = 30                          # cuadros
MIDI_BASE = 21                       # el bin 0 es el La más grave del piano

_sesion = None


def _modelo():
    global _sesion
    if _sesion is None:
        import onnxruntime as ort
        op = ort.SessionOptions()
        op.log_severity_level = 3
        _sesion = ort.InferenceSession(os.path.join(AQUI, "nmp.onnx"), op, providers=["CPUExecutionProvider"])
    return _sesion


def activaciones(y):
    """y mono a 22050 Hz -> (nota[cuadros, 88], ataque[cuadros, 88]) a ~86 cuadros por segundo."""
    ses = _modelo()
    entrada = ses.get_inputs()[0].name
    largo = len(y)
    y = np.concatenate([np.zeros(SOLAPE * HOP // 2, dtype=np.float32), y.astype(np.float32)])
    paso = N_MUESTRAS - SOLAPE * HOP
    ventanas = []
    for i in range(0, len(y), paso):
        v = y[i:i + N_MUESTRAS]
        ventanas.append(np.pad(v, (0, N_MUESTRAS - len(v))))
    nota, ataque = [], []
    for k in range(0, len(ventanas), 16):
        lote = np.stack(ventanas[k:k + 16])[:, :, None]
        n, a = ses.run(["StatefulPartitionedCall:1", "StatefulPartitionedCall:2"], {entrada: lote})
        nota.append(n)
        ataque.append(a)
    cuadros = int(largo * FPS / SR)

    def unir(xs):
        x = np.concatenate(xs)[:, SOLAPE // 2:-(SOLAPE // 2), :]
        return x.reshape(-1, x.shape[2])[:cuadros]

    return unir(nota), unir(ataque)


def notas(ruta, cache, bordes, rango, max_voces=6, u_nota=0.32, u_ataque=0.5):
    """bordes: tiempos de los bordes de las casillas (semicorcheas). rango: (midi mín, midi máx)."""
    import librosa
    if cache and os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(ruta):
        z = np.load(cache)
        nota, ataque = z["nota"].astype(np.float32) / 255, z["ataque"].astype(np.float32) / 255
    else:
        y, _ = librosa.load(ruta, sr=SR, mono=True)
        nota, ataque = activaciones(y)
        if cache:
            np.savez_compressed(cache, nota=np.round(nota * 255).astype(np.uint8),
                                ataque=np.round(ataque * 255).astype(np.uint8))
    if not len(nota):
        return []
    lo, hi = max(rango[0], MIDI_BASE) - MIDI_BASE, min(rango[1], MIDI_BASE + 87) - MIDI_BASE
    nc = len(bordes) - 1
    act = np.zeros((nc, 88), dtype=np.float32)
    atq = np.zeros((nc, 88), dtype=np.float32)
    f = np.clip(np.round(np.asarray(bordes) * FPS).astype(int), 0, len(nota))
    for s in range(nc):
        a, b = f[s], max(f[s + 1], f[s] + 1)
        if a >= len(nota):
            break
        act[s] = nota[a:b].mean(axis=0)
        # el ataque puede caer un par de cuadros antes del borde de la casilla
        atq[s] = ataque[max(a - 2, 0):max(b - 2, a + 1)].max(axis=0)
    out = []
    for p in range(lo, hi + 1):
        ini = None
        fuerza = []
        for s in range(nc + 1):
            suena = s < nc and act[s, p] > u_nota
            nuevo = s < nc and atq[s, p] > u_ataque and act[s, p] > u_nota
            if ini is not None and (not suena or nuevo):
                d = s - ini
                media = float(np.mean(fuerza))
                # una casilla suelta y floja suele ser un armónico o filtración de otra pista
                if d >= 2 or media > 0.5:
                    out.append({"i": ini, "d": d, "m": p + MIDI_BASE, "f": media})
                ini = None
            if suena and ini is None:
                # una nota arranca con ataque, o si viene de silencio con activación clara
                if nuevo or act[s, p] > u_nota + 0.1:
                    ini, fuerza = s, []
            if ini is not None and suena:
                fuerza.append(act[s, p])
    # armónicos: una nota que arranca junto con otra una octava (o 12ª) más abajo y bastante más floja
    por_inicio = {}
    for n in out:
        por_inicio.setdefault(n["i"], []).append(n)
    limpio = []
    for i, grupo in por_inicio.items():
        tonos = {n["m"]: n["f"] for n in grupo}
        grupo = [n for n in grupo if not any(tonos.get(n["m"] - k, 0) > n["f"] * 1.6 for k in (12, 19, 24))]
        grupo.sort(key=lambda n: -n["f"])
        limpio += grupo[:max_voces]
    limpio.sort(key=lambda n: (n["i"], n["m"]))
    return [{"i": int(n["i"]), "d": int(n["d"]), "m": int(n["m"])} for n in limpio]
