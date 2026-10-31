"""Breadth-first search, as a distinct algorithm for comparison.

BFS expands nodes level by level and therefore finds a route with the
fewest *steps*, regardless of how expensive those steps are. On a map
where plain costs 1.0 and crevasse costs 3.2, the fewest-step route can
be considerably more expensive in battery than the cheapest route, and
that gap is what the experiment measures. BFS needs no step costs and
no heuristic to search; the returned cost is computed afterwards from
``step_cost`` so it can be compared with the other algorithms.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, Optional

from .a_start import AStarResult, Coord, Neighbours, StepCost, Traversable


def breadth_first(
    start: Coord,
    goal: Coord,
    neighbours: Neighbours,
    traversable: Traversable,
    step_cost: StepCost,
) -> Optional[AStarResult]:
    """A fewest-step route from ``start`` to ``goal``, or ``None``."""
    if not traversable(start) or not traversable(goal):
        return None
    if start == goal:
        return AStarResult(path=(start,), cost=0.0, expanded=0)

    frontier = deque([start])
    came_from: Dict[Coord, Coord] = {start: start}
    expanded = 0
    while frontier:
        current = frontier.popleft()
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
            if nxt not in came_from and traversable(nxt):
                came_from[nxt] = current
                frontier.append(nxt)
    return None
