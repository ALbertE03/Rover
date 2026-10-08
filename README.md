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

## Cómo agregar nuevos terrenos

Los tipos de terreno viven en dos lugares de `config/default.json`:

1. **Catálogo** (`terrain`): declara cada terreno con `cost` (energía por unidad
   recorrida, > 0), `visibility` (calidad de observación desde ese suelo, en
   (0, 1]) y `glyph` (un solo carácter para el renderizado de texto). El nombre
   `"unknown"` está reservado para el suelo sin explorar y no se puede declarar.

2. **Bandas** (`generation.bands`): decide cuánto aparece cada terreno. El valor
   de suelo de cada celda cae en la primera banda cuyo borde `max` lo supera.
   Las bandas reparten el rango [0, 1), así que al añadir una, las demás se
   estrechan y la mezcla del mapa cambia. Los bordes deben ser distintos y, si
   una banda nombra un terreno que no está en el catálogo, el generador falla
   con `ValueError`.

Ejemplo: añadir barro entre la llanura y la arena, ocupando el 10% del rango:

```json
"terrain": {
  "mud": { "cost": 1.8, "visibility": 0.65, "glyph": "=" }
}
```

```json
"bands": [
  { "max": 0.55, "terrain": "plain" },
  { "max": 0.65, "terrain": "mud" },
  { "max": 0.72, "terrain": "sand" },
  { "max": 0.88, "terrain": "rocky" },
  { "max": 1.0,  "terrain": "crevasse" }
]
```

Si `biome_count` es mayor que 1, cada bioma sesga sus bandas hacia un terreno
dominante, así que el terreno nuevo también aparecerá concentrado en los biomas
que lo elijan como dominante.

3. **Terrenos fuera del ruido**: si el terreno no debe aparecer por el ruido de
   suelo (como `lava`, que solo existe dentro de las piscinas), omite el paso 2
   y colócalo directamente en una etapa del pipeline (`terrain/generate.py`, por
   ejemplo `_place_lava_pools`).


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
