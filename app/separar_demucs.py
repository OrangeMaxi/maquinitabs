"""Separa un tema con demucs y guarda las pistas con soundfile (sin torchaudio/torchcodec).

    python separar_demucs.py <entrada.wav> <carpeta_salida> [modelo=htdemucs_6s]

Hace lo mismo que `python -m demucs -n htdemucs_6s -o <carpeta_salida> <entrada.wav>` (mismos ajustes por
defecto: shifts=1, overlap=0.25, WAV de 16 bits reescalado si satura) y deja las pistas en el mismo lugar:
<carpeta_salida>/<modelo>/<nombre de la entrada>/<pista>.wav. Existe porque el comando de demucs guarda con
torchaudio, que desde la 2.9 necesita torchcodec, y torchcodec no tiene versión para procesadores ARM (el
servidor gratuito de Oracle Cloud). El progreso sale por stderr como en demucs (barra de tqdm con «NN%|»).
"""
import os
import sys

import numpy as np
import soundfile as sf
import torch
from demucs.apply import apply_model
from demucs.pretrained import get_model


def main():
    entrada, salida = sys.argv[1], sys.argv[2]
    nombre_modelo = sys.argv[3] if len(sys.argv) > 3 else "htdemucs_6s"
    modelo = get_model(nombre_modelo)
    modelo.cpu().eval()

    y, sr = sf.read(entrada, dtype="float32", always_2d=True)          # (muestras, canales)
    y = y.T
    if y.shape[0] == 1:
        y = np.repeat(y, 2, axis=0)
    y = y[:2]
    if sr != modelo.samplerate:
        import librosa
        y = librosa.resample(y, orig_sr=sr, target_sr=modelo.samplerate)
    wav = torch.from_numpy(np.ascontiguousarray(y))

    ref = wav.mean(0)                                                   # normalización igual que demucs
    media, desvio = ref.mean(), ref.std()
    wav = (wav - media) / (desvio + 1e-8)
    with torch.no_grad():
        fuentes = apply_model(modelo, wav[None], device="cpu", shifts=1, split=True, overlap=0.25,
                              progress=True, num_workers=0)[0]
    fuentes = fuentes * desvio + media

    destino = os.path.join(salida, nombre_modelo, os.path.splitext(os.path.basename(entrada))[0])
    os.makedirs(destino, exist_ok=True)
    for fuente, nombre in zip(fuentes, modelo.sources):
        x = fuente.numpy()
        pico = np.abs(x).max()
        if pico > 0.99:                                                 # clip_mode="rescale" de demucs
            x = x / (pico / 0.99)
        sf.write(os.path.join(destino, nombre + ".wav"), x.T, modelo.samplerate, subtype="PCM_16")


if __name__ == "__main__":
    main()
