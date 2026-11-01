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
