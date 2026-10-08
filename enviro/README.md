# Generación de terrenos

Generador determinista de mapas 3D para simular un rover explorador.
La misma semilla produce siempre el mismo mapa.

```python
from enviro.terrain import generate

mapa = generate(42)
```

## El pipeline

```
semilla ─▶ parámetros ─▶ relieve ─▶ suelo ─▶ obstáculos ─▶ red ─▶ objetivos ─▶ mapa
```

---

## 1. Los 3 ruidos — el relieve

El relieve nace de tres campos de ruido 2D que se evalúan en cada celda `(x, y)`:

| Ruido | Dibuja | Lo sortea la semilla |
|---|---|---|
| ⭐ Estrella | brazos radiales desde un centro | centro, nº de brazos (3–5), fase, atenuación |
| 🫧 Manchas | colinas gaussianas | 8–14 centros y sigmas |
| 🌊 Ondas | dunas direccionales | 3 senos: ángulo, frecuencia, fase |

La semilla también decide **cuánto aporta cada ruido**: sortea 3 pesos que suman 1
(en vez del antiguo promedio fijo). Cada campo se normaliza a [0,1], se mezclan
con esos pesos y **el combinado se normaliza de nuevo**. Al normalizar después de
mezclar, el mínimo queda exactamente en 0 y el máximo en 1 *por construcción*,
así que la cuantización a capas `z` **siempre alcanza el z máximo**, sin trucos
de contraste. Finalmente se redondea a la capa entera más cercana.

> Del determinismo se encarga el diseño: cada `create()` re-siembra el RNG y
> reconstruye el campo, así que el mismo generador entrega el mismo mapa siempre.

## 2. El suelo — qué tipo de terreno hay en cada celda

Con la altura ya decidida, otro ruido (multi-octava, ponderado por eje según
`axis_weights`) más la pendiente de profundidad deciden el **tipo de suelo**:
llanura, arena, roca o grieta, según las `bands` del config. Un diagrama de
Voronoi (`biome_count` regiones) elige qué juego de bandas aplica en cada zona,
para que los terrenos se agrupen en regiones en vez de salpicarse.

| Terreno | Costo | Visibilidad |
|---|---|---|
| Llanura | 1.0 | 0.90 |
| Arena | 1.5 | 0.75 |
| Roca | 2.2 | 0.60 |
| Grieta | 3.2 | 0.35 |
| Lava | ∞ (impasable) | 0.10 |

## 3. Obstáculos — rocas y lava

- **Rocas**: cada celda de superficie se bloquea con probabilidad `block_rate`.
- **Lava**: se inundan `lava_pools` pozos circulares (centro y radio aleatorios);
  toda celda alcanzada se vuelve lava impasable. Corre después de las rocas para
  sobreescribirlas.

## 4. La red — estaciones

Los presets de `network.stations` (`id`, `radio`, `señal`) se colocan sobre la
superficie con *farthest-point*: la primera al azar, cada siguiente lo más lejos
posible de las anteriores. El radio se capa a la diagonal del mapa. Radio 0 =
estación puntual: hay que pararse en su celda.

## 5. Los objetivos — puntos de interés

Cada POI debe cumplir cuatro reglas:

1. **Alcanzable** — se llega desde la superficie sin cruzar rocas.
2. **Observable** — alguna celda vecina tiene visibilidad ≥ `min_visibility`.
3. **Interesante** — cuesta llegar (altura, terreno caro) pero premia (más altura
   = más radio de exploración).
4. **Disperso** — uno por capa primero; los empates se rompen por lejanía.

## Configuración

Todo vive en `config/default.json`:

| Sección | Controla |
|---|---|
| `generation` | ruido (`noise_scale`, `noise_octaves`, `axis_weights`), `depth_slope`, `bands`, `biome_count`, `lava_pools`, `lava_pool_radius` |
| `map` | `width`, `height`, `depth`, `block_rate`, límites `min/max_axis` |
| `movement` | `radius` (paso), `climb_penalty`, `survey_height_bonus`, `allow_diagonal` |
| `network` | `stations`: `(id, radius, signal)` |
| `poi` | `count`, `min_visibility`, pesos de interés |
| `rover` | `battery`, `memory` (declarados; el generador no los gasta) |
| `terrain` | catálogo: `cost`, `visibility`, `glyph` por tipo |

## El resultado

`generate()` devuelve un `Map`: un contenedor puro de datos con `cells`
(diccionario por id `"z01_y04_x09"`), `params` (el spec congelado), `pois` y
`stations`. Sin métodos: lo generas, lo lees.
