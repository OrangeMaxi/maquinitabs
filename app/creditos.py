"""Instrumentos de un tema según fuentes públicas, para saber qué hay en la pista «otros» y cómo llamarla.

    instrumentos(titulo, artista) -> {"instrumentos": [...], "otros": "Sintetizador, saxo y clarinete" | "",
                                      "disco": "...", "fuentes": [urls]}

1. MusicBrainz (musicbrainz.org, datos abiertos): la grabación del disco original (el álbum oficial más viejo
   que la contiene) y sus créditos por instrumento; de ahí sale también el nombre del disco.
2. Wikipedia (es y en): la sección de músicos/personal de la página de ese disco. Es por disco, no por tema:
   puede nombrar instrumentos que en este tema no suenan.
Sin internet, o si no se encuentra nada, devuelve listas vacías y la pista queda como «Otros».
"""
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request

UA = {"User-Agent": "Maquinitabs/0.2 ( https://github.com/OrangeMaxi/maquinitabs )"}

# palabra clave (sin tildes, en minúscula; es o en) -> (nombre a mostrar, pista de demucs donde cae)
INSTRUMENTOS = [
    (r"sintetizador|synth|moog|vocoder|mellotron", "sintetizador", "otros"),
    (r"clavinet", "clavinet", "piano"),
    (r"piano electrico|electric piano|rhodes|wurlitzer", "piano eléctrico", "piano"),
    (r"organo|organ|hammond", "órgano", "otros"),
    (r"piano", "piano", "piano"),
    (r"teclado|keyboard", "teclados", "piano"),
    (r"saxo|saxophone", "saxo", "otros"),
    (r"trompeta|trumpet|flugelhorn|fliscorno", "trompeta", "otros"),
    (r"trombon|trombone", "trombón", "otros"),
    (r"clarinete|clarinet", "clarinete", "otros"),
    (r"flauta|flute", "flauta", "otros"),
    (r"corno|french horn|\bhorns?\b|vientos|brass", "vientos", "otros"),
    (r"violin|viola|violonchelo|chelo|cello|cuerdas|strings", "cuerdas", "otros"),
    (r"bandoneon", "bandoneón", "otros"),
    (r"acordeon|accordion", "acordeón", "otros"),
    (r"armonica|harmonica", "armónica", "otros"),
    (r"charango|quena|sikus?|zampona|bombo leguero", "instrumentos andinos", "otros"),
    (r"guitarra|guitar", "guitarra", "guitar"),
    (r"\bbajo\b|\bbass\b", "bajo", "bass"),
    (r"bateria|drums|caja de ritmos|drum machine", "batería", "drums"),
]


def _sin_tildes(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def _get(url, reintentos=4):
    for i in range(reintentos):
        time.sleep(1.1 + 2 * i)          # MusicBrainz pide no más de un pedido por segundo
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:      # 503 = servicio ocupado: se reintenta
            if e.code not in (429, 502, 503, 504) or i == reintentos - 1:
                raise
    return None


def _clasificar(texto):
    """Texto libre ('saxofón, clarinete y guitarra rítmica') -> [(nombre, pista)] sin repetir."""
    t = _sin_tildes(texto)
    out = []
    for patron, nombre, pista in INSTRUMENTOS:
        if re.search(patron, t) and nombre not in [n for n, _ in out]:
            # «piano eléctrico» no es además «piano»
            if nombre == "piano" and "piano electrico" in [_sin_tildes(n) for n, _ in out] \
                    and not re.search(r"piano(?! electrico)", t):
                continue
            out.append((nombre, pista))
    return out


def _musicbrainz(titulo, artista):
    mb = "https://musicbrainz.org/ws/2/"
    t = re.sub(r"[’`´]", "'", titulo)
    q = urllib.parse.quote(f'recording:"{t}" AND artist:"{artista}" AND status:official AND primarytype:album')
    recs = (_get(f"{mb}recording?query={q}&limit=100&fmt=json") or {}).get("recordings", [])
    junto = lambda s: re.sub(r"\W", "", _sin_tildes(s))
    recs = [r for r in recs if junto(artista) in junto(" ".join(a.get("name", "") for a in r.get("artist-credit", [])))]

    def discos(r):          # álbumes oficiales de estudio que tienen esta grabación, del más viejo al más nuevo
        ok = [x for x in r.get("releases", []) if x.get("status") == "Official"
              and (x.get("release-group") or {}).get("primary-type") == "Album"
              and not (x.get("release-group") or {}).get("secondary-types")]      # ni compilados ni en vivo
        return sorted(ok, key=lambda x: x.get("date") or "9999")

    recs = [r for r in recs if r.get("score", 0) >= 90 and discos(r)]
    recs.sort(key=lambda r: discos(r)[0].get("date") or "9999")
    primero = None
    for r in recs[:4]:          # la del disco original suele tener los créditos; si no, la que los tenga
        d = _get(f"{mb}recording/{r['id']}?inc=artist-rels&fmt=json") or {}
        inst = [" ".join(x.get("attributes") or []) for x in d.get("relations", []) if x.get("type") == "instrument"]
        dato = {"instrumentos": inst, "disco": discos(r)[0].get("title", ""), "fuente": f"https://musicbrainz.org/recording/{r['id']}"}
        primero = primero or dato
        if inst:
            return dato
    return primero or {"instrumentos": [], "disco": "", "fuente": ""}


def _wikipedia(disco, artista):
    if not disco:
        return "", ""
    for lang, palabra in (("es", "álbum"), ("en", "album")):
        api = f"https://{lang}.wikipedia.org/w/api.php?"
        s = _get(api + urllib.parse.urlencode({"action": "query", "list": "search", "format": "json", "formatversion": 2,
                                               "srsearch": f"{disco} {artista} {palabra}", "srlimit": 3}), 1) or {}
        for h in s.get("query", {}).get("search", []):
            # solo la página del disco (no la de la banda, que mezcla formaciones de todas las épocas)
            if _sin_tildes(disco) not in _sin_tildes(h["title"]):
                continue
            w = (_get(api + urllib.parse.urlencode({"action": "parse", "page": h["title"], "prop": "wikitext",
                                                    "format": "json", "formatversion": 2}), 1) or {})
            w = w.get("parse", {}).get("wikitext", "")
            m = re.search(r"==\s*(Personal|Músicos|Créditos|Personnel|Integrantes|Formación|Musicians)[^=\n]*==(.*?)(?=\n==[^=]|\Z)",
                          w, re.S | re.I)
            if m:
                texto = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", m.group(2))      # [[a|b]] -> b
                return texto, f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(h["title"].replace(" ", "_"))
    return "", ""


def nombre_otros(encontrados):
    """Nombre para la pista «otros» con lo que no cae en voz, guitarra, piano, bajo ni batería."""
    ns = [n for n, p in encontrados if p == "otros"]
    if not ns:
        return ""
    ns = [n.capitalize() if i == 0 else n for i, n in enumerate(ns[:3])]
    return ns[0] if len(ns) == 1 else ", ".join(ns[:-1]) + " y " + ns[-1]


def instrumentos(titulo, artista):
    """otros: nombre para la pista «otros» SOLO si sale de los créditos de esta grabación.
    en_el_disco: lo que figura en la ficha del disco y caería en «otros» (puede no sonar en este tema)."""
    out = {"instrumentos": [], "otros": "", "en_el_disco": "", "disco": "", "fuentes": []}
    try:
        m = _musicbrainz(titulo, artista)
    except Exception:  # noqa: BLE001  (sin internet, servicio caído)
        return out
    enc = _clasificar(" , ".join(m["instrumentos"]))
    out["disco"] = m["disco"]
    if m["fuente"]:
        out["fuentes"].append(m["fuente"])
    out["otros"] = nombre_otros(enc)
    if not enc:
        try:
            w, url = _wikipedia(m["disco"], artista)
        except Exception:  # noqa: BLE001
            w, url = "", ""
        if w:
            enc = _clasificar(w)
            out["en_el_disco"] = nombre_otros(enc)
            out["fuentes"].append(url)
    out["instrumentos"] = [n for n, _ in enc]
    return out


if __name__ == "__main__":
    import sys
    print(json.dumps(instrumentos(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=1))
