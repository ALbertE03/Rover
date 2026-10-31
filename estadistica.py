"""Statistics for the experimental protocol.

The protocol this module enforces is simple to state and easy to
violate by accident, so it is written here instead of left to each
experiment script:

* Several instances, of different sizes and difficulties.
* Several runs per instance, with declared seeds, for every algorithm
  with a random component. Deterministic algorithms run once per
  instance, but their time is still reported.
* A fixed compute budget, equal for every algorithm compared.
* Mean *and* dispersion reported, never the best run alone.
* Conclusions that do not exceed the numbers: if two algorithms cannot
  be distinguished with the evidence obtained, that must be said.

This module only uses the standard library. The 95% confidence interval
is the normal approximation ``mean +/- 1.96 * standard_error``; for
small samples (fewer than about 30 runs) a t-interval would be wider,
so these intervals are, if anything, optimistic. That limitation is
part of why ``necesita_mas_datos`` exists: it warns when the interval
is wide relative to the mean, instead of letting a narrow-looking
interval smuggle in a conclusion the data cannot support.
"""

from __future__ import annotations

import math
import statistics
from typing import Dict, List, Tuple


def resumen(valores: List[float]) -> Dict:
    """Summary of a list of measurements.

    Returns a dict with ``n``, ``media``, ``desviacion`` (sample
    standard deviation, 0 when ``n < 2``), ``mediana``, ``minimo``,
    ``maximo``, ``error_estandar``, ``ic95`` as a ``(low, high)`` pair,
    ``cv`` (coefficient of variation, ``desviacion / |media|``) and
    ``ancho_ic_relativo`` (interval width relative to ``|media|``).
    """
    if not valores:
        raise ValueError("resumen: no hay valores que resumir")
    n = len(valores)
    media = statistics.fmean(valores)
    desviacion = statistics.stdev(valores) if n > 1 else 0.0
    error = desviacion / math.sqrt(n) if n > 0 else 0.0
    return {
        "n": n,
        "media": media,
        "desviacion": desviacion,
        "mediana": statistics.median(valores),
        "minimo": min(valores),
        "maximo": max(valores),
        "error_estandar": error,
        "ic95": (media - 1.96 * error, media + 1.96 * error),
        "cv": (desviacion / abs(media)) if media != 0 else float("inf"),
        "ancho_ic_relativo": (
            (2 * 1.96 * error / abs(media)) if media != 0 else float("inf")
        ),
    }


def necesita_mas_datos(
    res: Dict, cv_max: float = 0.20, ic_rel_max: float = 0.40
) -> Tuple[bool, str]:
    """Whether more runs are needed before drawing conclusions.

    The thresholds are defaults, not magic numbers: they can be changed
    per experiment, but they must be declared when they are changed.
    The criterion is the one in the protocol -- if dispersion between
    runs is large, or results change a lot from one instance to another,
    more data is needed -- not reaching a round number of runs.
    """
    if res["n"] < 3:
        return True, "menos de 3 mediciones: la dispersión no es estimable"
    motivos = []
    if res["cv"] > cv_max:
        motivos.append(
            f"CV {res['cv']:.2f} > {cv_max:.2f}: dispersión alta entre corridas"
        )
    if res["ancho_ic_relativo"] > ic_rel_max:
        motivos.append(
            f"ancho IC95 relativo {res['ancho_ic_relativo']:.2f} > "
            f"{ic_rel_max:.2f}: el intervalo es demasiado ancho"
        )
    if motivos:
        return True, "; ".join(motivos)
    return False, "dispersión e intervalo dentro de los umbrales declarados"


def distinguibles(res_a: Dict, res_b: Dict) -> Tuple[bool, str]:
    """Whether two summaries can be distinguished with this evidence.

    Conservative rule: if the 95% intervals do not overlap, the
    algorithms are reported as distinguishable on this metric; if they
    overlap, the honest conclusion is that they cannot be distinguished
    with the evidence obtained. Overlapping intervals do not prove the
    algorithms are equal, only that this experiment cannot tell them
    apart -- and that distinction must be kept in the report.
    """
    a_low, a_high = res_a["ic95"]
    b_low, b_high = res_b["ic95"]
    if a_high < b_low or b_high < a_low:
        return True, "los IC95 no se solapan"
    return False, "los IC95 se solapan: no se distinguen con esta evidencia"


def resumen_jerarquico(datos_por_instancia: Dict[str, List[float]]) -> Dict:
    """Aggregate runs grouped by instance, without pooling incorrectly.

    Runs from different instances are not pooled into one list (that
    would hide instance-to-instance variation). Instead, each instance
    is summarised first, and the overall summary is over the
    per-instance means, with the per-instance summaries kept alongside
    for inspection.
    """
    por_instancia = {
        nombre: resumen(valores)
        for nombre, valores in datos_por_instancia.items()
        if valores
    }
    medias = [r["media"] for r in por_instancia.values()]
    return {
        "por_instancia": por_instancia,
        "general": resumen(medias) if medias else {},
    }


def tabla(resultados: Dict[str, Dict]) -> str:
    """A text table with mean and dispersion per algorithm.

    Deliberately not one number per algorithm: every row carries n,
    mean, standard deviation, median, min/max and the 95% interval.
    """
    encabezado = (
        f"{'algoritmo':<24} {'n':>3} {'media':>10} {'desv':>10} "
        f"{'mediana':>10} {'min':>10} {'max':>10} "
        f"{'IC95':>24}"
    )
    lineas = [encabezado, "-" * len(encabezado)]
    for nombre, res in resultados.items():
        low, high = res["ic95"]
        lineas.append(
            f"{nombre:<24} {res['n']:>3} {res['media']:>10.3f} "
            f"{res['desviacion']:>10.3f} {res['mediana']:>10.3f} "
            f"{res['minimo']:>10.3f} {res['maximo']:>10.3f} "
            f"[{low:>10.3f}, {high:>10.3f}]"
        )
    return "\n".join(lineas)
