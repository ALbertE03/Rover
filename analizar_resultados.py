from __future__ import annotations

"""Estadísticas de las Tablas 1-4 del informe, desde el JSONL del experimento.

Lee el archivo que escribe `experimento_representativo.py`
(`resultados_representativo.jsonl` por defecto) y calcula, sin inventar
nada, lo que las tablas piden:

- Tabla 1: búsqueda, orden fijo, sin metaheurística (meta == "ninguna").
- Tabla 2: metaheurísticas, con A* fijo.
- Tabla 3: interés entregado medio, agrupado por nº de POIs (3/5/7),
  para cada buscador y cada metaheurística.
- Tabla 4: legs, base a cada POI, con DFS incluido.

Reglas de cálculo (las mismas que las gráficas del experimento):
- Primero media por instancia (una misión por instancia y algoritmo,
  así que suele ser el propio valor), y después media, desviación
  estándar e IC95 sobre esas medias por instancia. Nunca se mezclan
  corridas de instancias distintas en una sola media.
- IC95 = media +/- 1.96 * desviación / sqrt(n), con n = nº de
  instancias. Con n = 1 no hay desviación ni IC95 (se deja en None).
- Diferencias pareadas: por instancia, valor del algoritmo menos
  valor de la referencia (A* en Tabla 1, random en Tabla 2); solo las
  instancias donde ambos están presentes y con ok = True. Se informa
  su media, desviación e IC95 igual que arriba.
- Las filas con ok = False NO entran en las medias: se cuentan aparte
  (n_fallidas, instancias_fallidas) para que el fallo no se esconda.
  Las filas de legs con poi = None son el fallo de generación de una
  instancia entera (ver `experimento_representativo.py`): tampoco
  entran en las medias de legs, se cuentan aparte.

Salida:
- En consola: las cuatro tablas en forma legible.
- `--salida` (por defecto `tablas_resultados.json`): todo lo anterior
  en JSON, con los números sin redondear de más (3 decimales en la
  impresión, valor completo en el JSON).
- `--latex` (por defecto `tablas_resultados.tex`): las cuatro tablas
  en LaTeX, listas para pegar en el informe. Cada celda es
  "media (DE) [IC95 inf, IC95 sup]"; en la Tabla 3, "media (DE)".

Solo biblioteca estándar. No corre misiones ni genera mapas.
"""

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

BUSQUEDAS_MISION = ["a_star", "dijkstra", "greedy", "bfs", "weighted", "beam"]
BUSQUEDAS_LEG = BUSQUEDAS_MISION + ["dfs"]
METAS = ["random", "hill_climbing", "simulated_annealing", "genetico", "tabu", "aco"]

NOMBRES = {
    "a_star": "A*",
    "dijkstra": "Dijkstra",
    "greedy": "Greedy",
    "bfs": "BFS",
    "weighted": "A* ponderado",
    "beam": "Beam",
    "dfs": "DFS",
    "random": "Random",
    "hill_climbing": "Hill climbing",
    "simulated_annealing": "Simulated annealing",
    "genetico": "Genético",
    "tabu": "Tabú",
    "aco": "ACO",
}


def resumen(valores: List[float]) -> Dict:
    """Media, desviación e IC95 de una lista (vacía -> todo None)."""
    if not valores:
        return {"n": 0, "media": None, "de": None, "ic95_inf": None, "ic95_sup": None}
    media = statistics.fmean(valores)
    if len(valores) > 1:
        de = statistics.stdev(valores)
        margen = 1.96 * de / math.sqrt(len(valores))
        return {
            "n": len(valores),
            "media": media,
            "de": de,
            "ic95_inf": media - margen,
            "ic95_sup": media + margen,
        }
    return {"n": 1, "media": media, "de": None, "ic95_inf": None, "ic95_sup": None}


def medias_por_instancia(filas: List[Dict], clave: str, metrica: str) -> Dict[str, List[float]]:
    """Por cada valor de `clave`, lista de medias por instancia."""
    por_instancia: Dict[tuple, List[float]] = defaultdict(list)
    for f in filas:
        if metrica in f and f[metrica] is not None:
            por_instancia[(f[clave], f["instancia"])].append(f[metrica])
    salida: Dict[str, List[float]] = defaultdict(list)
    for (grupo, _inst), vals in por_instancia.items():
        salida[grupo].append(statistics.fmean(vals))
    return salida


def tabla_misiones(filas: List[Dict], clave: str, metricas: List[str]) -> Dict:
    """Tabla 1 o 2: un grupo por algoritmo/meta, con sus métricas."""
    grupos = medias_por_instancia(filas, clave, metricas[0])
    tabla = {}
    for grupo, _ in sorted(grupos.items()):
        entrada: Dict = {"n_instancias": len(grupos[grupo])}
        for metrica in metricas:
            por_inst = medias_por_instancia(filas, clave, metrica)
            entrada[metrica] = resumen(por_inst.get(grupo, []))
        tabla[grupo] = entrada
    return tabla


def diferencias_pareadas(
    filas: List[Dict], clave: str, metrica: str, referencia: str
) -> Dict[str, Dict]:
    """Por grupo, media/DE/IC95 de (valor - valor de referencia) por instancia."""
    por_instancia: Dict[tuple, List[float]] = defaultdict(list)
    for f in filas:
        if metrica in f and f[metrica] is not None:
            por_instancia[(f[clave], f["instancia"])].append(f[metrica])
    medias = {
        (grupo, inst): statistics.fmean(vals) for (grupo, inst), vals in por_instancia.items()
    }
    grupos = sorted({g for g, _ in medias})
    salida = {}
    for grupo in grupos:
        if grupo == referencia:
            continue
        diffs = [
            medias[(grupo, inst)] - medias[(referencia, inst)]
            for inst in {i for g, i in medias if g == grupo}
            if (referencia, inst) in medias
        ]
        salida[grupo] = resumen(diffs)
    return salida


def analizar(entrada: Path) -> Dict:
    filas = [json.loads(linea) for linea in entrada.read_text().splitlines() if linea.strip()]
    misiones = [f for f in filas if "poi" not in f]
    legs = [f for f in filas if "poi" in f]
    misiones_ok = [f for f in misiones if f.get("ok")]
    legs_ok = [f for f in legs if f.get("ok") and f.get("poi") is not None]
    fallidas_mision = sorted({f["instancia"] for f in misiones if not f.get("ok")})
    fallidas_leg = sorted({f["instancia"] for f in legs if not f.get("ok")})
    fallidas_leg_generacion = sorted({f["instancia"] for f in legs if not f.get("ok") and f.get("poi") is None})

    busqueda = [f for f in misiones_ok if f.get("meta") == "ninguna"]
    metas = [f for f in misiones_ok if f.get("meta") != "ninguna"]
    metricas_mision = [
        "interes_recolectado",
        "interes_entregado",
        "bateria_gastada_total",
        "pasos",
        "nodos_expandidos",
        "tiempo_segundos",
    ]
    tabla1 = tabla_misiones(busqueda, "busqueda", metricas_mision)
    tabla2 = tabla_misiones(metas, "meta", metricas_mision)
    dif1 = {
        metrica: diferencias_pareadas(busqueda, "busqueda", metrica, "a_star")
        for metrica in metricas_mision
    }
    dif2 = {
        metrica: diferencias_pareadas(metas, "meta", metrica, "random")
        for metrica in metricas_mision
    }

    # Tabla 3: interés entregado por nº de POIs, por buscador y por meta.
    tabla3: Dict[str, Dict] = {}
    for filas_grupo, clave, etiqueta in [
        (busqueda, "busqueda", "busqueda"),
        (metas, "meta", "meta"),
    ]:
        for grupo in sorted({f[clave] for f in filas_grupo}):
            por_pois: Dict[int, List[float]] = defaultdict(list)
            for f in filas_grupo:
                if f[clave] == grupo and f.get("interes_entregado") is not None:
                    por_pois[f["n_pois"]].append(f["interes_entregado"])
            # Media por instancia primero: aquí una fila = una instancia,
            # así que la media por instancia es el propio valor; se agrupa
            # por nº de POIs sobre esos valores.
            tabla3.setdefault(etiqueta, {})[grupo] = {
                str(n): resumen(vals) for n, vals in sorted(por_pois.items())
            }

    # Tabla 4: legs por buscador.
    tabla4: Dict[str, Dict] = {}
    for bus in BUSQUEDAS_LEG:
        filas_bus = [f for f in legs_ok if f.get("busqueda") == bus]
        total_bus = [f for f in legs if f.get("busqueda") == bus and f.get("poi") is not None]
        entrada4: Dict = {
            "n_legs": len(total_bus),
            "exito_pct": 100.0 * len(filas_bus) / len(total_bus) if total_bus else None,
        }
        for metrica in ["coste", "pasos", "nodos_expandidos"]:
            por_inst = medias_por_instancia(filas_bus, "busqueda", metrica)
            entrada4[metrica] = resumen(por_inst.get(bus, []))
        tabla4[bus] = entrada4

    return {
        "entrada": str(entrada),
        "n_filas": len(filas),
        "n_misiones": len(misiones),
        "n_misiones_ok": len(misiones_ok),
        "instancias_mision_fallidas": fallidas_mision,
        "n_legs": len(legs),
        "n_legs_ok": len(legs_ok),
        "instancias_leg_fallidas": fallidas_leg,
        "instancias_leg_generacion_fallidas": fallidas_leg_generacion,
        "tabla1_busqueda": tabla1,
        "tabla1_diferencias_pareadas_vs_a_star": dif1,
        "tabla2_metaheuristicas": tabla2,
        "tabla2_diferencias_pareadas_vs_random": dif2,
        "tabla3_interes_por_pois": tabla3,
        "tabla4_legs": tabla4,
    }


def celda(res: Dict) -> str:
    if res["media"] is None:
        return ""
    if res["de"] is None:
        return f"{res['media']:.3f}"
    if res["ic95_inf"] is None:
        return f"{res['media']:.3f} ({res['de']:.3f})"
    return f"{res['media']:.3f} ({res['de']:.3f}) [{res['ic95_inf']:.3f}, {res['ic95_sup']:.3f}]"


def a_latex(resultado: Dict) -> str:
    partes = []
    for titulo, tabla, metricas in [
        ("Tabla 1: búsqueda, orden fijo, sin metaheurística", resultado["tabla1_busqueda"],
         ["interes_recolectado", "interes_entregado", "bateria_gastada_total", "nodos_expandidos", "tiempo_segundos"]),
        ("Tabla 2: metaheurísticas, A* fijo, presupuesto 100", resultado["tabla2_metaheuristicas"],
         ["interes_recolectado", "interes_entregado", "bateria_gastada_total", "pasos", "tiempo_segundos"]),
    ]:
        partes.append(f"% {titulo}\n\\begin{{tabular}}{{l{'c' * len(metricas)}}}")
        partes.append(" & ".join([""] + metricas) + " \\\\")
        for grupo, entrada in tabla.items():
            partes.append(" & ".join([NOMBRES.get(grupo, grupo)] + [celda(entrada[m]) for m in metricas]) + " \\\\")
        partes.append("\\end{tabular}\n")
    partes.append("% Tabla 3: interés entregado medio, agrupado por nº de POIs")
    partes.append("\\begin{tabular}{lccc}")
    partes.append("Algoritmo & 3 POIs & 5 POIs & 7 POIs \\\\")
    for etiqueta in ["busqueda", "meta"]:
        for grupo, por_pois in resultado["tabla3_interes_por_pois"].get(etiqueta, {}).items():
            celdas = []
            for n in ["3", "5", "7"]:
                r = por_pois.get(n, {"media": None, "de": None})
                celdas.append(f"{r['media']:.3f} ({r['de']:.3f})" if r["media"] is not None and r["de"] is not None else (f"{r['media']:.3f}" if r["media"] is not None else ""))
            partes.append(" & ".join([NOMBRES.get(grupo, grupo)] + celdas) + " \\\\")
    partes.append("\\end{tabular}\n")
    partes.append("% Tabla 4: legs, base a cada POI, con DFS incluido")
    partes.append("\\begin{tabular}{lccccc}")
    partes.append("Buscador & $n$ legs & Éxito (\\%) & Coste & Pasos & Nodos \\\\")
    for bus, entrada in resultado["tabla4_legs"].items():
        exito = f"{entrada['exito_pct']:.1f}" if entrada["exito_pct"] is not None else ""
        partes.append(" & ".join([
            NOMBRES.get(bus, bus), str(entrada["n_legs"]), exito,
            celda(entrada["coste"]), celda(entrada["pasos"]), celda(entrada["nodos_expandidos"]),
        ]) + " \\\\")
    partes.append("\\end{tabular}")
    return "\n".join(partes) + "\n"


def imprimir(resultado: Dict) -> None:
    print(f"Filas: {resultado['n_filas']} (misiones {resultado['n_misiones']}, "
          f"ok {resultado['n_misiones_ok']}; legs {resultado['n_legs']}, ok {resultado['n_legs_ok']})")
    if resultado["instancias_mision_fallidas"]:
        print(f"Misiones fallidas (instancias): {resultado['instancias_mision_fallidas']}")
    if resultado["instancias_leg_fallidas"]:
        print(f"Instancias con algún leg fallido: {resultado['instancias_leg_fallidas']}")
    if resultado["instancias_leg_generacion_fallidas"]:
        print(f"Instancias no generables en legs (poi = None): {resultado['instancias_leg_generacion_fallidas']}")
    for titulo, tabla in [
        ("Tabla 1 (búsqueda)", resultado["tabla1_busqueda"]),
        ("Tabla 2 (metaheurísticas)", resultado["tabla2_metaheuristicas"]),
    ]:
        print(f"\n{titulo}:")
        for grupo, entrada in tabla.items():
            print(f"  {NOMBRES.get(grupo, grupo)}: n={entrada['n_instancias']}, "
                  f"interés entr. {celda(entrada['interes_entregado'])}, "
                  f"batería {celda(entrada['bateria_gastada_total'])}")
    print("\nTabla 3 (interés entregado por nº de POIs):")
    for etiqueta in ["busqueda", "meta"]:
        for grupo, por_pois in resultado["tabla3_interes_por_pois"].get(etiqueta, {}).items():
            print(f"  {NOMBRES.get(grupo, grupo)}: " + ", ".join(
                f"{n} POIs: {celda(v)}" for n, v in sorted(por_pois.items())))
    print("\nTabla 4 (legs):")
    for bus, entrada in resultado["tabla4_legs"].items():
        print(f"  {NOMBRES.get(bus, bus)}: n={entrada['n_legs']}, éxito {entrada['exito_pct']}, "
              f"coste {celda(entrada['coste'])}, pasos {celda(entrada['pasos'])}, "
              f"nodos {celda(entrada['nodos_expandidos'])}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Estadísticas de las Tablas 1-4 desde el JSONL del experimento")
    parser.add_argument("--entrada", default="resultados_representativo.jsonl")
    parser.add_argument("--salida", default="tablas_resultados.json")
    parser.add_argument("--latex", default="tablas_resultados.tex")
    args = parser.parse_args()
    resultado = analizar(Path(args.entrada))
    Path(args.salida).write_text(json.dumps(resultado, indent=1))
    Path(args.latex).write_text(a_latex(resultado))
    imprimir(resultado)
    print(f"\nJSON en {args.salida}, LaTeX en {args.latex}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
