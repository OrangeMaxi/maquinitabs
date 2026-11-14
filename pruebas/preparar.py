"""Arma el set de prueba: referencias de McGill Billboard + audio de YouTube separado en pistas.

    python preparar.py <carpeta McGill-Billboard> <id> [<id> ...]

Por cada id: escribe referencias\\<id>.lab, busca en YouTube la grabación cuya duración coincide con la
anotada (± 4 s), la baja a canciones\\<id> <Título> - <Artista>\\ y la separa con demucs (5-10 min por tema).
Lo que ya está hecho se saltea. Deja el listado en temas.json.
"""
import csv
import json
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "app"))
import analisis  # noqa: E402
import billboard  # noqa: E402

CANCIONES = os.path.join(AQUI, "canciones")
REFS = os.path.join(AQUI, "referencias")
TEMAS = os.path.join(AQUI, "temas.json")


def buscar(artista, titulo, duracion):
    r = subprocess.run(["yt-dlp", "-J", "--flat-playlist", "--no-warnings", f"ytsearch8:{artista} {titulo}"],
                       capture_output=True, check=True)
    cand = [e for e in json.loads(r.stdout.decode("utf-8", "replace")).get("entries", []) if e.get("duration")]
    cand = sorted(cand, key=lambda e: abs(e["duration"] - duracion))
    if not cand or abs(cand[0]["duration"] - duracion) > 4:
        return None
    return cand[0]


def main():
    raiz, ids = sys.argv[1], [int(x) for x in sys.argv[2:]]
    os.makedirs(CANCIONES, exist_ok=True)
    os.makedirs(REFS, exist_ok=True)
    temas = json.load(open(TEMAS, encoding="utf-8")) if os.path.exists(TEMAS) else {}
    for i in ids:
        clave = f"{i:04d}"
        try:
            meta, tramos, dur = billboard.leer(os.path.join(raiz, clave, "salami_chords.txt"))
            billboard.escribir_lab(tramos, os.path.join(REFS, clave + ".lab"))
            titulo, artista = analisis.sa.limpiar(meta["title"]), analisis.sa.limpiar(meta["artist"])
            # el conjunto repite temas con otro id: si ya está, pesaría doble en el promedio
            igual = next((k for k, t in temas.items() if k != clave and t["titulo"].lower() == titulo.lower()
                          and t["artista"].lower() == artista.lower()), None)
            if igual:
                print(clave, titulo, "-> repetido de", igual, "(se saltea)", flush=True)
                continue
            base = os.path.join(CANCIONES, f"{clave} {titulo} - {artista}")
            wav = os.path.join(base, "audio", titulo + ".wav")
            if not os.path.exists(wav):
                v = buscar(meta["artist"], meta["title"], dur)
                if not v:
                    print(clave, titulo, "-> no encontré una grabación de", round(dur), "s", flush=True)
                    continue
                os.makedirs(os.path.join(base, "audio"), exist_ok=True)
                os.makedirs(os.path.join(base, "analisis"), exist_ok=True)
                url = "https://www.youtube.com/watch?v=" + v["id"]
                subprocess.run(["yt-dlp", "-q", "--no-playlist", "-x", "--audio-format", "wav",
                                "-o", os.path.join(base, "audio", titulo + ".%(ext)s"), url], check=True)
                with open(os.path.join(base, "analisis", "meta.json"), "w", encoding="utf-8") as f:
                    json.dump({"titulo": titulo, "artista": artista, "fuente": url}, f, ensure_ascii=False)
                print(clave, titulo, "-> bajado:", v.get("title"), v["duration"], "s (anotado", round(dur), "s)", flush=True)
            analisis.separar(base)
            temas[clave] = {"carpeta": os.path.basename(base), "titulo": titulo, "artista": artista,
                            "metro": meta.get("metre", ""), "tonica": meta.get("tonic", "")}
            with open(TEMAS, "w", encoding="utf-8") as f:
                json.dump(temas, f, ensure_ascii=False, indent=1)
            print(clave, titulo, "-> listo", flush=True)
        except Exception as e:  # noqa: BLE001
            print(clave, "ERROR", repr(e)[:300], flush=True)


if __name__ == "__main__":
    main()
