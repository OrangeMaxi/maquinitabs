"""
Pipeline de la app web: YouTube -> audio -> 6 pistas (demucs htdemucs_6s) -> análisis.

Reutiliza `_herramientas\\acordes\\sacar_acordes.py` (acordes, tempo, tonalidad, compases, estructura)
y agrega la línea de bajo y la melodía de la voz (pYIN, cuantizadas a semicorcheas).

Carpeta de cada tema (misma convención que la skill `acordes`):
  <Título> - <Artista>\\
    audio\\<Título>.wav, vocals/bass/drums/guitar/piano/otros.wav, other.wav (= guitar+piano+otros)
    analisis\\app.json   lo que lee la app
    estructura.txt       si existe, manda sobre la detección automática
"""
import json
import os
import re
import shutil
import subprocess
import sys

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "acordes"))
import sacar_acordes as sa  # noqa: E402

SR = 22050
HOP = 512
VERSION = 5
# "btc" = modelo entrenado (mucho mejor fuera del pop/rock); "" = plantillas de sacar_acordes.py
MODELO_ACORDES = os.environ.get("MODELO_ACORDES", "btc")
# "beat_this" = pulsos y "unos" con el modelo entrenado Beat This!; "" = solo librosa
MODELO_PULSOS = os.environ.get("MODELO_PULSOS", "beat_this")

PISTAS = [  # (id, nombre visible)
    ("vocals", "Voz"), ("guitar", "Guitarra"), ("piano", "Piano"),
    ("bass", "Bajo"), ("drums", "Batería"), ("otros", "Otros"), ("other", "Otros"),
]
BASURA = re.compile(
    r"\s*[\(\[][^\)\]]*(official|oficial|video|audio|lyric|letra|remaster|visualizer|hd|4k|vivo|live|mix|versi[oó]n|version|(?:19|20)\d\d)"
    r"[^\)\]]*[\)\]]", re.I)


def _noop(etapa, pct=None):
    pass


# ---------------------------------------------------------------- descarga
def info_youtube(url):
    r = subprocess.run(["yt-dlp", "-J", "--no-playlist", "--no-warnings", url],
                       capture_output=True, check=True)
    d = json.loads(r.stdout.decode("utf-8", "replace"))
    return titulo_y_artista(d.get("track"), d.get("title"), d.get("artist") or d.get("creator"),
                            d.get("uploader") or d.get("channel"))


def titulo_y_artista(track, title, artist, canal):
    """Título y artista prolijos a partir de los datos del video (que vienen en cualquier orden)."""
    canal = re.sub(r"\s*-\s*Topic$|VEVO$", "", canal or "").strip()
    artista = (artist or "").split(",")[0].strip()
    titulo = track or title or "Sin título"
    if not track:
        # "Artista - Tema (Official Video) - 4K REMASTER": se sacan los pedazos que son relleno
        relleno = re.compile(r"^\W*(official|oficial|video|audio|lyrics?|letra|remaster(ed)?|hd|4k|full album)\b", re.I)
        partes = [p.strip() for p in BASURA.sub("", titulo).split(" - ")]
        partes = [p for p in partes if p and not relleno.match(p) and not re.fullmatch(r"(4k|hd)?\s*remaster(ed)?.*", p, re.I)]
        if len(partes) >= 2:
            a, t = partes[0], " - ".join(partes[1:])
            # el artista es el pedazo que coincide con el canal o con el artista declarado
            junto = lambda s: re.sub(r"\W", "", s.lower())       # "johnlennon" == "John Lennon"
            ref, p0, p1 = junto(artista or canal), junto(partes[0]), junto(partes[1])
            if ref and p0 and p1 and (p1 in ref or ref in p1) and not (p0 in ref or ref in p0):
                a, t = partes[1], partes[0]
            artista, titulo = artista or a, t
        elif partes:
            titulo = partes[0]
    titulo = BASURA.sub("", titulo)
    titulo = re.sub(r"\s+(ft|feat)\.?\s.*$", "", titulo, flags=re.I).strip() or "Sin título"
    artista = BASURA.sub("", artista or canal or "Desconocido").strip() or "Desconocido"
    return sa.limpiar(titulo), sa.limpiar(artista)


def descargar(url, raiz, progreso=_noop):
    """Baja el audio y devuelve la carpeta del tema."""
    progreso("Leyendo datos del video…", 2)
    titulo, artista = info_youtube(url)
    base = os.path.join(raiz, f"{titulo} - {artista}")
    carpeta_audio = os.path.join(base, "audio")
    os.makedirs(carpeta_audio, exist_ok=True)
    os.makedirs(os.path.join(base, "analisis"), exist_ok=True)
    wav = os.path.join(carpeta_audio, f"{titulo}.wav")
    if not os.path.exists(wav):
        progreso(f"Descargando «{titulo}»…", 5)
        subprocess.run(["yt-dlp", "-q", "--no-playlist", "-x", "--audio-format", "wav",
                        "-o", os.path.join(carpeta_audio, f"{titulo}.%(ext)s"), url], check=True)
    meta = os.path.join(base, "analisis", "meta.json")
    with open(meta, "w", encoding="utf-8") as f:
        json.dump({"titulo": titulo, "artista": artista, "fuente": url}, f, ensure_ascii=False)
    return base


def importar(origen, nombre_archivo, raiz, titulo=None, artista=None):
    """Tema subido como archivo (mp3, m4a, wav, flac, ogg…) en vez de bajado de YouTube: hace falta en un
    servidor en internet, porque YouTube suele bloquear las descargas desde datacenters.
    Título y artista: los que se pasen o, si no, del nombre del archivo («Artista - Tema.mp3»).
    Convierte a WAV con ffmpeg y devuelve la carpeta del tema."""
    if not (titulo and artista):
        t, a = titulo_y_artista(None, os.path.splitext(nombre_archivo)[0], None, "")
        titulo, artista = titulo or t, artista or (a if a != "Desconocido" else "Sin artista")
    titulo, artista = sa.limpiar(titulo), sa.limpiar(artista)
    base = os.path.join(raiz, f"{titulo} - {artista}")
    os.makedirs(os.path.join(base, "audio"), exist_ok=True)
    os.makedirs(os.path.join(base, "analisis"), exist_ok=True)
    wav = os.path.join(base, "audio", f"{titulo}.wav")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", origen, "-vn", "-ar", "44100", "-ac", "2", wav], check=True)
    with open(os.path.join(base, "analisis", "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"titulo": titulo, "artista": artista, "fuente": ""}, f, ensure_ascii=False)
    return base


# ---------------------------------------------------------------- pistas
def mezcla_de(base):
    carpeta = os.path.join(base, "audio")
    reservados = {p + ".wav" for p, _ in PISTAS}
    for n in sorted(os.listdir(carpeta)):
        if n.lower().endswith(".wav") and n not in reservados:
            return os.path.join(carpeta, n)
    raise FileNotFoundError("No encuentro el audio original en " + carpeta)


def pistas_de(base):
    """Pistas reproducibles que hay en la carpeta (6 si se separó con htdemucs_6s, 4 si es vieja)."""
    carpeta = os.path.join(base, "audio")
    hay = lambda n: os.path.exists(os.path.join(carpeta, n + ".wav"))
    if hay("guitar") and hay("otros"):
        ids = ["vocals", "guitar", "piano", "bass", "drums", "otros"]
    else:
        ids = ["vocals", "bass", "drums", "other"]
    nombres = dict(PISTAS)
    return [{"id": i, "nombre": nombres[i]} for i in ids if hay(i)]


def separar(base, progreso=_noop):
    """demucs htdemucs_6s -> vocals, drums, bass, guitar, piano, otros (+ other = armonía completa)."""
    import soundfile as sf

    carpeta = os.path.join(base, "audio")
    wav = mezcla_de(base)
    seis = ["vocals", "drums", "bass", "guitar", "piano", "otros"]
    if all(os.path.exists(os.path.join(carpeta, n + ".wav")) for n in seis + ["other"]):
        return
    progreso("Separando en 6 pistas (demucs)…", 10)
    tmp = os.path.join(carpeta, "_sep")
    # el modelo viaja con el proyecto (_herramientas\modelos): así no hay que bajarlo en cada compu
    entorno = dict(os.environ)
    modelos = os.path.join(os.path.dirname(AQUI), "modelos")
    if "TORCH_HOME" not in entorno and os.path.isdir(os.path.join(modelos, "hub", "checkpoints")):
        entorno["TORCH_HOME"] = modelos
    # separar_demucs.py = el comando de demucs pero guardando con soundfile (anda también en ARM)
    p = subprocess.Popen([sys.executable, os.path.join(AQUI, "separar_demucs.py"), wav, tmp, "htdemucs_6s"],
                         stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, env=entorno)
    buf, cola = b"", b""
    while True:
        ch = p.stderr.read(64)
        if not ch:
            break
        cola = (cola + ch)[-4000:]
        buf = (buf + ch)[-200:]
        m = re.findall(rb"(\d+)%\|", buf)
        if m:
            progreso("Separando en 6 pistas (demucs)…", 10 + int(int(m[-1]) * 0.6))
    if p.wait() != 0:
        raise RuntimeError("demucs falló: " + cola.decode("utf-8", "replace")[-600:])
    src = os.path.join(tmp, "htdemucs_6s", os.path.splitext(os.path.basename(wav))[0])
    for n in ["vocals", "drums", "bass", "guitar", "piano"]:
        shutil.move(os.path.join(src, n + ".wav"), os.path.join(carpeta, n + ".wav"))
    shutil.move(os.path.join(src, "other.wav"), os.path.join(carpeta, "otros.wav"))
    shutil.rmtree(tmp, ignore_errors=True)
    # other.wav = guitarra + piano + otros: la armonía completa, que es lo que usa el detector de acordes
    suma, sr = None, None
    for n in ["guitar", "piano", "otros"]:
        y, sr = sf.read(os.path.join(carpeta, n + ".wav"), dtype="float32")
        suma = y if suma is None else suma[: len(y)] + y[: len(suma)]
    sf.write(os.path.join(carpeta, "other.wav"), np.clip(suma, -1, 1), sr, subtype="PCM_16")
    shutil.rmtree(os.path.join(carpeta, "_transp"), ignore_errors=True)


# ---------------------------------------------------------------- notas (bajo / voz)
def f0_de(ruta, cache, fmin, fmax, frame_length):
    import librosa

    mt = os.path.getmtime(ruta)
    if os.path.exists(cache):
        z = np.load(cache)
        if float(z["mtime"]) == mt:
            return z["f0"], z["voz"], z["rms"], z["onsets"]
    y, _ = librosa.load(ruta, sr=SR, mono=True)
    f0, vf, _ = librosa.pyin(y, fmin=fmin, fmax=fmax, sr=SR, frame_length=frame_length, hop_length=HOP)
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=HOP)[0]
    onsets = librosa.onset.onset_detect(y=y, sr=SR, hop_length=HOP, units="time")
    n = min(len(f0), len(rms))
    f0, vf, rms = np.nan_to_num(f0[:n]), vf[:n], rms[:n]
    np.savez(cache, f0=f0, voz=vf, rms=rms, onsets=onsets, mtime=mt)
    return f0, vf, rms, onsets


def notas_de(ruta, cache, bordes, afin, fmin, fmax, frame_length, rango=None):
    """Notas cuantizadas a la grilla de semicorcheas `bordes` (tiempos de los bordes de cada casilla).
    Devuelve [{"i": casilla inicial, "d": casillas, "m": nota MIDI}]."""
    import librosa

    f0, vf, rms, onsets = f0_de(ruta, cache, fmin, fmax, frame_length)
    if not len(f0) or rms.max() < 1e-4:
        return []
    t = librosa.frames_to_time(np.arange(len(f0)), sr=SR, hop_length=HOP)
    suena = vf & (rms > 0.08 * np.percentile(rms, 95)) & (f0 > 0)
    midi = np.zeros(len(f0))
    midi[suena] = librosa.hz_to_midi(f0[suena]) - afin
    idx = np.searchsorted(t, bordes)
    ns = len(bordes) - 1
    tono = [None] * ns
    for k in range(ns):
        a, b = idx[k], max(idx[k + 1], idx[k] + 1)
        s = suena[a:b]
        if len(s) and s.mean() >= 0.5:
            m = int(round(float(np.median(midi[a:b][s]))))
            if rango:
                while m > rango[1]:
                    m -= 12
                while m < rango[0]:
                    m += 12
            tono[k] = m
    ataque = set(int(x) for x in np.clip(np.searchsorted(bordes, onsets + 0.02) - 1, 0, ns - 1))
    notas = []
    for k in range(ns):
        m = tono[k]
        if m is None:
            continue
        ult = notas[-1] if notas else None
        pegada = ult is not None and ult["i"] + ult["d"] == k
        if pegada and ult["m"] == m and k not in ataque:
            ult["d"] += 1
        else:
            notas.append({"i": k, "d": 1, "m": m, "atq": k in ataque})
    # una sola casilla sin ataque = casi siempre un glissando o ruido: se la queda la nota anterior
    limpio = []
    for n in notas:
        if n["d"] == 1 and not n["atq"]:
            if limpio and limpio[-1]["i"] + limpio[-1]["d"] == n["i"]:
                limpio[-1]["d"] += 1
            continue
        limpio.append(n)
    return [{"i": n["i"], "d": n["d"], "m": n["m"]} for n in limpio]


# ---------------------------------------------------------------- correcciones a mano
def leer_correcciones(base):
    """correcciones.json del tema: {"compas": 3|4|None, "acordes": [[t, nombre]…], "unos": [t…]|None}.
    Todo va por tiempo (segundos) y no por número de pulso, para que sobreviva a un re-análisis."""
    ruta = os.path.join(base, "correcciones.json")
    d = {}
    if os.path.exists(ruta):
        try:
            with open(ruta, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = {}
    return {"compas": d.get("compas") or None, "acordes": d.get("acordes") or [], "unos": d.get("unos") or None}


def guardar_correcciones(base, corr):
    ruta = os.path.join(base, "correcciones.json")
    if not (corr.get("compas") or corr.get("acordes") or corr.get("unos")):
        if os.path.exists(ruta):
            os.remove(ruta)
        return
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(corr, f, ensure_ascii=False)


def aplicar_correcciones(out, corr):
    """Rearma compases y secciones de `out` (el app.json) a partir de lo detectado (`out["base"]`) más las
    correcciones del usuario. Es instantáneo: no vuelve a analizar el audio."""
    if "base" not in out:      # app.json anterior a las correcciones: lo detectado es lo que hay
        out["base"] = {
            "acordes": [a for c in out["compases"] for a, n in c["acordes"] for _ in range(n)],
            "largos": [c["pulsos"] for c in out["compases"]],
            "anacrusa": bool(out["compases"] and out["compases"][0]["anacrusa"]),
            "secciones": [{"nombre": s["nombre"], "letra": s.get("letra", ""), "t": out["compases"][s["ini"]]["t"]}
                          for s in out["secciones"]],
            "activa": {p["id"]: p["activa"] for p in out["pistas"]},
        }
    base = out["base"]
    tb = np.array(out["beats"][:-1])
    nb = len(base["acordes"])
    paso = float(np.median(np.diff(tb))) if nb > 1 else 0.5
    cerca = lambda t: int(np.argmin(np.abs(tb[:nb] - t)))

    acordes = list(base["acordes"])
    hechas = []
    for t, a in corr.get("acordes") or []:
        k = cerca(t)
        if abs(tb[k] - t) < 0.6 * paso and a != base["acordes"][k]:
            acordes[k] = a
            hechas.append([round(float(tb[k]), 3), a])

    largos, anacrusa, unos = base["largos"], base["anacrusa"], None
    if corr.get("unos"):
        ini = sorted({cerca(t) for t in corr["unos"]} | {0})
        largos = [b - a for a, b in zip(ini, ini[1:] + [nb])]
        anacrusa = len(largos) > 1 and largos[0] < out["compas"]
        unos = [round(float(tb[k]), 3) for k in ini]

    compases, k = [], 0
    for j, n in enumerate(largos):
        runs = []
        for x in acordes[k: k + n]:
            if runs and runs[-1][0] == x:
                runs[-1][1] += 1
            else:
                runs.append([x, 1])
        compases.append({"t": round(float(tb[k]), 3), "pulsos": n, "beat": k, "acordes": runs,
                         "anacrusa": anacrusa and j == 0})
        k += n
    out["compases"] = compases

    tc = np.array([c["t"] for c in compases])
    inis = sorted({int(np.argmin(np.abs(tc - s["t"]))): s for s in reversed(base["secciones"])}.items())
    if inis:
        inis[0] = (0, inis[0][1])
    out["secciones"] = [{"nombre": s["nombre"], "ini": i, "fin": inis[j + 1][0] if j + 1 < len(inis) else len(compases),
                         "letra": s.get("letra", "")} for j, (i, s) in enumerate(inis)]
    for p in out["pistas"]:
        if unos is None:
            p["activa"] = base["activa"][p["id"]]
        else:   # compases movidos a mano: la pista "toca" en un compás si suena en la mitad de sus pulsos
            p["activa"] = [int(2 * sum(p["pulsos"][c["beat"]: c["beat"] + c["pulsos"]]) >= c["pulsos"]) for c in compases]
    out["correcciones"] = {"compas": corr.get("compas") or None, "acordes": hechas, "unos": unos}
    return out


# ---------------------------------------------------------------- análisis completo
def analizar(base, compas=None, progreso=_noop):
    """compas: 3 o 4 para forzarlo; None = el que eligió el usuario en la app (correcciones.json) o,
    si no eligió, el que se detecta solo."""
    import librosa

    carpeta = os.path.join(base, "audio")
    carpeta_an = os.path.join(base, "analisis")
    os.makedirs(carpeta_an, exist_ok=True)
    wav = mezcla_de(base)
    stems = {n: os.path.join(carpeta, n + ".wav") for n in ("bass", "drums", "other", "vocals")}
    for n, p in stems.items():
        if not os.path.exists(p):
            raise FileNotFoundError(f"Falta la pista {n}.wav")

    meta = {}
    ruta_meta = os.path.join(carpeta_an, "meta.json")
    if os.path.exists(ruta_meta):
        with open(ruta_meta, encoding="utf-8") as f:
            meta = json.load(f)
    else:  # carpeta hecha con la skill `acordes`: "<Título> - <Artista>"
        nombre = os.path.basename(base)
        t, _, a = nombre.partition(" - ")
        meta = {"titulo": t, "artista": a, "fuente": ""}
        viejo = os.path.join(carpeta_an, "acordes.json")
        if os.path.exists(viejo):
            with open(viejo, encoding="utf-8") as f:
                v = json.load(f)
            meta = {k: v.get(k, meta[k]) for k in meta}

    progreso("Acordes, tempo y estructura…", 72)
    ruta_est = os.path.join(base, "estructura.txt")
    entradas = sa.leer_estructura(ruta_est) if os.path.exists(ruta_est) else []
    corr = leer_correcciones(base)
    if compas:
        corr["compas"] = compas
    res = sa.analizar(wav, stems, corr["compas"] or 0, False, sa.metricas_de(entradas, 10 ** 6), modelo=MODELO_ACORDES,
                      pulsos=MODELO_PULSOS)
    compas = res["pulsos_compas"]
    if entradas:
        manual = sa.secciones_manual(res["compases"], entradas)
        if manual:
            res["secciones"] = manual

    # grilla de semicorcheas: 4 casillas por pulso
    tb = np.array([b["t"] for b in res["beats"]])
    paso = float(np.median(np.diff(tb))) if len(tb) > 1 else 0.5
    tb_ext = np.append(tb, tb[-1] + paso)
    bordes = np.concatenate([np.linspace(tb_ext[i], tb_ext[i + 1], 5)[:4] for i in range(len(tb))]
                            + [[tb_ext[-1]]])
    afin = res["afinacion_cents"] / 100.0

    progreso("Línea de bajo…", 82)
    bajo = notas_de(stems["bass"], os.path.join(carpeta_an, "_f0_bass.npz"), bordes, afin,
                    fmin=30, fmax=330, frame_length=4096, rango=(23, 55))
    progreso("Melodía de la voz…", 90)
    voz = notas_de(stems["vocals"], os.path.join(carpeta_an, "_f0_vocals.npz"), bordes, afin,
                   fmin=70, fmax=1000, frame_length=2048)

    progreso("Actividad de cada pista…", 96)
    pistas = pistas_de(base)
    t_comp = [c["t"] for c in res["compases"]] + [float(tb_ext[-1])]
    mezcla, _ = librosa.load(wav, sr=SR, mono=True)
    ref = float(np.sqrt(np.mean(mezcla ** 2))) + 1e-9
    for p in pistas:
        y, _ = librosa.load(os.path.join(carpeta, p["id"] + ".wav"), sr=SR, mono=True)
        p["nivel"] = round(float(np.sqrt(np.mean(y ** 2))) / ref, 3)
        por_compas = []
        for a, b in zip(t_comp[:-1], t_comp[1:]):
            tramo = y[int(a * SR): max(int(b * SR), int(a * SR) + 1)]
            por_compas.append(float(np.sqrt(np.mean(tramo ** 2))) if len(tramo) else 0.0)
        tope = np.percentile(por_compas, 95) + 1e-9
        p["activa"] = [1 if v > 0.15 * tope and v > 0.02 * ref else 0 for v in por_compas]
        # lo mismo pulso por pulso: la hoja de acordes de guitarra/piano solo muestra lo que toca ese instrumento
        por_pulso = []
        for a, b in zip(tb_ext[:-1], tb_ext[1:]):
            tramo = y[int(a * SR): max(int(b * SR), int(a * SR) + 1)]
            por_pulso.append(float(np.sqrt(np.mean(tramo ** 2))) if len(tramo) else 0.0)
        tope = np.percentile(por_pulso, 95) + 1e-9
        p["pulsos"] = [1 if v > 0.12 * tope and v > 0.02 * ref else 0 for v in por_pulso]

    # guitarra y piano: transcripción polifónica (Basic Pitch) sobre cada pista
    progreso("Guitarra y piano…", 97)
    import transcribir
    poli = {}
    # «otros» = lo que demucs no reconoce como voz, guitarra, piano, bajo ni batería: sintes, vientos, cuerdas…
    for pid, clave, rango in (("guitar", "guitarra", (40, 88)), ("piano", "piano", (24, 100)), ("otros", "otros", (28, 100))):
        pista = next((p for p in pistas if p["id"] == pid), None)
        if pista is None:
            continue
        poli[clave] = [] if pista["nivel"] < 0.04 else transcribir.notas(
            os.path.join(carpeta, pid + ".wav"), os.path.join(carpeta_an, f"_bp_{pid}.npz"), bordes, rango,
            max_voces={"guitar": 6, "piano": 8}.get(pid, 6))
        # donde la pista está callada, lo que queda es filtración de otros instrumentos
        calla = {k for k, v in enumerate(pista["pulsos"]) if not v}
        poli[clave] = [n for n in poli[clave] if n["i"] // 4 not in calla]
        # ¿en qué pulsos toca acordes? Dos o más notas sonando a la vez; una línea suelta (un punteo,
        # un arreglo de una nota) no es un acorde y no va a la hoja de acordes de ese instrumento.
        voces = np.zeros(len(pista["pulsos"]) * 4 + 1, dtype=int)
        for n in poli[clave]:
            voces[n["i"]: n["i"] + n["d"]] += 1
        # ...o, con guitarras distorsionadas que se transcriben nota por nota, tres o más notas distintas
        # en el compás que rodea al pulso (un riff de acordes), siempre que la pista esté sonando.
        tonos = [set() for _ in pista["pulsos"]]
        for n in poli[clave]:
            for k in range(n["i"] // 4, min((n["i"] + n["d"] - 1) // 4 + 1, len(tonos))):
                tonos[k].add(n["m"] % 12)
        toca = []
        for k in range(len(pista["pulsos"])):
            cerca = set().union(*tonos[max(k - 2, 0): k + 2])
            toca.append(int(bool(pista["pulsos"][k]) and (voces[k * 4: k * 4 + 4].max() >= 2 or len(cerca) >= 3)))
        for k in range(1, len(toca) - 1):          # un pulso suelto entre dos con acorde también cuenta
            if not toca[k] and toca[k - 1] and toca[k + 1]:
                toca[k] = 1
        pista["acorde"] = toca

    # Tema instrumental: demucs igual deja algo en "vocals" (vientos, cuerdas), pero muy bajo. Ahí no hay
    # melodía de voz que transcribir ni versos/coros: las partes se llaman por letra.
    nivel_voz = next((p["nivel"] for p in pistas if p["id"] == "vocals"), 0)
    instrumental = nivel_voz < 0.18
    # pista de bajo vacía (tema sin bajo): lo que "transcribe" pYIN ahí es ruido de la separación
    if next((p["nivel"] for p in pistas if p["id"] == "bass"), 0) < 0.04:
        bajo = []
    if instrumental:
        voz = []
        if not entradas:
            for k, s in enumerate(res["secciones"]):
                if not (s["nombre"] == "Intro" and k == 0) and s["nombre"] != "Outro":
                    s["nombre"] = f"Parte {s.get('letra', '?')}"
    if not entradas:
        sa.escribir_estructura(res["secciones"], ruta_est)

    m = re.match(r"^([A-G][#b]?)", res["tonalidad"])
    # Modo de la tonalidad: el croma solo confunde mayor con menor en temas de un acorde (funk, blues).
    # Si los acordes detectados sobre la tónica son casi todos menores (o casi todos mayores), mandan ellos.
    notas = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7,
             "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
    en_tonica = [b["calidad"] for b in res["beats"] if b["raiz"] == notas.get(m.group(1))]
    menores = sum(1 for q in en_tonica if q in ("m", "m7", "m6", "mMaj7", "dim", "dim7", "m7b5"))
    mayores = sum(1 for q in en_tonica if q in ("", "maj7", "6", "aug"))    # el 7 de dominante no define modo
    if res["tonalidad_modo"] == "mayor" and menores > 2 * mayores and menores >= 8:
        res["tonalidad_modo"], res["tonalidad"] = "menor", m.group(1) + "m"
    elif res["tonalidad_modo"] == "menor" and mayores > 2 * menores and mayores >= 8:
        res["tonalidad_modo"], res["tonalidad"] = "mayor", m.group(1)
    out = {
        "version": VERSION,
        "titulo": meta["titulo"], "artista": meta["artista"], "fuente": meta.get("fuente", ""),
        "duracion": res["duracion"], "tempo": res["tempo"], "compas": compas,
        "tonalidad": {"nombre": res["tonalidad"], "tonica": m.group(1), "modo": res["tonalidad_modo"]},
        "pistas": pistas, "instrumental": instrumental,
        "beats": [round(float(x), 3) for x in tb_ext],
        "compases": [{"t": round(c["t"], 3), "pulsos": c["pulsos"], "beat": c["beat_ini"],
                      "acordes": c["runs"], "anacrusa": c["anacrusa"]} for c in res["compases"]],
        "secciones": [{"nombre": s["nombre"], "ini": s["ini"], "fin": s["fin"], "letra": s.get("letra", "")}
                      for s in res["secciones"]],
        "notas": {"bajo": bajo, "voz": voz, **poli},
        "creditos": creditos_de(base, meta["titulo"], meta["artista"], progreso),
    }
    aplicar_correcciones(out, corr)
    guardar(base, out)
    progreso("Listo", 100)
    return out


def creditos_de(base, titulo, artista, progreso=_noop):
    """Instrumentos del tema según MusicBrainz y Wikipedia (creditos.py). Se busca una vez y queda en
    analisis\\creditos.json; si no hay internet no se guarda, así se reintenta en el próximo análisis.
    SIN_INTERNET=1 lo saltea."""
    ruta = os.path.join(base, "analisis", "creditos.json")
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    if os.environ.get("SIN_INTERNET"):
        return None
    progreso("Buscando los instrumentos del tema en internet…", 98)
    import creditos
    c = creditos.instrumentos(titulo, artista)
    if c["fuentes"]:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False, indent=1)
    return c


def guardar(base, out):
    ruta = os.path.join(base, "analisis", "app.json")
    with open(ruta + ".tmp", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(ruta + ".tmp", ruta)


# ---------------------------------------------------------------- transporte
def transportar(base, pista, semitonos):
    """Devuelve la ruta de la pista transportada (FLAC en audio\\_transp, se calcula una sola vez)."""
    origen = os.path.join(base, "audio", pista + ".wav")
    if semitonos == 0 or pista == "drums":
        return origen
    carpeta = os.path.join(base, "audio", "_transp")
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, f"{pista}_{semitonos:+d}.flac")
    if not os.path.exists(destino) or os.path.getmtime(destino) < os.path.getmtime(origen):
        filtro = f"rubberband=pitch={2 ** (semitonos / 12):.8f}"
        if pista == "vocals":
            filtro += ":formant=preserved"
        tmp = destino + f".{os.getpid()}.{np.random.randint(1e9)}.tmp.flac"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", origen, "-af", filtro, tmp], check=True)
        os.replace(tmp, destino)
    return destino


if __name__ == "__main__":
    # uso: python analisis.py "<carpeta del tema>"   (re-analiza sin el servidor)
    r = analizar(sys.argv[1], progreso=lambda e, p=None: print(p, e, flush=True))
    print(r["tempo"], r["tonalidad"], len(r["notas"]["bajo"]), "notas de bajo,", len(r["notas"]["voz"]), "de voz")
