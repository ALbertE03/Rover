# Rover

Generador determinista de terrenos 3D sintéticos para simular un rover explorador.
La misma semilla produce siempre el mismo mapa.

```python
from enviro.terrain import generate

mapa = generate(42)
print(len(mapa.cells), "celdas,", len(mapa.pois), "POIs,", len(mapa.stations), "estaciones")
```

## Cómo funciona

La generación, paso a paso, está explicada en [enviro/README.md](enviro/README.md):
relieve por heightmap (3 ruidos con mezcla sorteada por la semilla), tipos de
terreno por bandas y biomas Voronoi, rocas, pozos de lava, estaciones de red y
puntos de interés con reglas de alcanzabilidad, observabilidad, interés y
dispersión.

## Configuración

`config/default.json` — secciones:

- **`generation`**: `noise_scale`, `noise_octaves`, `axis_weights` (peso por eje
  del ruido de tipos, suma 1), `depth_slope`, `bands` (umbrales de terreno),
  `biome_count`, `lava_pools`, `lava_pool_radius`.
- **`map`**: `width`, `height`, `depth`, `block_rate` (prob. de roca por celda),
  `min_axis`/`max_axis` (límites de validación).
- **`movement`**: `radius` (alcance de un paso), `climb_penalty` (costo extra por
  nivel subido), `survey_height_bonus` (radio extra de exploración en la cima),
  `allow_diagonal`.
- **`network`**: `stations` — lista de `(id, radius, signal)`; radio 0 = puntual.
- **`poi`**: `count`, `min_visibility`, `interest_climb_weight`,
  `interest_ground_weight`.
- **`rover`**: `battery`, `memory` — presupuestos declarados (el generador no los gasta).
- **`terrain`**: catálogo — `cost` (energía por celda), `visibility` (calidad de
  exploración, en (0,1]), `glyph` por cada tipo: `plain`, `sand`, `rock`,
  `crevasse`, `lava` (impasable).
