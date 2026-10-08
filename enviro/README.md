# Generación de terrenos — `enviro`

Este paquete genera mapas 3D sintéticos para simular un rover explorador.
Todo el proceso es determinista: la misma semilla produce siempre el mismo mapa.

Punto de entrada:

```python
from enviro.terrain import generate

mapa = generate(42)          # mapa 12x12x3 con el config por defecto
mapa = generate(42, depth=10, width=32, height=32)  # con overrides
```

El objeto devuelto (`Map`) es un contenedor puro de datos: `cells`, `params`, `pois`, `stations`.

---

## Paso 0 — Parámetros de la instancia

`generate(seed)` llama a `InstanceParams.from_config()`, que lee `config/default.json`
y extrae lo que varía entre instancias: `map.width/height/depth`, `map.block_rate`,
`poi.count` y `station_count` (= número de presets en `network.stations`).
`__post_init__` valida rangos (tamaño dentro de `min/max_axis`, `block_rate` en [0,1]…).
La idea: la familia de mapas queda definida por el archivo de config, no por
argumentos sueltos.

## Paso 1 — El campo de terreno (`TerrainField`)

`MapGenerator._build_field()` sortea el *origin* — un desfase de fase con
`rng.uniform()` — que es la influencia directa de la semilla sobre el terreno.
Con él se crea el `TerrainField`, que en `_configure()` lee la sección
`generation`: `noise_scale`, `noise_octaves`, `axis_weights` (validado: claves
`x`,`y` que suman 1), `depth_slope`, `bands` y `biome_count` (centros Voronoi
con bandas sesgadas a un terreno dominante vía `_biased_bands()`, para que los
terrenos se agrupen en regiones).

## Paso 2 — Heightmap: los 3 ruidos

`_place_terrain()` pide `height_at(x, y)`, que construye el heightmap una sola
vez (`_build_heightmap()`, con caché):

1. `_noise_seed()` deriva un entero del *origin* (o sea, de la semilla).
2. `_draw_noise_params()` sortea, todo de la semilla:
   - **estrella**: centro, nº de brazos (3–5), fase y atenuación radial;
   - **manchas**: 8–14 gaussianas con centro y sigma aleatorios;
   - **ondas**: 3 senos direccionales con ángulo, frecuencia y fase aleatorios;
   - **mezcla**: 3 pesos (0.25–1.0) normalizados a sumar 1 — la semilla decide
     cuánto aporta cada ruido, en vez de un promedio fijo.
3. Se evalúan `_star_value()`, `_blobs_value()` y `_waves_value()` en cada celda
   y cada campo se normaliza a [0,1] con `_normalize()`.
4. Se mezclan con los pesos de la semilla y **el combinado se normaliza** a [0,1].
   Al normalizar después de mezclar, el mínimo real queda en 0.0 y el máximo en
   1.0 por construcción, así que la cuantización `round(valor × (depth-1))`
   **siempre alcanza el z máximo**, sin necesidad de ningún contraste.
5. Se cuantiza a capas `z` en `[0, depth-1]`.

## Paso 3 — Tipo de terreno por celda

Por cada columna `(x, y)` con altura `h`:
- `z > h`: aire, no se crea celda;
- `z == h`: superficie transitable;
- `z < h`: interior sólido del cerro, bloqueado.

`terrain_at(x, y, z)` calcula `value()` = `_noise()` (ruido multi-octava donde
`axis_weights` pondera cuánto aporta cada eje, vía `_wave()`) más
`depth_slope × (z / z_max)`, elige el bioma con `biome_at()` (Voronoi al centro
más cercano) y devuelve el primer terreno cuya banda lo contenga.
O sea: el heightmap decide la **altura**, este ruido decide el **tipo de suelo**.

## Paso 4 — Rocas (`_place_boulders`)

Cada celda de superficie (`is_surface()`) se bloquea con probabilidad
`block_rate`. Solo la superficie puede llevar rocas: el interior ya es sólido
y el aire no existe como celda.

## Paso 5 — Lava (`_place_lava_pools`)

Se inundan `lava_pools` pozos circulares: centro y radio (`lava_pool_radius`)
aleatorios; toda celda de superficie dentro del radio pasa a `true_terrain =
"lava"` y se bloquea (impasable). Corre después de las rocas para
sobreescribirlas.

## Paso 6 — Estaciones (`_place_stations`)

Se toman los presets de `network.stations` (`id`, `radius`, `signal`) y se
colocan sobre la superficie con *farthest-point*: la primera al azar, cada
siguiente lo más lejos posible de las ya colocadas. `place_stations()` capa
cada radio a la diagonal del mapa, porque un radio mayor que el mundo no aporta
cobertura distinguible. Radio 0 = estación puntual (hay que pararse en su celda).

## Paso 7 — Puntos de interés (`_place_pois`)

Cuatro reglas, en orden:

1. **Alcanzable**: `_observable_cells()` hace flood fill (`reachable_cells()`)
   desde la superficie con los pasos de `movement_offsets()`.
2. **Observable**: alguna celda vecina tiene visibilidad ≥ `poi.min_visibility`
   (se usa el terreno real, nada está explorado aún).
3. **Interesante**: `_interest()` puntúa cada candidato —
   `peso_subida × altura_normalizada + peso_suelo × costo_terreno_normalizado`.
   Subir cuesta pero premia con más radio de exploración.
4. **Disperso**: una POI por capa primero (las capas compiten por interés con
   `_best()`), desempates por lejanía (`_farthest()`), y relleno con
   `_best_spread()` (50% interés + 50% distancia a las ya colocadas).

## Resultado

`Map(params, cells, stations, pois)` empaqueta todo. `params` es el spec
congelado (`MapParams`: movimiento, POIs, estaciones, batería, memoria);
`cells` es el diccionario de celdas por id (`"z01_y04_x09"`).

## Notas de diseño

- **Determinismo**: `create()` re-siembras el RNG y reconstruye el campo en
  cada llamada, así que el mismo generador entrega el mismo mapa siempre.
- **Separación de concerns**: relieve (heightmap), tipo de suelo (bandas +
  biomas), obstáculos (rocas/lava), red (estaciones) y objetivos (POIs) son
  etapas independientes; un experimento puede variar una sin tocar las demás.
- La configuración vive en `config/default.json`; ver el README principal para
  el detalle de cada clave.
