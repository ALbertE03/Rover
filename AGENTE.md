# Agente rover

Rama `rover-agente`. El generador (`enviro/`) no se toca: este agente
consume los mapas que genera, no cambia cómo se generan.

## Archivos

```
búsqueda/a_start.py   # A* genérico (no sabe nada de mapas)
rover.py              # el rover: conocimiento, survey, batería, acciones
metaheuristica.py     # una sola metaheurística: simulated annealing
planificacion.py      # planificación simbólica (apartado B, no C)
AGENTE.md             # este documento
```

Se ejecuta con `python rover.py [semilla]` (por defecto, 42).

## Apartado elegido: B (planificación), no C (CSP)

El enunciado permite uno de los dos. Se eligió B porque encaja directo
con la arquitectura pedida: el planificador decide la secuencia de alto
nivel y la búsqueda (A*) resuelve cada desplazamiento concreto. Un
solucionador CSP duplicaría el mismo razonamiento de orden, batería y
memoria en forma de restricciones sin añadir una capacidad nueva en esta
primera versión. Las restricciones que un CSP impondría se imponen igual
aquí, como precondiciones de las acciones: capacidad de batería,
capacidad de memoria, precedencias entre acciones y comunicación solo en
una estación. Lo que **no** está modelado todavía: límite de tiempo de
misión y ventanas de comunicación más allá de "estar en una estación"
(las estaciones tienen radio 0 en el config por defecto, así que una
ventana necesitaría primero un radio o un horario en el mapa, que no
existe).

## Cómo funciona una misión

1. El rover empieza en la base (primera estación, id `"base"`).
2. Conoce desde el inicio solo la posición de los POIs y de las
   estaciones. El resto lo desbloquea observando.
3. La metaheurística (simulated annealing) propone un orden de visita
   de los POIs, evaluado con costes A* planificados, desvíos de recarga
   y desvíos de transmisión.
4. El planificador convierte ese orden en acciones de alto nivel.
5. El rover ejecuta las acciones; cada `mover_a` se resuelve con A*,
   replanificando paso a paso a medida que el survey revela terreno.

## Acciones, precondiciones y efectos

| Acción | Precondiciones | Efectos |
|---|---|---|
| `mover_a(dest)` | Existe ruta A* y la batería paga el siguiente paso | Cambia la posición, gasta batería (0 cuesta abajo), observa al llegar |
| `recolectar(poi)` | Estar en la celda del POI, POI sin recoger, memoria libre | El POI entra en el buffer en bruto, memoria +1 |
| `analizar` | Al menos una muestra en bruto | Las muestras en bruto pasan a analizadas (la memoria no cambia) |
| `transmitir` | Estar en una estación, al menos una muestra analizada | Las muestras se entregan (su interés ya cuenta) y liberan memoria |
| `recargar` | Estar en una estación | Batería restaurada al máximo |

La precedencia es, por tanto: recolectar -> analizar -> transmitir, y
transmitir/recargar solo en estación.

## Conocimiento y survey

El modelo de conocimiento sigue lo que el propio generador documenta:
las celdas bloqueadas se ven desde cualquier sitio ("los obstáculos son
grandes"), pero el tipo de terreno bajo las ruedas no se conoce hasta
observarlo. "Desbloquear" una celda significa aquí revelar su tipo de
terreno (y su coste), no desbloquearla: una celda bloqueada sigue
bloqueada.

Estando parado en una celda, el rover primero conoce el terreno que
pisa y luego revela las celdas a su alrededor dentro de un radio que
crece con la altura y se escala con la visibilidad del terreno que pisa:

```
radio_base = move_radius + survey_height_bonus * z / (depth - 1)
radio_survey = radio_base * visibilidad(terreno_actual)
```

Ejemplo medido (misma altura, z=1): plain (visibilidad 0.9) revela 16
celdas con radio 2.52, mientras que crevasse (0.35) revela solo su propia
celda con radio 0.98. Mientras una celda no está observada, planificar
sobre ella cuesta `UNKNOWN` (2.2 en el catálogo por defecto, la mediana).

## Batería: cuesta abajo gratis, estaciones recargan

El coste real de un paso, en batería, es:

- 0 si baja (`dz < 0`), sea cual sea el terreno;
- el coste real del terreno destino en caso contrario, más
  `climb_penalty` por nivel subido.

Ojo: el coste planificado y el real pueden diferir, porque A* planifica
con el coste conocido (desconocido = 2.2) y el rover gasta el coste real
al pisar. Un atajo desconocido puede salir más barato (plain, 1.0) o más
caro (crevasse, 3.2) de lo planificado. Esa diferencia es el dilema
exploración/explotación, no un error del mapa.

Las estaciones son de comunicación (radio 0: hay que pararse en su
celda) y además recargan: la acción `recargar` solo existe en estación
y devuelve la batería al máximo. El planificador inserta desvíos a
estación cuando la memoria está llena o cuando la batería no cubre el
siguiente tramo más una reserva hasta la estación más cercana desde el
destino. Importante: "más cercana" se mide por coste A* alcanzable, no
por distancia en línea recta: una estación puede ser la más cercana y
estar en un componente desconectado (la relay de la semilla 42, por
ejemplo, es transitable pero inalcanzable desde la base).

## Metaheurística: simulated annealing (una sola, por ahora)

Busca el orden de visita de los POIs. Su vecino es un intercambio de
dos POIs (a veces, una inversión de segmento) y su aceptación es
probabilística: acepta siempre una mejora y acepta un empeoramiento con
probabilidad `exp((nuevo - actual) / T)`, con `T` enfriándose
geométricamente. Ahí vive la probabilidad del objetivo: el interés de
cada POI viene del mapa y no es aleatorio, pero la *elección* del orden
sí lo es, y los órdenes de alto interés tienen más probabilidad de
sobrevivir sin estar garantizados. La puntuación que evalúa es
`interés * 100 - coste_de_viaje`: el interés domina y el coste solo
desempata órdenes con el mismo interés. El mejor orden visto nunca se
devuelve siempre, así que el resultado nunca es peor que el orden
inicial (POIs ordenados por interés descendente).

Limitación conocida: el annealing busca órdenes, no subconjuntos. Un POI
alcanzable se recoge aunque su interés sea 0, si la batería lo permite;
descartar POIs por eficiencia es trabajo futuro, no un error de la
versión actual.

## Objetivo

Maximizar el interés **entregado**: la suma del `interest` de los POIs
recogidos, analizados y transmitidos en una estación. El interés
recogido pero no transmitido no cuenta, porque esos datos nunca llegaron
a una estación. "Recogido" significa aquí pisar la celda del POI; la
variante "observarlo desde una celda vecina con visibilidad >= 0.7"
queda como variante futura, no implementada.

## Resultados medidos

Con `python rover.py 42`: los 5 POIs entregados, interés 3.336 de 3.336
en el mapa, 52 pasos, 3 recargas y 3 transmisiones. Con la semilla 7
solo se entrega 1 POI, y eso es correcto: los otros 4 solo son
alcanzables desde la relay, que está en otro componente que la base, así
que el rover que empieza en la base no puede llegar a ellos. El
planificador los omite en vez de romper la misión.
