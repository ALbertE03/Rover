"""Dijkstra search, as a distinct algorithm for comparison.

Dijkstra is A* with a zero heuristic: it expands nodes in order of the
cost already paid, with no estimate of the remaining cost. It is
therefore optimal under the same conditions as A* (non-negative step
costs), but it typically expands many more nodes, because it has no
direction towards the goal. Implementing it as ``a_star`` with
``heuristic=None`` is not a shortcut: that *is* Dijkstra, and keeping
one implementation for both avoids two copies of the same search that
could drift apart. The comparison in the experiment is still meaningful:
same code path, different heuristic, different expanded-node count and
running time for the same optimal path cost.
"""

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
