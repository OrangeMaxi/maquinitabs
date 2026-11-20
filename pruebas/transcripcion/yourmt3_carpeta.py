"""Corre YourMT3 (vía mt3-infer) sobre todos los .wav de una carpeta y deja un .mid por archivo.

    <venv>/python -X utf8 yourmt3_carpeta.py <carpeta con .wav> <carpeta salida>

Lo ya hecho se saltea. Deja tiempos.json (segundos de cálculo y de audio por archivo).
"""
import json
import os
import sys
import time

import librosa
import mt3_infer

entrada, salida = sys.argv[1], sys.argv[2]
os.makedirs(salida, exist_ok=True)
ruta_t = os.path.join(salida, "tiempos.json")
tiempos = json.load(open(ruta_t)) if os.path.exists(ruta_t) else {}
audios = sorted(f for f in os.listdir(entrada) if f.lower().endswith(".wav"))
modelo = None
for k, f in enumerate(audios):
    clave = os.path.splitext(f)[0]
    destino = os.path.join(salida, clave + ".mid")
    if os.path.exists(destino):
        continue
    modelo = modelo or mt3_infer.load_model("yourmt3", device="cpu")
    y, _ = librosa.load(os.path.join(entrada, f), sr=16000, mono=True)
    t0 = time.time()
    modelo.transcribe(y, sr=16000).save(destino)
    tiempos[clave] = {"calculo": round(time.time() - t0, 1), "audio": round(len(y) / 16000, 1)}
    json.dump(tiempos, open(ruta_t, "w"), indent=1)
    print(f"{k + 1}/{len(audios)} {clave} {tiempos[clave]}", flush=True)
