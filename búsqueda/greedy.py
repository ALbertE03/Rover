from __future__ import annotations

import heapq
import itertools
from typing import Dict, Optional, Tuple

from .a_start import (
    AStarResult,
    Coord,
    Heuristic,
    Neighbours,
    StepCost,
    Traversable,
)


def greedy_best_first(
    start: Coord,
    goal: Coord,
    neighbours: Neighbours,
    traversable: Traversable,
    step_cost: StepCost,
    heuristic: Heuristic,
) -> Optional[AStarResult]:
    """A route from ``start`` to ``goal`` guided only by the heuristic.

    Returns ``None`` when the goal cannot be reached. The returned cost
    is the actual cost of the route found, computed from ``step_cost``,
    even though greedy did not optimise it.
    """
    if not traversable(start) or not traversable(goal):
        return None
    if start == goal:
        return AStarResult(path=(start,), cost=0.0, expanded=0)

    counter = itertools.count()
    frontier = [(heuristic(start, goal), next(counter), start)]
    came_from: Dict[Coord, Coord] = {}
    cost_so_far: Dict[Coord, float] = {start: 0.0}
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
            if nxt not in cost_so_far:
                came_from[nxt] = current
                cost_so_far[nxt] = cost_so_far[current] + cost
                heapq.heappush(
                    frontier, (heuristic(nxt, goal), next(counter), nxt)
                )
    return None
