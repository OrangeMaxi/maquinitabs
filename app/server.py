"""
Maquinitabs — servidor de la app (Flask). Abrir con:  python server.py   ->  http://localhost:5055
"""
import json
import os
import queue
import re
import threading
import time
import traceback
import uuid

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

import analisis

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.environ.get("CANCIONES_RAIZ") or os.path.dirname(os.path.dirname(AQUI))
PUERTO = int(os.environ.get("PORT", 5055))

app = Flask(__name__, static_folder=os.path.join(AQUI, "static"), static_url_path="")

trabajos = {}            # id -> {id, titulo, etapa, pct, estado, cancion, error}
cola = queue.Queue()
candados = {}
candado_global = threading.Lock()
candado_json = threading.Lock()


def carpeta_de(cid):
    if not cid or cid.startswith(("_", ".")) or re.search(r'[\\/:*?"<>|]', cid):
        abort(404)
    base = os.path.join(RAIZ, cid)
    if not os.path.isdir(os.path.join(base, "audio")):
        abort(404)
    return base


def trabajador():
    while True:
        t = cola.get()
        try:
            t["estado"] = "en curso"

            def progreso(etapa, pct=None):
                t["etapa"] = etapa
                if pct is not None:
                    t["pct"] = pct

            base = t.get("base")
            if t.get("url"):
                base = analisis.descargar(t["url"], RAIZ, progreso)
                t["cancion"] = os.path.basename(base)
                t["titulo"] = t["cancion"]
                analisis.separar(base, progreso)
            analisis.analizar(base, t.get("compas"), progreso)
            t["estado"] = "listo"
            t["pct"] = 100
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            t["estado"] = "error"
            t["error"] = str(e)[-500:]
        t["fin"] = time.time()


threading.Thread(target=trabajador, daemon=True).start()


def encolar(**datos):
    t = {"id": uuid.uuid4().hex[:8], "etapa": "En cola…", "pct": 0, "estado": "en cola", **datos}
    trabajos[t["id"]] = t
    cola.put(t)
    return t


def publico(t):
    return {k: t.get(k) for k in ("id", "titulo", "etapa", "pct", "estado", "cancion", "error")}


@app.get("/")
def inicio():
    return send_from_directory(app.static_folder, "index.html")


@app.after_request
def sin_cache(r):
    if request.path.endswith((".js", ".css", ".html")) or request.path == "/":
        r.headers["Cache-Control"] = "no-store"
    return r


@app.get("/api/canciones")
def lista():
    out = []
    for n in sorted(os.listdir(RAIZ), key=str.lower):
        base = os.path.join(RAIZ, n)
        if n.startswith(("_", ".")) or not os.path.exists(os.path.join(base, "audio", "vocals.wav")):
            continue
        titulo, _, artista = n.partition(" - ")
        out.append({"id": n, "titulo": titulo, "artista": artista,
                    "analizada": os.path.exists(os.path.join(base, "analisis", "app.json")),
                    "pistas": len(analisis.pistas_de(base))})
    return jsonify(out)


@app.post("/api/canciones")
def nueva():
    d = request.get_json(force=True)
    url = (d.get("url") or "").strip()
    if not re.match(r"^https?://([\w-]+\.)?(youtube\.com|youtu\.be)/", url):
        return jsonify({"error": "Pegá un link de YouTube (youtube.com o youtu.be)."}), 400
    return jsonify(publico(encolar(url=url, titulo=url)))


@app.post("/api/canciones/<cid>/analizar")
def reanalizar(cid):
    base = carpeta_de(cid)
    return jsonify(publico(encolar(base=base, cancion=cid, titulo=cid)))


@app.get("/api/trabajos")
def ver_trabajos():
    ahora = time.time()
    return jsonify([publico(t) for t in trabajos.values() if ahora - t.get("fin", ahora) < 600])


@app.get("/api/canciones/<cid>")
def cancion(cid):
    ruta = os.path.join(carpeta_de(cid), "analisis", "app.json")
    if not os.path.exists(ruta):
        abort(404)
    return send_file(ruta, mimetype="application/json", max_age=0)


@app.route("/api/canciones/<cid>/estructura", methods=["GET", "PUT"])
def estructura(cid):
    base = carpeta_de(cid)
    ruta = os.path.join(base, "estructura.txt")
    if request.method == "PUT":
        d = request.get_json(force=True)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(d.get("texto", ""))
        return jsonify(publico(encolar(base=base, cancion=cid, titulo=cid)))
    texto = ""
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            texto = f.read()
    return jsonify({"texto": texto})


@app.put("/api/canciones/<cid>/correcciones")
def correcciones(cid):
    """Guarda las correcciones hechas a mano (acordes por pulso, dónde cae el 1 de cada compás, compás del
    tema). Acordes y compases se aplican al instante; cambiar el compás del tema vuelve a analizar."""
    base = carpeta_de(cid)
    ruta = os.path.join(base, "analisis", "app.json")
    if not os.path.exists(ruta):
        abort(404)
    d = request.get_json(force=True)
    try:
        corr = {
            "compas": int(d["compas"]) if d.get("compas") else None,
            "acordes": [[float(t), str(a)[:16]] for t, a in d.get("acordes") or []],
            "unos": [float(t) for t in d.get("unos") or []] or None,
        }
    except (TypeError, ValueError):
        return jsonify({"error": "Correcciones mal formadas."}), 400
    if corr["compas"] not in (None, 2, 3, 4, 5, 6, 7):
        return jsonify({"error": "Compás no válido."}), 400
    with candado_json:
        with open(ruta, encoding="utf-8") as f:
            out = json.load(f)
        if corr["compas"] and corr["compas"] != out.get("compas"):
            corr["unos"] = None          # las barras de compás puestas a mano eran para el compás anterior
            analisis.guardar_correcciones(base, corr)
            return jsonify({"trabajo": publico(encolar(base=base, cancion=cid, titulo=cid))})
        analisis.aplicar_correcciones(out, corr)
        analisis.guardar_correcciones(base, out["correcciones"])
        analisis.guardar(base, out)
    return jsonify({"cancion": out})


@app.get("/api/canciones/<cid>/audio/<pista>")
def audio(cid, pista):
    base = carpeta_de(cid)
    if pista not in {p["id"] for p in analisis.pistas_de(base)}:
        abort(404)
    st = max(-6, min(6, int(request.args.get("st", 0))))
    clave = (cid, pista, st)
    with candado_global:
        c = candados.setdefault(clave, threading.Lock())
    with c:
        ruta = analisis.transportar(base, pista, st)
    return send_file(ruta, conditional=True, max_age=0)


if __name__ == "__main__":
    # HOST=0.0.0.0 (Docker, o para entrar desde otro dispositivo de la red); por defecto solo esta compu
    HOST = os.environ.get("HOST", "127.0.0.1")
    print(f"Maquinitabs · canciones en: {RAIZ}\nAbrí http://localhost:{PUERTO}", flush=True)
    try:
        from waitress import serve
        serve(app, host=HOST, port=PUERTO, threads=12)
    except ImportError:
        app.run(host=HOST, port=PUERTO, threaded=True)
