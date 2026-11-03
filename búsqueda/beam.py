from __future__ import annotations

import heapq
import itertools
from typing import Dict, List, Optional, Tuple

from .a_start import (
    AStarResult,
    Coord,
    Heuristic,
    Neighbours,
    StepCost,
    Traversable,
)


def beam_search(
    start: Coord,
    goal: Coord,
    neighbours: Neighbours,
    traversable: Traversable,
    step_cost: StepCost,
    heuristic: Heuristic,
    ancho: int = 20,
) -> Optional[AStarResult]:
    """Beam search with width ``ancho``.

    Like A*, it orders the frontier by f(n) = g(n) + h(n), but it keeps
    only the ``ancho`` best frontier nodes and discards the rest.
    It is therefore incomplete (it can discard every node on the only
    route to the goal) and not optimal, in exchange for bounded
    frontier memory. ``expanded`` counts nodes popped from the
    frontier.
    """
    if ancho < 1:
        raise ValueError(f"beam width must be >= 1, got {ancho}")
    if not traversable(start) or not traversable(goal):
        return None
    if start == goal:
        return AStarResult(path=(start,), cost=0.0, expanded=0)
    counter = itertools.count()
    frontier: List[Tuple[float, int, Coord]] = [
        (heuristic(start, goal), next(counter), start)
    ]
    came_from: Dict[Coord, Coord] = {}
    g_score: Dict[Coord, float] = {start: 0.0}
    expanded = 0
    visited = set()
    while frontier:
        _, _, current = heapq.heappop(frontier)
        if current in visited:
            continue
        visited.add(current)
        if current == goal:
            path = [current]
            total = 0.0
            while path[-1] != start:
                prev = came_from[path[-1]]
                total += step_cost(prev, path[-1])
                path.append(prev)
            path.reverse()
            return AStarResult(path=tuple(path), cost=total, expanded=expanded)
        expanded += 1
        for nxt in neighbours(current):
            if nxt in visited or not traversable(nxt):
                continue
            cost = step_cost(current, nxt)
            if cost < 0:
                raise ValueError("step cost must not be negative")
            tentative = g_score[current] + cost
            if tentative < g_score.get(nxt, float("inf")):
                came_from[nxt] = current
                g_score[nxt] = tentative
                heapq.heappush(
                    frontier,
                    (tentative + heuristic(nxt, goal), next(counter), nxt),
                )
        # Beam: keep only the best ``ancho`` frontier nodes.
        if len(frontier) > ancho:
            frontier = heapq.nsmallest(ancho, frontier)
            heapq.heapify(frontier)
    return None
