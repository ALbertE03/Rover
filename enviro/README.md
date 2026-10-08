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

El relieve nace de tres campos de ruido 2D. Cada uno tiene su fórmula y sus
parámetros, todos sorteados por la semilla:

**Estrella** — brazos radiales desde un centro sorteado `(cx, cy)`:

```
valor = 0.5 + 0.5 · cos(brazos·θ + fase) · cos(r·radial)
r = √(dx² + dy²),  θ = atan2(dy, dx),  (dx,dy) = distancia al centro
```

La semilla sortea: centro, nº de brazos (3–5), fase y atenuación radial.

**Manchas** — suma de gaussianas:

```
valor = Σ exp( −((x−bx)² + (y−by)²) / (2σ²) )
```

La semilla sortea: 8–14 manchas, cada una con centro `(bx, by)` y sigma.

**Ondas** — promedio de senos direccionales:

```
valor = promedio de [ 0.5 + 0.5·sin( 2π·(x·cos α + y·sin α)·f + φ ) ]
```

La semilla sortea: 3 ondas, cada una con ángulo `α`, frecuencia `f` y fase `φ`.

Además la semilla sortea **cuánto aporta cada ruido**: 3 pesos en el rango
`mixture_weight_range` del config (por defecto [0.25, 1.0]) que suman 1. El
mínimo 0.25 garantiza que ningún ruido desaparezca nunca del todo.

## 2. Ejemplo real, paso a paso

Semilla 7, grilla 8×8, `depth = 3`. Pesos sorteados:
estrella = 0.18, manchas = 0.39, ondas = 0.43.

**Paso 1 — cada ruido se normaliza a [0,1]**, así los tres campos son
comparables antes de mezclarlos y ninguno domina solo por su escala natural.

Ruido estrella normalizado:

```
 0.40  0.52  0.61  0.65  0.65  0.63  0.60  0.58
 0.33  0.45  0.53  0.55  0.52  0.47  0.46  0.50
 0.30  0.43  0.51  0.52  0.44  0.33  0.32  0.45
 0.32  0.46  0.56  0.58  0.46  0.24  0.20  0.47
 0.36  0.51  0.65  0.73  0.65  0.29  0.09  0.63
 0.42  0.55  0.70  0.85  0.94  0.75  0.00  1.00
 0.47  0.55  0.63  0.69  0.74  0.76  0.44  0.20
 0.52  0.52  0.49  0.40  0.21  0.03  0.86  0.52
```

Ruido manchas normalizado:

```
 0.01  0.12  0.22  0.33  0.43  0.51  0.56  0.55
 0.07  0.21  0.34  0.48  0.60  0.70  0.76  0.75
 0.12  0.28  0.44  0.60  0.75  0.86  0.91  0.88
 0.15  0.32  0.51  0.69  0.84  0.95  0.99  0.94
 0.15  0.33  0.52  0.71  0.87  0.97  1.00  0.94
 0.12  0.30  0.49  0.68  0.83  0.93  0.94  0.88
 0.07  0.23  0.41  0.59  0.73  0.82  0.83  0.78
 0.00  0.15  0.31  0.46  0.58  0.67  0.69  0.65
```

Ruido ondas normalizado:

```
 0.52  0.34  0.26  0.34  0.52  0.66  0.64  0.48
 0.37  0.28  0.35  0.51  0.63  0.60  0.44  0.25
 0.24  0.33  0.52  0.66  0.65  0.51  0.35  0.31
 0.40  0.60  0.75  0.74  0.60  0.44  0.40  0.52
 0.57  0.68  0.64  0.46  0.28  0.21  0.30  0.46
 0.49  0.43  0.24  0.06  0.00  0.10  0.28  0.38
 0.50  0.34  0.19  0.18  0.32  0.53  0.67  0.64
 0.66  0.52  0.53  0.68  0.88  1.00  0.95  0.79
```

**Paso 2 — mezcla ponderada con los pesos de la semilla y normalización del
combinado.** Al normalizar *después* de mezclar (no cada ruido por
separado), el mínimo real queda exactamente en 0.0 y el máximo en 1.0.
Después `relief_amplitude` (1.0 por defecto) reescala el relieve alrededor de
su media: con 1.0 el mapa usa todo el rango de alturas; al bajarlo, el relieve
se aplana y el mapa puede no tocar todas las capas (con 0.0 es una planicie a
la altura media).

```
combinado[x][y] = 0.18·estrella + 0.39·manchas + 0.43·ondas   → normalizar a [0,1]
```

```
 0.15  0.13  0.17  0.30  0.49  0.62  0.64  0.51
 0.07  0.12  0.28  0.48  0.63  0.66  0.58  0.45
 0.00  0.20  0.45  0.65  0.71  0.65  0.57  0.57
 0.13  0.42  0.66  0.78  0.74  0.64  0.63  0.76
 0.26  0.49  0.63  0.65  0.60  0.51  0.53  0.76
 0.21  0.31  0.35  0.38  0.46  0.54  0.46  0.77
 0.19  0.21  0.24  0.36  0.56  0.77  0.78  0.66
 0.27  0.27  0.36  0.54  0.71  0.78  1.00  0.77
```

**Paso 3 — cuantización a capas `z`** con `z = round(v · (n−1))`, `n = depth`.
Cada capa se lleva el rango de valores que redondea hacia ella:

| z | rango de v |
|---|---|
| 0 | [0, 0.5/(n−1)) |
| k (1 ≤ k ≤ n−2) | [(k−0.5)/(n−1), (k+0.5)/(n−1)) |
| n−1 | [1 − 0.5/(n−1), 1] |

Con la amplitud por defecto (1.0) el combinado toca 0.0 y 1.0, así que el z
máximo siempre se alcanza.

Heightmap resultante (ejemplo: `v = 0.78 → z = 2`, `v = 0.13 → z = 0`):

```
 0  0  0  1  1  1  1  1
 0  0  1  1  1  1  1  1
 0  0  1  1  1  1  1  1
 0  1  1  2  1  1  1  2
 1  1  1  1  1  1  1  2
 0  1  1  1  1  1  1  2
 0  0  0  1  1  2  2  1
 1  1  1  1  1  2  2  2
```

## 3. El suelo — qué tipo de terreno hay en cada celda

Antes de repartir terrenos, el mapa se divide en `biome_count` regiones con un
diagrama de Voronoi: se sortean `biome_count` centros y cada celda cae en la
región de su centro más cercano. Cada región tiene sus propias bandas, con la
del terreno dominante ensanchada a costa de las vecinas.

Sin este paso el ruido repartiría terreno rocoso, arena y grieta al azar por todos lados
y el mapa saldría moteado. Con el Voronoi, cada zona queda dominada por un
terreno y el mapa tiene regiones reconocibles.

Centros sorteados: (1.3, 4.3), (3.4, 4.5) y (4.0, 5.3), con dominantes arena, llanura y
terreno rocoso. Así queda cada celda asignada a su región:

```
0  0  0  1  1  1  1  1
0  0  0  1  1  1  1  1
0  0  0  1  1  1  1  1
0  0  0  1  1  1  1  2
0  0  0  1  1  2  2  2
0  0  0  1  2  2  2  2
0  0  0  2  2  2  2  2
0  0  2  2  2  2  2  2
```

Después, un **ruido multi-octava** asigna un valor a cada celda:

```
ruido(x,y) = Σ aᵢ · (wx·tri(x·fᵢ/W) + wy·tri(y·fᵢ/H)) / Σ aᵢ
tri(p) = |(p mod 2) − 1|        (onda triangular en [0,1])
a₀ = 1,  aᵢ₊₁ = aᵢ/2            (cada octava aporta la mitad)
f₀ = noise_scale,  fᵢ₊₁ = 2·fᵢ  (cada octava duplica la frecuencia)
```

Se suman `noise_octaves` octavas (3 por defecto): la primera dibuja las formas
grandes y cada siguiente agrega detalle fino con la mitad de fuerza — el truco
clásico del ruido fractal. `axis_weights` (`wx`, `wy`, suman 1) controla cuánto
aporta cada eje: con más peso en `x`, las franjas de terreno se alargan a lo
largo de X.

El valor final suma la pendiente de profundidad y se recorta a [0,1]:

El valor final mezcla el ruido con el relieve, suma la pendiente de
profundidad y se recorta a [0,1]:

```
valor(x,y,z) = clamp( (1−w)·ruido(x,y) + w·relieve(x,y)
                      + depth_slope · z/(depth−1),  0, 1 )
w = terrain_relief_weight (0.5 por defecto)
relieve(x,y): campo continuo del heightmap, normalizado a [0,1]
```

A más profundidad, el valor tiende al extremo caro. Y con el relieve en la
mezcla, la altura y el tipo de suelo quedan correlacionados: las zonas altas
tienden a terreno caro (rocoso, grietas) y las bajas a barato (llanura,
arena). Así quedan los valores en el ejemplo (superficie):

```
 0.29  0.29  0.31  0.48  0.61  0.75  0.74  0.61
 0.22  0.25  0.42  0.53  0.65  0.74  0.68  0.55
 0.16  0.27  0.49  0.60  0.66  0.71  0.65  0.58
 0.25  0.50  0.62  0.78  0.70  0.73  0.70  0.80
 0.39  0.52  0.58  0.59  0.61  0.64  0.63  0.78
 0.30  0.46  0.47  0.50  0.57  0.69  0.63  0.82
 0.35  0.36  0.37  0.54  0.67  0.96  0.94  0.72
 0.55  0.56  0.60  0.69  0.81  1.00  1.00  0.93
```

El terreno de cada celda sale de juntar tres piezas: el ruido multi-octava,
el relieve y la región Voronoi. El valor `v` mezcla el ruido con el relieve
continuo (`terrain_relief_weight` controla el reparto); la región decide con
qué juego de bandas se lee ese valor, y el terreno es la primera banda cuyo
borde supere a `v`.

Las bandas base salen de `generation.bands` en `config/default.json` y son las
mismas para todo el mapa:

| llanura | arena | rocoso | grieta |
|---|---|---|---|
| [0, 0.55) | [0.55, 0.72) | [0.72, 0.88) | [0.88, 1] |

Cada región sesga ese juego hacia su dominante, ensanchando su banda a costa
de las vecinas. Las bandas sesgadas reales del ejemplo:

| Región | llanura | arena | rocoso | grieta |
|---|---|---|---|---|
| 0 (arena) | [0, 0.33) | [0.33, 0.78) | [0.78, 0.88) | [0.88, 1] |
| 1 (llanura) | [0, 0.62) | [0.62, 0.72) | [0.72, 0.88) | [0.88, 1] |
| 2 (terreno rocoso) | [0, 0.55) | [0.55, 0.65) | [0.65, 0.93) | [0.93, 1] |

La banda dominante se ensancha de forma visible: la arena pasa de [0.55, 0.72)
a [0.33, 0.78) en su región.

Así queda la asignación final en el ejemplo
(`.` llanura, `:` arena, `#` rocoso, `/` grieta):

```
.  .  .  .  .  #  #  .
.  .  :  .  :  #  :  .
.  .  :  .  :  :  :  .
.  :  :  #  :  #  :  #
:  :  :  .  .  :  :  #
.  :  :  .  :  #  :  #
:  :  :  .  #  /  /  #
:  :  :  #  #  /  /  /
```

Se ven las dos fuerzas: el sesgo de cada región y el relieve. La región 0
(dominante arena) está en zona baja y queda en llanura y arena (9 y 14 de 23
celdas); la 2 (dominante rocoso) está en zona alta y concentra lo rocoso y las
grietas (13 de 19 celdas).

| Terreno | Costo | Visibilidad |
|---|---|---|
| Llanura | 1.0 | 0.90 |
| Arena | 1.5 | 0.75 |
| Rocoso | 2.2 | 0.60 |
| Grieta | 3.2 | 0.35 |
| Lava | ∞ (impasable) | 0.10 |

## 4. Obstáculos — rocas y lava

- **Rocas**: cada celda de superficie se bloquea con probabilidad `block_rate`.
- **Lava**: se inundan `lava_pools` pozos circulares (centro y radio aleatorios);
  toda celda alcanzada se vuelve lava impasable. Corre después de las rocas para
  sobreescribirlas.

## 5. La red — estaciones

Los presets de `network.stations` (`id`, `radio`, `señal`) se colocan sobre la
superficie con *farthest-point*: la primera al azar, cada siguiente lo más lejos
posible de las anteriores. El radio se capa a la diagonal del mapa. Radio 0 =
estación puntual: hay que pararse en su celda.

## 6. Los objetivos — puntos de interés

Cada POI debe cumplir cuatro reglas:

1. **Alcanzable** — se llega desde la superficie sin cruzar rocas.
2. **Observable** — alguna celda vecina tiene visibilidad ≥ `min_visibility`.
3. **Interesante** — cuesta llegar (altura, terreno caro) pero premia (más altura
   = más radio de exploración).
4. **Disperso** — uno por capa primero; los empates se rompen por lejanía.
