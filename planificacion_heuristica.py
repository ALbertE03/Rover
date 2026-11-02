from __future__ import annotations

from typing import Dict, List, Set, Tuple

AccionSTRIPS = Tuple[Set[str], Set[str], Set[str]]


def _cost_table(
    combiner: str,
    hechos_iniciales: Set[str],
    acciones: List[AccionSTRIPS],
) -> Dict[str, float]:
    """Fact costs under the delete-relaxation, conference C2b section 4.

    Cost(action) = 1 + combine(cost of its preconditions), with
    combine = max for h_max and sum for h_add. Facts only accumulate
    (delete effects ignored), so iteration reaches a fixed point.
    """
    costo: Dict[str, float] = {h: 0.0 for h in hechos_iniciales}
    changed = True
    while changed:
        changed = False
        for pre, add, _del in acciones:
            if any(p not in costo for p in pre):
                continue
            if combiner == "max":
                c_pre = max((costo[p] for p in pre), default=0.0)
            else:
                c_pre = sum(costo[p] for p in pre)
            c_accion = 1.0 + c_pre
            for hecho in add:
                if hecho not in costo or c_accion < costo[hecho]:
                    costo[hecho] = c_accion
                    changed = True
    return costo


def h_max_h_add(
    hechos_iniciales: Set[str],
    objetivo: Set[str],
    acciones: List[AccionSTRIPS],
) -> Tuple[float, float]:
    """(h_max, h_add) for a STRIPS goal, conference C2b section 4.

    h_max takes the maximum cost over goal facts: admissible, but
    pessimistic (it assumes the most expensive subgoal brings the
    others for free). h_add sums them: more informative, but not
    admissible in general, because shared work is counted twice.
    Unreachable goal facts give infinite cost.
    """
    inf = float("inf")
    tabla_max = _cost_table("max", hechos_iniciales, acciones)
    tabla_add = _cost_table("sum", hechos_iniciales, acciones)
    if any(h not in tabla_max for h in objetivo):
        return inf, inf
    h_max = max((tabla_max[h] for h in objetivo), default=0.0)
    h_add = sum(tabla_add[h] for h in objetivo)
    return h_max, h_add


def acciones_rover_pois(pois: List[str]) -> List[AccionSTRIPS]:
    """Abstract STRIPS actions for POI stages, ignoring positions.

    Facts are Tiene(p), Analizada(p), Transmitida(p). Recolectar
    needs no precondition in this abstraction (position is handled
    by the route search); Analizar needs Tiene; Transmitir needs
    Analizada. This is the delete-relaxation view used in the
    report: h_max = 3 for one POI (recolectar, analizar, transmitir
    in a chain), h_add = 3 per POI summed over the goal.
    """
    acciones: List[AccionSTRIPS] = []
    for p in pois:
        acciones.append((set(), {f"Tiene({p})"}, set()))
        acciones.append(({f"Tiene({p})"}, {f"Analizada({p})"}, set()))
        acciones.append(
            ({f"Analizada({p})"}, {f"Transmitida({p})"}, set())
        )
    return acciones
