# Rover

Generador determinista de terrenos 3D sintéticos para simular un rover explorador.
La misma semilla produce siempre el mismo mapa.

## Clonar el repo

```bash
git clone https://github.com/ALbertE03/Rover.git
cd Rover
python rover.py 42
```

El enlace para clonar es https://github.com/ALbertE03/Rover.git
(si prefieres descargarlo sin git, en GitHub: Code → Download ZIP).

## Cómo correr el proyecto (agente rover)

Todo se corre desde la raíz del repo clonado, con Python ≥ 3.12, solo
biblioteca estándar (sin dependencias). No hay que instalar nada.

```bash
# Una misión (semilla 42 por defecto, SA + A*)
python rover.py 42

# Una misión con otro buscador o metaheurística
python rover.py 42   # el buscador y la meta se eligen en rover.py / ejecutar_mision
```

Algoritmos que existen, **solo de las conferencias** (C1, C2b y
metaheurísticas). Cualquier otro algoritmo fue eliminado, no está
en el código:

- Búsqueda (C1): `a_star`, `dijkstra` (= coste uniforme), `greedy`,
  `bfs`, `weighted` (A* ponderado, w = 2.0), `beam` (ancho 20).
  `dfs` también es de C1, pero solo se compara en rutas (legs):
  en misiones replanifica tras cada survey y oscila hasta agotar
  la batería (ver `AGENTE.md`).
- Metaheurísticas: `random`, `hill_climbing`,
  `simulated_annealing`, `genetico`, `tabu`, `aco`.
- Planificación (C2b, apartado B): `planificacion.py`, dominio
  STRIPS en `rover-domain.pddl`.

```bash
# Experimento (único script: experimento_representativo.py).
# Los experimentos viejo, grande y pequeño, y los scripts
# analizar_grande.py, legs.py y barrido.py, se borraron: todo lo
# que hacían está dentro de este script, en un solo diseño.
# Diseño: 9 estratos (12x12, 16x16, 32x32 x z=3, 5, 7), asignación
# igual por estrato, muestreo por hipercubo latino (LHS) para los
# parámetros continuos y factores discretos equilibrados (POIs 3/5/7,
# radio 1.0/1.8/2.5, diagonal sí/no, batería, memoria, bloqueos,
# penalización de subida, bonus de survey, terrenos, bandas...).
# Cada instancia lleva una configuración COMPLETA, nada queda por
# defecto. Diseño pareado: la misma instancia corre con todos los
# algoritmos, presupuesto igual (100 evaluaciones de órdenes).
# Tamaño: con sigma piloto 27 y media 65, un margen del 20% al 95%
# pide n=17 por estrato; el default 30 por estrato es conservador.
# Gráficas: 11 PNG en --graficos (batería, interés y nodos por
# buscador; interés y batería por metaheurística; por instancia;
# más 4 agrupadas por nº de POIs). No falla si falta un algoritmo
# o una métrica: omite la figura sin datos y sigue.
python experimento_representativo.py --piloto
# solo diseña y calcula n necesario, no corre misiones.
python experimento_representativo.py --prueba
# prueba pequeña: 2 instancias, todos los algoritmos, gráficas.
# NO es el experimento completo.
# python experimento_representativo.py --n-por-estrato 30
# experimento completo: 270 instancias, 3240 misiones + legs.
# NO correrlo sin tiempo de cómputo suficiente.
```

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
| `network` | `stations`: lista de `(id, radius, signal)` |
| `poi` | `count`, `min_visibility`, pesos de interés |
| `rover` | `battery`, `memory` (declarados; el generador no los gasta) |
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
