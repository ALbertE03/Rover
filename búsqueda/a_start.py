"""A* search, adapted to the Rover terrain.

This module is deliberately generic: it knows nothing about maps, stations
or points of interest. It works on coordinates and on three callables the
caller supplies:

* ``neighbours(coord)``: coordinates the rover may step to from ``coord``.
* ``traversable(coord)``: whether that coordinate may be stood on.
* ``step_cost(from_coord, to_coord)``: the cost of that step.

The Rover (``rover.py``) supplies those callables from its known map: the
neighbours come from ``movement_offsets`` (so ``move_radius`` and
``allow_diagonal`` are honoured), blocked cells are excluded, and the step
cost is the known terrain cost plus the climb penalty, except that a
downhill step costs 0 (see ``rover.py``).

Heuristic and admissibility
----------------------------
A step downhill costs 0, so a heuristic proportional to the distance to
the goal can overestimate: a goal below the start could in principle be
reached almost for free. That makes distance-based heuristics inadmissible
here, and an inadmissible heuristic can return a path that is not the
cheapest one. The heuristic provided here,
:func:`height_heuristic`, is therefore based only on height: to reach a
goal ``dz`` levels above the start, any path needs at least ``dz`` upward
steps, and each upward step costs at least ``min_step_cost +
climb_penalty``. When the goal is at or below the start, the heuristic is
0, which is always admissible. It is weak, but it is honest: A* with this
heuristic never returns a path more expensive than the cheapest one under
the supplied step costs.

Pass ``heuristic=None`` to run plain Dijkstra (heuristic 0 everywhere).
"""

from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple

Coord = Tuple[int, int, int]
Neighbours = Callable[[Coord], Iterable[Coord]]
Traversable = Callable[[Coord], bool]
StepCost = Callable[[Coord, Coord], float]
Heuristic = Callable[[Coord, Coord], float]


@dataclass(frozen=True)
class AStarResult:
    """Result of a successful A* search.

    Attributes:
        path: Coordinates from start to goal, both inclusive.
        cost: Sum of the step costs along ``path``.
        expanded: Number of nodes taken off the frontier (a rough measure
            of how much of the graph the search had to look at).
    """

    path: Tuple[Coord, ...]
    cost: float
    expanded: int


def height_heuristic(
    min_step_cost: float, climb_penalty: float
) -> Heuristic:
    """Build the height-based admissible heuristic described above.

    Args:
        min_step_cost: Cheapest possible cost of one step on flat ground
            (for the default catalogue, plain at 1.0).
        climb_penalty: Extra cost per level gained.
    """

    def heuristic(current: Coord, goal: Coord) -> float:
        gain = goal[2] - current[2]
        if gain <= 0:
            return 0.0
        return gain * (min_step_cost + climb_penalty)

    return heuristic


def a_star(
    start: Coord,
    goal: Coord,
    neighbours: Neighbours,
    traversable: Traversable,
    step_cost: StepCost,
    heuristic: Optional[Heuristic] = None,
) -> Optional[AStarResult]:
    """Find a cheapest path from ``start`` to ``goal``, or ``None``.

    Args:
        start: Starting coordinate.
        goal: Goal coordinate.
        neighbours: Steps allowed from a coordinate.
        traversable: Whether a coordinate may be stood on.
        step_cost: Cost of a step. Must not be negative.
        heuristic: Estimate of the remaining cost. It must never overestimate
            the true remaining cost, otherwise the returned path may not be
            the cheapest one. Defaults to 0 (Dijkstra).

    Returns:
        An :class:`AStarResult` with the path and its cost, or ``None``
        when the goal cannot be reached (for example, when the start or
        the goal itself is not traversable, or when blocked cells cut the
        graph into pieces with no route between them).
    """
    if not traversable(start) or not traversable(goal):
        return None
    if start == goal:
        return AStarResult(path=(start,), cost=0.0, expanded=0)

    estimate = heuristic if heuristic is not None else (lambda _c, _g: 0.0)
    counter = itertools.count()
    # Frontier entries are (f, tie-breaker, coordinate). The counter keeps
    # the heap from ever comparing coordinates against each other.
    frontier: List[Tuple[float, int, Coord]] = [
        (estimate(start, goal), next(counter), start)
    ]
    came_from: Dict[Coord, Coord] = {}
    g_score: Dict[Coord, float] = {start: 0.0}
    expanded = 0

    while frontier:
        _, _, current = heapq.heappop(frontier)
        if current == goal:
            path: List[Coord] = [current]
            while path[-1] != start:
                path.append(came_from[path[-1]])
            path.reverse()
            return AStarResult(
                path=tuple(path), cost=g_score[goal], expanded=expanded
            )
        expanded += 1
        for nxt in neighbours(current):
            if not traversable(nxt):
                continue
            cost = step_cost(current, nxt)
            if cost < 0:
                raise ValueError(
                    f"step cost must not be negative, got {cost} "
                    f"for {current} -> {nxt}"
                )
            tentative = g_score[current] + cost
            if tentative < g_score.get(nxt, float("inf")):
                came_from[nxt] = current
                g_score[nxt] = tentative
                heapq.heappush(
                    frontier,
                    (tentative + estimate(nxt, goal), next(counter), nxt),
                )
    return None
