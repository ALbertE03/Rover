"""Experimental comparison, following the experimental protocol.

Two comparisons, kept separate because they vary different things:

1. Search algorithms (``comparar_busqueda``): A*, Dijkstra, greedy and
   BFS, with a fixed POI order (interest descending) and no
   metaheuristic. These algorithms are deterministic, so they run once
   per instance, but their time and expanded-node count are reported
   just the same.

2. Metaheuristics (``comparar_metaheuristicas``): simulated annealing,
   genetic algorithm and tabu search, all with A* as the search, all
   with the same evaluation budget (``presupuesto_evaluaciones``), and
   several runs per instance with declared seeds.

Instances are deliberately varied in size and difficulty, not just in
seed: a default 12x12 map, a larger 16x16 map, a map with a higher
block rate and more lava pools, and the low-relief seed 7 map. An
instance is a (map seed, config) pair, and its name says what varies.

What "fixed budget" means here, precisely
------------------------------------------
* For metaheuristics: every metaheuristic gets exactly
  ``presupuesto_evaluaciones`` order evaluations in every run. That is
  the budget, and it is the same for all of them by construction (see
  ``metaheuristica.py``: SA uses ``presupuesto - 1`` iterations plus
  the initial evaluation, GA and tabu stop at ``presupuesto``).
* For search algorithms: the budget is one mission per instance, with
  the same order, the same planner and the same maps for all four.
  Their expanded-node counts and times are the cost side of the
  comparison, not a budget to be equalised by giving the slower ones
  extra work.

Reporting
---------
Results are aggregated with ``estadistica.py``: per instance first,
then over instance means, never by pooling runs from different
instances and never by reporting only the best run. The report prints
mean, standard deviation, median, min/max and the 95% interval, plus
whether more runs are recommended and whether each pair of algorithms
can actually be distinguished on delivered interest.

Run with ``python experimento.py`` for the quick version (few
instances, few runs, small budget, meant to finish in about a minute),
or ``python experimento.py --completo`` for more instances, more runs
and a larger budget. The quick version is a smoke test of the
machinery, not evidence for a conclusion: its own report will say so
when its intervals are wide.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import estadistica
from rover import ejecutar_mision

ALGORITMOS_BUSQUEDA = ["a_star", "dijkstra", "greedy", "bfs"]
METAHEURISTICAS = ["simulated_annealing", "genetico", "tabu"]


@dataclass
class Instancia:
    """One problem instance: a map seed plus a config override."""

    nombre: str
    semilla_mapa: int
    config: Optional[Dict] = None
    descripcion: str = ""


INSTANCIAS_RAPIDAS = [
    Instancia("12x12-defecto", 42, None, "mapa por defecto"),
    Instancia("12x12-semilla-0", 0, None, "mapa por defecto, otra semilla"),
    Instancia("plana-semilla-7", 7, None, "relieve bajo, casi plana"),
]

INSTANCIAS_COMPLETAS = INSTANCIAS_RAPIDAS + [
    Instancia(
        "16x16",
        1,
        {"map": {"width": 16, "height": 16}},
        "mapa más grande",
    ),
    Instancia(
        "bloqueos-altos",
        2,
        {
            "map": {"block_rate": 0.12},
            "generation": {"lava_pools": 3},
        },
        "más rocas y más piscinas de lava",
    ),
    Instancia("12x12-semilla-3", 3, None, "mapa por defecto, otra semilla"),
]


def _registrar(resultados, algoritmo, instancia, informe):
    resultados.setdefault(algoritmo, {}).setdefault(instancia.nombre, []).append(
        informe
    )


def comparar_busqueda(instancias: List[Instancia]) -> Dict:
    """Compare search algorithms, one deterministic run per instance."""
    resultados: Dict = {}
    for instancia in instancias:
        for algoritmo in ALGORITMOS_BUSQUEDA:
            informe = ejecutar_mision(
                semilla=instancia.semilla_mapa,
                config=instancia.config,
                algoritmo_busqueda=algoritmo,
                metaheuristica="ninguna",
            )
            _registrar(resultados, algoritmo, instancia, informe)
    return resultados


def comparar_metaheuristicas(
    instancias: List[Instancia],
    corridas_por_instancia: int = 3,
    semillas_corridas: Optional[List[int]] = None,
    presupuesto_evaluaciones: int = 300,
) -> Dict:
    """Compare metaheuristics, several declared-seed runs per instance."""
    if semillas_corridas is None:
        semillas_corridas = [7, 11, 13, 17, 19][:corridas_por_instancia]
    resultados: Dict = {}
    for instancia in instancias:
        for meta in METAHEURISTICAS:
            for semilla_corrida in semillas_corridas:
                informe = ejecutar_mision(
                    semilla=instancia.semilla_mapa,
                    config=instancia.config,
                    algoritmo_busqueda="a_star",
                    metaheuristica=meta,
                    presupuesto_evaluaciones=presupuesto_evaluaciones,
                    semilla_metaheuristica=semilla_corrida,
                )
                informe["semilla_corrida"] = semilla_corrida
                _registrar(resultados, meta, instancia, informe)
    return resultados


def _informe_tabla(titulo: str, resultados: Dict, metrica: str) -> None:
    print(f"\n## {titulo} -- métrica: {metrica}")
    # Per-algorithm summary over instance means (not pooled runs).
    res_por_algoritmo = {}
    for algoritmo, por_instancia in resultados.items():
        datos = {
            nombre: [inf[metrica] for inf in informes]
            for nombre, informes in por_instancia.items()
        }
        jerarquico = estadistica.resumen_jerarquico(datos)
        res_por_algoritmo[algoritmo] = jerarquico["general"]
        print(f"\n{algoritmo}:")
        for nombre, res in jerarquico["por_instancia"].items():
            print(
                f"  {nombre}: media {res['media']:.3f}, "
                f"desv {res['desviacion']:.3f}, n={res['n']}"
            )
    print("\nResumen general (sobre medias por instancia):")
    print(estadistica.tabla(res_por_algoritmo))
    print("\n¿Hacen falta más datos?")
    print(
        "  Nota: el resumen general es sobre medias por instancia, así "
        "que un CV alto aquí significa sobre todo que las instancias "
        "difieren mucho entre sí (p. ej. la semilla 7 entrega mucho "
        "menos interés que las demás porque casi todo su mapa está en "
        "otro componente). Para saber si hacen falta más corridas, "
        "mira la desviación dentro de cada instancia, arriba."
    )
    for algoritmo, res in res_por_algoritmo.items():
        falta, motivo = estadistica.necesita_mas_datos(res)
        print(f"  {algoritmo}: {'SÍ - ' + motivo if falta else 'no - ' + motivo}")
    nombres = list(res_por_algoritmo.keys())
    print(f"\n¿Se distinguen entre sí ({metrica})?")
    for i in range(len(nombres)):
        for j in range(i + 1, len(nombres)):
            a, b = nombres[i], nombres[j]
            ok, motivo = estadistica.distinguibles(
                res_por_algoritmo[a], res_por_algoritmo[b]
            )
            print(f"  {a} vs {b}: {'sí' if ok else 'NO'} ({motivo})")


def _main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Experimento del rover")
    parser.add_argument(
        "--completo",
        action="store_true",
        help="más instancias, más corridas y mayor presupuesto",
    )
    parser.add_argument(
        "--modo",
        choices=["busqueda", "metaheuristicas", "ambos"],
        default="ambos",
    )
    args = parser.parse_args(argv)
    if args.completo:
        instancias = INSTANCIAS_COMPLETAS
        corridas, presupuesto = 5, 300
    else:
        instancias = INSTANCIAS_RAPIDAS
        corridas, presupuesto = 2, 100
        print(
            "Versión rápida: pocas instancias, 2 corridas y presupuesto "
            "100. Es una prueba del mecanismo, no evidencia para concluir: "
            "el propio informe avisará si los intervalos son anchos."
        )
    print(
        f"Instancias: {[i.nombre for i in instancias]} "
        f"(semillas de mapa declaradas en INSTANCIAS_*)."
    )
    inicio = time.perf_counter()
    if args.modo in ("busqueda", "ambos"):
        res_busqueda = comparar_busqueda(instancias)
        _informe_tabla(
            "Búsqueda (orden fijo, sin metaheurística)",
            res_busqueda,
            "interes_entregado",
        )
        # El interés por sí solo no distingue a los buscadores: todos
        # entregan los mismos POIs alcanzables. Lo que los distingue
        # es la batería gastada (coste de la ruta) y el trabajo de
        # búsqueda (nodos expandidos, tiempo).
        _informe_tabla(
            "Búsqueda -- batería gastada total",
            res_busqueda,
            "bateria_gastada_total",
        )
        _informe_tabla(
            "Búsqueda -- nodos expandidos en ejecución",
            res_busqueda,
            "nodos_expandidos",
        )
        _informe_tabla(
            "Búsqueda -- tiempo (segundos)",
            res_busqueda,
            "tiempo_segundos",
        )
    if args.modo in ("metaheuristicas", "ambos"):
        res_meta = comparar_metaheuristicas(
            instancias,
            corridas_por_instancia=corridas,
            presupuesto_evaluaciones=presupuesto,
        )
        _informe_tabla(
            f"Metaheurísticas (A*, presupuesto {presupuesto} evaluaciones, "
            f"{corridas} corridas por instancia)",
            res_meta,
            "interes_entregado",
        )
        _informe_tabla(
            "Metaheurísticas -- batería gastada total",
            res_meta,
            "bateria_gastada_total",
        )
        _informe_tabla(
            "Metaheurísticas -- puntuación del orden "
            "(interés*100 - coste de viaje)",
            res_meta,
            "puntuacion_final",
        )
    print(f"\nTiempo total del experimento: {time.perf_counter() - inicio:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
