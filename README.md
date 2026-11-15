# Maquinitabs

De un link de YouTube a la sala de ensayo. Pegás el link de una canción y la app:

- baja el audio y lo separa en **voz, guitarra, piano, bajo, batería y otros**;
- saca **acordes, tempo, compás, tonalidad y estructura** (intro, verso, estribillo…);
- arma la **hoja de acordes**, y la **partitura y tablatura** de guitarra, piano, bajo y voz;
- deja **mutear o aislar pistas, transportar**, usar **metrónomo** y cuenta previa, y repetir una sección;
- sugiere **escalas para improvisar** e ideas de arreglo;
- permite **corregir a mano** acordes y compases mientras escuchás el tema («Editar hoja»).

Todo corre en la computadora donde se instala: no usa servicios externos, salvo YouTube para bajar el audio.
Los resultados son automáticos y hay que revisarlos de oído.

## Qué compartir

La carpeta `_herramientas` completa (unos 170 MB). Adentro va todo lo necesario:

| Carpeta | Contenido |
| --- | --- |
| `app/` | La aplicación: servidor, análisis, interfaz, `Dockerfile` y `docker-compose.yml` |
| `acordes/` | Detector de acordes y los modelos de acordes (BTC) y de transcripción (Basic Pitch) |
| `modelos/` | Modelos de separación en 6 pistas (demucs `htdemucs_6s`) y de pulsos y compases (Beat This!) |

Las canciones no viajan con el proyecto: cada equipo guarda las suyas (ver «Dónde quedan las canciones»).

## Opción 1: con Docker (recomendada para otro equipo)

Sirve en Windows, Mac y Linux. Solo hace falta tener instalado
[Docker Desktop](https://www.docker.com/products/docker-desktop/) y abierto.

En Windows, doble clic en **`Iniciar con Docker.bat`**. En cualquier sistema, desde la carpeta `_herramientas`:

```bash
docker compose -f app/docker-compose.yml up -d --build
```

Después abrí <http://localhost:5055>.

La primera vez tarda entre 10 y 20 minutos, porque descarga unos 2 GB de componentes; las siguientes arranca
en segundos. Para apagarla:

```bash
docker compose -f app/docker-compose.yml down
```

### Dónde quedan las canciones

Por defecto en `app/canciones`. Para usar otra carpeta, definí la variable `CANCIONES` antes de arrancar:

```powershell
$env:CANCIONES = "E:\Música\banda sin nombre"
```

```bash
export CANCIONES="/ruta/a/mis/canciones"
```

Cada tema ocupa entre 200 y 650 MB (audio original más las pistas separadas). Para pasarle a alguien un tema
ya analizado, copiá su carpeta completa dentro de la carpeta de canciones del otro equipo.

### Usarla desde otro dispositivo de la misma red

Con la app corriendo en una compu, desde el celular, la tablet u otra compu conectada al mismo wifi abrí
`http://<IP de la compu>:5055`, por ejemplo `http://192.168.0.23:5055`.

Para saber la IP: `ipconfig` en Windows (línea «Dirección IPv4»), `ipconfig getifaddr en0` en Mac,
`hostname -I` en Linux. Si no carga, casi siempre es el firewall: en Windows hay que permitir a Docker Desktop
en redes privadas cuando lo pregunta.

### Llevar la imagen ya construida (sin internet en el otro equipo)

```bash
docker save maquinitabs -o maquinitabs.tar
```

Se copia `maquinitabs.tar` (unos 3 GB) junto con la carpeta `_herramientas` y en el otro equipo:

```bash
docker load -i maquinitabs.tar
```

```bash
docker compose -f app/docker-compose.yml up -d
```

### En un servidor en internet (para usarla desde cualquier lado)

La carpeta `servidor/` la deja en un servidor con HTTPS y usuario y contraseña, por ejemplo en el plan
gratuito de Oracle Cloud. Paso a paso en [servidor/GUIA-ORACLE.md](servidor/GUIA-ORACLE.md).

## Opción 2: sin Docker (Windows)

Hace falta **Python 3.11** y **ffmpeg** en el PATH. Desde la carpeta `_herramientas`:

```powershell
pip install torch==2.9.1 torchaudio==2.9.1 --index-url https://download.pytorch.org/whl/cpu
```

```powershell
pip install -r app\requirements.txt onnxruntime==1.31.1 beat-this==1.1.0 einops soxr rotary-embedding-torch
```

```powershell
python app\server.py
```

Las canciones se guardan en la carpeta que contiene a `_herramientas`. Para usar otra, definí la variable
`CANCIONES_RAIZ` antes de arrancar. Para entrar desde otro dispositivo de la red, además definí `HOST=0.0.0.0`.

## Cómo se usa

1. Pegá un link de YouTube arriba y tocá **Analizar** (la locomotora), o subí un archivo de audio con la
   flecha de al lado (mp3, m4a, wav, flac…; nombre ideal «Artista - Tema.mp3»). Una canción tarda entre 5 y 10 minutos la primera vez
   (casi todo es la separación en pistas; depende del procesador).
2. Cuando termina se abre sola. A la izquierda están las pistas (M = mutear, S = solo, volumen) y la lista
   de canciones. El botón de arriba a la izquierda muestra u oculta ese panel (oculto, la hoja ocupa toda
   la pantalla: útil en una tablet). La app recuerda la elección. La última pista es el **metrónomo**: M lo prende o apaga, y tiene su propio volumen.
3. Pestañas:
   - **Acordes y estructura**: la hoja de guitarra o de piano, con diagramas. Muestra solo lo que toca ese
     instrumento, sacado de su propia pista: el acorde que forman sus notas, ♪ si toca una línea o notas
     sueltas (están en la partitura) y – si no suena. Nunca se rellena con lo que toca el bajo u otro
     instrumento. La armonía completa del tema se ve en **Editar hoja**. Clic en un compás para saltar ahí.
   - **Guitarra / Piano / Otros / Bajo / Voz**: partitura (y tablatura en guitarra y bajo). «Otros» es lo que
     no es voz, guitarra, piano, bajo ni batería (sintes, vientos, cuerdas…); también tiene su hoja de acordes.
     Al analizar, la app busca en MusicBrainz y Wikipedia qué instrumentos tiene el tema: si los créditos son
     de esa grabación, la pista toma ese nombre (p. ej. «Sintetizador, saxo y trompeta»); si solo están los
     del disco, se mencionan como referencia. Sin internet (o con `SIN_INTERNET=1`) queda como «Otros».
   - **Improvisación**: escalas recomendadas e ideas de arreglo por sección.
4. Abajo: volver al principio (tecla Inicio), reproducir (barra espaciadora), los botones **Cuenta**
   (un compás de clics antes de arrancar) y **Repetir** (verde = prendido; elegís desde qué compás hasta
   cuál, arranca con la sección que está sonando y el tramo queda marcado en la hoja) y transporte de tonalidad
   (cambia el audio y toda la notación).
5. **Imprimir** saca la vista actual en papel o PDF.

### Corregir la hoja

El compás (3/4 o 4/4) se detecta solo. Si quedó mal, o hay acordes equivocados, tocá **Editar hoja**:

- **Compás del tema**: 3/4 o 4/4. Vuelve a analizar el tema (menos de un minuto).
- Clic en un compás y escribí los acordes, una casilla por pulso. Vacía = sigue el acorde anterior;
  `nc` = sin acorde. Acepta cifrado americano o solfeo (`Am7`, `lam7`, `Sib`). Enter guarda y pasa al siguiente.
- **Escuchar** reproduce solo ese compás.
- **Pulsos del compás (− / +)**, **Partir en dos** y **Unir con el siguiente** mueven las barras de compás.
- **Volver a lo detectado** borra todas las correcciones del tema.

**Secciones** permite cambiar los nombres y los tiempos de las partes del tema.

Las correcciones se guardan en la carpeta de cada tema (`correcciones.json` y `estructura.txt`).

## Problemas frecuentes

- **«No se puede acceder» en localhost:5055**: Docker Desktop no está abierto, o el contenedor no arrancó.
  Mirá el registro con `docker logs maquinitabs`.
- **Falla la descarga de un link**: YouTube cambia seguido. Reconstruí la imagen para traer la última
  versión de `yt-dlp`: `docker compose -f app/docker-compose.yml build --no-cache`.
- **El puerto 5055 está ocupado**: definí `PUERTO` antes de arrancar, por ejemplo `$env:PUERTO = "8080"`.
- **Va muy lento**: la separación usa solo el procesador. En Docker Desktop conviene asignarle al menos
  4 núcleos y 6 GB de memoria (Settings → Resources).

## Límites conocidos

- Los acordes, la estructura y sobre todo las partituras son una base para corregir, no una transcripción fiel.
- La detección del compás puede fallar en ritmos irregulares (por ejemplo el 3+3+2 del tango).
- Solo distingue compases de 3 y de 4 pulsos de forma automática; otros se marcan a mano.
- Guitarras muy distorsionadas se transcriben nota por nota en lugar de acordes.

## Créditos y licencias de los modelos

- Separación de pistas: [Demucs](https://github.com/facebookresearch/demucs) (`htdemucs_6s`), licencia MIT.
- Acordes: [BTC-ISMIR19](https://github.com/jayg996/BTC-ISMIR19), licencia MIT (`acordes/btc/LICENSE`), con los
  pesos re-entrenados de [ChordMini](https://github.com/ptnghia-j/ChordMini), licencia MIT.
- Pulsos y compases: [Beat This!](https://github.com/CPJKU/beat_this), licencia MIT.
- Transcripción de guitarra y piano: [Basic Pitch](https://github.com/spotify/basic-pitch) de Spotify,
  licencia Apache 2.0 (`acordes/basic_pitch/LICENSE`).
- Partituras: [VexFlow](https://www.vexflow.com/), licencia MIT.

Usá la app con música que tengas derecho a descargar.
