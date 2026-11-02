from __future__ import annotations

from typing import Optional

from .a_start import AStarResult, Coord, Neighbours, StepCost, Traversable, a_star


def dijkstra(
    start: Coord,
    goal: Coord,
    neighbours: Neighbours,
    traversable: Traversable,
    step_cost: StepCost,
) -> Optional[AStarResult]:
    """Cheapest path from ``start`` to ``goal``, or ``None``.

    See :func:`búsqueda.a_start.a_star` for the argument meanings.
    """
    return a_star(
        start,
        goal,
        neighbours=neighbours,
        traversable=traversable,
        step_cost=step_cost,
        heuristic=None,
    )
