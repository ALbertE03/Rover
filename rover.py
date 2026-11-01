from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from búsqueda.a_start import AStarResult, a_star, height_heuristic
from búsqueda.bfs import breadth_first
from búsqueda.dijkstra import dijkstra
from búsqueda.greedy import greedy_best_first
from enviro.terrain.catalogue import TERRAIN, UNKNOWN, terrain
from enviro.terrain.grid import (
    Coord,
    cell_id,
    distance,
    movement_offsets,
    neighbour_offsets,
    parse_cell_id,
)
from enviro.terrain.instance import Map

# One collected point of interest occupies this much sample memory.
MEMORY_PER_POI = 1.0


class PreconditionError(ValueError):
    """An action was attempted whose preconditions do not hold."""


# ---------------------------------------------------------------------------
# Pure planning helpers (no Rover state): shared by Rover.move_to and by the
# planner's order evaluation, so both plan with exactly the same costs.
# ---------------------------------------------------------------------------


def build_neighbours(
    cells: Dict,
    offsets: Tuple[Coord, ...],
    known_blocked=None,
) -> Callable[[Coord], List[Coord]]:
    """Neighbour coordinates a rover may step to from a coordinate.

    A destination must be a real cell of the map and must not be known
    to be blocked. Blocked status is only known for cells the rover has
    surveyed (or tried to step into); an unsurveyed cell is assumed
    traversable until it is discovered otherwise, it is never assumed
    blocked from the true map.
    """
    blocked = known_blocked if known_blocked is not None else set()

    def neighbours(current: Coord) -> List[Coord]:
        x, y, z = current
        out = []
        for dx, dy, dz in offsets:
            dest = (x + dx, y + dy, z + dz)
            cell = cells.get(cell_id(*dest))
            if cell is not None and cell_id(*dest) not in blocked:
                out.append(dest)
        return out

    return neighbours


def build_planned_cost(
    known: Dict[str, str],
    registry: Dict,
    climb_penalty: float,
) -> Callable[[Coord, Coord], float]:
    """Step cost for planning, from the rover's current knowledge.

    Unknown destination terrain costs ``UNKNOWN`` (2.2 by default).
    Downhill steps cost 0; otherwise the cost is the known terrain cost
    plus ``climb_penalty`` per level gained.
    """
    unknown_cost = terrain(UNKNOWN, registry).cost

    def cost(current: Coord, dest: Coord) -> float:
        dz = dest[2] - current[2]
        if dz < 0:
            return 0.0
        name = known.get(cell_id(*dest))
        ground = terrain(name, registry).cost if name else unknown_cost
        return ground + climb_penalty * dz

    return cost


def plan_route(
    start: Coord,
    goal: Coord,
    cells: Dict,
    offsets: Tuple[Coord, ...],
    known: Dict[str, str],
    registry: Dict,
    climb_penalty: float,
    algoritmo: str = "a_star",
    known_blocked=None,
) -> Optional[AStarResult]:
    """Planned route from ``start`` to ``goal`` with ``algoritmo``.

    ``algoritmo`` is one of ``"a_star"``, ``"dijkstra"``, ``"greedy"``
    or ``"bfs"``. All four share the same neighbours, traversable cells
    and step costs, so a comparison between them varies only the search
    itself, not the map or the cost model. A* and Dijkstra guarantee the
    cheapest planned route; greedy and BFS do not, which is the point
    of comparing them. Traversability follows the rover's knowledge:
    only cells in ``known_blocked`` are excluded, unsurveyed cells are
    assumed traversable.
    """
    blocked = known_blocked if known_blocked is not None else set()
    neighbours = build_neighbours(cells, offsets, blocked)
    min_cost = min(t.cost for t in registry.values() if t.name != UNKNOWN)

    def is_traversable(coord: Coord) -> bool:
        cell = cells.get(cell_id(*coord))
        return cell is not None and cell_id(*coord) not in blocked

    cost_fn = build_planned_cost(known, registry, climb_penalty)
    if algoritmo == "a_star":
        return a_star(
            start,
            goal,
            neighbours=neighbours,
            traversable=is_traversable,
            step_cost=cost_fn,
            heuristic=height_heuristic(min_cost, climb_penalty),
        )
    if algoritmo == "dijkstra":
        return dijkstra(
            start,
            goal,
            neighbours=neighbours,
            traversable=is_traversable,
            step_cost=cost_fn,
        )
    if algoritmo == "greedy":
        return greedy_best_first(
            start,
            goal,
            neighbours=neighbours,
            traversable=is_traversable,
            step_cost=cost_fn,
            heuristic=lambda c, g: distance(c, g) * min_cost,
        )
    if algoritmo == "bfs":
        return breadth_first(
            start,
            goal,
            neighbours=neighbours,
            traversable=is_traversable,
            step_cost=cost_fn,
        )
    raise ValueError(
        f"unknown search algorithm {algoritmo!r}; expected 'a_star', "
        "'dijkstra', 'greedy' or 'bfs'"
    )


@dataclass
class Rover:
    """A rover moving on a generated map, under partial observability.

    Attributes:
        mapa: The generated map (terrain, stations, POIs).
        pos: Current coordinate. Starts at the base station.
        battery: Remaining battery. Starts full.
        memory_used: Sample memory currently occupied.
        known: Cell id -> terrain name, for surveyed cells only.
        known_blocked: Cell ids known to be blocked, from survey or
            from a failed step attempt, never from the true map.
        delivered_interest: Interest already transmitted at a station.
        path: Every coordinate stepped on, in order, including the start.
        steps: Number of steps taken.
    """

    mapa: Map
    registry: Dict = field(default_factory=lambda: dict(TERRAIN))
    algoritmo_busqueda: str = "a_star"
    pos: Coord = field(init=False)
    battery: float = field(init=False)
    memory_used: float = field(init=False)
    known: Dict[str, str] = field(default_factory=dict, init=False)
    known_blocked: set = field(default_factory=set, init=False)
    delivered_interest: float = field(default=0.0, init=False)
    path: List[Coord] = field(default_factory=list, init=False)
    steps: int = field(default=0, init=False)
    recharges: int = field(default=0, init=False)
    transmits: int = field(default=0, init=False)
    expanded_total: int = field(default=0, init=False)
    bateria_gastada_total: float = field(default=0.0, init=False)
    # POI ids by stage. A POI is in exactly one of these (or nowhere).
    _raw: List[str] = field(default_factory=list, init=False)
    _analysed: List[str] = field(default_factory=list, init=False)
    _delivered: List[str] = field(default_factory=list, init=False)
    _collected: List[str] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if not self.mapa.stations:
            raise ValueError("the map has no stations; the rover has no base")
        self.pos = self.mapa.stations[0].center
        self.battery = self.mapa.params.battery
        self.memory_used = 0.0
        self.path = [self.pos]
        self.survey()

    # -- stations -----------------------------------------------------------

    @property
    def base(self):
        return self.mapa.stations[0]

    @property
    def relays(self):
        return self.mapa.stations[1:]

    def station_at(self, coord: Coord):
        for station in self.mapa.stations:
            if station.center == coord:
                return station
        return None

    def at_station(self) -> bool:
        return self.station_at(self.pos) is not None

    def nearest_station(self, coord: Coord):
        return min(
            self.mapa.stations, key=lambda s: (distance(coord, s.center), s.id)
        )

    def nearest_reachable_station(self, coord: Coord):
        """Nearest station by planned A* cost, not by straight-line distance.

        A station can be the closest in Euclidean distance and still be
        unreachable (its component may be cut off by blocked cells, as
        the relay is in seed 42). Detours must therefore use this method:
        it returns ``(station, leg_cost)`` for the cheapest reachable
        station, or ``None`` when no station can be reached from ``coord``.
        """
        best = None
        for station in self.mapa.stations:
            cost = self.planned_leg_cost(coord, station.center)
            if cost is None:
                continue
            if best is None or cost < best[1]:
                best = (station, cost)
        return best

    # -- survey ---------------------------------------------------------------

    def survey_radius(self) -> float:
        """Radius revealed from the current position.

        Height raises it (``survey_height_bonus`` at the top layer) and
        the visibility of the terrain underfoot scales it: plain reveals
        more than crevasse.
        """
        params = self.mapa.params
        if params.depth > 1:
            height_fraction = self.pos[2] / (params.depth - 1)
        else:
            height_fraction = 0.0
        base_radius = params.move_radius + (
            params.survey_height_bonus * height_fraction
        )
        standing = self.known.get(cell_id(*self.pos))
        if standing is None:
            # The rover always knows the ground it stands on (survey()
            # reveals it first); this is only a defensive fallback.
            return base_radius
        return base_radius * terrain(standing, self.registry).visibility

    def survey(self) -> int:
        """Reveal the terrain around the current position.

        Returns the number of cells revealed for the first time.
        Surveying a cell reveals both its terrain type and whether it
        is blocked; nothing else reveals either of those two facts.
        """
        # The ground underfoot is always revealed first, so the radius
        # below is computed with a known visibility, never with UNKNOWN.
        own = self.mapa.cells.get(cell_id(*self.pos))
        if own is not None and cell_id(*self.pos) not in self.known:
            self.known[cell_id(*self.pos)] = own.true_terrain
            if own.blocked:
                self.known_blocked.add(cell_id(*self.pos))
            revealed = 1
        else:
            revealed = 0
        radius = self.survey_radius()
        if radius <= 0:
            return revealed
        for dx, dy, dz in neighbour_offsets(radius):
            dest = (
                self.pos[0] + dx,
                self.pos[1] + dy,
                self.pos[2] + dz,
            )
            dest_id = cell_id(*dest)
            if dest_id in self.known:
                continue
            cell = self.mapa.cells.get(dest_id)
            if cell is not None:
                self.known[dest_id] = cell.true_terrain
                if cell.blocked:
                    self.known_blocked.add(dest_id)
                revealed += 1
        return revealed

    # -- costs ----------------------------------------------------------------

    def actual_step_cost(self, current: Coord, dest: Coord) -> float:
        """Battery actually spent stepping from ``current`` to ``dest``.

        Uses the true terrain, not the known one: the physical cost is
        what it is, whether the rover had surveyed that cell or not.
        Downhill steps cost 0.
        """
        dz = dest[2] - current[2]
        if dz < 0:
            return 0.0
        cell = self.mapa.cells[cell_id(*dest)]
        return terrain(cell.true_terrain, self.registry).cost + (
            self.mapa.params.climb_penalty * dz
        )

    def planned_route(self, goal: Coord) -> Optional[AStarResult]:
        params = self.mapa.params
        return plan_route(
            self.pos,
            goal,
            self.mapa.cells,
            movement_offsets(params.move_radius, params.move_allow_diagonal),
            self.known,
            self.registry,
            params.climb_penalty,
            algoritmo=self.algoritmo_busqueda,
            known_blocked=self.known_blocked,
        )

    def planned_leg_cost(self, start: Coord, goal: Coord) -> Optional[float]:
        params = self.mapa.params
        result = plan_route(
            start,
            goal,
            self.mapa.cells,
            movement_offsets(params.move_radius, params.move_allow_diagonal),
            self.known,
            self.registry,
            params.climb_penalty,
            algoritmo=self.algoritmo_busqueda,
            known_blocked=self.known_blocked,
        )
        return result.cost if result is not None else None

    # -- movement ---------------------------------------------------------------

    def move_to(self, goal: Coord) -> Tuple[bool, List[Coord], float]:
        """Walk to ``goal`` with online replanning, step by step.

        After every step the rover surveys its new position and replans
        from there, so a terrain cost revealed mid-route can change the
        rest of the route. An unsurveyed cell is planned through
        optimistically; if the rover then tries to step into it and it
        turns out to be blocked, it does not move and spends no battery,
        it only learns that the cell is blocked and replans around it.
        Returns ``(reached, steps_taken, battery_spent)``. It returns
        ``reached=False`` (without raising) when there is no planned
        route, or when the battery cannot pay for the next step: the
        planner treats that POI as skipped and moves on.
        """
        taken: List[Coord] = []
        spent = 0.0
        max_steps = len(self.mapa.cells) * 4 + 100
        attempts = 0
        while self.pos != goal:
            self.survey()
            result = self.planned_route(goal)
            if result is None or len(result.path) < 2:
                return False, taken, spent
            self.expanded_total += result.expanded
            nxt = result.path[1]
            nxt_cell = self.mapa.cells.get(cell_id(*nxt))
            if nxt_cell is not None and nxt_cell.blocked:
                self.known_blocked.add(cell_id(*nxt))
                attempts += 1
                if attempts > max_steps:
                    return False, taken, spent
                continue
            cost = self.actual_step_cost(self.pos, nxt)
            if cost > self.battery:
                return False, taken, spent
            self.pos = nxt
            self.path.append(nxt)
            taken.append(nxt)
            self.steps += 1
            self.battery -= cost
            self.bateria_gastada_total += cost
            spent += cost
            if len(taken) > max_steps:
                return False, taken, spent
        self.survey()
        return True, taken, spent

    # -- high-level actions (preconditions + effects) ---------------------------

    def poi_coord(self, poi_id: str) -> Coord:
        return parse_cell_id(self.mapa.pois[poi_id].cell_id)

    def poi_interest(self, poi_id: str) -> float:
        return self.mapa.pois[poi_id].interest

    def collect(self, poi_id: str) -> None:
        """Preconditions: at the POI cell, POI not yet collected, free
        memory. Effect: the POI enters the raw buffer, memory +1."""
        if self.pos != self.poi_coord(poi_id):
            raise PreconditionError(
                f"collect {poi_id}: rover is at {self.pos}, "
                f"POI is at {self.poi_coord(poi_id)}"
            )
        if poi_id in self._collected:
            raise PreconditionError(f"collect {poi_id}: already collected")
        if self.memory_used + MEMORY_PER_POI > self.mapa.params.memory + 1e-9:
            raise PreconditionError(
                f"collect {poi_id}: memory full "
                f"({self.memory_used}/{self.mapa.params.memory}); "
                "transmit at a station first"
            )
        self._raw.append(poi_id)
        self._collected.append(poi_id)
        self.memory_used += MEMORY_PER_POI

    def analyse(self) -> None:
        """Preconditions: at least one raw sample. Effect: raw samples
        become analysed samples (memory unchanged)."""
        if not self._raw:
            raise PreconditionError("analyse: no raw samples to analyse")
        self._analysed.extend(self._raw)
        self._raw.clear()

    def transmit(self) -> float:
        """Preconditions: at a station, at least one analysed sample.
        Effect: analysed samples are delivered, their memory is freed,
        and their interest counts towards the objective. Returns the
        interest delivered by this action."""
        if not self.at_station():
            raise PreconditionError("transmit: rover is not at a station")
        if not self._analysed:
            raise PreconditionError("transmit: no analysed samples to send")
        interest = sum(self.poi_interest(p) for p in self._analysed)
        self._delivered.extend(self._analysed)
        self._analysed.clear()
        # Delivered samples no longer occupy memory; raw samples still do.
        self.memory_used = MEMORY_PER_POI * len(self._raw)
        self.delivered_interest += interest
        self.transmits += 1
        return interest

    def recharge(self) -> None:
        """Preconditions: at a station. Effect: battery restored to full."""
        if not self.at_station():
            raise PreconditionError("recharge: rover is not at a station")
        self.battery = self.mapa.params.battery
        self.recharges += 1

    def execute_action(self, action) -> str:
        """Execute one high-level action object (duck-typed).

        The action carries ``tipo`` (``"mover_a"``, ``"recolectar"``,
        ``"analizar"``, ``"transmitir"`` or ``"recargar"``) and
        ``objetivo`` (a coordinate for ``mover_a``, a POI id for
        ``recolectar``, None otherwise). Returns a short trace line.
        """
        tipo = action.tipo
        if tipo == "mover_a":
            reached, taken, spent = self.move_to(action.objetivo)
            if not reached:
                raise PreconditionError(
                    f"mover_a {action.objetivo}: no route or battery "
                    "ran out mid-route"
                )
            return (
                f"mover_a {action.objetivo}: {len(taken)} pasos, "
                f"batería gastada {spent:.1f}, batería restante "
                f"{self.battery:.1f}"
            )
        if tipo == "recolectar":
            self.collect(action.objetivo)
            return (
                f"recolectar {action.objetivo}: interés "
                f"{self.poi_interest(action.objetivo):.3f}, memoria "
                f"{self.memory_used}/{self.mapa.params.memory}"
            )
        if tipo == "analizar":
            self.analyse()
            return "analizar: muestras en bruto -> analizadas"
        if tipo == "transmitir":
            interest = self.transmit()
            return (
                f"transmitir: interés entregado {interest:.3f}, total "
                f"entregado {self.delivered_interest:.3f}"
            )
        if tipo == "recargar":
            self.recharge()
            return f"recargar: batería a {self.battery:.1f}"
        raise ValueError(f"unknown action type {tipo!r}")

    # -- mission wiring -----------------------------------------------------------

    @property
    def delivered_pois(self) -> List[str]:
        return list(self._delivered)

    @property
    def collected_pois(self) -> List[str]:
        return list(self._collected)


def ejecutar_mision(
    semilla: int = 42,
    config: Optional[Dict] = None,
    iteraciones_sa: Optional[int] = None,
    semilla_sa: int = 7,
    algoritmo_busqueda: str = "a_star",
    metaheuristica: str = "simulated_annealing",
    presupuesto_evaluaciones: int = 300,
    semilla_metaheuristica: Optional[int] = None,
) -> Dict:
    """Run one full mission and return a report.

    Wiring: the metaheuristic proposes a POI order from the knowledge
    available at the start; the planner turns that order into high-level
    actions; the rover executes them, resolving every displacement with
    the chosen search algorithm and surveying as it goes.

    Args:
        metaheuristica: ``"simulated_annealing"``, ``"genetico"``,
            ``"tabu"`` or ``"ninguna"`` (fixed interest-descending order,
            no metaheuristic; the mission is then deterministic).
        presupuesto_evaluaciones: Evaluation budget shared by every
            metaheuristic in a comparison, so no metaheuristic wins by
            simply evaluating more orders. For simulated annealing it
            means ``presupuesto - 1`` iterations plus the initial
            evaluation; the genetic algorithm and tabu search stop
            exactly at this many evaluations.
    """
    import time

    # Lazy imports: the planner needs a Rover and the rover needs the
    # planner only for this wiring function.
    from metaheuristica import (
        AlgoritmoGenetico,
        BusquedaTabu,
        SimulatedAnnealing,
    )
    from planificacion import Planificador, evaluar_orden

    from enviro.terrain import InstanceParams, MapGenerator

    inicio = time.perf_counter()
    mapa = MapGenerator(
        InstanceParams.from_config(seed=semilla, config=config)
    ).create()
    rover = Rover(mapa, algoritmo_busqueda=algoritmo_busqueda)
    conocidos_inicio = dict(rover.known)
    bloqueados_inicio = set(rover.known_blocked)
    cache_tramos: Dict = {}
    pois = list(mapa.pois.keys())
    orden_inicial = sorted(pois, key=lambda p: -mapa.pois[p].interest)

    def evaluar(orden: List[str]) -> float:
        return evaluar_orden(
            orden,
            mapa,
            conocidos_inicio,
            rover.registry,
            algoritmo=algoritmo_busqueda,
            known_blocked=bloqueados_inicio,
            cache=cache_tramos,
        )[0]

    puntuacion_inicial = evaluar(orden_inicial)
    semilla_meta = (
        semilla_metaheuristica if semilla_metaheuristica is not None else semilla_sa
    )
    if metaheuristica == "ninguna":
        mejor_orden, mejor_puntuacion = orden_inicial, puntuacion_inicial
    elif metaheuristica == "simulated_annealing":
        iteraciones = (
            iteraciones_sa
            if iteraciones_sa is not None
            else max(0, presupuesto_evaluaciones - 1)
        )
        sa = SimulatedAnnealing(
            evaluar, iteraciones=iteraciones, semilla=semilla_meta
        )
        mejor_orden, mejor_puntuacion, _h = sa.optimizar(orden_inicial)
    elif metaheuristica == "genetico":
        ga = AlgoritmoGenetico(
            evaluar, presupuesto=presupuesto_evaluaciones, semilla=semilla_meta
        )
        mejor_orden, mejor_puntuacion, _h = ga.optimizar(orden_inicial)
    elif metaheuristica == "tabu":
        tabu = BusquedaTabu(
            evaluar, presupuesto=presupuesto_evaluaciones, semilla=semilla_meta
        )
        mejor_orden, mejor_puntuacion, _h = tabu.optimizar(orden_inicial)
    else:
        raise ValueError(
            f"unknown metaheuristic {metaheuristica!r}; expected "
            "'simulated_annealing', 'genetico', 'tabu' or 'ninguna'"
        )
    planificador = Planificador(rover)
    plan = planificador.planificar(mejor_orden)
    traza = planificador.ejecutar(rover, plan.acciones)
    duracion = time.perf_counter() - inicio

    return {
        "semilla": semilla,
        "algoritmo_busqueda": algoritmo_busqueda,
        "metaheuristica": metaheuristica,
        "presupuesto_evaluaciones": (
            presupuesto_evaluaciones if metaheuristica != "ninguna" else 0
        ),
        "estacion_base": rover.base.center,
        "orden_inicial": orden_inicial,
        "puntuacion_inicial": round(puntuacion_inicial, 2),
        "orden_sa": mejor_orden,
        "orden_final": mejor_orden,
        "puntuacion_sa": round(mejor_puntuacion, 2),
        "puntuacion_final": round(mejor_puntuacion, 2),
        "pois_omitidos_en_plan": plan.pois_omitidos,
        "acciones": [str(a) for a in plan.acciones],
        "traza": traza,
        "pois_entregados": rover.delivered_pois,
        "interes_entregado": round(rover.delivered_interest, 3),
        "interes_total_mapa": round(
            sum(p.interest for p in mapa.pois.values()), 3
        ),
        "pasos": rover.steps,
        "bateria_final": round(rover.battery, 1),
        "bateria_gastada_total": round(rover.bateria_gastada_total, 1),
        "nodos_expandidos": rover.expanded_total,
        "tiempo_segundos": round(duracion, 3),
        "recargas": rover.recharges,
        "transmisiones": rover.transmits,
        "celdas_conocidas": len(rover.known),
        "celdas_bloqueadas_conocidas": len(rover.known_blocked),
        "celdas_totales": len(mapa.cells),
    }


def _main(argv: List[str]) -> int:
    semilla = int(argv[1]) if len(argv) > 1 else 42
    informe = ejecutar_mision(semilla=semilla)
    print(f"Misión, semilla {informe['semilla']}")
    print(f"Base: {informe['estacion_base']}")
    print(
        f"Orden inicial (por interés): {informe['orden_inicial']} "
        f"-> puntuación {informe['puntuacion_inicial']}"
    )
    print(
        f"Orden tras {informe['metaheuristica']}: {informe['orden_final']} "
        f"-> puntuación {informe['puntuacion_final']} "
        f"(búsqueda: {informe['algoritmo_busqueda']}, "
        f"{informe['tiempo_segundos']} s, "
        f"{informe['nodos_expandidos']} nodos expandidos)"
    )
    if informe["pois_omitidos_en_plan"]:
        print(f"POIs omitidos en el plan: {informe['pois_omitidos_en_plan']}")
    print("Plan:")
    for accion in informe["acciones"]:
        print(f"  - {accion}")
    print("Ejecución:")
    for linea in informe["traza"]:
        print(f"  {linea}")
    print(
        f"Resultado: {len(informe['pois_entregados'])} POIs entregados, "
        f"interés {informe['interes_entregado']} de "
        f"{informe['interes_total_mapa']} en el mapa, "
        f"{informe['pasos']} pasos, batería final "
        f"{informe['bateria_final']}, {informe['recargas']} recargas, "
        f"{informe['transmisiones']} transmisiones, "
        f"{informe['celdas_conocidas']}/{informe['celdas_totales']} "
        "celdas conocidas al final."
    )
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
