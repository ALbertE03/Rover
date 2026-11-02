from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import estadistica
from rover import ejecutar_mision

# Solo algoritmos de las conferencias. Búsqueda (C1): A*, Dijkstra
# (= coste uniforme), greedy, BFS, A* ponderado y beam. DFS es de C1
# pero NO va en misiones: replanifica tras cada survey y oscila
# (ver AGENTE.md); DFS solo se compara en legs, en legs.py.
# Metaheurísticas (conferencia): random, hill climbing, SA, genético,
# tabú y ACO. No hay DE, PSO ni GRASP: DE/PSO son para espacios
# continuos y GRASP solo aparece nombrado, sin algoritmo detallado.
ALGORITMOS_BUSQUEDA = ["a_star", "dijkstra", "greedy", "bfs", "weighted", "beam"]
METAHEURISTICAS = [
    "random",
    "hill_climbing",
    "simulated_annealing",
    "genetico",
    "tabu",
    "aco",
]


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


def _media_por_instancia(resultados, metrica):
    """Mean over instance means for one metric, robust to missing data.

    ``resultados`` is {algoritmo: {instancia: [informes]}}. Returns
    {algoritmo: (media, desviacion, n_instancias)} where media is
    over per-instance means (never pooled runs), desviacion is the
    sample std over those means (0.0 when there is only one
    instance), and n_instancias is how many instances actually had
    that metric. Algorithms with no usable data are omitted, so a
    figure never crashes on a missing algorithm or metric.
    """
    import math

    out = {}
    for algoritmo, por_instancia in resultados.items():
        medias = []
        for informes in por_instancia.values():
            valores = [
                inf[metrica] for inf in informes if metrica in inf and inf[metrica] is not None
            ]
            if valores:
                medias.append(sum(valores) / len(valores))
        if not medias:
            continue
        media = sum(medias) / len(medias)
        if len(medias) > 1:
            var = sum((x - media) ** 2 for x in medias) / (len(medias) - 1)
            desv = math.sqrt(var)
        else:
            desv = 0.0
        out[algoritmo] = (media, desv, len(medias))
    return out


def generar_graficas(res_busqueda, res_meta, directorio):
    """Generate matplotlib figures from experiment results, in-place.

    Called by _main after the tables. It never raises: if matplotlib
    is missing, it prints how to install it and returns; if a figure
    has no data, it is skipped with a warning; every figure is
    closed after saving, so several runs in a row do not accumulate
    open figures. Output: PNG files in ``directorio`` (created if
    needed), with the same names on every run, so a new run
    overwrites the old figures instead of duplicating them.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print(
            "\n[gráficas] matplotlib no está instalado; "
            "instala con: pip install matplotlib"
        )
        return
    import os

    os.makedirs(directorio, exist_ok=True)

    def _barras(titulo, datos, ylabel, nombre_archivo):
        if not datos:
            print(f"[gráficas] sin datos para {nombre_archivo}, se omite")
            return
        nombres = sorted(datos)
        medias = [datos[n][0] for n in nombres]
        errores = [datos[n][1] for n in nombres]
        # Error bars need at least 2 instances; with 1 instance the
        # std is 0.0 by construction, which matplotlib accepts.
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(nombres, medias, yerr=errores, capsize=4)
        ax.set_ylabel(ylabel)
        ax.set_title(f"{titulo} (n={datos[nombres[0]][2]} instancias)")
        ax.tick_params(axis="x", rotation=20)
        for etiqueta in ax.get_xticklabels():
            etiqueta.set_ha("right")
        fig.tight_layout()
        fig.savefig(os.path.join(directorio, nombre_archivo), dpi=200)
        plt.close(fig)
        print(f"[gráficas] {nombre_archivo}")

    def _barras_agrupadas_por_pois(titulo, resultados, metrica, ylabel, nombre_archivo):
        """Grouped bars: x = algorithm, groups = number of POIs.

        ``resultados`` is {algoritmo: {instancia: [informes]}} and
        each informe may carry ``n_pois`` (added by ejecutar_mision).
        Instances without ``n_pois`` are grouped under ``n=?`` and
        still plotted, so old JSONL files without that field do not
        crash the figure. When there is only one POI count in the
        whole run, the figure is a single group per algorithm and
        is still useful; when there are several, the groups show
        how the metric scales when POIs are added or removed.
        Values are means over per-instance means, exactly as in
        _media_por_instancia, never pooled runs.
        """
        # Collect POI counts present, in numeric order.
        counts = set()
        for por_instancia in resultados.values():
            for informes in por_instancia.values():
                for inf in informes:
                    counts.add(inf.get("n_pois", None))
        if not resultados:
            print(f"[gráficas] sin datos para {nombre_archivo}, se omite")
            return
        # Sort with None (unknown) last.
        counts_ord = sorted([c for c in counts if c is not None]) + (
            [None] if None in counts else []
        )
        nombres = sorted(resultados)
        fig, ax = plt.subplots(figsize=(9, 4))
        import numpy as np

        x = np.arange(len(nombres))
        ancho = 0.8 / max(1, len(counts_ord))
        for k, cnt in enumerate(counts_ord):
            medias = []
            for algoritmo in nombres:
                medias_inst = []
                for informes in resultados[algoritmo].values():
                    valores = [
                        inf[metrica] for inf in informes
                        if metrica in inf and inf[metrica] is not None
                        and inf.get("n_pois", None) == cnt
                    ]
                    if valores:
                        medias_inst.append(sum(valores) / len(valores))
                medias.append(
                    sum(medias_inst) / len(medias_inst) if medias_inst else 0.0
                )
            etiqueta = f"{cnt} POIs" if cnt is not None else "n=? POIs"
            ax.bar(x + (k - (len(counts_ord) - 1) / 2) * ancho, medias, ancho, label=etiqueta)
        ax.set_xticks(x)
        ax.set_xticklabels(nombres, rotation=20, ha="right")
        ax.set_ylabel(ylabel)
        ax.set_title(titulo)
        ax.legend()
        fig.tight_layout()
        fig.savefig(os.path.join(directorio, nombre_archivo), dpi=200)
        plt.close(fig)
        print(f"[gráficas] {nombre_archivo}")

    def _lineas_por_instancia(titulo, resultados, metrica, ylabel, nombre_archivo):
        # One line per algorithm, x = instance names in a stable order.
        # Missing (algoritmo, instancia) pairs are skipped, not
        # treated as zero, so a partial run still plots correctly.
        instancias = []
        for por_instancia in resultados.values():
            for nombre in por_instancia:
                if nombre not in instancias:
                    instancias.append(nombre)
        if not instancias or not resultados:
            print(f"[gráficas] sin datos para {nombre_archivo}, se omite")
            return
        fig, ax = plt.subplots(figsize=(8, 4))
        for algoritmo in sorted(resultados):
            xs, ys = [], []
            for nombre in instancias:
                informes = resultados[algoritmo].get(nombre, [])
                valores = [
                    inf[metrica] for inf in informes
                    if metrica in inf and inf[metrica] is not None
                ]
                if valores:
                    xs.append(nombre)
                    ys.append(sum(valores) / len(valores))
            if xs:
                ax.plot(xs, ys, marker="o", label=algoritmo)
        ax.set_ylabel(ylabel)
        ax.set_title(titulo)
        ax.legend()
        ax.tick_params(axis="x", rotation=20)
        for etiqueta in ax.get_xticklabels():
            etiqueta.set_ha("right")
        fig.tight_layout()
        fig.savefig(os.path.join(directorio, nombre_archivo), dpi=200)
        plt.close(fig)
        print(f"[gráficas] {nombre_archivo}")

    if res_busqueda is not None:
        _barras(
            "Batería gastada total por buscador",
            _media_por_instancia(res_busqueda, "bateria_gastada_total"),
            "Batería total media",
            "fig_bateria_busqueda.png",
        )
        _barras(
            "Interés entregado por buscador",
            _media_por_instancia(res_busqueda, "interes_entregado"),
            "Interés entregado medio",
            "fig_interes_busqueda.png",
        )
        _barras(
            "Nodos expandidos por buscador",
            _media_por_instancia(res_busqueda, "nodos_expandidos"),
            "Nodos expandidos medios",
            "fig_nodos_busqueda.png",
        )
        _lineas_por_instancia(
            "Batería por instancia y buscador",
            res_busqueda,
            "bateria_gastada_total",
            "Batería total",
            "fig_bateria_por_instancia.png",
        )
    if res_busqueda is not None:
        _barras_agrupadas_por_pois(
            "Batería por buscador, agrupada por nº de POIs",
            res_busqueda,
            "bateria_gastada_total",
            "Batería total media",
            "fig_bateria_busqueda_por_pois.png",
        )
        _barras_agrupadas_por_pois(
            "Interés entregado por buscador, agrupado por nº de POIs",
            res_busqueda,
            "interes_entregado",
            "Interés entregado medio",
            "fig_interes_busqueda_por_pois.png",
        )
    if res_meta is not None:
        _barras_agrupadas_por_pois(
            "Interés entregado por metaheurística, agrupado por nº de POIs",
            res_meta,
            "interes_entregado",
            "Interés entregado medio",
            "fig_interes_meta_por_pois.png",
        )
        _barras_agrupadas_por_pois(
            "Batería por metaheurística, agrupada por nº de POIs",
            res_meta,
            "bateria_gastada_total",
            "Batería total media",
            "fig_bateria_meta_por_pois.png",
        )
        _barras(
            "Interés entregado por metaheurística",
            _media_por_instancia(res_meta, "interes_entregado"),
            "Interés entregado medio",
            "fig_interes_meta.png",
        )
        _barras(
            "Batería gastada total por metaheurística",
            _media_por_instancia(res_meta, "bateria_gastada_total"),
            "Batería total media",
            "fig_bateria_meta.png",
        )
        _lineas_por_instancia(
            "Interés entregado por instancia y metaheurística",
            res_meta,
            "interes_entregado",
            "Interés entregado",
            "fig_interes_meta_por_instancia.png",
        )


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
    parser.add_argument(
        "--graficos",
        default="figuras",
        help="directorio donde se guardan las gráficas PNG (se crea si no existe)",
    )
    parser.add_argument(
        "--resultados-jsonl",
        default=None,
        help="si se da, guarda una fila JSON por misión en este archivo",
    )
    parser.add_argument(
        "--poi-counts",
        default=None,
        help="nº de POIs por instancia, separados por coma, p. ej. 3,5,7. "
        "Si se da, cada instancia base se repite una vez por cada "
        "valor, con config override poi.count, y las gráficas "
        "agrupadas por nº de POIs muestran cómo escala cada "
        "algoritmo al añadir o quitar POIs. Si no se da, se usa "
        "el nº de POIs del config (5 por defecto).",
    )
    args = parser.parse_args(argv)
    if args.completo:
        instancias = INSTANCIAS_COMPLETAS
        # Presupuesto 100, no 300: con 5 POI solo hay 5! = 120 órdenes
        # distintos, así que un presupuesto de 300 órdenes distintos
        # (el que cuenta el algoritmo genético) nunca se alcanzaría.
        corridas, presupuesto = 5, 100
    else:
        instancias = INSTANCIAS_RAPIDAS
        corridas, presupuesto = 2, 100
        print(
            "Versión rápida: pocas instancias, 2 corridas y presupuesto "
            "100. Es una prueba del mecanismo, no evidencia para concluir: "
            "el propio informe avisará si los intervalos son anchos."
        )
    if args.poi_counts:
        try:
            counts = [int(x) for x in args.poi_counts.split(",") if x.strip()]
        except ValueError:
            parser.error("--poi-counts debe ser una lista de enteros, p. ej. 3,5,7")
        if not counts or any(c < 1 for c in counts):
            parser.error("--poi-counts debe contener solo enteros >= 1")
        instancias_expandidas = []
        for inst in instancias:
            for cnt in counts:
                cfg = dict(inst.config) if inst.config else {}
                cfg = {**cfg, "poi": {"count": cnt}}
                instancias_expandidas.append(
                    Instancia(
                        f"{inst.nombre}-poi{cnt}",
                        inst.semilla_mapa,
                        cfg,
                        f"{inst.descripcion}, {cnt} POIs",
                    )
                )
        instancias = instancias_expandidas
    print(
        f"Instancias: {[i.nombre for i in instancias]} "
        f"(semillas de mapa declaradas en INSTANCIAS_*)."
    )
    inicio = time.perf_counter()
    res_busqueda = None
    res_meta = None
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
    if args.resultados_jsonl:
        import json

        with open(args.resultados_jsonl, "w") as f:
            for resultados in (res_busqueda, res_meta):
                if not resultados:
                    continue
                for algoritmo, por_instancia in resultados.items():
                    for nombre, informes in por_instancia.items():
                        for inf in informes:
                            fila = dict(inf)
                            fila["algoritmo"] = algoritmo
                            fila["instancia"] = nombre
                            # Acciones y traza son texto largo; no van al JSONL.
                            fila.pop("acciones", None)
                            fila.pop("traza", None)
                            f.write(json.dumps(fila, default=str) + "\n")
        print(f"\nResultados guardados en {args.resultados_jsonl}")
    print(f"\nGenerando gráficas en {args.graficos} ...")
    generar_graficas(res_busqueda, res_meta, args.graficos)
    print(f"\nTiempo total del experimento: {time.perf_counter() - inicio:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
