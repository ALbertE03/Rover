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
