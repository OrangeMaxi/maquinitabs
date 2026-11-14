"""Mide qué tan bien saca los acordes la app, contra acordes verificados.

    python evaluar.py                       todas las variantes, todos los temas del set
    python evaluar.py actual anterior       solo esas variantes
    python evaluar.py --tema 0107           solo los temas cuyo id/carpeta contiene ese texto
    python evaluar.py --rehacer             ignora los resultados guardados y vuelve a analizar
    python evaluar.py --verificar "<carpeta del tema>"
        guarda la hoja actual de ese tema (ya corregida a mano con «Editar hoja») como referencia.lab;
        desde ahí el tema entra en el set de prueba (con su propio promedio: ver abajo).

Temas del set:
  - temas.json + referencias\\<id>.lab + canciones\\  (los arma preparar.py desde McGill Billboard)
  - cualquier tema de la carpeta de canciones de la banda que tenga un referencia.lab

Métricas (mir_eval, las del concurso MIREX), en % del tiempo evaluable de todos los temas juntos:
  raíz      acierta la nota fundamental
  may/men   acierta la tríada mayor o menor (los acordes de referencia que no son ni mayores ni menores no cuentan)
  séptimas  acierta también la séptima (7, maj7, m7) cuando la hay
  mirex     comparte al menos 3 notas con el acorde de referencia
  cortes    qué tan bien coinciden los cambios de acorde (promedio por tema)

El audio bajado de YouTube no empieza exactamente donde el anotado: el desfase se busca una sola vez por
tema (con todas las variantes juntas, así no favorece a ninguna) y se guarda. Si el desfase cambia entre la
primera y la segunda mitad del tema, el audio es otra edición o va a otra velocidad: el tema se marca como
sospechoso y no entra en el promedio.

Los temas de la banda (--verificar) se promedian aparte: su referencia sale de la hoja que armó la app
(corregida a mano), así que favorece a la variante «actual» y no sirve para comparar variantes entre sí.
"""
import hashlib
import json
import os
import re
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "app"))
import analisis  # noqa: E402

sa = analisis.sa
RAIZ_BANDA = os.environ.get("CANCIONES_RAIZ") or os.path.dirname(os.path.dirname(AQUI))
CACHE = os.path.join(AQUI, "resultados")
ACORDES = os.path.join(os.path.dirname(AQUI), "acordes")

# variante -> (pesos del modelo de acordes, detector de pulsos)
VARIANTES = {
    "actual": ("btc_chordmini.pt", "beat_this"),
    "btc-original": ("btc_grande.pt", "beat_this"),
    "pulsos-librosa": ("btc_chordmini.pt", ""),
    "anterior": ("btc_grande.pt", ""),          # como estaba la app antes del 13/11/2026
    "combinado": ("btc_grande.pt+btc_chordmini.pt", "beat_this"),   # promedio de los dos modelos
}
HARTE = {"": "maj", "m": "min", "7": "7", "maj7": "maj7", "m7": "min7", "dim": "dim", "aug": "aug", "6": "maj6",
         "m6": "min6", "mMaj7": "minmaj7", "dim7": "dim7", "m7b5": "hdim7", "sus2": "sus2", "sus4": "sus4",
         # calidades que no saca el detector pero se pueden escribir a mano en «Editar hoja»
         "min": "min", "-": "min", "M7": "maj7", "m(maj7)": "minmaj7", "°": "dim", "°7": "dim7", "ø": "hdim7",
         "m7(b5)": "hdim7", "+": "aug", "sus": "sus4", "7sus4": "sus4(b7)", "5": "5", "add9": "maj(9)",
         "madd9": "min(9)", "9": "9", "m9": "min9", "maj9": "maj9", "11": "11", "m11": "min11", "13": "13",
         "m13": "min13", "maj13": "maj13", "6/9": "maj6(9)", "69": "maj6(9)", "7b9": "7(b9)", "7#9": "7(#9)"}
METRICAS = [("root", "raíz"), ("majmin", "may/men"), ("sevenths", "séptimas"), ("mirex", "mirex"), ("seg", "cortes")]


def a_harte(nombre, desconocidas=None):
    """'F#m7' / 'Bb' / 'N.C.' (cifrado de la app) -> 'F#:min7' / 'Bb:maj' / 'N'.
    Una calidad que no se reconoce da 'X' (mir_eval no cuenta ese tramo) en vez de inventar una tríada."""
    if nombre in ("", "N.C.", None):
        return "N"
    m = re.match(r"^([A-G][#b]?)([^/]*)(?:/([A-G][#b]?))?$", nombre)
    if not m or m.group(2) not in HARTE:
        if desconocidas is not None:
            desconocidas.add(nombre)
        return "X"
    return f"{m.group(1)}:{HARTE[m.group(2)]}"


def tramos_de(compases, beats, desconocidas=None):
    """Compases de la app ([{beat, acordes: [[nombre, pulsos]…]}]) -> [(inicio, fin, Harte)]."""
    out = []
    for c in compases:
        k = c["beat"]
        for a, n in c["acordes"]:
            a = re.sub(r"^\(\d+/\d+\)\s*", "", a)          # "(7/4) Am": marca de compás de la hoja
            x = a_harte(a, desconocidas)
            ini, fin = beats[min(k, len(beats) - 1)], beats[min(k + n, len(beats) - 1)]
            if out and out[-1][2] == x and abs(out[-1][1] - ini) < 1e-6:
                out[-1] = (out[-1][0], fin, x)
            elif fin > ini:
                out.append((ini, fin, x))
            k += n
    return out


def leer_lab(ruta):
    out = []
    with open(ruta, encoding="utf-8") as f:
        for l in f:
            p = l.split()
            if len(p) >= 3:
                out.append((float(p[0]), float(p[1]), p[2]))
    return out


def temas():
    out = []
    ruta = os.path.join(AQUI, "temas.json")
    if os.path.exists(ruta):
        for clave, t in json.load(open(ruta, encoding="utf-8")).items():
            out.append({"id": clave, "nombre": f"{t['titulo']} - {t['artista']}", "base": os.path.join(AQUI, "canciones", t["carpeta"]),
                        "ref": os.path.join(AQUI, "referencias", clave + ".lab"), "billboard": True})
    for n in sorted(os.listdir(RAIZ_BANDA)):       # temas de la banda corregidos a mano y marcados como verificados
        ref = os.path.join(RAIZ_BANDA, n, "referencia.lab")
        if not n.startswith(("_", ".")) and os.path.exists(ref):
            out.append({"id": n, "nombre": n, "base": os.path.join(RAIZ_BANDA, n), "ref": ref, "billboard": False})
    return [t for t in out if os.path.exists(t["ref"]) and os.path.exists(os.path.join(t["base"], "audio", "vocals.wav"))]


def _huella(tema, variante):
    """Cambia si cambia el detector, los pesos, la variante o el audio: ahí hay que volver a analizar."""
    h = hashlib.sha1(repr(VARIANTES[variante]).encode())
    pesos = VARIANTES[variante][0]
    archivos = [os.path.join(ACORDES, "sacar_acordes.py"), os.path.join(ACORDES, "btc_acordes.py"),
                analisis.mezcla_de(tema["base"])] + [os.path.join(ACORDES, "btc", p) for p in pesos.split("+")]
    archivos += [os.path.join(tema["base"], "audio", n + ".wav") for n in ("bass", "drums", "other", "vocals")]
    for a in archivos:
        st = os.stat(a)
        h.update(f"{os.path.basename(a)}:{st.st_size}:{int(st.st_mtime)}".encode())
    return h.hexdigest()[:16]


def _nombre_cache(tema, cosa):
    seguro = re.sub(r"[^\w.-]+", "_", tema["id"])[:40] + "_" + hashlib.sha1(tema["id"].encode()).hexdigest()[:6]
    return os.path.join(CACHE, f"{seguro}__{cosa}.json")


def estimar(tema, variante, rehacer=False):
    """Corre el detector de la app con esa variante. Devuelve [(inicio, fin, Harte)]. Cachea en resultados\\."""
    os.makedirs(CACHE, exist_ok=True)
    cache, huella = _nombre_cache(tema, variante), _huella(tema, variante)
    if os.path.exists(cache) and not rehacer:
        d = json.load(open(cache, encoding="utf-8"))
        if isinstance(d, dict) and d.get("huella") == huella:
            return [tuple(x) for x in d["tramos"]]
    import btc_acordes
    pesos, pulsos = VARIANTES[variante]
    btc_acordes.PESOS = pesos
    carpeta = os.path.join(tema["base"], "audio")
    stems = {n: os.path.join(carpeta, n + ".wav") for n in ("bass", "drums", "other", "vocals")}
    # sin estructura.txt ni correcciones: se mide lo que detecta la app sola
    res = sa.analizar(analisis.mezcla_de(tema["base"]), stems, 0, False, None, modelo="btc", pulsos=pulsos)
    tb = [b["t"] for b in res["beats"]]
    paso = float(np.median(np.diff(tb)))
    comp = [{"beat": c["beat_ini"], "acordes": c["runs"]} for c in res["compases"]]
    tr = tramos_de(comp, tb + [tb[-1] + paso])
    with open(cache, "w", encoding="utf-8") as f:
        json.dump({"huella": huella, "tramos": tr}, f)
    return tr


def _preparar(ref, est, desfase):
    import mir_eval
    ri = np.array([[a, b] for a, b, _ in ref])
    rl = [x for _, _, x in ref]
    ei = np.array([[a, b] for a, b, _ in est]) + desfase
    el = [x for _, _, x in est]
    ei = np.clip(ei, ri[0, 0], ri[-1, 1])          # mir_eval rellena con N lo que falte en los bordes
    ok = ei[:, 1] - ei[:, 0] > 1e-6
    ei, el = ei[ok], [x for x, k in zip(el, ok) if k]
    ei, el = mir_eval.util.adjust_intervals(ei, el, ri.min(), ri.max(), mir_eval.chord.NO_CHORD, mir_eval.chord.NO_CHORD)
    return ri, rl, ei, el


def puntuar(ref, est, desfase=0.0, desde=None, hasta=None):
    """{métrica: (segundos acertados, segundos evaluables)} y "seg": (puntaje, 1).
    desde/hasta: solo esa parte del tema (para comparar las dos mitades)."""
    import mir_eval
    ri, rl, ei, el = _preparar(ref, est, desfase)
    iv, r_l, e_l = mir_eval.util.merge_labeled_intervals(ri, rl, ei, el)
    dur = mir_eval.util.intervals_to_durations(iv)
    if desde is not None:
        medio = iv.mean(axis=1)
        dur = np.where((medio >= desde) & (medio < hasta), dur, 0.0)
    out = {}
    for k in ("root", "majmin", "sevenths", "mirex"):
        comp = np.asarray(getattr(mir_eval.chord, k)(r_l, e_l), dtype=float)
        valido = comp >= 0
        out[k] = (float(np.sum(dur[valido] * comp[valido])), float(np.sum(dur[valido])))
    if desde is None:
        out["seg"] = (float(mir_eval.chord.seg(ri, ei)), 1.0)
    return out


def _tasa(p, k):
    a, b = p[k]
    return a / b if b else 0.0


def mejor_desfase(ref, ests, desde=None, hasta=None):
    """Desfase (s) entre el audio anotado y el nuestro: el que maximiza el acierto de raíz sumado sobre
    todas las variantes. Devuelve (desfase, ¿quedó en el borde del rango buscado?)."""
    mejor, mejor_d = -1, 0.0
    for paso, centro, ancho in ((0.25, 0.0, 8.0), (0.05, None, 0.3)):
        c = mejor_d if centro is None else centro
        for d in np.arange(c - ancho, c + ancho + 1e-9, paso):
            v = sum(_tasa(puntuar(ref, e, d, desde, hasta), "root") for e in ests)
            if v > mejor + 1e-9:
                mejor, mejor_d = v, float(d)
    return round(mejor_d, 2), abs(mejor_d) >= 7.7


def desfase_de(tema, ref, rehacer=False):
    """Desfase del tema, calculado una vez con TODAS las variantes y guardado. Marca sospechoso el tema si
    el desfase de cada mitad difiere (otra edición, otra velocidad) o si quedó en el borde."""
    cache = _nombre_cache(tema, "desfase")
    huellas = {v: _huella(tema, v) for v in VARIANTES}
    if os.path.exists(cache) and not rehacer:
        d = json.load(open(cache, encoding="utf-8"))
        if d.get("huellas") == huellas and d.get("ref") == os.path.getsize(tema["ref"]):
            return d["desfase"], d["sospechoso"]
    if not tema["billboard"]:
        d, sospechoso = 0.0, ""
    else:
        ests = [estimar(tema, v) for v in VARIANTES]
        d, borde = mejor_desfase(ref, ests)
        mitad = (ref[0][0] + ref[-1][1]) / 2
        d1, _ = mejor_desfase(ref, ests, ref[0][0], mitad)
        d2, _ = mejor_desfase(ref, ests, mitad, ref[-1][1])
        sospechoso = ("el desfase quedó en el borde del rango" if borde else
                      f"desfase distinto en cada mitad ({d1:+.2f} / {d2:+.2f} s): otra edición o velocidad"
                      if abs(d1 - d2) > 0.6 else "")
    with open(cache, "w", encoding="utf-8") as f:
        json.dump({"desfase": d, "sospechoso": sospechoso, "huellas": huellas, "ref": os.path.getsize(tema["ref"])}, f)
    return d, sospechoso


def verificar(carpeta):
    base = carpeta if os.path.isabs(carpeta) else os.path.join(RAIZ_BANDA, carpeta)
    c = json.load(open(os.path.join(base, "analisis", "app.json"), encoding="utf-8"))
    raras = set()
    tr = tramos_de(c["compases"], c["beats"], raras)
    with open(os.path.join(base, "referencia.lab"), "w", encoding="utf-8") as f:
        for a, b, x in tr:
            f.write(f"{a:.3f}\t{b:.3f}\t{x}\n")
    print("Referencia guardada:", os.path.join(base, "referencia.lab"))
    if raras:
        print("Estos acordes no se pudieron traducir y no se van a contar:", ", ".join(sorted(raras)))


def main():
    args = sys.argv[1:]
    if args[:1] == ["--verificar"]:
        return verificar(args[1])
    rehacer = "--rehacer" in args
    args = [a for a in args if a != "--rehacer"]
    filtro = None
    if "--tema" in args:
        filtro = args[args.index("--tema") + 1].lower()
        del args[args.index("--tema"): args.index("--tema") + 2]
    variantes = args or list(VARIANTES)
    sa.log = lambda *a: None
    grupos = {"billboard": {v: [] for v in variantes}, "banda": {v: [] for v in variantes}}
    for t in temas():
        if filtro and filtro not in (t["id"] + t["nombre"]).lower():
            continue
        ref = leer_lab(t["ref"])
        ests = {v: estimar(t, v, rehacer) for v in variantes}
        d, sospechoso = desfase_de(t, ref, rehacer)
        print(f"\n{t['nombre'][:46]:46s} (desfase {d:+.2f} s)" + (f"  ** SOSPECHOSO, no entra en el promedio: {sospechoso}" if sospechoso else ""))
        for v in variantes:
            p = puntuar(ref, ests[v], d)
            if not sospechoso:
                grupos["billboard" if t["billboard"] else "banda"][v].append(p)
            print(f"  {v:15s} " + "  ".join(f"{nom} {100 * _tasa(p, k):5.1f}" for k, nom in METRICAS))
    for g, filas in grupos.items():
        n = len(next(iter(filas.values()), []))
        if not n:
            continue
        titulo = (f"PROMEDIO de {n} temas de McGill Billboard (sirve para comparar variantes)" if g == "billboard" else
                  f"PROMEDIO de {n} temas de la banda (la referencia sale de la app: favorece a «actual»)")
        print("\n" + titulo)
        for v in variantes:
            cols = []
            for k, nom in METRICAS:
                if k == "seg":
                    val = np.mean([p[k][0] for p in filas[v]])
                else:
                    tot = sum(p[k][1] for p in filas[v])
                    val = sum(p[k][0] for p in filas[v]) / tot if tot else 0.0
                cols.append(f"{nom} {100 * val:5.1f}")
            print(f"  {v:15s} " + "  ".join(cols))


if __name__ == "__main__":
    main()
