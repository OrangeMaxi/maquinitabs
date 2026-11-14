# Set de prueba de acordes

Sirve para saber con números si un cambio en la detección de acordes mejora o empeora, en vez de juzgarlo
a oído tema por tema.

## Qué hay

| Archivo / carpeta | Qué es |
| --- | --- |
| `referencias\*.lab` | Acordes verificados con tiempos de 16 temas del [McGill Billboard Project](https://ddmal.music.mcgill.ca/research/The_McGill_Billboard_Project_(Chord_Analysis_Dataset)/) (anotados por músicos expertos) |
| `temas.json` | La lista de esos temas y su carpeta de audio |
| `canciones\` | El audio de cada tema bajado de YouTube y separado en pistas (no viaja con el proyecto: ~6 GB) |
| `resultados\` | Lo que detectó cada variante (se reutiliza mientras no cambie el detector) e `informe.txt` |
| `billboard.py` | Lee el formato de McGill Billboard |
| `preparar.py` | Baja y separa los temas |
| `evaluar.py` | Corre el detector y compara con las referencias |

Temas: Sweet Home Alabama, Ain't No Sunshine, Sunshine of Your Love, Bad Moon Rising, Come Together, Help!,
We Are The Champions, Beat It, With Or Without You, Just The Way You Are, Goodbye Yellow Brick Road,
(Sittin' On) The Dock Of The Bay, Higher Ground, Every Little Thing She Does Is Magic, Riders On The Storm,
Lovely Day.

## Uso

Desde esta carpeta:

```powershell
python evaluar.py
```

Compara cuatro variantes del detector:

| Variante | Modelo de acordes | Pulsos y compases |
| --- | --- | --- |
| `actual` | BTC re-entrenado (ChordMini) | Beat This! |
| `btc-original` | BTC original | Beat This! |
| `pulsos-librosa` | BTC re-entrenado (ChordMini) | librosa |
| `anterior` | BTC original | librosa (como estaba la app antes del 13/11/2026) |
| `combinado` | promedio de los dos BTC (tarda el doble) | Beat This! |

En la app se elige el modelo con la variable `PESOS_BTC` (`btc_chordmini.pt`, `btc_grande.pt` o
`btc_grande.pt+btc_chordmini.pt` para el combinado).

La primera vez tarda alrededor de una hora; después solo se re-analiza lo que cambió. Para medir un cambio
nuevo, agregá una variante en `VARIANTES` dentro de `evaluar.py`.

Las métricas son las del concurso MIREX, en % del tiempo de los temas:

- **raíz**: acierta la nota fundamental.
- **may/men**: acierta si es mayor o menor.
- **séptimas**: acierta también la séptima cuando la hay.
- **mirex**: el acorde comparte al menos 3 notas con el correcto.
- **cortes**: qué tan bien caen los cambios de acorde.

## Sumar temas de la banda

1. Abrí el tema en la app, corregí la hoja con **Editar hoja** escuchándolo, hasta que esté bien.
2. Guardala como referencia:

   ```powershell
   python evaluar.py --verificar "Mil Horas - Los Abuelos De La Nada"
   ```

Esos temas se promedian aparte: su referencia sale de la hoja que armó la app, así que favorecen a la
variante `actual` y no sirven para comparar variantes entre sí, pero sí para ver si un cambio rompe algo
en el repertorio de la banda.

## Sumar temas de McGill Billboard

Bajá las anotaciones (`billboard-2.0-salami_chords.tar.gz` desde la página del proyecto), descomprimilas y:

```powershell
python preparar.py "<carpeta McGill-Billboard>" 107 1058 114
```

Los números son los ids del índice del conjunto. Cada tema tarda 5–10 minutos (descarga y separación).
Conviene revisar que la grabación bajada sea la original de estudio: si el desfase cambia a lo largo del
tema, `evaluar.py` lo marca como sospechoso y lo deja fuera del promedio.
