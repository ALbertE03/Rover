# Agente rover

Rama `rover-agente`. El generador (`enviro/`) no se toca: este agente
consume los mapas que genera, no cambia cómo se generan.

## Archivos

```
búsqueda/a_start.py   # A*
búsqueda/dijkstra.py  # Dijkstra (A* con heurística 0)
búsqueda/greedy.py    # greedy best-first (solo heurística)
búsqueda/bfs.py       # BFS (menos pasos, sin mirar el coste)
búsqueda/dfs.py       # DFS (solo en rutas, no en misiones: ver abajo)
búsqueda/weighted.py  # A* ponderado, f = g + 2h
búsqueda/beam.py      # beam search, ancho 20
rover.py              # el rover: conocimiento, survey, batería, acciones
metaheuristica.py     # random, hill climbing, SA, genético, tabú, ACO
planificacion.py      # planificación simbólica (apartado B, no C)
planificacion_heuristica.py  # h_max y h_add sobre hechos STRIPS
rover-domain.pddl     # dominio STRIPS del rover (C2b)
experimento_grande.py # 30 instancias aleatorias por tamaño x profundidad
estadistica.py        # media, dispersión, IC95, "¿hacen falta más datos?"
experimento.py        # comparación con protocolo experimental
AGENTE.md             # este documento
```

Se ejecuta con `python rover.py [semilla]` (por defecto, 42) para una
misión, y con `python experimento.py` para la comparación (versión
rápida) o `python experimento.py --completo` para la versión larga.

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
3. La metaheurística elegida propone un orden de visita de los POIs,
   evaluado con costes planificados, desvíos de recarga y desvíos de
   transmisión.
4. El planificador convierte ese orden en acciones de alto nivel.
5. El rover ejecuta las acciones; cada `mover_a` se resuelve con el
   algoritmo de búsqueda elegido, replanificando paso a paso a medida
   que el survey revela terreno.

## Reglas del planificador

Estas son todas las reglas que el planificador aplica, sin excepciones
ocultas:

1. **Orden dado, no buscado.** El planificador no busca un orden de
   POIs: recibe el orden de la metaheurística (o el orden fijo por
   interés descendente si no hay metaheurística) y lo respeta.
2. **Un POI, cuatro acciones.** Por cada POI del orden, en este orden
   estricto: `mover_a` a su celda, `recolectar`, `analizar`. La
   transmisión no va por POI, va por lote (regla 4).
3. **POI sin ruta, POI omitido.** Si no hay ruta planificada al POI, o
   no hay estación alcanzable desde el POI (para entregar después), el
   POI se omite y la misión sigue con el siguiente. Nunca se rompe la
   misión por un POI.
4. **Memoria llena, desvío a estación.** Antes de recoger un POI, si la
   memoria no tiene sitio para una muestra más (capacidad 2.0, una
   muestra por POI), el plan inserta: `mover_a` a la estación
   alcanzable más barata, `transmitir`, `recargar`. Solo entonces se
   sigue al POI.
5. **Batería con reserva, desvío a recargar.** Antes de un tramo, si la
   batería no cubre el tramo más una reserva (el coste hasta la
   estación alcanzable más barata desde el destino), el plan inserta:
   `mover_a` a la estación alcanzable más barata desde la posición
   actual, `recargar`. La reserva es la regla que evita que el rover
   se quede tirado en un POI sin poder volver a transmitir.
6. **Estación alcanzable, no cercana.** "La estación más barata" se
   mide siempre por coste de ruta planificada, nunca por distancia en
   línea recta. Una estación cercana en línea recta puede estar en un
   componente desconectado y ser inútil (la relay de la semilla 42).
   Si ninguna estación es alcanzable, el POI se omite (regla 3).
7. **Cierre en estación.** Al final, siempre: `mover_a` a la estación
   alcanzable más barata, `transmitir` si queda algo en el buffer y
   `recargar`. Si no hay estación alcanzable al final, la misión
   termina con las muestras sin entregar, y el informe lo muestra así
   (no se inventa una entrega).
8. **Fallo en ejecución, no en el plan.** El plan se construye con
   costes planificados, pero la ejecución gasta costes reales, así que
   un tramo puede fallar en ejecución (sin ruta tras observar, o sin
   batería para el siguiente paso). En ese caso, la ejecución marca
   ese POI como saltado: se omiten su `recolectar` y su `analizar`,
   pero el resto del plan sigue (incluidas las transmisiones en
   estación). Un fallo nunca aborta la misión entera.
   **Excepción:** si el tramo fallido era un desvío a estación, la
   ejecución no lo da por perdido: prueba las demás estaciones, de
   menor coste planificado a mayor con el conocimiento descubierto
   hasta ese momento, antes de dar por perdida la transmisión. Sin
   este respaldo, una relay que parecía alcanzable por una ruta
   optimista y resultó estar en otro componente haría perder todo el
   lote en buffer.
9. **Precondiciones antes de cada acción.** Cada acción comprueba sus
   precondiciones en ejecución (tabla siguiente) y, si no se cumplen,
   se reporta como fallo en la traza en vez de aplicarse en silencio.

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

El rover, literalmente, solo conoce los POIs y las bases (estaciones)
al empezar. Nada más: ni el tipo de terreno, ni si una celda está
bloqueada, ni si hay una loma en una coordenada. Todo eso lo descubre
poco a poco, parado en una celda y observando a su alrededor (ver la
fórmula abajo). Observar una celda revela su posición (o sea, su
altura: así descubre si hay lomas), su tipo de terreno y si está
bloqueada.

La ejecución (`move_to`) viaja solo sobre terreno descubierto: su
grafo son las celdas observadas más la posición del POI o estación
destino, que sí se conoce. Si el destino no es alcanzable por ese
grafo, el rover se mueve por terreno descubierto hacia la celda
alcanzable más cercana al destino que todavía tenga un vecino sin
observar (la frontera) y observa desde ahí. Si él mismo es esa
frontera, da un paso a ciegas al vecino sin observar más cercano al
destino: si ahí no hay celda, lo aprende; si está bloqueada, lo
aprende; si no, se mueve, paga el coste real y observa desde la
nueva celda. El coste de un paso se comprueba antes con el coste
planificado (conocido, o `UNKNOWN` 2.2 si la celda no está observada),
nunca con el coste real de una celda sin observar; el coste real solo
se descuenta después de pisarla.

El planificador, en cambio, usa una estimación optimista (todas las
celdas menos las bloqueadas conocidas, a coste `UNKNOWN` si no están
observadas) para ordenar los POIs y decidir si un POI merece
intentarse. Si ni siquiera con esa estimación hay ruta, el POI es
de verdad inalcanzable y se omite; si la hay, puede que la ejecución
descubra después que no lo era, y entonces se salta en ejecución.
Los desvíos a estación no exploran: si no hay ruta por terreno
descubierto a esa estación, fallan de inmediato sin gastar batería,
para que el respaldo a otra estación todavía pueda correr. Y la
exploración a un POI nunca gasta la batería de regreso: se detiene
cuando la batería llega a la ruta conocida más barata a una estación
más un margen de seguridad de 8.0 (ajustado a mano: un paso a coste
máximo, 3.8, más el regreso que puede crecer otro paso, 3.8).

Nota sobre estilo: los archivos del agente ya no llevan docstring de
inicio, como los archivos de `enviro/` (que empiezan directamente con
los imports). Los docstrings de funciones y clases siguen en inglés,
que es el idioma del código del proyecto (los documentos, como este,
van en español).

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

## Algoritmos de búsqueda: A*, Dijkstra, greedy, BFS, DFS, ponderado, beam

Todos comparten vecinos, celdas transitables y costes de paso, así
que una comparación entre ellos varía solo la búsqueda, no el mapa ni
el modelo de coste. El rover elige con `algoritmo_busqueda`:

- **A***: coste pagado + heurística de altura (admisible, ver
  `búsqueda/a_start.py`). Garantiza la ruta planificada más barata.
- **Dijkstra**: A* con heurística 0. Garantiza lo mismo que A*, pero
  suele expandir más nodos porque no tiene dirección hacia el objetivo.
- **Greedy best-first**: solo heurística (distancia euclídea), sin
  mirar el coste pagado. Rápido y con pocos nodos expandidos, pero su
  ruta no tiene por qué ser la más barata.
- **BFS**: menos pasos, sin mirar el coste. Su ruta puede ser la más
  cara en batería aunque tenga los mismos pasos que las demás.
- **A* ponderado** (`weighted`, w = 2.0): f = g + 2h. No es admisible
  y pierde la optimalidad, pero suele ser más rápido; su coste está
  acotado por 2 veces el óptimo cuando h es admisible.
- **Beam** (`beam`, ancho 20): como A*, pero conserva solo los 20
  mejores nodos de la frontera. Es incompleto (puede descartar la
  única ruta) y no óptimo, a cambio de memoria acotada.
- **DFS**: solo se compara en rutas (legs), no en misiones completas.
  Motivo medido: `move_to` replanifica tras cada survey, y DFS no
  tiene subestructura óptima, así que el primer paso de una ruta DFS
  replanificada puede deshacer el avance anterior y el rover oscila
  hasta agotar la batería (semilla 42 con config por defecto: 116
  pasos, 0 POIs entregados, mientras A* entrega los 5). En una ruta
  estática, sin replanificación, DFS sí es comparable: en el leg
  base→poi_0 de la primera instancia aleatoria, DFS cuesta 61.8
  frente a 14.9 de A*. La reserva de retorno en `move_to` se calcula
  siempre con A* (el retorno más barato), para que una búsqueda no
  óptima no aborte la misión por sobreestimar el retorno.

Algoritmos de C1 que **no** se implementan, con motivo: IDDFS es
óptimo solo si todos los costes son iguales, y aquí no lo son;
IDA* y SMA* son variantes acotadas en memoria de A*, innecesarias
porque un mapa 32x32x7 cabe entero en memoria; la búsqueda
bidireccional necesita un criterio de encuentro con costes
asimétricos (bajar cuesta 0, subir cuesta) y un grafo conocido, que
el rover no tiene bajo observabilidad parcial; DE y PSO son para
espacios continuos (conferencia de metaheurísticas) y el orden de
POIs es una permutación.

## Metaheurísticas: random, hill climbing, SA, genético, tabú, ACO

Las seis buscan el orden de visita de los POIs, con la misma interfaz
y el mismo presupuesto de evaluaciones (ver el protocolo abajo):

- **Random search**: órdenes aleatorios, se queda con el mejor.
  Es la línea base: cualquier metaheurística debe superarla para
  justificar su complejidad.
- **Hill climbing**: vecino por intercambio, solo se mueve si mejora
  estrictamente. Es la línea base local: se queda en el primer
  óptimo local que encuentra.
- **Simulated annealing**: un orden, vecino por intercambio (a veces
  inversión de segmento), aceptación probabilística
  `exp((nuevo - actual) / T)` con `T` enfriándose.
- **Algoritmo genético**: población de 20 órdenes, selección por
  torneo, cruce de orden (un segmento de un padre y el resto en el
  orden del otro, para que el hijo siga siendo una permutación válida)
  y mutación por intercambio, con elitismo (los 2 mejores sobreviven).
- **Búsqueda tabú**: un orden, 20 vecinos por iteración, y una memoria
  de los últimos intercambios prohibidos durante 10 iteraciones (con
  aspiración: un movimiento tabú que mejora el mejor global sí se
  permite), para no deshacer el último paso y ciclar entre dos órdenes.
- **ACO**: 10 hormigas construyen órdenes paso a paso, con
  probabilidad proporcional a la feromona del arco POI→POI, que
  evapora con rho = 0.3 y se refuerza en el mejor orden de cada
  iteración. La feromona vive en arcos POI→POI, no en celdas.

La puntuación que evalúan las seis es `interés * 100 - coste_de_viaje`:
el interés domina y el coste solo desempata órdenes con el mismo
interés. Todas devuelven siempre el mejor orden visto, así que
ninguna puede ser peor que el orden inicial (POIs por interés
descendente). El interés de un POI es determinista dado el mapa
(altura + coste de terreno), pero el mapa es aleatorio (config de
terreno aleatoria + semilla), así que el interés recogido es una
variable aleatoria sobre instancias: los puntos altos tienden a
tener más interés por el término de altura, sin que sea una
garantía, porque el término de terreno y la colocación de POIs
también varían.

Limitación conocida: buscan órdenes, no subconjuntos. Un POI alcanzable
se recoge aunque su interés sea 0, si la batería lo permite; descartar
POIs por eficiencia es trabajo futuro, no un error de la versión actual.

## Protocolo experimental (`estadistica.py`, `experimento.py`)

- **Instancias variadas**: 12x12 por defecto (semillas 42, 0, 3), 16x16,
  bloqueos altos con más lava, y la semilla 7 de relieve bajo. Una
  instancia es un par (semilla de mapa, config), con nombre que dice
  qué varía.
- **Corridas declaradas**: los buscadores son deterministas, una
  corrida por instancia (con su tiempo igualmente reportado). Las
  metaheurísticas corren varias veces por instancia con semillas
  declaradas (por defecto 7, 11, 13, 17, 19).
- **Presupuesto fijo e igual**: todas las metaheurísticas reciben
  exactamente el mismo número de evaluaciones de órdenes en cada
  corrida. Los buscadores reciben una misión por instancia, con el
  mismo orden, planificador y mapas.
- **Media y dispersión, nunca el mejor**: cada instancia se resume
  primero, y el resumen general es sobre las medias por instancia (no
  se mezclan corridas de instancias distintas). Cada fila de la tabla
  lleva n, media, desviación, mediana, min/max e IC95.
- **Cuántas corridas bastan**: no hay un número mágico. `estadistica`
  avisa cuando el CV supera 0.20 o el ancho del IC95 relativo supera
  0.40 (umbrales declarados, cambiables), y cuando dos IC95 se solapan
  la conclusión es "no se distinguen con esta evidencia", no "son
  iguales".
- **Conclusión que no excede los números**: en la versión rápida, el
  interés entregado no distingue a nadie, porque todos entregan los
  mismos POIs alcanzables. Lo que distingue a los buscadores es la
  batería gastada: A* y Dijkstra idénticos (como dice la teoría, ambos
  óptimos), greedy y BFS más caros en cada instancia individual
  (semilla 42: A* 93.3, greedy 101.9, BFS 104.7), aunque los IC95
  generales se solapan porque las instancias difieren mucho entre sí.
  Esa es la conclusión honesta con 3 instancias: el orden por instancia
  se sostiene, la media general todavía no.

## Objetivo y estados formales

**Objetivo**: maximizar el interés **recolectado** (y, en el informe,
también el entregado, para que ambas lecturas queden a la vista).
"Recolectado" significa pisar la celda del POI; la misión completa
sigue exigiendo analizar y transmitir en una estación para que el
interés cuente como entregado, porque esos datos nunca llegaron a
una estación si no se transmiten. `ejecutar_mision` devuelve ambas
cantidades: `interes_recolectado` e `interes_entregado`. La variante
"observarlo desde una celda vecina con visibilidad >= 0.7" queda
como variante futura, no implementada.

**Estado (C1)**: s = (pos, batería, memoria, conocido, bloqueados,
sin-celda, estadio), donde pos es la celda actual, batería y memoria
son los recursos restantes, conocido mapea celdas observadas a
terreno, bloqueados/sin-celda son los obstáculos y no-celdas
aprendidos, y estadio asigna a cada POI uno de {sin-visitar,
recogido, analizado, entregado} (exactamente uno por POI, invariante
mutex). Estado inicial s0: pos = base B, batería y memoria llenas,
conocido = survey desde B, todos los POIs sin visitar. Acciones:
mover_a, recolectar, analizar, transmitir, recargar, con sus
precondiciones y efectos (ver `rover.py`). Coste de paso: 0 al bajar
(dz < 0), coste de terreno + penalización de subida en otro caso.
Test de objetivo: todo POI entregable está entregado; la misión
termina honestamente sin entregar si ninguna estación es alcanzable.

**Estado STRIPS (C2b)**: hechos (en ?x) con exactamente uno por
estado, (muestra-en ?m ?x), (tiene ?m), (analizada ?m),
(transmitida ?m) con exactamente un estadio por muestra, y hechos
estáticos (zona-com ?x), (conectado ?x ?y). Dominio en
`rover-domain.pddl`. La batería y la memoria no son hechos STRIPS:
se tratan como recursos fuera del dominio (C2b, sección 6, opción 2:
el planificador decide la secuencia y la capa de recursos inserta
recargas y transmisiones por memoria llena). Heurísticas de
planificación: `planificacion_heuristica.py` calcula h_max (admisible)
y h_add (informativa, no admisible) sobre la relajación que ignora
borrados, para la cadena recolectar→analizar→transmitir.
Supuestos clásicos que el modelo viola (C2b, sección 7): observabilidad
total (el rover solo conoce POIs y estaciones), mundo estático y
determinista (el terreno se descubre al observar), y acciones
instantáneas. El remedio de la conferencia que se aplica es
**replanificación**: ejecutar, observar, replanificar desde el
estado observado, que es exactamente lo que hace `move_to`.

## Resultados medidos

Con `python rover.py 42`: los 5 POIs entregados, interés 3.336 de 3.336
en el mapa, 52 pasos, 3 recargas y 3 transmisiones. Con la semilla 7
solo se entrega 1 POI, y eso es correcto: los otros 4 solo son
alcanzables desde la relay, que está en otro componente que la base, así
que el rover que empieza en la base no puede llegar a ellos. El
planificador los omite en vez de romper la misión.

## Por qué la semilla 7 salió (casi) plana

Corrección primero: en la demo anterior la semilla 7 salió *totalmente*
plana (144 columnas a z=1) porque esa demo corría con el config local
viejo, que todavía tenía `relief_amplitude [0.3, 0.4, 1.0]`. Con el
config de main (`[0.5, 0.7, 1.0]`, el de la rama) la semilla 7 queda
*casi* plana: 140 columnas a z=1 y 4 a z=2. El mecanismo es el mismo en
los dos casos, solo cambia la amplitud:

1. La semilla 7 dibuja la amplitud más baja de la lista. Con el config
   viejo era 0.3; con el de main es 0.5 (el sorteo usa el mismo flujo
   aleatorio, así que elige la misma posición de la lista en ambos).
2. El campo combinado de ruidos se normaliza a [0, 1] y luego se
   encoge alrededor de su media (0.532) multiplicando por la amplitud.
   Con amplitud 0.3 el relieve queda en [0.373, 0.673]; con 0.5 queda en
   [0.266, 0.766].
3. La altura se cuantiza con `int(v * (depth - 1) + 0.5)` para depth 3,
   o sea, umbrales en 0.25 y 0.75: por debajo de 0.25 es z=0, entre 0.25
   y 0.75 es z=1, por encima de 0.75 es z=2.
4. Con amplitud 0.3, *todo* el relieve cae dentro de (0.25, 0.75): todo
   z=1, mapa totalmente plano. Con amplitud 0.5, casi todo sigue dentro
   de esa banda y solo 4 columnas cruzan 0.75: 140 a z=1, 4 a z=2.

No es un error de la semilla 7 ni un mapa roto: es lo que la calibración
ya decía de la amplitud 0.5 (0% de mapas planos, siempre exactamente 2
capas, ~2% de celdas en z=2; aquí 4/144 = 2.8%). La semilla 7 es, por
tanto, una instancia legítima de relieve bajo, no una anomalía, y por
eso está incluida como instancia en el experimento. Lo que sí es
independiente del relieve es que sus POIs estén en otro componente que
la base: eso es conectividad del mapa (rocas/lava), no altura.
