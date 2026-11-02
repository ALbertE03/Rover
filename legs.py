from __future__ import annotations

import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

BUSQUEDAS = ["a_star", "dijkstra", "greedy", "bfs", "dfs", "weighted", "beam"]


def _legs_instancia(inst):
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
    filas = []
    for bus in BUSQUEDAS:
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
                        "ancho": inst["ancho"],
                        "profundidad": inst["profundidad"],
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
                        "ancho": inst["ancho"],
                        "profundidad": inst["profundidad"],
                        "busqueda": bus,
                        "poi": poi,
                        "ok": False,
                        "error": repr(exc),
                    }
                )
    return filas


def main() -> int:
    instancias = json.loads(Path(sys.argv[1]).read_text())
    salida = Path(sys.argv[2])
    with open(salida, "w") as f:
        with Pool(4) as pool:
            for i, filas in enumerate(pool.imap_unordered(_legs_instancia, instancias, chunksize=2)):
                for r in filas:
                    f.write(json.dumps(r) + "\n")
                f.flush()
                if (i + 1) % 20 == 0:
                    print(f"legs instancias: {i + 1}/{len(instancias)}", flush=True)
    print("fin legs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
