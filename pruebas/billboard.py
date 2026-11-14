"""Lee las anotaciones del McGill Billboard Project (salami_chords.txt) y las pasa a acordes con tiempos.

El conjunto (Burgoyne, Wild y Fujinaga, ISMIR 2011; ddmal.music.mcgill.ca) trae, por tema, los acordes de
cada compás escritos por músicos expertos, con el tiempo en que empieza cada frase. Acá cada frase se
reparte entre sus compases según cuántos pulsos tiene cada uno (un compás suelto de 2/4 dura la mitad que
uno de 4/4), y cada compás en partes iguales entre sus acordes.
"""
import re

import numpy as np

METRO = re.compile(r"\((\d+)/(\d+)\)")


def _negras(metro):
    m = re.match(r"(\d+)/(\d+)", metro or "")
    return int(m.group(1)) * 4.0 / int(m.group(2)) if m else 4.0


def leer(ruta):
    """-> (meta, [(inicio, fin, acorde en sintaxis Harte)], duración).
    'X' = tramo sin anotar o de duración incierta (mir_eval no lo cuenta)."""
    meta, lineas, metro = {}, [], "4/4"
    with open(ruta, encoding="utf-8") as f:
        for l in f:
            l = l.rstrip("\n")
            if l.startswith("#"):
                k, _, v = l[1:].partition(":")
                meta.setdefault(k.strip(), v.strip())      # el primero: título, artista, metro y tónica iniciales
                if k.strip() == "metre":
                    metro = v.strip()                       # los "# metre:" a mitad de archivo valen desde ahí
            elif l.strip():
                t, _, txt = l.partition("\t")
                lineas.append((float(t), txt.strip(), metro))

    # cada frase -> lista de compases (fichas, peso en negras); "&pause" no es un compás (peso None)
    frases = []
    for (t0, txt, metro), (t1, _, _) in zip(lineas, lineas[1:]):
        if "|" not in txt:
            frases.append((t0, t1, None, "N" if re.match(r"^(silence|end|Z)\b", txt) else "X"))
            continue
        cuerpo = txt[txt.index("|"): txt.rindex("|") + 1]
        rep = re.search(r"\bx(\d+)\b", txt[txt.rindex("|") + 1:])
        compases = []
        for comp in [c.strip() for c in cuerpo.strip("|").split("|")] * (int(rep.group(1)) if rep else 1):
            if comp == "&pause":
                compases.append((["&pause"], None))
                continue
            en_linea = METRO.search(comp)
            fichas = [x for x in comp.split() if not METRO.fullmatch(x)] or ["."]
            compases.append((fichas, _negras(en_linea.group(0)[1:-1]) if en_linea else _negras(metro)))
        frases.append((t0, t1, compases, None))

    # segundos por negra del tema: mediana de las frases sin pausas (para saber cuánto dura una pausa)
    spn = [(t1 - t0) / sum(p for _, p in cs) for t0, t1, cs, _ in frases if cs and all(p for _, p in cs)]
    spn = float(np.median(spn)) if spn else None

    tramos, previo = [], "X"
    for t0, t1, cs, fijo in frases:
        if cs is None:
            tramos.append((t0, t1, fijo))
            continue
        total = sum(p for _, p in cs if p)
        con_pausa = any(p is None for _, p in cs)
        if con_pausa and spn and total * spn < (t1 - t0):
            unidad, pausa = spn, ((t1 - t0) - total * spn) / sum(1 for _, p in cs if p is None)
        else:
            unidad, pausa = (t1 - t0) / max(total, 1e-9), 0.0
        t = t0
        for fichas, peso in cs:
            if peso is None:                    # pausa: no se sabe si el acorde sigue sonando -> no se cuenta
                if pausa > 0:
                    tramos.append((t, t + pausa, "X"))
                t += pausa
                continue
            paso = peso * unidad / len(fichas)
            for x in fichas:
                if x == ".":
                    x = previo
                elif x == "&pause":
                    x = "N"
                elif x == "*" or not re.match(r"^([A-G][b#]*|N)", x):
                    x = "X"
                previo = x
                tramos.append((t, t + paso, x))
                t += paso
    unidos = []
    for a, b, x in tramos:
        if b - a < 1e-6:
            continue
        if unidos and unidos[-1][2] == x and abs(unidos[-1][1] - a) < 1e-6:
            unidos[-1] = (unidos[-1][0], b, x)
        else:
            unidos.append((a, b, x))
    return meta, unidos, lineas[-1][0] if lineas else 0.0


def escribir_lab(tramos, ruta):
    with open(ruta, "w", encoding="utf-8") as f:
        for a, b, x in tramos:
            f.write(f"{a:.3f}\t{b:.3f}\t{x}\n")
