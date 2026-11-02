from __future__ import annotations

"""Experimento estadísticamente representativo del rover.

Este es el ÚNICO script de experimentos del proyecto. Sustituye a
experimento.py, experimento_grande.py, experimento_pequeno.py,
analizar_grande.py, legs.py y barrido.py, que se borraron para no
tener tres experimentos distintos. Todo lo que hacían esos scripts
(misiones, legs con DFS, análisis, gráficas, barrido de parámetros)
está aquí, en un solo diseño.

Diseño, en resumen:

- Estratos: tamaño (12x12, 16x16, 32x32) x profundidad (z=3, 5, 7),
  9 estratos. Dentro de cada estrato se sortean n instancias con
  la misma n para todos los estratos (asignación igual), para que
  ningún tamaño domine el resumen general.
- Muestreo: hipercubo latino (Latin Hypercube Sampling, LHS) para
  los parámetros continuos: el rango de cada parámetro se divide
  en n intervalos iguales, se sortea un punto en cada intervalo y
  se permutan los órdenes de forma independiente entre parámetros.
  Así cada parámetro cubre todo su rango, sin aglomerarse en una
  zona por azar, y las combinaciones son aleatorias. Los
  parámetros discretos (nº de POIs, radio de movimiento, diagonal,
  piscinas de lava, biomas, batería, memoria) se reparten de forma
  equilibrada dentro de cada estrato: cada valor aparece casi el
  mismo número de veces.
- Nada por defecto: cada instancia lleva una configuración
  COMPLETA, con todas las secciones explícitas (generación, mapa,
  movimiento, red, POI, rover, terreno). InstanceParams hace
  merge sobre el default, pero aquí no hay nada que heredar: todos
  los valores que importan están sorteados en la instancia.
- Diseño pareado: la misma instancia se corre con todos los
  algoritmos (búsqueda y metaheurísticas), así que la comparación
  es por instancia, no entre instancias distintas. Los buscadores
  son deterministas (1 corrida por instancia); las metaheurísticas
  usan semilla declarada (7 por defecto, configurable).
- Tamaño de muestra: con una desviación piloto sigma y una media
  mu, el n necesario para un margen relativo m al 95% es
  n = (1.96 * sigma / (m * mu))^2. Con los datos piloto de la
  corrida de prueba (batería: sigma ~27, media ~65), un margen
  del 20% pide n ~ 17 por estrato; el default de 30 por estrato
  es, por tanto, conservador para ese margen, y además hace que
  la media sea aproximadamente normal por el teorema central del
  límite. La función calcular_n() calcula esto para cualquier
  sigma/margen, y --piloto lo imprime sin correr misiones.
- Presupuesto igual: todas las metaheurísticas reciben 100
  evaluaciones de órdenes (con 5 POIs hay 120 órdenes distintos,
  así que 100 es alcanzable; con 7 POIs, 5040, es un muestreo).
- Análisis: media, desviación, IC95 sobre medias por instancia
  (nunca corridas mezcladas), diferencias pareadas por instancia
  contra A* (búsqueda) y contra random (metaheurísticas), y
  resúmenes agrupados por estrato y por nº de POIs.

Algoritmos, solo de las conferencias (C1, C2b, metaheurísticas):
búsqueda en misiones: a_star, dijkstra, greedy, bfs, weighted,
beam; en legs también dfs (en misiones oscila al replanificar,
ver AGENTE.md). Metaheurísticas: random, hill_climbing,
simulated_annealing, genetico, tabu, aco. No hay DE, PSO ni GRASP.

Uso:
  python experimento_representativo.py --piloto
      # solo diseña instancias y calcula n necesario, no corre nada
  python experimento_representativo.py --prueba
      # prueba pequeña: 2 instancias, todos los algoritmos,
      # gráficas, para ver que funciona. NO es el experimento completo.
  python experimento_representativo.py --n-por-estrato 30
      # experimento completo. NO correrlo sin tiempo: son
      # 9 estratos x 30 x 12 misiones = 3240 misiones + legs.
"""

import argparse
import json
import math
import random
import time
from multiprocessing import Pool
from pathlib import Path
from typing import Dict, List

ESTRATOS = [
    (12, 12, 3),
    (12, 12, 5),
    (12, 12, 7),
    (16, 16, 3),
    (16, 16, 5),
    (16, 16, 7),
    (32, 32, 3),
    (32, 32, 5),
    (32, 32, 7),
]
BUSQUEDAS_MISION = ["a_star", "dijkstra", "greedy", "bfs", "weighted", "beam"]
BUSQUEDAS_LEG = BUSQUEDAS_MISION + ["dfs"]
METAS = ["random", "hill_climbing", "simulated_annealing", "genetico", "tabu", "aco"]


def calcular_n(sigma: float, media: float, margen_relativo: float = 0.20, z: float = 1.96) -> int:
    """n necesario para un IC95 con semiancho <= margen_relativo * media."""
    if media <= 0 or sigma <= 0 or margen_relativo <= 0:
        raise ValueError("sigma, media y margen deben ser > 0")
    return math.ceil((z * sigma / (margen_relativo * media)) ** 2)


def _lhs(rng: random.Random, lo: float, hi: float, n: int) -> List[float]:
    """Valores LHS: un punto aleatorio por intervalo, orden permutado."""
    if n <= 0:
        return []
    paso = (hi - lo) / n
    valores = [lo + (i + rng.random()) * paso for i in range(n)]
    rng.shuffle(valores)
    return valores


def _equilibrado(rng: random.Random, valores: List, n: int) -> List:
    """Reparte valores discretos de forma equilibrada, orden aleatorio."""
    out = [valores[i % len(valores)] for i in range(n)]
    rng.shuffle(out)
    return out


def config_completa(
    rng: random.Random,
    ancho: int,
    alto: int,
    profundidad: int,
    n_pois: int,
    radio: float,
    diagonal: bool,
    block_rate: float,
    climb: float,
    survey_bonus: float,
    bateria: float,
    memoria: float,
    min_vis: float,
    climb_w: float,
    lava_pools: int,
    biome_count: int,
    relief: float,
    axis_x: float,
) -> Dict:
    """Configuración completa, sin heredar nada del default.

    Todos los valores que importan están explícitos. Los costes de
    terreno se sortean ordenados (plain < sand < rocky < crevasse)
    y las visibilidades en orden inverso, para que los nombres de
    terreno conserven su significado; las bandas tienen bordes
    crecientes en (0, 1).
    """
    costes = sorted(
        [
            rng.uniform(0.8, 1.2),
            rng.uniform(1.2, 1.8),
            rng.uniform(1.8, 2.6),
            rng.uniform(2.8, 3.8),
        ]
    )
    vis = sorted(
        [
            rng.uniform(0.80, 0.95),
            rng.uniform(0.65, 0.85),
            rng.uniform(0.50, 0.70),
            rng.uniform(0.25, 0.45),
        ],
        reverse=True,
    )
    cortes = sorted(
        [
            rng.uniform(0.45, 0.65),
            rng.uniform(0.65, 0.80),
            rng.uniform(0.80, 0.92),
        ]
    )
    return {
        "generation": {
            "axis_weights": {"x": round(axis_x, 3), "y": round(1.0 - axis_x, 3)},
            "bands": [
                {"max": round(cortes[0], 3), "terrain": "plain"},
                {"max": round(cortes[1], 3), "terrain": "sand"},
                {"max": round(cortes[2], 3), "terrain": "rocky"},
                {"max": 1.0, "terrain": "crevasse"},
            ],
            "depth_slope": round(rng.uniform(0.1, 0.3), 3),
            "terrain_relief_weight": round(rng.uniform(0.3, 0.7), 3),
            "relief_amplitude": round(relief, 3),
            "noise_octaves": rng.randint(2, 4),
            "noise_scale": rng.choice([2, 4]),
            "mixture_weight_range": [0.25, 1.0],
            "biome_count": biome_count,
            "lava_pools": lava_pools,
            "lava_pool_radius": [2, rng.randint(3, 5)],
        },
        "map": {
            "width": ancho,
            "height": alto,
            "depth": profundidad,
            "block_rate": round(block_rate, 3),
            "min_axis": 5,
            "max_axis": 64,
        },
        "movement": {
            "radius": radio,
            "climb_penalty": round(climb, 3),
            "survey_height_bonus": round(survey_bonus, 3),
            "allow_diagonal": diagonal,
        },
        "network": {
            "stations": [
                {"id": "base"},
                {"id": "relay"},
            ]
        },
        "poi": {
            "count": n_pois,
            "min_visibility": round(min_vis, 3),
            "interest_climb_weight": round(climb_w, 3),
            "interest_ground_weight": round(1.0 - climb_w, 3),
        },
        "rover": {"battery": float(bateria), "memory": float(memoria)},
        "terrain": {
            "plain": {"cost": round(costes[0], 3), "visibility": round(vis[0], 3), "glyph": "."},
            "sand": {"cost": round(costes[1], 3), "visibility": round(vis[1], 3), "glyph": ":"},
            "rocky": {"cost": round(costes[2], 3), "visibility": round(vis[2], 3), "glyph": "#"},
            "crevasse": {"cost": round(costes[3], 3), "visibility": round(vis[3], 3), "glyph": "/"},
            "lava": {"cost": 999.0, "visibility": 0.1, "glyph": "~", "color": "#e03c00"},
        },
    }


def generar_instancias(n_por_estrato: int = 30, semilla_base: int = 0) -> List[Dict]:
    """n instancias por estrato, con LHS y factores equilibrados."""
    instancias: List[Dict] = []
    for idx_estrato, (ancho, alto, prof) in enumerate(ESTRATOS):
        rng = random.Random(semilla_base + idx_estrato * 10000)
        n = n_por_estrato
        lhs_block = _lhs(rng, 0.03, 0.12, n)
        lhs_climb = _lhs(rng, 0.3, 0.9, n)
        lhs_survey = _lhs(rng, 1.0, 3.0, n)
        lhs_bateria = _lhs(rng, 50.0, 200.0, n)
        lhs_min_vis = _lhs(rng, 0.6, 0.8, n)
        lhs_climb_w = _lhs(rng, 0.4, 0.8, n)
        lhs_relief = _lhs(rng, 0.4, 1.0, n)
        lhs_axis = _lhs(rng, 0.3, 0.7, n)
        pois = _equilibrado(rng, [3, 5, 7], n)
        radios = _equilibrado(rng, [1.0, 1.8, 2.5], n)
        diags = _equilibrado(rng, [False, True], n)
        memorias = _equilibrado(rng, [1.0, 2.0, 3.0, 4.0], n)
        lavas = _equilibrado(rng, [1, 2, 3], n)
        biomas = _equilibrado(rng, [2, 3, 4], n)
        for run in range(n):
            cfg = config_completa(
                rng,
                ancho,
                alto,
                prof,
                pois[run],
                radios[run],
                diags[run],
                lhs_block[run],
                lhs_climb[run],
                lhs_survey[run],
                lhs_bateria[run],
                memorias[run],
                lhs_min_vis[run],
                lhs_climb_w[run],
                lavas[run],
                biomas[run],
                lhs_relief[run],
                lhs_axis[run],
            )
            iid = idx_estrato * 1000 + run
            instancias.append(
                {
                    "id": iid,
                    "estrato": f"{ancho}x{alto}_z{prof}",
                    "ancho": ancho,
                    "alto": alto,
                    "profundidad": prof,
                    "corrida": run,
                    "n_pois": pois[run],
                    "semilla_mapa": 20000 + iid,
                    "config": cfg,
                }
            )
    return instancias


def _mision(tarea: Dict) -> Dict:
    from rover import ejecutar_mision

    inst = tarea["instancia"]
    t0 = time.perf_counter()
    try:
        inf = ejecutar_mision(
            semilla=inst["semilla_mapa"],
            config=inst["config"],
            algoritmo_busqueda=tarea.get("busqueda", "a_star"),
            metaheuristica=tarea.get("meta", "ninguna"),
            presupuesto_evaluaciones=tarea.get("presupuesto", 100),
            semilla_metaheuristica=tarea.get("semilla_meta", 7),
        )
        return {
            "instancia": inst["id"],
            "estrato": inst["estrato"],
            "ancho": inst["ancho"],
            "profundidad": inst["profundidad"],
            "n_pois": inst["n_pois"],
            "busqueda": tarea.get("busqueda", "a_star"),
            "meta": tarea.get("meta", "ninguna"),
            "ok": True,
            "interes_recolectado": inf["interes_recolectado"],
            "interes_entregado": inf["interes_entregado"],
            "interes_total_mapa": inf["interes_total_mapa"],
            "pasos": inf["pasos"],
            "bateria_gastada_total": inf["bateria_gastada_total"],
            "nodos_expandidos": inf["nodos_expandidos"],
            "tiempo_segundos": round(time.perf_counter() - t0, 3),
            "recargas": inf["recargas"],
            "transmisiones": inf["transmisiones"],
            "celdas_conocidas": inf["celdas_conocidas"],
            "celdas_totales": inf["celdas_totales"],
        }
    except Exception as exc:  # noqa: BLE001 - el experimento no debe morir
        return {
            "instancia": inst["id"],
            "estrato": inst["estrato"],
            "ancho": inst["ancho"],
            "profundidad": inst["profundidad"],
            "n_pois": inst["n_pois"],
            "busqueda": tarea.get("busqueda", "a_star"),
            "meta": tarea.get("meta", "ninguna"),
            "ok": False,
            "error": repr(exc),
        }


def _legs_instancia(inst: Dict) -> List[Dict]:
    from enviro.terrain import InstanceParams, MapGenerator
    from enviro.terrain.grid import movement_offsets
    from rover import Rover, plan_route

    mapa = MapGenerator(
        InstanceParams.from_config(seed=inst["semilla_mapa"], config=inst["config"])
    ).create()
    rover = Rover(mapa, algoritmo_busqueda="a_star")
    conocidos = dict(rover.known)
    bloqueados = set(rover.known_blocked)
    offsets = movement_offsets(mapa.params.move_radius, mapa.params.move_allow_diagonal)
    filas: List[Dict] = []
    for bus in BUSQUEDAS_LEG:
        for poi in list(mapa.pois.keys()):
            t0 = time.perf_counter()
            try:
                res = plan_route(
                    rover.pos,
                    rover.poi_coord(poi),
                    mapa.cells,
                    offsets,
                    conocidos,
                    rover.registry,
                    mapa.params.climb_penalty,
                    algoritmo=bus,
                    known_blocked=bloqueados,
                )
                filas.append(
                    {
                        "instancia": inst["id"],
                        "estrato": inst["estrato"],
                        "ancho": inst["ancho"],
                        "profundidad": inst["profundidad"],
                        "n_pois": inst["n_pois"],
                        "busqueda": bus,
                        "poi": poi,
                        "ok": res is not None,
                        "coste": round(res.cost, 3) if res else None,
                        "pasos": len(res.path) - 1 if res else None,
                        "nodos_expandidos": res.expanded if res else None,
                        "tiempo_segundos": round(time.perf_counter() - t0, 4),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                filas.append(
                    {
                        "instancia": inst["id"],
                        "estrato": inst["estrato"],
                        "ancho": inst["ancho"],
                        "profundidad": inst["profundidad"],
                        "n_pois": inst["n_pois"],
                        "busqueda": bus,
                        "poi": poi,
                        "ok": False,
                        "error": repr(exc),
                    }
                )
    return filas



def generar_graficas(res_busqueda, res_meta, directorio: str) -> None:
    """11 figuras PNG, incluyendo 4 agrupadas por nº de POIs.

    Nunca falla por datos faltantes: una figura sin datos se omite
    con aviso, y cada figura se cierra tras guardarla. Los valores
    son medias sobre medias por instancia, nunca corridas mezcladas.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[gráficas] matplotlib no está instalado; pip install matplotlib")
        return
    import os

    import numpy as np

    os.makedirs(directorio, exist_ok=True)

    def _media_por_instancia(resultados, metrica):
        out = {}
        for algoritmo, por_instancia in resultados.items():
            medias = []
            for informes in por_instancia.values():
                vals = [inf[metrica] for inf in informes if metrica in inf and inf[metrica] is not None]
                if vals:
                    medias.append(sum(vals) / len(vals))
            if medias:
                media = sum(medias) / len(medias)
                desv = math.sqrt(sum((x - media) ** 2 for x in medias) / (len(medias) - 1)) if len(medias) > 1 else 0.0
                out[algoritmo] = (media, desv, len(medias))
        return out

    def _barras(titulo, datos, ylabel, nombre):
        if not datos:
            print(f"[gráficas] sin datos para {nombre}, se omite")
            return
        nombres = sorted(datos)
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(nombres, [datos[n][0] for n in nombres], yerr=[datos[n][1] for n in nombres], capsize=4)
        ax.set_ylabel(ylabel)
        ax.set_title(f"{titulo} (n={datos[nombres[0]][2]} instancias)")
        ax.tick_params(axis="x", rotation=20)
        for e in ax.get_xticklabels():
            e.set_ha("right")
        fig.tight_layout()
        fig.savefig(os.path.join(directorio, nombre), dpi=200)
        plt.close(fig)
        print(f"[gráficas] {nombre}")

    def _agrupadas_por_pois(titulo, resultados, metrica, ylabel, nombre):
        if not resultados:
            return
        counts = sorted({inf.get("n_pois") for por in resultados.values() for informes in por.values() for inf in informes if inf.get("n_pois") is not None})
        if not counts:
            counts = [None]
        nombres = sorted(resultados)
        fig, ax = plt.subplots(figsize=(9, 4))
        x = np.arange(len(nombres))
        ancho = 0.8 / max(1, len(counts))
        for k, cnt in enumerate(counts):
            medias = []
            for algoritmo in nombres:
                mi = []
                for informes in resultados[algoritmo].values():
                    vals = [inf[metrica] for inf in informes if metrica in inf and inf[metrica] is not None and inf.get("n_pois") == cnt]
                    if vals:
                        mi.append(sum(vals) / len(vals))
                medias.append(sum(mi) / len(mi) if mi else 0.0)
            ax.bar(x + (k - (len(counts) - 1) / 2) * ancho, medias, ancho, label=f"{cnt} POIs" if cnt is not None else "n=?")
        ax.set_xticks(x)
        ax.set_xticklabels(nombres, rotation=20, ha="right")
        ax.set_ylabel(ylabel)
        ax.set_title(titulo)
        ax.legend()
        fig.tight_layout()
        fig.savefig(os.path.join(directorio, nombre), dpi=200)
        plt.close(fig)
        print(f"[gráficas] {nombre}")

    def _lineas(resultados, metrica, ylabel, titulo, nombre):
        instancias = []
        for por in resultados.values():
            for nom in por:
                if nom not in instancias:
                    instancias.append(nom)
        if not instancias or not resultados:
            return
        fig, ax = plt.subplots(figsize=(8, 4))
        for algoritmo in sorted(resultados):
            xs, ys = [], []
            for nom in instancias:
                vals = [inf[metrica] for inf in resultados[algoritmo].get(nom, []) if metrica in inf and inf[metrica] is not None]
                if vals:
                    xs.append(nom)
                    ys.append(sum(vals) / len(vals))
            if xs:
                ax.plot(xs, ys, marker="o", label=algoritmo)
        ax.set_ylabel(ylabel)
        ax.set_title(titulo)
        ax.legend()
        ax.tick_params(axis="x", rotation=20)
        for e in ax.get_xticklabels():
            e.set_ha("right")
        fig.tight_layout()
        fig.savefig(os.path.join(directorio, nombre), dpi=200)
        plt.close(fig)
        print(f"[gráficas] {nombre}")

    if res_busqueda is not None:
        _barras("Batería gastada total por buscador", _media_por_instancia(res_busqueda, "bateria_gastada_total"), "Batería total media", "fig_bateria_busqueda.png")
        _barras("Interés entregado por buscador", _media_por_instancia(res_busqueda, "interes_entregado"), "Interés entregado medio", "fig_interes_busqueda.png")
        _barras("Nodos expandidos por buscador", _media_por_instancia(res_busqueda, "nodos_expandidos"), "Nodos expandidos medios", "fig_nodos_busqueda.png")
        _lineas(res_busqueda, "bateria_gastada_total", "Batería total", "Batería por instancia y buscador", "fig_bateria_por_instancia.png")
        _agrupadas_por_pois("Batería por buscador, agrupada por nº de POIs", res_busqueda, "bateria_gastada_total", "Batería total media", "fig_bateria_busqueda_por_pois.png")
        _agrupadas_por_pois("Interés entregado por buscador, agrupado por nº de POIs", res_busqueda, "interes_entregado", "Interés entregado medio", "fig_interes_busqueda_por_pois.png")
    if res_meta is not None:
        _barras("Interés entregado por metaheurística", _media_por_instancia(res_meta, "interes_entregado"), "Interés entregado medio", "fig_interes_meta.png")
        _barras("Batería gastada total por metaheurística", _media_por_instancia(res_meta, "bateria_gastada_total"), "Batería total media", "fig_bateria_meta.png")
        _lineas(res_meta, "interes_entregado", "Interés entregado", "Interés entregado por instancia y metaheurística", "fig_interes_meta_por_instancia.png")
        _agrupadas_por_pois("Interés entregado por metaheurística, agrupado por nº de POIs", res_meta, "interes_entregado", "Interés entregado medio", "fig_interes_meta_por_pois.png")
        _agrupadas_por_pois("Batería por metaheurística, agrupada por nº de POIs", res_meta, "bateria_gastada_total", "Batería total media", "fig_bateria_meta_por_pois.png")


def main() -> int:
    parser = argparse.ArgumentParser(description="Experimento representativo del rover")
    parser.add_argument("--n-por-estrato", type=int, default=30, help="instancias por estrato (default 30; 9 estratos)")
    parser.add_argument("--trabajadores", type=int, default=4)
    parser.add_argument("--salida", default="resultados_representativo.jsonl")
    parser.add_argument("--instancias", default="instancias_representativo.json")
    parser.add_argument("--graficos", default="figuras_representativo")
    parser.add_argument("--modo", choices=["misiones", "legs", "ambos"], default="ambos")
    parser.add_argument("--presupuesto", type=int, default=100, help="evaluaciones de órdenes por metaheurística")
    parser.add_argument("--semilla-meta", type=int, default=7)
    parser.add_argument("--piloto", action="store_true", help="solo diseña y calcula n necesario, no corre misiones")
    parser.add_argument("--prueba", action="store_true", help="prueba pequeña: 2 instancias, todos los algoritmos, gráficas")
    args = parser.parse_args()

    if args.piloto:
        print("Diseño: 9 estratos (3 tamaños x 3 profundidades), asignación igual.")
        print(f"n por estrato (default): {args.n_por_estrato} -> instancias totales: {9 * args.n_por_estrato}")
        print(f"Misiones totales (12 por instancia): {9 * args.n_por_estrato * 12}")
        for sigma, media, margen in [(27.0, 65.0, 0.20), (27.0, 65.0, 0.10), (10.0, 65.0, 0.20)]:
            print(f"  sigma={sigma}, media={media}, margen={int(margen*100)}% -> n necesario por estrato: {calcular_n(sigma, media, margen)}")
        print("Con sigma=27, media=65, margen 20%: n=17; el default 30 es conservador.")
        return 0

    if args.prueba:
        # 2 instancias del primer estrato, con 3 y 5 POIs, config completa.
        rng = random.Random(0)
        instancias = []
        for j, n_pois in enumerate([3, 5]):
            cfg = config_completa(rng, 12, 12, 3, n_pois, 1.8, False, 0.06, 0.6, 2.0, 100.0, 2.0, 0.7, 0.6, 2, 3, 0.7, 0.5)
            instancias.append({"id": j, "estrato": "12x12_z3", "ancho": 12, "alto": 12, "profundidad": 3, "corrida": j, "n_pois": n_pois, "semilla_mapa": 20000 + j, "config": cfg})
        print("Modo prueba: 2 instancias, NO es el experimento completo.")
    else:
        instancias = generar_instancias(args.n_por_estrato)
        print(f"{len(instancias)} instancias generadas ({args.n_por_estrato} por estrato x 9 estratos)")

    Path(args.instancias).write_text(json.dumps(instancias, indent=1))
    tareas = []
    if args.modo in ("misiones", "ambos"):
        for inst in instancias:
            for bus in BUSQUEDAS_MISION:
                tareas.append({"instancia": inst, "busqueda": bus, "meta": "ninguna", "presupuesto": args.presupuesto, "semilla_meta": args.semilla_meta})
            for meta in METAS:
                tareas.append({"instancia": inst, "busqueda": "a_star", "meta": meta, "presupuesto": args.presupuesto, "semilla_meta": args.semilla_meta})
    res_busqueda: Dict = {}
    res_meta: Dict = {}
    with open(args.salida, "w") as f:
        if tareas:
            with Pool(args.trabajadores) as pool:
                for i, res in enumerate(pool.imap_unordered(_mision, tareas, chunksize=4)):
                    f.write(json.dumps(res) + "\n")
                    f.flush()
                    if (i + 1) % 100 == 0:
                        print(f"misiones: {i + 1}/{len(tareas)}", flush=True)
        if args.modo in ("legs", "ambos"):
            with Pool(args.trabajadores) as pool:
                for i, filas in enumerate(pool.imap_unordered(_legs_instancia, instancias, chunksize=2)):
                    for r in filas:
                        f.write(json.dumps(r) + "\n")
                    f.flush()
                    if (i + 1) % 10 == 0:
                        print(f"legs instancias: {i + 1}/{len(instancias)}", flush=True)
    # Reagrupar para gráficas (sin releer el JSONL en este script,
    # se reagrupa desde el archivo recién escrito).
    filas = [json.loads(l) for l in Path(args.salida).read_text().splitlines() if l.strip()]
    for r in filas:
        if "poi" in r:
            continue
        destino = res_busqueda if r["meta"] == "ninguna" else res_meta
        clave = r["busqueda"] if r["meta"] == "ninguna" else r["meta"]
        destino.setdefault(clave, {}).setdefault(r["estrato"] + "#" + str(r["instancia"]), []).append(r)
    print(f"Generando gráficas en {args.graficos} ...")
    generar_graficas(res_busqueda or None, res_meta or None, args.graficos)
    print("fin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
