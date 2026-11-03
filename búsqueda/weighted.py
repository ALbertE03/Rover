from __future__ import annotations

from typing import Optional

from .a_start import (
    AStarResult,
    Coord,
    Heuristic,
    Neighbours,
    StepCost,
    Traversable,
    a_star,
)


def weighted_a_star(
    start: Coord,
    goal: Coord,
    neighbours: Neighbours,
    traversable: Traversable,
    step_cost: StepCost,
    heuristic: Heuristic,
    peso: float = 2.0,
) -> Optional[AStarResult]:
    """Weighted A*: f(n) = g(n) + w * h(n).

    With w = 1 this is A*. With w > 1 the heuristic is no longer
    admissible, so optimality is lost, but the search is usually
    faster: it is bounded-suboptimal, with a solution cost at most w
    times the optimal cost when h itself is admissible. The returned
    cost is the true cost of the route found, not f.
    """
    if peso < 1.0:
        raise ValueError(f"weighted A* weight must be >= 1, got {peso}")
    return a_star(
        start,
        goal,
        neighbours=neighbours,
        traversable=traversable,
        step_cost=step_cost,
        heuristic=lambda c, g: peso * heuristic(c, g),
    )
