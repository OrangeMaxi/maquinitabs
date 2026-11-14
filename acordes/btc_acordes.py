"""Acordes con el modelo entrenado BTC (Park et al., ISMIR 2019 — github.com/jayg996/BTC-ISMIR19, MIT).

    prob, dt = probabilidades(y, sr, afin)   # (cuadros, 170) y segundos por cuadro
    ETIQUETAS[k] -> (raiz 0-11, calidad) | None (sin acorde)

El modelo espera la mezcla completa a 22050 Hz. Vocabulario grande: 12 raíces x 14 calidades + X + N.
"""
import os
import sys

import numpy as np

AQUI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btc")
SR = 22050
HOP = 2048
TROZO = 10.0          # el modelo se entrenó con ventanas de 10 s = 108 cuadros
PASOS = 108
DT = TROZO / PASOS

# calidades del modelo -> sufijo de cifrado
CALIDADES_BTC = ["m", "", "dim", "aug", "m6", "6", "m7", "mMaj7", "maj7", "7", "dim7", "m7b5", "sus2", "sus4"]
ETIQUETAS = [(i // 14, CALIDADES_BTC[i % 14]) for i in range(168)] + [None, None]   # 168 = X, 169 = N

CONFIG = dict(feature_size=144, timestep=PASOS, num_chords=170, input_dropout=0.2, layer_dropout=0.2,
              attention_dropout=0.2, relu_dropout=0.2, num_layers=8, num_heads=4, hidden_size=128,
              total_key_depth=128, total_value_depth=128, filter_size=128, loss="ce", probs_out=True)

# Pesos: "btc_chordmini.pt" = el mismo BTC re-entrenado por ChordMini (Phan et al., arXiv 2602.19778,
# github.com/ptnghia-j/ChordMini, MIT) con 1.072 h de audio pseudo-etiquetado: en su evaluación le saca a
# BTC +1,3 puntos en mayores/menores y +2,9 en séptimas. "btc_grande.pt" = el BTC original.
PESOS = os.environ.get("PESOS_BTC", "btc_chordmini.pt")
_modelos = {}


def _cargar(pesos=None):
    pesos = pesos or PESOS
    _modelo = _modelos.get(pesos)
    if _modelo is None:
        import torch
        if AQUI not in sys.path:
            sys.path.insert(0, AQUI)
        from btc_model import BTC_model
        # los .pt son los checkpoints originales re-guardados solo con tensores (pesos + media y desvío
        # de la normalización) para poder cargarlos con weights_only=True
        ck = torch.load(os.path.join(AQUI, pesos), map_location="cpu", weights_only=True)
        m = BTC_model(config=CONFIG)
        m.load_state_dict(ck["model"])
        m.eval()
        _modelo = _modelos[pesos] = (m, float(ck["mean"]), float(ck["std"]))
    return _modelo


def _cqt(y, afin):
    import librosa
    n = int(SR * TROZO)
    partes = []
    for i in range(0, len(y), n):                 # por trozos de 10 s, igual que en el entrenamiento
        trozo = y[i:i + n]
        if len(trozo) < HOP * 2:
            break
        c = librosa.cqt(trozo, sr=SR, n_bins=144, bins_per_octave=24, hop_length=HOP, tuning=afin)
        partes.append(c[:, :PASOS] if len(trozo) == n else c)
    return np.log(np.abs(np.concatenate(partes, axis=1)) + 1e-6).T


def probabilidades(y, sr=SR, afin=0.0, pesos=None):
    """y: mezcla mono. afin: desafinación en fracción de semitono (librosa.estimate_tuning).
    Devuelve (prob[cuadros, 170], segundos por cuadro). Promedia ventanas solapadas a la mitad.
    pesos "a.pt+b.pt" promedia las probabilidades de los dos modelos."""
    import librosa
    if sr != SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=SR)
    pesos = pesos or PESOS
    if "+" in pesos:
        ps = [_probabilidades(y, afin, p) for p in pesos.split("+")]
        n = min(len(p) for p in ps)
        return sum(p[:n] for p in ps) / len(ps), DT
    return _probabilidades(y, afin, pesos), DT


def _probabilidades(y, afin, pesos):
    import torch
    modelo, media, desvio = _cargar(pesos)
    x = (_cqt(y, afin) - media) / desvio
    n = x.shape[0]
    relleno = (-n) % PASOS
    x = np.pad(x, ((0, relleno + PASOS // 2), (0, 0)))
    suma = np.zeros((x.shape[0], 170))
    veces = np.zeros((x.shape[0], 1))
    with torch.no_grad():
        for a in range(0, x.shape[0] - PASOS + 1, PASOS // 2):
            t = torch.tensor(x[a:a + PASOS], dtype=torch.float32).unsqueeze(0)
            oculto, _ = modelo.self_attn_layers(t)
            p = torch.softmax(modelo.output_layer(oculto), -1)[0].numpy()
            suma[a:a + PASOS] += p
            veces[a:a + PASOS] += 1
    return (suma / np.maximum(veces, 1))[:n]
