# Cambios

Lo nuevo de cada versión de Maquinitabs, de la más reciente a la más vieja. Los números siguen el
[versionado semántico](https://semver.org/lang/es/) (MAYOR.MENOR.PARCHE) y el formato, el de
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Cómo sacar una versión: ver «Versiones» en el README.

## [Sin publicar]

### Arreglado

- **Las notas de guitarra, piano y otros se atrasaban** a lo largo del tema (~6 ms por segundo: más de 1 s al
  final de un tema de 4 minutos), al unir las ventanas del modelo Basic Pitch. En la partitura y la tab caían en
  la semicorchea equivocada, y la hoja de acordes por instrumento salía corrida. Medido con GuitarSet: las notas
  correctas pasaron de 34 % a 81 %. Hay que volver a analizar los temas para verlo (las transcripciones
  guardadas se rehacen solas).

### Agregado

- Set de prueba de transcripción (`pruebas/transcripcion`): compara modelos nota por nota con GuitarSet y EGDB
  (guitarra eléctrica). Se probó YourMT3: mejora poco con guitarra eléctrica y es 30-50 veces más lento.

## [1.2.0] - 2026-11-19

### Agregado

- **Interfaz para celular.**
  - La barra de arriba entra en un solo renglón.
  - El panel de pistas y canciones es un cajón que se abre encima de la hoja: arranca abierto con la lista de
    temas, se cierra al elegir uno y se abre al analizar para ver el progreso.
  - Las pestañas se deslizan a lo ancho, y el reproductor ocupa dos renglones (uno con el celular acostado).
  - En la hoja: diagramas en una tira que se desliza, compases con más de un acorde que ya no se cortan,
    partitura de a un compás por renglón y la tabla de improvisación como tarjetas.
  - Los campos tienen 16 px, para que el iPhone no haga zoom al tocarlos.
- **Configuración** en los engranajes del logo, guardada en cada navegador:
  - tema claro, oscuro o del sistema;
  - hoja oscura para poca luz;
  - tamaño de la hoja;
  - compases por renglón;
  - cifrado americano (C, Am) o latino (Do, Lam);
  - si la hoja sigue la reproducción;
  - si suena el silbato al analizar.
- El editor de la hoja acepta el bajo en cifrado latino (`La/Do#`).
- **Versionado**: la versión de la app (`app/VERSION`) se ve en la Configuración, en `GET /api/version` y al
  arrancar el servidor. Se agregó este archivo de cambios.

### Arreglado

- El reproductor y las pestañas aparecían antes de abrir un tema.

## [1.1.0] - 2026-11-18

### Agregado

- Una pestaña por instrumento (Guitarra, Piano, Otros, Bajo, Voz) y, separada, **Tema completo** con la armonía
  de todo el tema. Dentro de cada una se elige Acordes, Partitura o Improvisación.
- **Editar la hoja de cada instrumento**: además de la armonía del tema, se corrige lo que toca la guitarra, el
  piano u Otros («–» = no toca, «♪» = línea). Se guarda en `correcciones.json` (clave `pistas`) y se conserva al
  volver a analizar.

### Cambiado

- Al abrir un tema se elige sola la pestaña del instrumento que más acordes toca, en vez de arrancar siempre en
  Guitarra.
- «Editar hoja» edita la hoja de la pestaña abierta y solo se activa en la vista Acordes.

## [1.0.0] - 2026-11-15

Primera versión: de un link de YouTube (o un archivo de audio) a la sala de ensayo.

- Separación en voz, guitarra, piano, bajo, batería y otros (Demucs).
- Acordes (BTC), pulsos y compases (Beat This!), tonalidad y estructura.
- Hoja de acordes y partitura y tablatura de guitarra, piano, bajo, voz y Otros.
- Mezclador con mute, solo y volumen, y metrónomo.
- Cuenta previa, repetir un tramo y transporte de tonalidad.
- Escalas para improvisar e ideas de arreglo.
- Corrección a mano de acordes, compases y secciones.
- Docker, servidor en internet con HTTPS y contraseña, y subir audio.
