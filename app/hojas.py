"""Hojas compartidas: lo que un músico corrigió a mano en un tema, en un archivo chico para pasárselo a otro.

Un archivo «.maquinitabs» (JSON) lleva la hoja tal como la ve el que la manda —el acorde de cada pulso, dónde
empieza cada compás y las secciones—, más lo corregido en la hoja de cada instrumento, el compás si lo forzó y
de qué audio salió (link de YouTube y duración). Se manda la hoja entera y no solo lo corregido porque el que la
abre puede detectar otra cosa (otra versión de la app); al abrirla, lo que coincide con lo detectado ahí no
queda como corrección. No lleva audio: el que la abre tiene que tener el tema o bajarlo. Todo va por tiempo
(segundos), así que con el mismo audio cae donde lo puso el otro.
"""
import json
import os
import re
import time

import analisis


FORMATO = "maquinitabs-hoja"
VERSION = 1
EXTENSION = ".maquinitabs"
PISTAS_CON_HOJA = ("guitar", "piano", "otros")
COMPASES = (None, 2, 3, 4, 5, 6, 7)
MAX_ESTRUCTURA = 20000          # caracteres: una estructura real ocupa unos cientos


def validar_correcciones(d):
    """Correcciones que llegan de afuera (la app o un archivo) -> dict limpio. ValueError si están mal."""
    try:
        corr = {
            "compas": int(d["compas"]) if d.get("compas") else None,
            "acordes": [[float(t), str(a)[:16]] for t, a in d.get("acordes") or []],
            "unos": [float(t) for t in d.get("unos") or []] or None,
            "pistas": {p: [[round(float(t), 3), str(a)[:16]] for t, a in v]
                       for p, v in (d.get("pistas") or {}).items() if p in PISTAS_CON_HOJA and v},
        }
    except (TypeError, ValueError, AttributeError) as e:
        raise ValueError("Correcciones mal formadas.") from e
    if corr["compas"] not in COMPASES:
        raise ValueError("Compás no válido.")
    return corr


def id_youtube(url):
    """ID del video (11 caracteres) de cualquier link de YouTube, o "" si no es de YouTube."""
    m = re.search(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/)|youtu\.be/)([\w-]{11})", url or "")
    return m.group(1) if m else ""


def _meta(base):
    for ruta in (os.path.join(base, "analisis", "meta.json"), os.path.join(base, "analisis", "app.json")):
        if os.path.exists(ruta):
            try:
                with open(ruta, encoding="utf-8") as f:
                    d = json.load(f)
                return {"titulo": d.get("titulo") or "", "artista": d.get("artista") or "", "fuente": d.get("fuente") or ""}
            except (OSError, ValueError):
                pass
    t, _, a = os.path.basename(base).partition(" - ")
    return {"titulo": t, "artista": a, "fuente": ""}


def _estructura(base):
    ruta = os.path.join(base, "estructura.txt")
    if not os.path.exists(ruta):
        return None
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def _mmss_seg(t):
    return f"{int(t) // 60}:{t % 60:05.2f}"


def _secciones_txt(out):
    """Las secciones que se ven en la hoja, en el formato de estructura.txt."""
    lineas = ["# Secciones de una hoja compartida de Maquinitabs: una por línea, «m:ss Nombre»."]
    for s in out.get("secciones") or []:
        if s["ini"] < len(out["compases"]):
            lineas.append(f'{_mmss_seg(out["compases"][s["ini"]]["t"])} {s["nombre"]}')
    return "\n".join(lineas) + "\n"


def exportar(base, version_app):
    """La hoja del tema como se ve (lo que va en el archivo .maquinitabs)."""
    with open(os.path.join(base, "analisis", "app.json"), encoding="utf-8") as f:
        out = json.load(f)
    propias = analisis.leer_correcciones(base)
    beats = out["beats"]
    acordes, k = [], 0
    for c in out["compases"]:
        k = c.get("beat", k)
        for a, n in c["acordes"]:
            for _ in range(n):
                if k < len(beats):
                    acordes.append([round(float(beats[k]), 3), a])
                k += 1
    est = _estructura(base)
    if est is None:
        est = _secciones_txt(out)          # las secciones que se ven, aunque nadie las haya corregido
    return {
        "formato": FORMATO, "version": VERSION, "app": version_app,
        "exportada": time.strftime("%Y-%m-%d %H:%M"),
        "titulo": out.get("titulo") or "", "artista": out.get("artista") or "",
        "fuente": out.get("fuente") or "", "duracion": out.get("duracion"),
        "estructura": est,
        "correcciones": {
            "compas": propias["compas"],                         # solo si lo forzó: si no, que se detecte
            "acordes": acordes,                                  # el acorde de cada pulso
            "unos": [c["t"] for c in out["compases"]],           # dónde empieza cada compás
            "pistas": propias["pistas"],                         # lo corregido en la hoja de cada instrumento
        },
    }


def nombre_archivo(hoja):
    nombre = f'{hoja["titulo"]} - {hoja["artista"]}' if hoja["artista"] else hoja["titulo"]
    return re.sub(r'[\\/:*?"<>|]+', " ", nombre).strip() + EXTENSION


def leer(d):
    """Hoja recibida (ya parseada del JSON) -> hoja limpia. ValueError con un mensaje para el músico."""
    if not isinstance(d, dict) or d.get("formato") != FORMATO:
        raise ValueError("Ese archivo no es una hoja de Maquinitabs.")
    if int(d.get("version") or 0) > VERSION:
        raise ValueError("La hoja se hizo con una versión más nueva de Maquinitabs: actualizá la app para abrirla.")
    est = d.get("estructura")
    if est is not None and (not isinstance(est, str) or len(est) > MAX_ESTRUCTURA):
        raise ValueError("La estructura de la hoja está mal formada.")
    try:
        duracion = float(d["duracion"]) if d.get("duracion") is not None else None
    except (TypeError, ValueError):
        duracion = None
    return {
        "titulo": str(d.get("titulo") or "").strip()[:200] or "Sin título",
        "artista": str(d.get("artista") or "").strip()[:200],
        "fuente": str(d.get("fuente") or "").strip()[:500],
        "duracion": duracion,
        "estructura": est,
        "correcciones": validar_correcciones(d.get("correcciones") or {}),
    }


def _junto(s):
    return re.sub(r"\W", "", (s or "").lower())


def buscar(raiz, hoja):
    """El tema de la hoja en esta compu: primero por el video de YouTube, después por título y artista."""
    yt = id_youtube(hoja["fuente"])
    por_nombre = None
    for n in sorted(os.listdir(raiz)):
        base = os.path.join(raiz, n)
        if n.startswith(("_", ".")) or not os.path.exists(os.path.join(base, "audio", "vocals.wav")):
            continue
        m = _meta(base)
        if yt and id_youtube(m["fuente"]) == yt:
            return n
        if por_nombre is None and _junto(m["titulo"]) == _junto(hoja["titulo"]) \
                and _junto(m["artista"]) == _junto(hoja["artista"]):
            por_nombre = n
    return por_nombre


def _entradas(texto):
    """Secciones de un texto de estructura: [(segundos, nombre, compás forzado o "")]."""
    out = []
    for linea in (texto or "").splitlines():
        m = re.match(r"\s*(\d+):(\d{1,2}(?:\.\d+)?)\s+(.+?)\s*(?:\[([^\]]+)\])?\s*$", linea)
        if m and not linea.strip().startswith("#"):
            out.append((int(m.group(1)) * 60 + float(m.group(2)), m.group(3).strip(), (m.group(4) or "").strip()))
    return sorted(out)


def _misma_estructura(base, texto):
    """¿Las secciones de la hoja ya son las que se ven en este tema? Entonces no hace falta tocar nada."""
    if texto == _estructura(base):
        return True
    try:
        with open(os.path.join(base, "analisis", "app.json"), encoding="utf-8") as f:
            out = json.load(f)
    except (OSError, ValueError):
        return False
    hoja = _entradas(texto)
    if any(e[2] for e in hoja):            # trae compases forzados por sección: eso solo lo hace el análisis
        return False
    aca = [(out["compases"][s["ini"]]["t"], s["nombre"]) for s in out.get("secciones") or []
           if s["ini"] < len(out["compases"])]
    return len(aca) == len(hoja) and all(n1 == n2 and abs(t1 - t2) < 0.35 for (t1, n1), (t2, n2, _) in zip(aca, hoja))


def describir(raiz, cid, hoja):
    """Lo que la app le cuenta al músico antes de abrir la hoja en un tema que ya tiene."""
    base = os.path.join(raiz, cid)
    m = _meta(base)
    avisos = []
    if id_youtube(hoja["fuente"]) and id_youtube(m["fuente"]) != id_youtube(hoja["fuente"]):
        avisos.append("Tu versión del tema salió de otro video o archivo: si no es la misma grabación, los "
                      "acordes y las secciones pueden quedar corridos.")
    try:
        with open(os.path.join(base, "analisis", "app.json"), encoding="utf-8") as f:
            dur = float(json.load(f).get("duracion") or 0)
    except (OSError, ValueError, TypeError):
        dur = 0
    if hoja["duracion"] and dur and abs(dur - hoja["duracion"]) > 1.5:
        avisos.append(f"Tu audio dura {_mmss(dur)} y el de la hoja {_mmss(hoja['duracion'])}: los acordes y las "
                      "secciones pueden quedar corridos.")
    c = analisis.leer_correcciones(base)
    propias = bool(c["compas"] or c["acordes"] or c["unos"] or c["pistas"])
    if _estructura(base) is not None and hoja["estructura"] is not None \
            and not _misma_estructura(base, hoja["estructura"]):
        propias = True                      # sus secciones (estructura.txt) se reemplazan
    return {"cancion": cid, "analizada": os.path.exists(os.path.join(base, "analisis", "app.json")),
            "propias": propias, "avisos": avisos}


def _mmss(t):
    return f"{int(t) // 60}:{int(t) % 60:02d}"


def poner(base, hoja):
    """Escribe la estructura y las correcciones de la hoja en el tema. Devuelve True si hace falta volver a
    analizar (cambió la estructura o el compás, o el tema no estaba analizado); si no, ya quedó aplicada."""
    ruta_est = os.path.join(base, "estructura.txt")
    ruta = os.path.join(base, "analisis", "app.json")
    antes = _estructura(base)
    cambia = hoja["estructura"] is not None and not _misma_estructura(base, hoja["estructura"])
    if cambia:
        with open(ruta_est, "w", encoding="utf-8") as f:
            f.write(hoja["estructura"])
    corr = hoja["correcciones"]
    analisis.guardar_correcciones(base, corr)
    if not os.path.exists(ruta):
        return True
    with open(ruta, encoding="utf-8") as f:
        out = json.load(f)
    if corr["compas"] and corr["compas"] != out.get("compas"):
        return True
    if not corr["compas"] and (out.get("correcciones") or {}).get("compas"):
        return True                         # el local tenía el compás forzado y la hoja usa el detectado
    if cambia:                              # secciones nuevas: al instante, salvo que fuercen un compás
        out = analisis.aplicar_estructura(base, antes)
        if out is None:
            return True
    else:
        analisis.aplicar_correcciones(out, corr)
        analisis.guardar(base, out)
    analisis.guardar_correcciones(base, out["correcciones"])
    return False
