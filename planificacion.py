"""Symbolic planning (assignment section B, not C).

Section B was chosen over section C (CSP) because the assignment allows
exactly one of the two, and planning fits this agent directly: the
planner decides the high-level sequence of actions, and A* resolves each
concrete displacement. A CSP solver would have duplicated the same
ordering, battery and memory reasoning in constraint form without adding
a new capability for this first version. The constraints a CSP would
have imposed are still enforced here, as action preconditions: battery
capacity, memory capacity, precedence between actions, and communication
only at a station. What is *not* modelled yet is a mission time limit
and communication windows beyond "at a station" (stations have radius 0
in the default config, so a window would first need a radius or a
schedule in the map, which does not exist yet).

Actions, preconditions and effects
----------------------------------
====================  =====================================================
Action               Preconditions -> Effects
====================  =====================================================
``mover_a(dest)``    A planned A* route exists and the battery can pay
                     for its next step (checked again step by step while
                     moving) -> position changes, battery decreases
                     (0 on downhill steps), terrain is surveyed on arrival.
``recolectar(poi)``  At the POI cell, POI not yet collected, free memory
                     -> POI enters the raw buffer, memory +1.
``analizar``         At least one raw sample -> raw samples become
                     analysed samples (memory unchanged).
``transmitir``       At a station, at least one analysed sample ->
                     analysed samples are delivered (their interest now
                     counts), their memory is freed.
``recargar``         At a station -> battery restored to full.
====================  =====================================================

Precedence is therefore: collect -> analyse -> transmit, and transmit /
recharge only at a station. A plan that tried to transmit before
analysing, or to collect with a full memory, would fail its preconditions
at execution time instead of silently producing a wrong score.

The planner itself is deliberately simple: it walks the POI order given
by the metaheuristic, inserts a station detour (transmit + recharge)
whenever memory is full or the battery cannot cover the next leg plus a
reserve to the nearest station from the goal, and finishes with a final
station detour to transmit and recharge. It does not search over action
sequences from scratch; the search over orders lives in the
metaheuristic, and the search over routes lives in A*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from búsqueda.a_start import AStarResult
from enviro.terrain.catalogue import terrain
from enviro.terrain.grid import Coord, cell_id, movement_offsets, parse_cell_id
from enviro.terrain.instance import Map
from rover import MEMORY_PER_POI, plan_route

# Score scale for order evaluation: one unit of interest is worth 100
# units of travel cost, so interest dominates the order and travel cost
# only breaks ties between orders with the same interest. Without this
# weighting, a slightly cheaper order that drops a POI would beat an
# order that collects everything.
PESO_INTERES = 100.0


@dataclass(frozen=True)
class Action:
    """One high-level action of a plan.

    Attributes:
        tipo: ``"mover_a"``, ``"recolectar"``, ``"analizar"``,
            ``"transmitir"`` or ``"recargar"``.
        objetivo: A coordinate for ``mover_a``, a POI id for
            ``recolectar``, None otherwise.
    """

    tipo: str
    objetivo: object = None

    def __str__(self) -> str:
        if self.objetivo is None:
            return self.tipo
        return f"{self.tipo}({self.objetivo})"


@dataclass
class PlanResult:
    """A plan plus the POIs it deliberately left out."""

    acciones: List[Action] = field(default_factory=list)
    pois_omitidos: List[str] = field(default_factory=list)


def _leg_cost(
    start: Coord,
    goal: Coord,
    mapa: Map,
    conocidos: Dict[str, str],
    registry: Dict,
    algoritmo: str = "a_star",
) -> Optional[float]:
    params = mapa.params
    result: Optional[AStarResult] = plan_route(
        start,
        goal,
        mapa.cells,
        movement_offsets(params.move_radius, params.move_allow_diagonal),
        conocidos,
        registry,
        params.climb_penalty,
        algoritmo=algoritmo,
    )
    return result.cost if result is not None else None


def evaluar_orden(
    orden: List[str],
    mapa: Map,
    conocidos: Dict[str, str],
    registry: Dict,
    algoritmo: str = "a_star",
) -> Tuple[float, Dict]:
    """Score an order of POI ids, for the metaheuristic.

    Simulates the tour abstractly (no rover moves): legs are A* planned
    costs from the knowledge snapshot, battery is refilled by a station
    detour whenever the next leg does not fit, and memory is freed by a
    station detour whenever it is full. A POI with no planned route is
    skipped and contributes no interest. Returns ``(score, details)``
    with ``score = interest * PESO_INTERES - travel_cost``.
    """
    params = mapa.params
    stations = [s.center for s in mapa.stations]
    if not stations:
        return float("-inf"), {"interes": 0.0, "coste": 0.0, "alcanzados": 0}

    def nearest_reachable(coord: Coord) -> Optional[Tuple[Coord, float]]:
        """Cheapest reachable station from ``coord``, or ``None``.

        Euclidean closeness is not enough: a station can be close and
        still be in a disconnected component (see the relay in seed 42).
        """
        best: Optional[Tuple[Coord, float]] = None
        for station in stations:
            cost = _leg_cost(coord, station, mapa, conocidos, registry, algoritmo)
            if cost is None:
                continue
            if best is None or cost < best[1]:
                best = (station, cost)
        return best

    pos = stations[0]
    battery = params.battery
    memory = 0.0
    interest = 0.0
    travel = 0.0
    reached = 0
    for poi_id in orden:
        goal = parse_cell_id(mapa.pois[poi_id].cell_id)
        leg = _leg_cost(pos, goal, mapa, conocidos, registry, algoritmo)
        if leg is None:
            continue
        if memory + MEMORY_PER_POI > params.memory + 1e-9:
            detour_station = nearest_reachable(pos)
            if detour_station is None:
                continue
            detour_coord, detour = detour_station
            travel += detour
            pos = detour_coord
            battery = params.battery
            memory = 0.0
            leg = _leg_cost(pos, goal, mapa, conocidos, registry, algoritmo)
            if leg is None:
                continue
        reserve_station = nearest_reachable(goal)
        if reserve_station is None:
            # The POI could be reached but its interest could never be
            # delivered at a station, so it does not count.
            continue
        reserve = reserve_station[1]
        if leg + reserve > battery:
            detour_station = nearest_reachable(pos)
            if detour_station is None:
                continue
            detour_coord, detour = detour_station
            travel += detour
            pos = detour_coord
            battery = params.battery
            leg = _leg_cost(pos, goal, mapa, conocidos, registry, algoritmo)
            if leg is None:
                continue
        travel += leg
        battery -= leg
        pos = goal
        memory += MEMORY_PER_POI
        interest += mapa.pois[poi_id].interest
        reached += 1
    return interest * PESO_INTERES - travel, {
        "interes": interest,
        "coste": travel,
        "alcanzados": reached,
    }


class Planificador:
    """Turn a POI order into high-level actions, and execute them.

    The planner tracks a *planned* position, battery and memory (using
    planned leg costs) while building the plan. Execution may differ
    from the plan -- actual terrain costs differ from planned ones -- so
    execution reports failures per action instead of assuming the plan
    is exact, and a failed displacement skips only that POI's collect /
    analyse, not the rest of the mission.
    """

    def __init__(self, rover) -> None:
        self.rover = rover

    def planificar(self, orden: List[str]) -> PlanResult:
        mapa = self.rover.mapa
        params = mapa.params
        registry = self.rover.registry
        conocidos = dict(self.rover.known)
        algoritmo = self.rover.algoritmo_busqueda
        pos = self.rover.pos
        battery = self.rover.battery
        memory = self.rover.memory_used
        acciones: List[Action] = []
        omitidos: List[str] = []

        def estacion_cercana(coord: Coord) -> Optional[Coord]:
            """Cheapest reachable station from ``coord``, or ``None``."""
            reachable = self.rover.nearest_reachable_station(coord)
            return reachable[0].center if reachable is not None else None

        def ir_a(dest: Coord) -> bool:
            nonlocal pos, battery
            leg = _leg_cost(pos, dest, mapa, conocidos, registry, algoritmo)
            if leg is None:
                return False
            acciones.append(Action("mover_a", dest))
            pos = dest
            battery -= leg
            return True

        for poi_id in orden:
            goal = self.rover.poi_coord(poi_id)
            if memory + MEMORY_PER_POI > params.memory + 1e-9:
                station = estacion_cercana(pos)
                if station is None or not ir_a(station):
                    omitidos.append(poi_id)
                    continue
                acciones.append(Action("transmitir"))
                acciones.append(Action("recargar"))
                memory = 0.0
                battery = params.battery
            leg = _leg_cost(pos, goal, mapa, conocidos, registry, algoritmo)
            if leg is None:
                omitidos.append(poi_id)
                continue
            station_goal = estacion_cercana(goal)
            if station_goal is None:
                omitidos.append(poi_id)
                continue
            reserve = _leg_cost(goal, station_goal, mapa, conocidos, registry, algoritmo)
            reserve = reserve if reserve is not None else 0.0
            if leg + reserve > battery:
                station = estacion_cercana(pos)
                if station is None or not ir_a(station):
                    omitidos.append(poi_id)
                    continue
                acciones.append(Action("recargar"))
                battery = params.battery
                leg = _leg_cost(pos, goal, mapa, conocidos, registry, algoritmo)
                if leg is None:
                    omitidos.append(poi_id)
                    continue
            if not ir_a(goal):
                omitidos.append(poi_id)
                continue
            acciones.append(Action("recolectar", poi_id))
            acciones.append(Action("analizar"))
            memory += MEMORY_PER_POI

        station = estacion_cercana(pos)
        if station is not None and ir_a(station):
            if memory > 0:
                acciones.append(Action("transmitir"))
            acciones.append(Action("recargar"))
        return PlanResult(acciones=acciones, pois_omitidos=omitidos)

    def ejecutar(self, rover, acciones: List[Action]) -> List[str]:
        """Execute actions on ``rover``, reporting one line per action.

        A failed ``mover_a`` marks its POI as skipped: the following
        ``recolectar``/``analizar`` for that POI are skipped as well, but
        later actions (including a station ``transmitir``/``recargar``)
        still run. A failed ``transmitir`` (for example, because the
        buffer holds only raw samples) is reported and skipped, not
        fatal.
        """
        traza: List[str] = []
        saltar_poi: Optional[str] = None
        for accion in acciones:
            if accion.tipo == "mover_a":
                saltar_poi = None
            if saltar_poi is not None and accion.tipo in (
                "recolectar",
                "analizar",
            ):
                traza.append(f"omitido {accion}: POI anterior no alcanzado")
                continue
            try:
                traza.append(rover.execute_action(accion))
            except Exception as exc:  # PreconditionError and route failures
                traza.append(f"FALLO {accion}: {exc}")
                if accion.tipo == "mover_a":
                    saltar_poi = "mover_a"
                # A failed transmit/recharge at the final station is not
                # fatal either: the mission simply ends with samples
                # still buffered, which the report makes visible.
        return traza
