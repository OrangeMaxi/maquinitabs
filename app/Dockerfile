# Maquinitabs — imagen Docker (CPU).
# El contexto de build es la carpeta _herramientas (la app usa acordes/sacar_acordes.py):
#   docker compose -f _herramientas/app/docker-compose.yml up -d --build
FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
 && rm -rf /var/lib/apt/lists/*

# yt-dlp necesita un runtime de JavaScript para YouTube
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

WORKDIR /maquinitabs
COPY app/requirements.txt app/requirements.txt
RUN pip install --no-cache-dir torch==2.9.1 torchaudio==2.9.1 --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r app/requirements.txt

# El modelo de separación en 6 pistas (htdemucs_6s) viaja con el proyecto, en modelos/, y queda dentro de
# la imagen: el build no depende del servidor de descarga original (dl.fbaipublicfiles.com), que en
# noviembre de 2026 tenía el certificado vencido. Si el archivo no está, la línea de abajo intenta bajarlo.
ENV TORCH_HOME=/opt/modelos
COPY modelos/ /opt/modelos/
RUN python -c "from demucs.pretrained import get_model; get_model('htdemucs_6s')"

# modelo de transcripción de guitarra y piano (Basic Pitch, va en acordes/basic_pitch)
RUN pip install --no-cache-dir onnxruntime==1.31.1

# pulsos y compases con Beat This! (los pesos van en modelos/beat_this, ya copiados arriba)
RUN pip install --no-cache-dir beat-this==1.1.0 einops==0.8.1 soxr==1.1.0 rotary-embedding-torch==0.9.2

COPY acordes/sacar_acordes.py acordes/btc_acordes.py acordes/transcribir.py acordes/
COPY acordes/btc/ acordes/btc/
COPY acordes/basic_pitch/ acordes/basic_pitch/
COPY app/ app/

ENV HOST=0.0.0.0 PORT=5055 CANCIONES_RAIZ=/canciones \
    NUMBA_CACHE_DIR=/tmp/numba PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
VOLUME /canciones
EXPOSE 5055
CMD ["python", "app/server.py"]
