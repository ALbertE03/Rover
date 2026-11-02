from __future__ import annotations

import argparse
import json
import random
import time
from multiprocessing import Pool
from pathlib import Path
from typing import Dict, List

TAMANOS = [(12, 12), (16, 16), (32, 32)]
PROFUNDIDADES = [3, 5, 7]
BUSQUEDAS_MISION = ["a_star", "dijkstra", "greedy", "bfs", "weighted", "beam"]
BUSQUEDAS_LEG = BUSQUEDAS_MISION + ["dfs"]
METAS = ["random", "hill_climbing", "simulated_annealing", "tabu", "genetico", "aco"]


def config_aleatoria(rng: random.Random) -> Dict:
    """A random, valid terrain configuration, never the default.

    Costs are ordered plain < sand < rocky < crevasse and
    visibilities decrease in the same order, so terrain names keep
    their meaning; bands are increasing cut points in (0, 1); lava
    stays blocked at cost 999. Every other field is sampled in a
    range that InstanceParams accepts, so generation cannot fail
    on validation (generation itself is still tried by the caller).
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
            "bands": [
                {"max": round(cortes[0], 3), "terrain": "plain"},
                {"max": round(cortes[1], 3), "terrain": "sand"},
                {"max": round(cortes[2], 3), "terrain": "rocky"},
                {"max": 1.0, "terrain": "crevasse"},
            ],
            "biome_count": rng.randint(2, 4),
            "lava_pools": rng.randint(1, 3),
            "lava_pool_radius": [2, rng.randint(3, 5)],
            "relief_amplitude": round(rng.uniform(0.4, 1.0), 3),
        },
        "map": {"block_rate": round(rng.uniform(0.03, 0.12), 3)},
        "movement": {
            "climb_penalty": round(rng.uniform(0.3, 0.9), 3),
            "survey_height_bonus": round(rng.uniform(1.0, 3.0), 3),
            "radius": 1.8,
            "allow_diagonal": False,
        },
        "terrain": {
            "plain": {"cost": round(costes[0], 3), "visibility": round(vis[0], 3), "glyph": "."},
            "sand": {"cost": round(costes[1], 3), "visibility": round(vis[1], 3), "glyph": ":"},
            "rocky": {"cost": round(costes[2], 3), "visibility": round(vis[2], 3), "glyph": "#"},
            "crevasse": {"cost": round(costes[3], 3), "visibility": round(vis[3], 3), "glyph": "/"},
            "lava": {"cost": 999.0, "visibility": 0.1, "glyph": "~", "color": "#e03c00"},
        },
    }


def generar_instancias(n_por_combo: int = 30) -> List[Dict]:
    """30 instances per (size, depth) combo, each with its own config.

    Instance id encodes combo and run: id = combo_index * 1000 + run.
    The map seed is 10000 + id, the config RNG seed is id, so every
    instance is fully declared and reproducible from this file.
    """
    instancias: List[Dict] = []
    combo = 0
    for w, h in TAMANOS:
        for depth in PROFUNDIDADES:
            for run in range(n_por_combo):
                iid = combo * 1000 + run
                rng = random.Random(iid)
                cfg = config_aleatoria(rng)
                cfg["map"]["width"] = w
                cfg["map"]["height"] = h
                cfg["map"]["depth"] = depth
                instancias.append(
                    {
                        "id": iid,
                        "ancho": w,
                        "alto": h,
                        "profundidad": depth,
                        "corrida": run,
                        "semilla_mapa": 10000 + iid,
                        "config": cfg,
                    }
                )
            combo += 1
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
            presupuesto_evaluaciones=100,
            semilla_metaheuristica=7,
        )
        return {
            "instancia": inst["id"],
            "ancho": inst["ancho"],
            "profundidad": inst["profundidad"],
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
    except Exception as exc:  # noqa: BLE001 - experiment must not die
        return {
            "instancia": inst["id"],
            "ancho": inst["ancho"],
            "profundidad": inst["profundidad"],
            "busqueda": tarea.get("busqueda", "a_star"),
            "meta": tarea.get("meta", "ninguna"),
            "ok": False,
            "error": repr(exc),
        }


def _leg(tarea: Dict) -> Dict:
    from enviro.terrain import InstanceParams, MapGenerator
    from enviro.terrain.grid import movement_offsets
    from rover import Rover, plan_route

    inst = tarea["instancia"]
    mapa = MapGenerator(
        InstanceParams.from_config(
            seed=inst["semilla_mapa"], config=inst["config"]
        )
    ).create()
    rover = Rover(mapa, algoritmo_busqueda="a_star")
    conocidos = dict(rover.known)
    bloqueados = set(rover.known_blocked)
    t0 = time.perf_counter()
    try:
        res = plan_route(
            rover.pos,
            rover.poi_coord(tarea["poi"]),
            mapa.cells,
            movement_offsets(
                mapa.params.move_radius, mapa.params.move_allow_diagonal
            ),
            conocidos,
            rover.registry,
            mapa.params.climb_penalty,
            algoritmo=tarea["busqueda"],
            known_blocked=bloqueados,
        )
        return {
            "instancia": inst["id"],
            "ancho": inst["ancho"],
            "profundidad": inst["profundidad"],
            "busqueda": tarea["busqueda"],
            "poi": tarea["poi"],
            "ok": res is not None,
            "coste": round(res.cost, 3) if res else None,
            "pasos": len(res.path) - 1 if res else None,
            "nodos_expandidos": res.expanded if res else None,
            "tiempo_segundos": round(time.perf_counter() - t0, 4),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "instancia": inst["id"],
            "ancho": inst["ancho"],
            "profundidad": inst["profundidad"],
            "busqueda": tarea["busqueda"],
            "poi": tarea["poi"],
            "ok": False,
            "error": repr(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Experimento grande del rover")
    parser.add_argument("--salida", default="resultados_grande.jsonl")
    parser.add_argument("--instancias", default="instancias_grande.json")
    parser.add_argument("--trabajadores", type=int, default=4)
    parser.add_argument("--modo", choices=["misiones", "legs", "ambos"], default="ambos")
    args = parser.parse_args()
    instancias = generar_instancias(30)
    Path(args.instancias).write_text(json.dumps(instancias, indent=1))
    print(f"{len(instancias)} instancias generadas")
    tareas: List[Dict] = []
    if args.modo in ("misiones", "ambos"):
        for inst in instancias:
            for bus in BUSQUEDAS_MISION:
                tareas.append({"instancia": inst, "busqueda": bus, "meta": "ninguna"})
            for meta in METAS:
                tareas.append({"instancia": inst, "busqueda": "a_star", "meta": meta})
    if args.modo in ("legs", "ambos"):
        # Leg tasks are appended after missions in the same file,
        # marked by the presence of "poi".
        pass
    # Run missions first, then legs, writing incrementally.
    with open(args.salida, "w") as f:
        if tareas:
            with Pool(args.trabajadores) as pool:
                for i, res in enumerate(pool.imap_unordered(_mision, tareas, chunksize=4)):
                    f.write(json.dumps(res) + "\n")
                    f.flush()
                    if (i + 1) % 100 == 0:
                        print(f"misiones: {i + 1}/{len(tareas)}", flush=True)
        if args.modo in ("legs", "ambos"):
            # Leg tasks need POI ids per instance; regenerate maps here
            # is avoided by asking _leg to build its own map.
            tareas_leg: List[Dict] = []
            for inst in instancias:
                for bus in BUSQUEDAS_LEG:
                    for k in range(5):
                        tareas_leg.append(
                            {"instancia": inst, "busqueda": bus, "poi": f"poi_{k}"}
                        )
            with Pool(args.trabajadores) as pool:
                for i, res in enumerate(pool.imap_unordered(_leg, tareas_leg, chunksize=20)):
                    f.write(json.dumps(res) + "\n")
                    f.flush()
                    if (i + 1) % 500 == 0:
                        print(f"legs: {i + 1}/{len(tareas_leg)}", flush=True)
    print("fin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
