# Rover

Generador determinista de terrenos 3D sintéticos para simular un rover explorador.
La misma semilla produce siempre el mismo mapa.

## Clonar el repo

```bash
git clone https://github.com/ALbertE03/Rover.git
cd Rover
```
## Cómo correr el proyecto 

```bash
uv sync
uv run experimento_representativo.py
```

`uv sync` instala las dependencias de `pyproject.toml` (solo matplotlib, para las gráficas; el generador, el rover, la búsqueda y la planificación son solo biblioteca estándar). Una misión suelta se corre con `uv run rover.py 42`.

- Búsqueda: `a_star`, `dijkstra` (= coste uniforme), `greedy`,
  `bfs`, `weighted` (A* ponderado, w = 2.0), `beam` (ancho 20).
  `dfs` pero solo se compara en rutas (legs):
  en misiones replanifica tras cada survey y oscila hasta agotar
  la batería.
- Metaheurísticas: `random`, `hill_climbing`,
  `simulated_annealing`, `genetico`, `tabu`, `aco`.
- Planificación: `planificacion.py`, dominio
  STRIPS en `rover-domain.pddl`.

```bash
# Experimento (único script: experimento_representativo.py).

# Diseño: 9 estratos (12x12, 16x16, 32x32 x z=3, 5, 7), asignación
# igual por estrato, muestreo por hipercubo (LHS) para los
# parámetros continuos y factores discretos equilibrados (POIs 3/5/7,
# radio 1.0/1.8/2.5, diagonal sí/no, batería, memoria, bloqueos,
# penalización de subida, bonus de survey, terrenos, bandas...).
# Cada instancia lleva una configuración COMPLETA. Diseño pareado: la misma instancia corre con todos los
# algoritmos, presupuesto igual (100 evaluaciones de órdenes).

python experimento_representativo.py --piloto
# solo diseña y calcula n necesario, no corre misiones.

python experimento_representativo.py --prueba
# prueba pequeña: 2 instancias, todos los algoritmos, gráficas.
```

Por defecto (`uv run experimento_representativo.py`): 30 instancias por estrato, 270 instancias, 3240 misiones (12 por instancia) + legs, 4 trabajadores. Escribe `resultados_representativo.jsonl`, `instancias_representativo.json` (configuración completa y semilla 20000 + id) y 11 figuras PNG en `figuras_representativo/`, y termina imprimiendo "fin". Si una instancia no se puede generar (como la 2, sin celdas observables), sus misiones quedan con `ok: False` y sus legs con una fila de error, sin abortar la corrida.

### Parámetros de `experimento_representativo.py`

| Parámetro | Default | Qué hace |
|---|---|---|
| `--n-por-estrato` | 30 | Instancias por estrato; total = 9 × este número (1 → 9 instancias, 3 → 27, 30 → 270). Los 9 estratos siempre están; no hay parámetro para elegir un solo estrato. |
| `--trabajadores` | 4 | Procesos en paralelo. |
| `--salida` | `resultados_representativo.jsonl` | JSONL de resultados; se sobrescribe en cada corrida, usa otro nombre para conservar una anterior. |
| `--instancias` | `instancias_representativo.json` | JSON con las instancias y su configuración completa. |
| `--graficos` | `figuras_representativo` | Carpeta de las 11 figuras PNG; sin matplotlib avisa y sigue sin figuras. |
| `--modo` | `ambos` | `misiones`, `legs` o `ambos`. |
| `--presupuesto` | 100 | Evaluaciones de órdenes por metaheurística, no generaciones. |
| `--semilla-meta` | 7 | Semilla de las metaheurísticas, la misma para todas (diseño pareado). |
| `--piloto` | — | Solo diseña y calcula el n necesario, no corre misiones. |
| `--prueba` | — | Prueba pequeña: 2 instancias del primer estrato, todos los algoritmos. No es el experimento completo. |

Las Tablas 1-4 del informe se calculan desde el JSONL con `analizar_resultados.py` (media por instancia, desviación, IC95 y diferencias pareadas), y las estadísticas del terreno, sin misiones, con `estadisticas_terreno.py` (mismas instancias, salidas `stats_terreno.jsonl` y `resumen_terreno.json`).


Los resultados del experimento pequeño y del completo son archivos
JSONL (una fila por misión o por leg), con instancia, tamaño,
profundidad, algoritmo, interés recolectado y entregado, batería,
pasos, nodos y tiempo, para que cualquier tabla del informe se pueda
recalcular desde el archivo, sin volver a correr nada.

```python
from enviro.terrain import InstanceParams, MapGenerator

mapa = MapGenerator(InstanceParams.from_config(seed=42)).create()
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
| `network` | `stations`: lista de ids (una estación es una celda: hay que pararse en ella para transmitir o recargar) |
| `poi` | `count`, `min_visibility`, pesos de interés |
| `rover` | `battery`, `memory`, `reserve_margin` (margen de retorno) |
| `terrain` | Catálogo: `cost`, `visibility`, `glyph` por tipo |

## Configuración del consumidor

Quien consume la API puede mandar su propio config parcial y este sobrescribe
al por defecto; si no manda ninguno, se usa el por defecto tal cual. La fusión
es profunda: los diccionarios anidados se mezclan clave a clave, y las listas
y escalares reemplazan al valor por defecto (no se concatenan).

```python
from enviro.terrain import InstanceParams, MapGenerator

# Solo cambia lo que manda; el resto sigue siendo el config por defecto.
mapa = MapGenerator(InstanceParams.from_config(seed=42, config={
    "generation": {"relief_amplitude": 1.0},  # relieve completo siempre
    "map": {"width": 20},
    "terrain": {"plain": {"cost": 50.0}},  # visibility y glyph de plain se conservan
})).create()
```

Un archivo parcial también vale, con la misma regla, vía `config_path`:

```python
from pathlib import Path
from enviro.terrain import MapGenerator, InstanceParams

gen = MapGenerator(InstanceParams.from_config(config_path=Path("mi_config.json")))
```

Precedencia, de menor a mayor: por defecto < archivo en `config_path` < dict
en `config`. El dict que se manda se copia, así que cambiarlo después no
afecta al generador ya construido.

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
├── main.py                  # estadísticas agregadas de un lote de terrenos
├── experimento_representativo.py  # experimento: 9 estratos, misiones + legs + 11 gráficas
├── estadisticas_terreno.py      # estadísticas del terreno, sin misiones
├── analizar_resultados.py       # Tablas 1-4 desde el JSONL
├── enviro/
│   ├── README.md            # explicación paso a paso de la generación
│   ├── config.py            # carga del JSON
│   └── terrain/
│       ├── generate.py      # InstanceParams.from_config + MapGenerator (el pipeline)
│       ├── field.py         # ruidos, heightmap, tipos de suelo
│       ├── instance.py      # Map / MapParams (contenedores de datos)
│       ├── grid.py          # celdas, distancias, vecindarios
│       ├── features.py      # estaciones y POIs
│       ├── catalogue.py     # catálogo de terrenos
│       └── types.py         # alias de tipos
└── pyproject.toml
```
