# Set de prueba de transcripción (audio → notas)

Mide con números qué tan bien saca las notas un modelo, para comparar el que usa la app (Basic Pitch) con
otros antes de cambiarlo. Es el equivalente, para partituras y tabs, del set de prueba de acordes (`pruebas/`).

## Datos (no viajan con el proyecto)

| Carpeta | Qué es | De dónde |
| --- | --- | --- |
| `pruebas/guitarset/` | GuitarSet: 360 fragmentos de guitarra acústica con cada nota anotada (CC BY 4.0) | <https://zenodo.org/records/3371780> (`annotation.zip` y `audio_mono-mic.zip`, ~700 MB) |
| `pruebas/egdb/` | EGDB: guitarra eléctrica pasada por amplificadores (se usa el Plexi, con distorsión) y 5 grabaciones reales anotadas por un músico | carpeta de Google Drive enlazada en <https://ss12f32v.github.io/Guitar-Transcription> (se bajaron `README.txt`, `RealData/`, y `audio_Plexi/` + `audio_label/` del 1 al 30) |

## Uso

```powershell
python evaluar_notas.py "<ruta>\pruebas\guitarset" 05     # GuitarSet, guitarrista 05 (60 fragmentos)
python evaluar_notas.py egdb "<ruta>\pruebas\egdb"         # EGDB
```

Para YourMT3 hace falta un entorno de Python aparte (no se mezcla con el de la app):

```powershell
python -m venv venv_mt3
venv_mt3\Scripts\python -m pip install torch==2.9.1 torchaudio==2.9.1 --index-url https://download.pytorch.org/whl/cpu
venv_mt3\Scripts\python -m pip install "mt3-infer[torch]" "transformers==4.44.2" librosa soundfile
venv_mt3\Scripts\python -X utf8 yourmt3_guitarset.py "<ruta>\pruebas\guitarset" "<ruta>\pruebas\guitarset\yourmt3" 05
venv_mt3\Scripts\python -X utf8 yourmt3_carpeta.py "<ruta>\pruebas\egdb\audio_Plexi" "<ruta>\pruebas\egdb\yourmt3_plexi"
venv_mt3\Scripts\python -X utf8 yourmt3_carpeta.py "<ruta>\pruebas\egdb\RealData\Audio" "<ruta>\pruebas\egdb\yourmt3_real"
```

(`transformers` tiene que ser la 4.44: con las más nuevas YourMT3 falla.)

Métricas (las de MIREX, con `mir_eval`), en % promediado sobre los fragmentos:

- **ataque**: nota correcta = misma altura y el ataque a menos de 50 ms;
- **ataque+fin**: además el final cae cerca (decide si es negra o corchea en la partitura);
- **clase**: como «ataque» pero sin mirar la octava.

## Resultados (2026-11-19)

| Set | Basic Pitch | YourMT3 |
| --- | --- | --- |
| GuitarSet, 60 fragmentos (acústica limpia) — ataque | 81,3 | 94,1 |
| GuitarSet — ataque+fin | 58,5 | 85,5 |
| EGDB, Plexi con distorsión, 30 temas — ataque | 62,5 | 65,1 |
| EGDB, Plexi — ataque+fin | 38,1 | 48,8 |
| EGDB, 5 grabaciones reales — ataque | 76,4 | 78,9 |
| EGDB, grabaciones reales — ataque+fin | 42,9 | 56,8 |
| Velocidad en CPU (cálculo / duración del audio) | ~0,05 | 1,5–2,7 |

- **Lo más importante que salió de esto fue un error de la app**, no del modelo: al unir las ventanas de 2 s de
  Basic Pitch, las notas se atrasaban ~6 ms por segundo (0,18 s a los 30 s; más de 1 s al final de un tema).
  Arreglado en `acordes/transcribir.py`: Basic Pitch pasó de 34 % a 81 % en GuitarSet.
- Los dos modelos se entrenaron (al menos en parte) con GuitarSet: ahí la diferencia exagera. Con guitarra
  eléctrica, que ninguno vio, YourMT3 saca ~2,5 puntos más en notas y 10-14 más en duraciones.
- YourMT3 no se adoptó por ahora: es 30-50 veces más lento (un tema de 4 minutos sumaría unos 6 minutos por
  pista transcripta), pesa 536 MB (no entra en el repo de GitHub), pide una versión vieja de `transformers` y
  su código es GPL-3.0 (usarlo dentro de la app obligaría a publicarla bajo GPL).
