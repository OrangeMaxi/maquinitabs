"""
Saca acordes, tempo, tonalidad y estructura de un tema y arma una hoja (PDF + TXT + JSON).

Uso:
  python sacar_acordes.py "<url de YouTube o archivo de audio>" --titulo "De caza" --artista "Marilina Bertoldi"
         [--destino "E:\\Música\\banda sin nombre"] [--sin-stems] [--compas 4] [--rehacer]

Crea:
  <destino>\\<Titulo> - <Artista>\\
      audio\\<Titulo>.wav + bass/drums/other/vocals.wav (demucs)
      analisis\\acordes.json       todo el análisis (beats, acordes por beat, compases, secciones)
      analisis\\acordes_beats.csv  acorde por beat con tiempo (para revisar)
      <Titulo> - <Artista>.txt     hoja en texto (editable)
      <Titulo> - <Artista>.pdf     hoja de acordes
"""
import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys

import numpy as np

NOTAS_SOST = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTAS_BEMOL = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

# calidad -> (intervalos, pesos, penalización a priori)
CALIDADES = {
    "":     ([0, 4, 7], [1.0, 0.9, 0.8], 0.00),
    "m":    ([0, 3, 7], [1.0, 0.9, 0.8], 0.00),
    "7":    ([0, 4, 7, 10], [1.0, 0.8, 0.7, 0.6], 0.05),
    "maj7": ([0, 4, 7, 11], [1.0, 0.8, 0.7, 0.6], 0.05),
    "m7":   ([0, 3, 7, 10], [1.0, 0.8, 0.7, 0.6], 0.05),
    "sus4": ([0, 5, 7], [1.0, 0.9, 0.8], 0.05),
    "dim":  ([0, 3, 6], [1.0, 0.9, 0.8], 0.06),
}

# calidades extra que solo da el modelo entrenado (BTC): intervalos, para nombrar inversiones
INTERVALOS_EXTRA = {"aug": [0, 4, 8], "m6": [0, 3, 7, 9], "6": [0, 4, 7, 9], "mMaj7": [0, 3, 7, 11],
                    "dim7": [0, 3, 6, 9], "m7b5": [0, 3, 6, 10], "sus2": [0, 2, 7]}


def intervalos(calidad):
    return CALIDADES[calidad][0] if calidad in CALIDADES else INTERVALOS_EXTRA[calidad]


UMBRAL_CORTE = 0.60  # cuánto tiene que cambiar timbre/energía/voz para partir una sección larga

PERFIL_MAYOR =np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
PERFIL_MENOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
# tonalidades que se escriben con bemoles
BEMOLES_MAYOR = {5, 10, 3, 8, 1, 6}      # F Bb Eb Ab Db Gb
BEMOLES_MENOR = {2, 7, 0, 5, 10, 3}      # Dm Gm Cm Fm Bbm Ebm


def log(*a):
    print(*a, flush=True)


def limpiar(nombre):
    return re.sub(r'[<>:"/\\|?*]', "", nombre).strip()


# ---------------------------------------------------------------- descarga + stems
def preparar_audio(fuente, carpeta_audio, titulo, usar_stems, rehacer):
    os.makedirs(carpeta_audio, exist_ok=True)
    wav = os.path.join(carpeta_audio, f"{titulo}.wav")
    if os.path.exists(fuente):
        if os.path.abspath(fuente) != os.path.abspath(wav) and (rehacer or not os.path.exists(wav)):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", fuente, wav], check=True)
    elif rehacer or not os.path.exists(wav):
        log("Descargando audio…")
        subprocess.run(["yt-dlp", "-q", "-x", "--audio-format", "wav",
                        "-o", os.path.join(carpeta_audio, f"{titulo}.%(ext)s"), fuente], check=True)
    stems = {}
    if usar_stems:
        nombres = ["bass", "drums", "other", "vocals"]
        rutas = {n: os.path.join(carpeta_audio, f"{n}.wav") for n in nombres}
        if rehacer or not all(os.path.exists(p) for p in rutas.values()):
            log("Separando pistas con demucs (1–3 min)…")
            tmp = os.path.join(carpeta_audio, "_sep")
            subprocess.run([sys.executable, "-m", "demucs", "-n", "htdemucs", "-o", tmp, wav], check=True)
            src = os.path.join(tmp, "htdemucs", titulo)
            for n in nombres:
                shutil.move(os.path.join(src, f"{n}.wav"), rutas[n])
            shutil.rmtree(tmp, ignore_errors=True)
        stems = rutas
    return wav, stems


# ---------------------------------------------------------------- análisis
def plantillas():
    nombres, T, pen, raices, calidades = [], [], [], [], []
    for r in range(12):
        for q, (ints, pesos, p) in CALIDADES.items():
            v = np.zeros(12)
            for i, w in zip(ints, pesos):
                v[(r + i) % 12] = w
            T.append(v / np.linalg.norm(v))
            nombres.append((r, q))
            pen.append(p)
            raices.append(r)
            calidades.append(q)
    return nombres, np.array(T), np.array(pen), np.array(raices)


def estimar_tonalidad(chroma_total):
    c = chroma_total / (chroma_total.sum() + 1e-9)
    mejor = None
    for modo, perfil in (("mayor", PERFIL_MAYOR), ("menor", PERFIL_MENOR)):
        for r in range(12):
            corr = np.corrcoef(c, np.roll(perfil, r))[0, 1]
            if mejor is None or corr > mejor[0]:
                mejor = (corr, r, modo)
    _, r, modo = mejor
    usa_bemol = r in (BEMOLES_MAYOR if modo == "mayor" else BEMOLES_MENOR)
    return r, modo, usa_bemol


def nombre_acorde(raiz, calidad, bajo, bemol):
    notas = NOTAS_BEMOL if bemol else NOTAS_SOST
    s = notas[raiz] + calidad
    if bajo is not None and bajo != raiz:
        s += "/" + notas[bajo]
    return s


def extender_pulsos(beats, env, rms):
    """Continúa la grilla de pulsos hacia atrás (hasta donde empieza a sonar el tema) y hacia adelante
    (hasta donde deja de sonar), al tempo de los pulsos vecinos y ajustando cada uno al ataque más
    cercano de la mezcla. Los pulsos que ya había no se tocan."""
    if len(beats) < 8:
        return beats
    n = min(len(env), len(rms))
    umbral = 0.03 * np.percentile(rms[:n], 95)
    fuerte = np.percentile(env[:n], 75)

    def tramo(desde, periodo, sentido):
        tol = max(1, int(round(0.12 * periodo)))
        nuevos, f = [], desde + sentido * periodo
        while 0 <= f < n:
            resto = rms[: int(f) + tol] if sentido < 0 else rms[max(0, int(f) - tol): n]
            if not len(resto) or resto.max() < umbral:
                break  # de acá en adelante (o hacia atrás) es silencio
            a, b = max(0, int(round(f)) - tol), min(n, int(round(f)) + tol + 1)
            k = a + int(np.argmax(env[a:b])) if b > a else int(round(f))
            f = float(k) if env[min(k, n - 1)] >= fuerte else f
            nuevos.append(int(round(f)))
            f += sentido * periodo
        return nuevos

    antes = tramo(float(beats[0]), float(np.median(np.diff(beats[:9]))), -1)[::-1]
    despues = tramo(float(beats[-1]), float(np.median(np.diff(beats[-9:]))), +1)
    todos = np.array(antes + list(beats) + despues, dtype=int)
    return np.unique(todos[(todos >= 0) & (todos < n)])


def pulsos_beat_this(y, sr):
    """Pulsos y "unos" con Beat This! (Foscarin, Schlüter y Widmer, ISMIR 2024 — github.com/CPJKU/beat_this,
    MIT). Se corren dos modelos (final0 y small0, en _herramientas\\modelos\\beat_this).
    Devuelve None si no está instalado o si ninguno arma compases parejos de 3 o 4 pulsos (pasa con folklore
    en 6/8 y con rubatos: ahí conviene el método anterior). Si no:
      {"pulsos": tiempos, "compas": 3|4, "unos": [tiempos de los "1" de cada modelo]}"""
    carpeta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modelos", "beat_this")
    if not os.path.isdir(carpeta) and os.environ.get("TORCH_HOME"):     # en Docker los modelos van en TORCH_HOME
        carpeta = os.path.join(os.environ["TORCH_HOME"], "beat_this")
    try:
        from beat_this.inference import Audio2Beats
    except ImportError:
        return None
    res = []
    for nombre in ("final0", "small0"):
        ruta = os.path.join(carpeta, nombre + ".ckpt")
        try:
            b, d = Audio2Beats(checkpoint_path=ruta if os.path.exists(ruta) else nombre, device="cpu", dbn=False)(y, sr)
        except Exception as e:  # noqa: BLE001  (sin pesos y sin red, etc.)
            log(f"Beat This! ({nombre}) no disponible: {e}")
            continue
        b, d = np.asarray(b, dtype=float), np.asarray(d, dtype=float)
        if len(b) < 16 or len(d) < 4:
            continue
        largos = np.diff(np.searchsorted(b, d - 0.03))
        vals, cu = np.unique(largos, return_counts=True)
        res.append({"pulsos": b, "unos": d, "compas": int(vals[np.argmax(cu)]), "parejo": float(cu.max() / len(largos))})
    buenos = [r for r in res if r["compas"] in (3, 4) and r["parejo"] >= 0.6]
    if not buenos:
        return None
    mejor = max(buenos, key=lambda r: r["parejo"])
    log(f"Beat This!: compás de {mejor['compas']} pulsos en el {100 * mejor['parejo']:.0f}% de los compases")
    return {"pulsos": suavizar_pulsos(mejor["pulsos"]), "compas": mejor["compas"], "unos": [r["unos"] for r in res]}


def suavizar_pulsos(b, vecinos=4, tope=0.03):
    """Beat This! da los pulsos en cuadros de 20 ms: a 170 BPM eso es un 6 % de pulso y el metrónomo suena
    renguito. Cada pulso pasa a la recta que mejor ajusta a sus vecinos (±4 pulsos), salvo que eso lo mueva
    más de 30 ms (ahí hay un cambio de tempo o un rubato real, y se respeta)."""
    b = np.asarray(b, dtype=float)
    out = b.copy()
    for i in range(len(b)):
        a, z = max(0, i - vecinos), min(len(b), i + vecinos + 1)
        if z - a < 5:
            continue
        k = np.arange(a, z)
        m, c = np.polyfit(k, b[a:z], 1)
        if abs(m * i + c - b[i]) < tope:
            out[i] = m * i + c
    return out


def ritmo_en(y, sr, t_beats):
    """Cuánto se repite el patrón rítmico cada 3 y cada 4 pulsos: autocorrelación de los ataques (por
    bandas, 4 casillas por pulso) a 3 y 6 pulsos de distancia, y a 4 y 8."""
    import librosa

    if len(t_beats) < 24:
        return 0.0, 0.0
    env = librosa.onset.onset_strength_multi(y=y, sr=sr, hop_length=256, channels=[0, 6, 24, 64, 128])
    bordes = np.concatenate([np.linspace(t_beats[i], t_beats[i + 1], 5)[:4] for i in range(len(t_beats) - 1)])
    fr = np.clip(librosa.time_to_frames(bordes, sr=sr, hop_length=256), 0, env.shape[1] - 1)
    F = np.array([[env[b, max(a - 2, 0): a + 3].max() for a in fr] for b in range(env.shape[0])])
    F = F.reshape(F.shape[0], -1, 4).transpose(1, 0, 2).reshape(len(t_beats) - 1, -1)   # pulsos x (bandas*4)
    F = F - F.mean(axis=0)
    ac = lambda L: float((F[:-L] * F[L:]).sum() / (np.linalg.norm(F[:-L]) * np.linalg.norm(F[L:]) + 1e-9))
    return ac(3) + ac(6), ac(4) + ac(8)


def analizar(wav, stems, compas, con_bajo=False, metricas=None, modelo=None, pulsos=None):
    """modelo="btc": los acordes salen del modelo entrenado BTC (sobre la mezcla) en vez de las plantillas."""
    import librosa

    sr = 22050
    hop = 512
    log("Cargando audio…")
    mezcla, _ = librosa.load(wav, sr=sr, mono=True)
    dur = len(mezcla) / sr

    def cargar(n):
        y, _ = librosa.load(stems[n], sr=sr, mono=True)
        return y[: len(mezcla)] if len(y) >= len(mezcla) else np.pad(y, (0, len(mezcla) - len(y)))

    if stems:
        bajo, bat, otros, voz = (cargar(n) for n in ("bass", "drums", "other", "vocals"))
        armonia = otros + bajo
    else:
        armonia, bat = librosa.effects.hpss(mezcla)
        bajo, otros, voz = armonia, armonia, None

    # ---- tempo y beats (desde la batería si está)
    log("Tempo y pulsos…")
    env = librosa.onset.onset_strength(y=bat if stems else mezcla, sr=sr, hop_length=hop)
    tempo, beats = librosa.beat.beat_track(onset_envelope=env, sr=sr, hop_length=hop, units="frames")
    tempo = float(np.atleast_1d(tempo)[0])
    bthis = pulsos_beat_this(mezcla, sr) if pulsos == "beat_this" else None
    if bthis:      # pulsos del modelo entrenado en vez de los de librosa
        beats = np.unique(librosa.time_to_frames(bthis["pulsos"], sr=sr, hop_length=hop))
        tempo = float(60.0 / np.median(np.diff(bthis["pulsos"])))
    elif tempo < 70:  # evitar mitad de tempo
        # (comparar con el tempo de la mezcla para detectar la mitad no sirve: en Can't Buy Me Love acierta,
        # pero en Imagine las corcheas del piano dan el doble. La mitad de tempo la resuelve Beat This!)
        tempo2, beats2 = librosa.beat.beat_track(onset_envelope=env, sr=sr, hop_length=hop, start_bpm=tempo * 2)
        if float(np.atleast_1d(tempo2)[0]) > 90:
            tempo, beats = float(np.atleast_1d(tempo2)[0]), beats2
    # la batería puede entrar tarde (intro de piano/guitarra) o cortar antes del final: ahí no hay
    # pulsos y esos compases faltarían en la hoja. Se extiende la grilla con los ataques de la mezcla.
    if stems:
        beats = extender_pulsos(np.asarray(beats), librosa.onset.onset_strength(y=mezcla, sr=sr, hop_length=hop),
                                librosa.feature.rms(y=mezcla, hop_length=hop)[0])
    def exactos(t):
        # los cuadros de librosa son de 23 ms: a 170 BPM eso desparejaría el metrónomo. Donde el pulso es
        # de Beat This! se usa su tiempo exacto (los agregados por extender_pulsos quedan como están).
        if not bthis or len(bthis["pulsos"]) < 2:
            return t
        bp = np.asarray(bthis["pulsos"], dtype=float)
        j = np.clip(np.searchsorted(bp, t), 1, len(bp) - 1)
        cerca = np.where(np.abs(bp[j - 1] - t) < np.abs(bp[j] - t), bp[j - 1], bp[j])
        return np.where(np.abs(cerca - t) < 0.03, cerca, t)

    t_beats = exactos(librosa.frames_to_time(beats, sr=sr, hop_length=hop))
    if len(t_beats) > 2:
        tempo = float(60.0 / np.median(np.diff(t_beats)))

    # ---- afinación y cromas
    log("Cromagrama…")
    afin = float(librosa.estimate_tuning(y=otros, sr=sr))
    # croma de acordes SIN el bajo: el bajo domina y se filtra a semitonos vecinos (falsos maj7)
    chroma = librosa.feature.chroma_cqt(y=otros, sr=sr, hop_length=hop, tuning=afin, bins_per_octave=36)
    chroma_bajo = librosa.feature.chroma_cqt(y=bajo, sr=sr, hop_length=hop, tuning=afin,
                                             fmin=librosa.note_to_hz("E1"), n_octaves=3, bins_per_octave=36)
    rms_arm = librosa.feature.rms(y=otros, hop_length=hop)[0]   # N.C. = no suenan sintes/guitarras

    bounds = np.concatenate([[0], beats, [chroma.shape[1]]])
    bounds = np.unique(np.clip(bounds, 0, chroma.shape[1]))
    cb = librosa.util.sync(chroma, bounds, aggregate=np.median)
    cbb = librosa.util.sync(chroma_bajo, bounds, aggregate=np.median)
    eb = librosa.util.sync(rms_arm[None, :], bounds, aggregate=np.mean)[0]
    t_ini = exactos(librosa.frames_to_time(bounds[:-1], sr=sr, hop_length=hop))
    n = cb.shape[1]

    # ---- tonalidad
    k_raiz, k_modo, bemol = estimar_tonalidad(chroma.sum(axis=1))

    # ---- acordes: plantillas + bajo + Viterbi
    log("Acordes…")
    nombres, T, pen, raices = plantillas()
    cbn = cb / (np.linalg.norm(cb, axis=0, keepdims=True) + 1e-9)
    bajo_n = cbb / (cbb.max(axis=0, keepdims=True) + 1e-9)
    # SOLO armonía de sintes/guitarras (stem other): el bajo no vota en el acorde (pedido de Maxi)
    score = T @ cbn - pen[:, None]
    # sin acorde: energía armónica baja
    umbral = 0.08 * np.percentile(eb, 95)
    s_nc = np.where(eb < umbral, 1.0, 0.0)
    score = np.vstack([score, s_nc[None, :]])
    S = len(nombres) + 1
    prob = np.exp(18 * (score - score.max(axis=0, keepdims=True)))
    prob /= prob.sum(axis=0, keepdims=True)
    trans = librosa.sequence.transition_loop(S, 0.80)
    ruta = librosa.sequence.viterbi(prob, trans)
    if modelo == "btc":
        import btc_acordes
        log("Acordes (modelo BTC)…")
        pm, dt = btc_acordes.probabilidades(mezcla, sr, afin)
        bt = librosa.frames_to_time(bounds, sr=sr, hop_length=hop)
        pb = np.full((len(btc_acordes.ETIQUETAS), n), 1e-9)
        for i in range(n):
            a = min(int(bt[i] / dt), len(pm) - 1)
            b = max(min(int(round(bt[i + 1] / dt)), len(pm)), a + 1)
            pb[:, i] += pm[a:b].mean(axis=0)
        pb[-2] = 1e-9                          # "X" (acorde fuera del vocabulario): gana el más parecido
        # sin acorde solo si el modelo lo dice o si no suena nada (silencio de toda la mezcla)
        em = librosa.util.sync(librosa.feature.rms(y=mezcla, hop_length=hop)[0][None, :chroma.shape[1]],
                               bounds, aggregate=np.mean)[0]
        callado = em < 0.03 * np.percentile(em, 95)
        pb[-1, eb >= umbral] *= 0.15           # si las guitarras/teclados suenan, cuesta más decir N.C.
        pb[:, callado] = 1e-9
        pb[-1, callado] = 1.0
        pb /= pb.sum(axis=0, keepdims=True)
        # suavizado leve: quedarse en el acorde vale 4 veces más que cambiar a otro cualquiera. (Con
        # transition_loop cada cambio costaba ~1/170 y se comía los acordes de 1-3 pulsos de los riffs.)
        tr = np.ones((pb.shape[0], pb.shape[0])) + 3.0 * np.eye(pb.shape[0])
        ruta_m = librosa.sequence.viterbi(pb, tr / tr.sum(axis=1, keepdims=True))
        nombres = [e for e in btc_acordes.ETIQUETAS[:-2]] + [None]
        S = len(nombres)
        ruta = np.minimum(ruta_m, S - 1)

    acordes_beat = []
    for i, s in enumerate(ruta):
        if s == S - 1:
            acordes_beat.append({"raiz": None, "calidad": None, "bajo": None, "nombre": "N.C."})
            continue
        r, q = nombres[s]
        b = int(np.argmax(cbb[:, i]))
        ints = [(r + x) % 12 for x in intervalos(q)]
        # inversión solo si el bajo está claramente en otra nota del acorde
        bajo_nota = b if (con_bajo and b in ints and b != r and bajo_n[b, i] > 0.95 and bajo_n[r, i] < 0.3) else None
        acordes_beat.append({"raiz": r, "calidad": q, "bajo": bajo_nota,
                             "nombre": nombre_acorde(r, q, bajo_nota, bemol)})
    # ruido de 1 beat aislado -> vecino
    for i in range(1, n - 1):
        a, b, c = acordes_beat[i - 1]["nombre"], acordes_beat[i]["nombre"], acordes_beat[i + 1]["nombre"]
        if b != a and b != c and a == c:
            acordes_beat[i] = dict(acordes_beat[i - 1])

    # primer "beat" es el tramo antes del primer pulso; lo descartamos para la grilla
    off = 1 if bounds[0] == 0 and len(beats) and beats[0] > 0 else 0
    ab = acordes_beat[off:]
    tb = t_ini[off:]

    # ---- fase del compás: el 1 donde más cambian los acordes + golpe de bajo
    env_b = librosa.onset.onset_strength(y=bajo, sr=sr, hop_length=hop)
    fuerza = env_b[np.clip(beats, 0, len(env_b) - 1)] if len(beats) else np.zeros(len(ab))
    cambios = np.array([1.0 if i > 0 and ab[i]["nombre"] != ab[i - 1]["nombre"] else 0.0 for i in range(len(ab))])
    fz = fuerza[: len(ab)] / (fuerza.max() + 1e-9)
    # programación dinámica sobre los "1": compases de `compas` pulsos, con algún compás
    # irregular permitido (penalizado) por si el beat tracking pierde/gana un pulso o hay un 2/4.
    nab = len(ab)
    peso = cambios * 1.0 + fz * 0.3
    if bthis:
        # cada modelo de Beat This! que marca un "1" en ese pulso suma más que un cambio de acorde; la
        # programación dinámica de abajo empareja lo que quede irregular
        for unos_bt in bthis["unos"]:
            for i in np.flatnonzero(np.min(np.abs(np.asarray(tb)[:, None] - unos_bt[None, :]), axis=1) < 0.07):
                peso[i] += 1.2
    # medio compás de más/de menos (2/4, 6/4) es un recurso real de arreglo; uno de 3 o 5 pulsos casi
    # siempre es un acorde detectado un pulso tarde/temprano (eso ya lo cubre la anticipación).
    # compás forzado por sección (estructura.txt "[7/4]"): ahí solo compases de ese largo y el 1
    # cae en el primer pulso de la sección
    # forzado[i] = largo del compás que empieza en el pulso i; en_forzada = pulsos de una zona forzada
    forzado = [None] * nab
    en_forzada = [False] * nab
    peso = peso.copy()
    for t0, t1, seq in (metricas or []):
        i0 = int(np.argmin(np.abs(tb - t0)))
        fin = next((i for i in range(nab) if tb[i] >= t1 - 0.25), nab)
        if fin <= i0:
            continue
        peso[i0] += 50.0
        for i in range(i0, fin):
            en_forzada[i] = True
        i, k = i0, 0
        while i < fin:
            forzado[i] = seq[k % len(seq)]
            i += seq[k % len(seq)]
            k += 1
    def barras(compas):
        """Los "1" del tema para compases de `compas` pulsos y qué tan bien calzan (puntaje)."""
        largos = {compas: 0.0}
        for L, p in ((2, -1.5), (3, -3.5), (5, -3.5), (6, -1.5)):
            if L != compas:
                largos[L] = p
        mejor = np.full(nab + 1, -np.inf)
        previo = np.full(nab + 1, -1)
        for d in range(min(compas, nab)):
            mejor[d] = peso[d]
        for d in range(nab):
            if mejor[d] == -np.inf:
                continue
            if en_forzada[d] and not forzado[d]:
                continue  # dentro de una zona forzada solo valen los "1" de la secuencia
            opciones = {forzado[d]: 0.0} if forzado[d] else largos
            for L, pen_l in opciones.items():
                if d + L < nab and en_forzada[d + L] and not forzado[d + L]:
                    continue
                e = d + L
                if e < nab:
                    v = mejor[d] + pen_l + peso[e]
                    if v > mejor[e]:
                        mejor[e], previo[e] = v, d
                elif e >= nab and mejor[d] + pen_l * (L != compas) > mejor[nab]:
                    mejor[nab], previo[nab] = mejor[d], d
        unos = []
        k = previo[nab]
        while k >= 0:
            unos.append(int(k))
            k = previo[k]
        unos = unos[::-1]
        # puntaje comparable entre compases: lo que suman los "1" por encima de caer en un pulso cualquiera,
        # menos lo que costaron los compases irregulares
        lims_ = unos + [nab]
        pts = sum(peso[u] - medio for u in unos) + sum(largos.get(b_ - a_, 0.0) for a_, b_ in zip(lims_[:-2], lims_[1:-1]))
        return unos, float(pts)

    medio = float(np.mean(peso[~np.array(en_forzada)])) if nab and not all(en_forzada) else 0.0
    if not compas and bthis:
        compas = bthis["compas"]
        log(f"Compás automático: {compas}/4 (Beat This!)")
    if not compas:
        # compás automático (0): es de 3 solo si lo dicen las dos pistas que hay: los compases de 3 calzan
        # mejor con los cambios de acorde Y el patrón rítmico se repite más cada 3 pulsos que cada 4.
        # (Cada una por separado se equivoca: temas con un solo acorde, ritmos 3+3+2…)
        p3, p4 = barras(3)[1], barras(4)[1]
        r3, r4 = ritmo_en(mezcla, sr, tb)
        compas = 3 if p3 > p4 and r3 > r4 else 4
        log(f"Compás automático: {compas}/4 (acordes en 3: {p3:.1f}, en 4: {p4:.1f}; ritmo en 3: {r3:.2f}, en 4: {r4:.2f})")
    unos, _ = barras(compas)
    fase = unos[0] if unos else 0

    # ---- anticipaciones: acorde que entra 1 pulso antes del 1 -> va al compás siguiente
    nombres_g = [b["nombre"] for b in ab]
    for d in unos[1:]:
        i = d - 1
        if i >= 1 and nombres_g[i] != nombres_g[i - 1] and nombres_g[i] == nombres_g[d]:
            nombres_g[i] = nombres_g[i - 1]
    # ...y el caso inverso: acorde que se "queda" 1 pulso después del 1 -> el compás nuevo
    # empieza con el acorde nuevo (detección un pulso tarde)
    for d in unos[1:]:
        if d + 2 < nab and nombres_g[d] == nombres_g[d - 1] and nombres_g[d] != nombres_g[d + 1] \
                and nombres_g[d + 1] == nombres_g[d + 2]:
            nombres_g[d] = nombres_g[d + 1]

    # ---- compases
    compases = []
    if fase:
        compases.append({"ini": 0, "beats": list(range(0, fase)), "anacrusa": True})
    lims = unos + [nab]
    for a_, b_ in zip(lims[:-1], lims[1:]):
        compases.append({"ini": a_, "beats": list(range(a_, b_)), "anacrusa": False})
    # marca de compás: se escribe cuando cambia el largo respecto del compás anterior
    # (o del 4/4 de base), como en una partitura: "(7/4) Emaj7 … (4/4) C#m"
    actual = compas
    for k, c in enumerate(compases):
        largo = len(c["beats"])
        ultimo = k == len(compases) - 1
        c["irregular"] = False
        if c["anacrusa"] or (ultimo and largo < actual):
            continue
        if largo != actual:
            c["irregular"] = True
            actual = largo
    for c in compases:
        nombres_c = [nombres_g[i] for i in c["beats"]]
        runs = []
        for x in nombres_c:
            if runs and runs[-1][0] == x:
                runs[-1][1] += 1
            else:
                runs.append([x, 1])
        c["acordes"] = [r[0] for r in runs]
        c["runs"] = [[r[0], r[1]] for r in runs]   # (acorde, pulsos) para la app web
        if c["irregular"]:
            c["acordes"][0] = f"({len(c['beats'])}/4) " + c["acordes"][0]
        c["tiempo"] = float(tb[c["beats"][0]]) if c["beats"] else 0.0

    # ---- features por compás para estructura
    log("Estructura…")
    mfcc = librosa.feature.mfcc(y=mezcla, sr=sr, hop_length=hop, n_mfcc=13)
    mfcc_b = librosa.util.sync(mfcc, bounds, aggregate=np.mean)[:, off:]
    cb_g = cbn[:, off:]
    rms_stems = []
    for y in ([bajo, bat, otros, voz] if stems else [mezcla]):
        r = librosa.feature.rms(y=y, hop_length=hop)[0]
        rms_stems.append(librosa.util.sync(r[None, :], bounds, aggregate=np.mean)[0][off:])
    rms_stems = np.array(rms_stems)

    feats, voz_c, energia_c = [], [], []
    voz_ref = np.percentile(rms_stems[3], 90) if stems else 1
    for c in compases:
        idx = c["beats"]
        f_ch = cb_g[:, idx].mean(axis=1)
        f_mf = mfcc_b[:, idx].mean(axis=1)
        f_rm = np.log1p(100 * rms_stems[:, idx].mean(axis=1))
        feats.append(np.concatenate([f_ch / (np.linalg.norm(f_ch) + 1e-9) * 2.0, f_mf, f_rm]))
        voz_c.append(float(rms_stems[3][idx].mean() / (voz_ref + 1e-9)) if stems else 1.0)
        energia_c.append(float(rms_stems[:, idx].mean(axis=1).sum()))
    F = np.array(feats)
    F = (F - F.mean(axis=0)) / (F.std(axis=0) + 1e-9)
    secciones = segmentar(F, compases, voz_c, energia_c)

    return {
        "duracion": dur,
        "tempo": round(tempo, 1),
        "compas": f"{compas}/4",
        "pulsos_compas": compas,
        "afinacion_cents": round(afin * 100),
        "tonalidad": nombre_acorde(k_raiz, "" if k_modo == "mayor" else "m", None, bemol),
        "tonalidad_modo": k_modo,
        "beats": [{"t": float(tb[i]), **ab[i]} for i in range(len(ab))],
        "compases": [{"n": j + 1, "t": c["tiempo"], "acordes": c["acordes"], "anacrusa": c["anacrusa"],
                      "voz": round(voz_c[j], 2), "pulsos": len(c["beats"]), "runs": c["runs"],
                      "beat_ini": c["beats"][0] if c["beats"] else 0} for j, c in enumerate(compases)],
        "secciones": secciones,
    }


def segmentar(F, compases, voz_c, energia_c, umbral_voz=0.2, min_sec=8):
    """1) cortar por presencia de voz, 2) partir tramos largos donde cambia armonía/intensidad
    (en múltiplos de 4 compases), 3) agrupar partes parecidas, 4) nombrar."""
    from scipy.ndimage import median_filter
    from scipy.cluster.hierarchy import linkage, fcluster

    nb = len(F)
    voz = np.array(voz_c)
    hay_voz = median_filter((voz > umbral_voz).astype(int), size=3, mode="nearest").astype(bool)

    # 1) tramos con/sin voz; los de menos de 4 compases se pegan al anterior
    tramos = []
    for i in range(nb):
        if tramos and tramos[-1][2] == hay_voz[i]:
            tramos[-1][1] = i + 1
        else:
            tramos.append([i, i + 1, bool(hay_voz[i])])
    cambio = True
    while cambio and len(tramos) > 1:
        cambio = False
        for k, t in enumerate(tramos):
            if t[1] - t[0] < 4:
                if k == 0:
                    tramos[1][0] = t[0]
                else:
                    tramos[k - 1][1] = t[1]
                tramos.pop(k)
                # unir vecinos del mismo tipo
                for j in range(len(tramos) - 1, 0, -1):
                    if tramos[j][2] == tramos[j - 1][2]:
                        tramos[j - 1][1] = tramos[j][1]
                        tramos.pop(j)
                cambio = True
                break

    # 2) partir tramos largos: punto (múltiplo de 4 desde el inicio) donde más difieren los lados
    Fx = np.column_stack([F, 3 * (voz - voz.mean()) / (voz.std() + 1e-9)])
    # para CORTAR solo timbre + energía + voz (no croma: un cambio de acorde no es una sección nueva)
    Fs = Fx[:, 12:]

    def partir(a, b):
        if b - a < 2 * min_sec:
            return [(a, b)]
        mejor, punto = 0.0, None
        for p in range(a + min_sec, b - min_sec + 1, 4):
            w = min(8, p - a, b - p)
            izq, der = Fs[p - w:p].mean(axis=0), Fs[p:p + w].mean(axis=0)
            d = np.linalg.norm(izq - der) / np.sqrt(Fs.shape[1])
            if d > mejor:
                mejor, punto = d, p
        if os.environ.get("ACORDES_DEBUG"):
            log(f"  corte {a}-{b}: mejor punto {punto} fuerza {mejor:.2f}")
        if punto is None or mejor < UMBRAL_CORTE:
            return [(a, b)]
        return partir(a, punto) + partir(punto, b)

    segs = []
    for a, b, _ in tramos:
        segs += partir(a, b)

    # 3) agrupar
    medias = np.array([Fx[a:b].mean(axis=0) for a, b in segs])
    if len(segs) > 1:
        Z = linkage(medias, method="average", metric="euclidean")
        etiquetas = fcluster(Z, t=0.55 * np.sqrt(Fx.shape[1]), criterion="distance")
    else:
        etiquetas = np.array([1])
    # letras en orden de aparición
    orden = {}
    for e in etiquetas:
        orden.setdefault(int(e), len(orden) + 1)

    info = []
    for (a, b), e in zip(segs, etiquetas):
        info.append({"ini": a, "fin": b, "grupo": orden[int(e)],
                     "voz": float(np.mean(voz[a:b])), "energia": float(np.mean(energia_c[a:b]))})

    # 4) nombres
    vocales = [s for s in info if s["voz"] > umbral_voz]
    grupos_v = {}
    for s in vocales:
        grupos_v.setdefault(s["grupo"], []).append(s)
    coro = None
    # la primera parte cantada casi siempre es verso: su grupo no puede ser el coro (si hay otro)
    if len(grupos_v) > 1 and vocales:
        grupos_v.pop(vocales[0]["grupo"], None)
    if grupos_v:
        # coro: grupo vocal con más voz+energía, preferentemente repetido
        coro = max(grupos_v, key=lambda g: (len(grupos_v[g]) >= 2,
                                            np.mean([s["voz"] + s["energia"] for s in grupos_v[g]])))
    centro = medias.mean(axis=0)
    cont = {}
    for i, s in enumerate(info):
        if s["voz"] <= umbral_voz:
            if i == 0:
                base = "Intro"
            elif i == len(info) - 1:
                base = "Outro"
            else:
                # instrumental con armonía distinta al resto del tema -> puente
                rara = sum(1 for x in info if x["grupo"] == s["grupo"]) == 1 and \
                    np.linalg.norm(medias[i][:12] - centro[:12]) > 0.9 * np.sqrt(12)
                base = "Puente" if rara else "Instrumental"
        elif s["grupo"] == coro:
            base = "Coro"
        elif sum(1 for x in info if x["grupo"] == s["grupo"]) == 1 and i >= len(info) / 2 \
                and i < len(info) - 1:
            base = "Puente"
        elif i == len(info) - 1 and s["fin"] - s["ini"] < 8:
            base = "Outro"
        else:
            base = "Verso"
        s["base"] = base
    # puentes seguidos -> uno solo
    k = 1
    while k < len(info):
        if info[k]["base"] == info[k - 1]["base"] == "Puente":
            info[k - 1]["fin"] = info[k]["fin"]
            info.pop(k)
        else:
            k += 1
    for s in info:
        cont[s["base"]] = cont.get(s["base"], 0) + 1
        s["num"] = cont[s["base"]]
    for s in info:
        tot = sum(1 for x in info if x["base"] == s["base"])
        s["nombre"] = f'{s["base"]} {s["num"]}' if s["base"] == "Verso" and tot > 1 else s["base"]
        s["letra"] = chr(64 + s["grupo"])
        s["t"] = compases[s["ini"]]["tiempo"]
        s["compases"] = s["fin"] - s["ini"]
    return info


# ---------------------------------------------------------------- estructura manual
CABECERA_ESTRUCTURA = """# Estructura del tema: una sección por línea, "m:ss Nombre".
# Generada automáticamente: corregila y volvé a correr el script (se ajusta al compás más cercano).
# Para volver a la detección automática, borrá este archivo.
"""


def leer_estructura(ruta):
    entradas = []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            m = re.match(r"(\d+):(\d{1,2}(?:\.\d+)?)\s+(.+?)\s*(?:\[([^\]]+)\])?$", linea)
            if m:
                entradas.append((int(m.group(1)) * 60 + float(m.group(2)), m.group(3).strip(),
                                 parsear_metrica(m.group(4)) if m.group(4) else None))
    return sorted(entradas)


def parsear_metrica(txt):
    """"7/4" -> [7]; "7/4 x2, 4/4 x4" -> [7, 7, 4, 4, 4, 4] (largos de compás en pulsos).
    La secuencia se repite si la sección es más larga."""
    largos = []
    for item in txt.split(","):
        m = re.match(r"\s*(\d+)/4\s*(?:x\s*(\d+))?\s*$", item)
        if not m:
            raise ValueError(f"Compás no entendido en estructura.txt: '{item}' (usar '7/4' o '7/4 x2, 4/4 x4')")
        largos += [int(m.group(1))] * int(m.group(2) or 1)
    return largos


def metricas_de(entradas, duracion):
    """[(t_ini, t_fin, pulsos)] de las secciones con compás forzado ("[7/4]")."""
    out = []
    for k, (t, _, L) in enumerate(entradas):
        if L:
            t1 = entradas[k + 1][0] if k + 1 < len(entradas) else duracion + 1
            out.append((t, t1, L))
    return out


def escribir_estructura(secciones, ruta):
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(CABECERA_ESTRUCTURA)
        for s in secciones:
            f.write(f"{mmss(s['t'])} {s['nombre']}\n")


def secciones_manual(compases, entradas):
    """Secciones a partir de (tiempo, nombre); cada tiempo va al compás cuyo inicio está más cerca."""
    tiempos = np.array([c["t"] for c in compases])
    inis = []
    for t, nombre, *resto in entradas:
        i = int(np.argmin(np.abs(tiempos - t)))
        if inis and i <= inis[-1][0]:
            continue
        inis.append((i, nombre, resto[0] if resto else None))
    if not inis:
        return []
    if inis[0][0] > 0:  # lo anterior a la primera sección se suma a ella
        inis[0] = (0,) + inis[0][1:]
    def acordes_de(a, b):
        return {x.split(") ")[-1] for c in compases[a:b] for x in c["acordes"]} - {"N.C."}

    # misma letra = mismo nombre base Y acordes parecidos (Puente 2 puede ser otra música)
    previas = []  # (base, acordes, letra)
    out = []
    for k, (i, nombre, metro) in enumerate(inis):
        fin = inis[k + 1][0] if k + 1 < len(inis) else len(compases)
        base = re.sub(r"\s*\d+$", "", nombre)
        ac = acordes_de(i, fin)
        letra = None
        for b_, ac_, l_ in previas:
            if b_ == base and len(ac & ac_) / max(1, len(ac | ac_)) >= 0.4:
                letra = l_
                break
        if letra is None:
            letra = chr(65 + len({l for _, _, l in previas}))
        previas.append((base, ac, letra))
        out.append({"ini": i, "fin": fin, "nombre": nombre, "base": base, "letra": letra,
                    "t": compases[i]["t"], "compases": fin - i, "manual": True,
                    "metro": " y ".join(dict.fromkeys(f"{L}/4" for L in metro)) if metro else None})
    return out


# ---------------------------------------------------------------- salida
def mmss(t):
    return f"{int(t // 60)}:{int(t % 60):02d}"


def filas_seccion(compases_sec, por_fila=4):
    """Filas de hasta 4 compases; donde cambia el compás ("(7/4) …") empieza fila nueva."""
    marca = re.compile(r"^\(\d+/4\)\s*")
    filas, fila, previo = [], [], None
    for c in compases_sec:
        txt = " ".join(c["acordes"])
        cambia_metro = bool(marca.match(txt))
        if fila and (len(fila) == por_fila or cambia_metro):
            filas.append(fila)
            fila, previo = [], None
        limpio = marca.sub("", txt)
        fila.append("%" if previo is not None and limpio == previo and not cambia_metro else txt)
        previo = limpio
    if fila:
        filas.append(fila)
    # comprimir filas repetidas consecutivas -> x2
    out = []
    for f in filas:
        if out and out[-1][0] == f:
            out[-1][1] += 1
        else:
            out.append([f, 1])
    return out


def escribir_txt(res, titulo, artista, ruta):
    L = [f"{titulo} — {artista}",
         f"Tempo: {res['tempo']:.0f} BPM · Compás: {res['compas']} · Tonalidad: {res['tonalidad']}", ""]
    for s in res["secciones"]:
        metro = f", en {s['metro']}" if s.get("metro") else ""
        L.append(f"[{s['nombre']}]  ({mmss(s['t'])}, {s['compases']} compases{metro}, parte {s['letra']})")
        for fila, rep in filas_seccion(res["compases"][s["ini"]:s["fin"]]):
            linea = "| " + " | ".join(f"{c:<10}" for c in fila) + " |"
            L.append(linea + (f"  x{rep}" if rep > 1 else ""))
        L.append("")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def escribir_pdf(res, titulo, artista, ruta):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor

    W, H = A4
    m = 50
    c = canvas.Canvas(ruta, pagesize=A4)
    c.setTitle(f"{titulo} - {artista}")
    gris = HexColor("#777777")

    def cabecera():
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(W / 2, H - 55, titulo)
        c.setFont("Helvetica", 11)
        c.drawCentredString(W / 2, H - 72, artista)
        c.setFont("Helvetica", 9.5)
        c.setFillColor(gris)
        c.drawCentredString(W / 2, H - 90,
                            f"Tempo {res['tempo']:.0f} BPM   ·   Compás {res['compas']}   ·   Tonalidad {res['tonalidad']}"
                            f"   ·   {mmss(res['duracion'])}")
        c.setFillColor(HexColor("#000000"))
        return H - 120

    y = cabecera()
    ancho_celda = (W - 2 * m - 30) / 4
    alto_fila = 22
    for s in res["secciones"]:
        filas = filas_seccion(res["compases"][s["ini"]:s["fin"]])
        necesario = 22 + alto_fila * len(filas) + 10
        if y - necesario < 50:
            c.showPage()
            y = H - 50
        c.setFont("Helvetica-Bold", 11)
        c.drawString(m, y, f"[{s['nombre']}]")
        c.setFont("Helvetica", 8.5)
        c.setFillColor(gris)
        c.drawString(m + c.stringWidth(f"[{s['nombre']}]", "Helvetica-Bold", 11) + 8, y,
                     f"{mmss(s['t'])}  ·  {s['compases']} compases"
                     + (f" en {s['metro']}" if s.get("metro") else "") + f"  ·  {s['letra']}")
        c.setFillColor(HexColor("#000000"))
        y -= 18
        for fila, rep in filas:
            c.setLineWidth(0.6)
            for k in range(5):
                x = m + k * ancho_celda
                if k <= len(fila):
                    c.line(x, y - 6, x, y + 12)
            c.setFont("Helvetica", 11)
            for k, celda in enumerate(fila):
                c.drawString(m + k * ancho_celda + 8, y, celda)
            if rep > 1:
                c.setFont("Helvetica-Bold", 10)
                c.drawString(m + 4 * ancho_celda + 6, y, f"x{rep}")
            y -= alto_fila
        y -= 10
    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillColor(gris)
    c.drawString(m, 30, "Generado automáticamente a partir del audio — revisar de oído.")
    c.save()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fuente", help="URL de YouTube o archivo de audio")
    ap.add_argument("--titulo", required=True)
    ap.add_argument("--artista", required=True)
    ap.add_argument("--destino", default=r"E:\Música\banda sin nombre")
    ap.add_argument("--compas", type=int, default=4, help="tiempos por compás (default 4)")
    ap.add_argument("--sin-stems", action="store_true", help="no separar con demucs (más rápido, menos preciso)")
    ap.add_argument("--con-bajo", action="store_true",
                    help="escribir inversiones (Bmaj7/F#); por defecto solo el acorde, para guitarra")
    ap.add_argument("--rehacer",action="store_true", help="volver a descargar y separar")
    a = ap.parse_args()

    titulo, artista = limpiar(a.titulo), limpiar(a.artista)
    base = os.path.join(a.destino, f"{titulo} - {artista}")
    carpeta_audio = os.path.join(base, "audio")
    carpeta_an = os.path.join(base, "analisis")
    os.makedirs(carpeta_an, exist_ok=True)

    wav, stems = preparar_audio(a.fuente, carpeta_audio, titulo, not a.sin_stems, a.rehacer)
    # estructura: si existe estructura.txt (corregida a mano) manda; si no, se crea con la automática
    ruta_est = os.path.join(base, "estructura.txt")
    entradas = leer_estructura(ruta_est) if os.path.exists(ruta_est) else []
    metricas = metricas_de(entradas, 10 ** 6)
    res = analizar(wav, stems, a.compas, a.con_bajo, metricas)
    res.update({"titulo": a.titulo, "artista": a.artista, "fuente": a.fuente})

    if entradas:
        manual = secciones_manual(res["compases"], entradas)
        if manual:
            res["secciones_auto"] = res["secciones"]
            res["secciones"] = manual
            log(f"Estructura tomada de {ruta_est}")
    else:
        escribir_estructura(res["secciones"], ruta_est)

    with open(os.path.join(carpeta_an, "acordes.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    with open(os.path.join(carpeta_an, "acordes_beats.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tiempo", "mm:ss", "acorde"])
        for b in res["beats"]:
            w.writerow([f"{b['t']:.2f}", mmss(b["t"]), b["nombre"]])
    nombre = f"{titulo} - {artista}"
    escribir_txt(res, a.titulo, a.artista, os.path.join(base, nombre + ".txt"))
    ruta_pdf = os.path.join(base, nombre + ".pdf")
    try:
        escribir_pdf(res, a.titulo, a.artista, ruta_pdf)
    except PermissionError:
        ruta_pdf = os.path.join(base, nombre + " (nuevo).pdf")
        escribir_pdf(res, a.titulo, a.artista, ruta_pdf)
        log(f"El PDF original está abierto en otro programa; guardé {ruta_pdf}")
    log(f"\nListo: {base}")
    log(f"Tempo {res['tempo']} · Tonalidad {res['tonalidad']} · {len(res['secciones'])} secciones")


if __name__ == "__main__":
    main()
