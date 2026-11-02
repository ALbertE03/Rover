from __future__ import annotations

import argparse
import json
from multiprocessing import Pool
from pathlib import Path

from experimento_grande import generar_instancias, _mision
from legs import _legs_instancia

# Versión pequeña del experimento completo (experimento_grande.py,
# que queda como "completo" con 30 instancias por combo). Esta
# versión usa 5 instancias por combo (9 combos = 45 instancias),
# con las mismas configs aleatorias válidas, los mismos algoritmos
# de las conferencias y el mismo presupuesto (100 evaluaciones).
# Misiones: 45 x (6 búsquedas + 6 metaheurísticas) = 540.
# Legs: 45 x 7 búsquedas x 5 POIs = 1575, con un solo mapa por
# instancia (legs.py), no un mapa por leg.


def main() -> int:
    parser = argparse.ArgumentParser(description="Experimento pequeño del rover")
    parser.add_argument("--salida", default="resultados_pequeno.jsonl")
    parser.add_argument("--instancias", default="instancias_pequeno.json")
    parser.add_argument("--trabajadores", type=int, default=4)
    parser.add_argument("--n-por-combo", type=int, default=5)
    args = parser.parse_args()
    instancias = generar_instancias(args.n_por_combo)
    Path(args.instancias).write_text(json.dumps(instancias, indent=1))
    print(f"{len(instancias)} instancias generadas ({args.n_por_combo} por combo)")
    from experimento_grande import BUSQUEDAS_MISION, METAS

    tareas = []
    for inst in instancias:
        for bus in BUSQUEDAS_MISION:
            tareas.append({"instancia": inst, "busqueda": bus, "meta": "ninguna"})
        for meta in METAS:
            tareas.append({"instancia": inst, "busqueda": "a_star", "meta": meta})
    with open(args.salida, "w") as f:
        with Pool(args.trabajadores) as pool:
            for i, res in enumerate(pool.imap_unordered(_mision, tareas, chunksize=4)):
                f.write(json.dumps(res) + "\n")
                f.flush()
                if (i + 1) % 100 == 0:
                    print(f"misiones: {i + 1}/{len(tareas)}", flush=True)
        with Pool(args.trabajadores) as pool:
            for i, filas in enumerate(pool.imap_unordered(_legs_instancia, instancias, chunksize=2)):
                for r in filas:
                    f.write(json.dumps(r) + "\n")
                f.flush()
                if (i + 1) % 10 == 0:
                    print(f"legs instancias: {i + 1}/{len(instancias)}", flush=True)
    print("fin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
