from __future__ import annotations

from typing import Dict, Optional

from .a_start import AStarResult, Coord, Neighbours, StepCost, Traversable


def depth_first(
    start: Coord,
    goal: Coord,
    neighbours: Neighbours,
    traversable: Traversable,
    step_cost: StepCost,
) -> Optional[AStarResult]:
    """Depth-first route from ``start`` to ``goal``, or ``None``.

    Conference C1: DFS expands the deepest node first (LIFO frontier).
    It is not optimal in cost: it returns the first route found, which
    may not be the cheapest. In graphs it can loop on cycles, so this
    implementation keeps a visited set (graph DFS); that guarantees
    termination on a finite graph, at the cost of the tree version's
    O(b*m) memory bound. ``expanded`` counts nodes popped from the
    stack, comparable to the other search modules.
    """
    if not traversable(start) or not traversable(goal):
        return None
    if start == goal:
        return AStarResult(path=(start,), cost=0.0, expanded=0)
    stack = [start]
    came_from: Dict[Coord, Coord] = {start: start}
    visited = {start}
    expanded = 0
    while stack:
        current = stack.pop()
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
            if nxt not in visited and traversable(nxt):
                visited.add(nxt)
                came_from[nxt] = current
                stack.append(nxt)
    return None
