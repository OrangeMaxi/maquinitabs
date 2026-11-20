"""Corre YourMT3 (vía el paquete mt3-infer) sobre GuitarSet y guarda un MIDI por grabación.

Se corre con el Python del entorno aparte donde está mt3-infer (ver LEEME.md), no con el de la app:

    <venv>/python -X utf8 yourmt3_guitarset.py <carpeta guitarset> <carpeta salida> [jugador=05]

Lo ya hecho se saltea. Deja también tiempos.json (segundos de cálculo por grabación).
"""
import json
import os
import sys
import time

import librosa
import mt3_infer

guitarset, salida = sys.argv[1], sys.argv[2]
jugador = sys.argv[3] if len(sys.argv) > 3 else "05"
os.makedirs(salida, exist_ok=True)
ruta_t = os.path.join(salida, "tiempos.json")
tiempos = json.load(open(ruta_t)) if os.path.exists(ruta_t) else {}
audios = sorted(f for f in os.listdir(os.path.join(guitarset, "audio_mono-mic")) if f.startswith(jugador + "_"))
modelo = mt3_infer.load_model("yourmt3", device="cpu")
for k, f in enumerate(audios):
    clave = f.replace("_mic.wav", "")
    destino = os.path.join(salida, clave + ".mid")
    if os.path.exists(destino):
        continue
    y, _ = librosa.load(os.path.join(guitarset, "audio_mono-mic", f), sr=16000, mono=True)
    t0 = time.time()
    midi = modelo.transcribe(y, sr=16000)
    tiempos[clave] = {"calculo": round(time.time() - t0, 1), "audio": round(len(y) / 16000, 1)}
    midi.save(destino)
    json.dump(tiempos, open(ruta_t, "w"), indent=1)
    print(f"{k + 1}/{len(audios)} {clave} {tiempos[clave]}", flush=True)
