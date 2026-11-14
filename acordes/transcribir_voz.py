"""
Transcribe la pista de voz (stem vocals) con faster-whisper y guarda los tiempos de cada frase.

Uso:
  python transcribir_voz.py "<carpeta del tema>" [--modelo small] [--idioma es]

Crea <carpeta>\\analisis\\voz_tiempos.json: [{"ini": s, "fin": s, "texto": "..."}]
Sirve para ubicar secciones por la letra ("el coro empieza en ...").
"""
import argparse
import json
import os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("carpeta")
    ap.add_argument("--modelo", default="small")
    ap.add_argument("--idioma", default="es")
    a = ap.parse_args()

    from faster_whisper import WhisperModel

    voz = os.path.join(a.carpeta, "audio", "vocals.wav")
    modelo = WhisperModel(a.modelo, device="cpu", compute_type="int8")
    segs, _ = modelo.transcribe(voz, language=a.idioma, vad_filter=True, word_timestamps=True)
    out = [{"ini": round(s.start, 2), "fin": round(s.end, 2), "texto": s.text.strip()} for s in segs]
    ruta = os.path.join(a.carpeta, "analisis", "voz_tiempos.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"{len(out)} frases -> {ruta}")


if __name__ == "__main__":
    main()
