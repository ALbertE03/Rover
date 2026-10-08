# Rover

Generador determinista de terrenos 3D sintéticos para simular un rover explorador.
La misma semilla produce siempre el mismo mapa.

```python
from enviro.terrain import generate

mapa = generate(42)
print(len(mapa.cells), "celdas ·", len(mapa.pois), "POIs ·", len(mapa.stations), "estaciones")
```

## Cómo funciona

El proceso completo —los 3 ruidos del relieve, los tipos de suelo, los obstáculos,
la red de estaciones y los puntos de interés— está explicado paso a paso en
**[enviro/README.md](enviro/README.md)**.

```
semilla ─▶ parámetros ─▶ relieve ─▶ suelo ─▶ obstáculos ─▶ red ─▶ objetivos ─▶ mapa
```

## Configuración — `config/default.json`

| Sección | Qué controla |
|---|---|
| `generation` | Ruido (`noise_scale`, `noise_octaves`, `axis_weights`), `mixture_weight_range` (rango de los pesos de cada ruido), `depth_slope`, `terrain_relief_weight` (correlación altura–terreno), `relief_amplitude` (amplitud del relieve: número fijo, rango `[lo, hi]` o lista de opciones), `bands`, `biome_count`, `lava_pools`, `lava_pool_radius` |
| `map` | `width`, `height`, `depth`, `block_rate`, límites `min/max_axis` |
| `movement` | `radius` (paso), `climb_penalty`, `survey_height_bonus`, `allow_diagonal` |
| `network` | `stations`: lista de `(id, radius, signal)` |
| `poi` | `count`, `min_visibility`, pesos de interés |
| `rover` | `battery`, `memory` (declarados; el generador no los gasta) |
| `terrain` | Catálogo: `cost`, `visibility`, `glyph` por tipo |

## Cómo extender el generador

Todo lo que varía entre mapas se controla en tres lugares: `config/default.json`,
el campo (`terrain/field.py`) y el pipeline (`terrain/generate.py`). Extender el
generador es añadir un ruido al campo o un eslabón al pipeline, sin romper el
determinismo: todo sorteo aleatorio sale de `self.rng` (sembrado con la semilla
del mapa) y `create()` re-sembra y reconstruye el campo en cada llamada, así que
la misma semilla siempre produce el mismo mapa. El código (nombres y comentarios)
va en inglés; la documentación, en español.

### Nuevo tipo de terreno

1. Decláralo en la sección `terrain` del JSON con `cost` (> 0), `visibility`
   (en (0, 1]) y `glyph` (un solo carácter). El nombre `"unknown"` está reservado
   para el suelo sin explorar y no se puede declarar.
2. Añádelo a `generation.bands` con su borde `max`. Las bandas reparten el rango
   [0, 1), así que al añadir una, las demás cambian de ancho. Si una banda nombra
   un terreno que no existe en el catálogo, el generador falla con `ValueError`.
3. Si el terreno no debe salir del ruido (como `lava`, que solo aparece en las
   piscinas), omite el paso 2 y colócalo en una etapa del pipeline.

### Nuevo ruido en el relieve

El relieve mezcla tres ruidos en `TerrainField._build_heightmap` (`_star_value`,
`_blobs_value`, `_waves_value`): cada uno se normaliza por separado y se combina
con pesos que la semilla sortea. Para añadir uno, implementa su `_x_value(x, y,
params)`, sortea sus parámetros en `_draw_noise_params` con el `rng` que recibe
(derivado de la semilla) y súmalo a la mezcla normalizada en `_build_heightmap`.
La mezcla resultante debe quedar normalizada para que la cuantización en capas
no cambie.

### Nueva etapa en el pipeline

`MapGenerator.create()` corre en este orden: relieve → suelo → rocas →
piscinas de lava → estaciones → POIs. Una etapa nueva se inserta en esa cadena,
trabaja sobre `cells`, usa `self.rng` para cualquier sorteo y
`self.field.is_surface(x, y, z)` para limitarse a la superficie cuando corresponda.
Si la etapa necesita su propia secuencia de sorteos sin alterar los sorteos que
ya existen, crea una rama de aleatoriedad aparte derivada de la semilla (como hace
`relief_amplitude` con su propia instancia de `random.Random`) en vez de consumir
`self.rng`, así las semillas ya generadas no cambian de mapa.

### Nueva estrategia de colocación

Las estaciones se colocan por llenado de punto más lejano, o en la malla de
`network.grid` si se define; los POIs combinan interés (costo de llegar,
recompensa de observar) con dispersión entre capas. Para cambiar la heurística,
sustituye `_place_stations` o `_place_pois` manteniendo el contrato: estaciones
sobre celdas de superficie transitables, POIs sobre celdas alcanzables y
observables (ver `_observable_cells`).

### Nuevo parámetro de experimento

`InstanceParams` (en `generate.py`) es la superficie que barre un experimento:
dimensiones, `block_rate`, conteo de POIs y estaciones, semilla y archivo de
configuración alternativo, todo validado en `__post_init__`. Si el parámetro
varía entre mapas de una misma configuración, va ahí; si define a la familia
entera de mapas, va en `config/default.json`.

## Estructura

```
├── config/default.json      # toda la configuración
├── enviro/
│   ├── README.md            # explicación paso a paso de la generación
│   ├── config.py            # carga del JSON
│   └── terrain/
│       ├── generate.py      # generate() + MapGenerator (el pipeline)
│       ├── field.py         # ruidos, heightmap, tipos de suelo
│       ├── instance.py      # Map / MapParams (contenedores de datos)
│       ├── grid.py          # celdas, distancias, vecindarios
│       ├── features.py      # estaciones y POIs
│       ├── catalogue.py     # catálogo de terrenos
│       └── types.py         # alias de tipos
└── pyproject.toml
```
