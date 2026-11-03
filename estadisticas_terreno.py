from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
from typing import Dict, List

from enviro.terrain import InstanceParams, MapGenerator
from enviro.terrain.grid import cell_id, movement_offsets, parse_cell_id
from experimento_representativo import config_completa, generar_instancias


def _componentes(celdas, offsets):
    """Componentes conexas de celdas transitables, por id de celda."""
    transitables = {cid for cid, c in celdas.items() if not c.blocked}
    vistos = set()
    comps = []
    for inicio in transitables:
        if inicio in vistos:
            continue
        comp = set()
        frontera = [inicio]
        vistos.add(inicio)
        while frontera:
            actual = frontera.pop()
            comp.add(actual)
            x, y, z = parse_cell_id(actual)
            for dx, dy, dz in offsets:
                vecino = cell_id(x + dx, y + dy, z + dz)
                if vecino in transitables and vecino not in vistos:
                    vistos.add(vecino)
                    frontera.append(vecino)
        comps.append(comp)
    return comps


def estadisticas_instancia(inst: Dict) -> Dict:
    try:
        mapa = MapGenerator(
            InstanceParams.from_config(seed=inst["semilla_mapa"], config=inst["config"])
        ).create()
    except Exception as exc:  # instancia no generable: se registra, no se aborta
        return {
            "instancia": inst["id"],
            "estrato": inst["estrato"],
            "ancho": inst["ancho"],
            "profundidad": inst["profundidad"],
            "n_pois_config": inst["n_pois"],
            "semilla_mapa": inst["semilla_mapa"],
            "error": str(exc),
        }
    params = mapa.params
    celdas = mapa.cells
    # Superficie: celda más alta por columna (x, y).
    tops = {}
    for cell in celdas.values():
        x, y, z = cell.pos
        if z > tops.get((x, y), -1):
            tops[(x, y)] = z
    superficie = [c for c in celdas.values() if c.pos[2] == tops[(c.pos[0], c.pos[1])]]
    terrenos = Counter(c.true_terrain for c in celdas.values())
    alturas = Counter(tops.values())
    offsets = movement_offsets(params.move_radius, params.move_allow_diagonal)
    comps = _componentes(celdas, offsets)
    comp_de = {}
    for i, comp in enumerate(comps):
        for cid in comp:
            comp_de[cid] = i
    estaciones = [(s.id, cell_id(*s.center)) for s in mapa.stations]
    centros_est = {cid for _, cid in estaciones}
    comp_est = {comp_de[cid] for _, cid in estaciones if cid in comp_de}
    base_id = estaciones[0][1] if estaciones else None
    comp_base = comp_de.get(base_id) if base_id else None
    pois = list(mapa.pois.values())
    intereses = [p.interest for p in pois]
    pois_en_est = sum(1 for p in pois if p.cell_id in centros_est)
    pois_bloq = sum(1 for p in pois if celdas[p.cell_id].blocked)
    alc_cualq = sum(1 for p in pois if p.cell_id in comp_de and comp_de[p.cell_id] in comp_est)
    alc_base = sum(1 for p in pois if p.cell_id in comp_de and comp_de[p.cell_id] == comp_base)
    comp_unica = sum(1 for p in pois if p.cell_id in comp_de and len(comps[comp_de[p.cell_id]]) == 1)
    return {
        "instancia": inst["id"],
        "estrato": inst["estrato"],
        "ancho": inst["ancho"],
        "profundidad": inst["profundidad"],
        "n_pois_config": inst["n_pois"],
        "semilla_mapa": inst["semilla_mapa"],
        "celdas_totales": len(celdas),
        "celdas_interiores": len(celdas) - len(superficie),
        "celdas_superficie": len(superficie),
        "superficie_bloqueada": sum(1 for c in superficie if c.blocked),
        "superficie_transitable": sum(1 for c in superficie if not c.blocked),
        "celdas_transitables": sum(1 for c in superficie if not c.blocked),
        "terrenos": dict(terrenos),
        "altura_max_columna": dict(alturas),
        "toca_capa_maxima": max(tops.values()) == params.depth - 1 if tops else False,
        "n_estaciones": len(estaciones),
        "estaciones": [s_id for s_id, _ in estaciones],
        "n_pois": len(pois),
        "interes_poi_medio": round(sum(intereses) / len(intereses), 4) if intereses else 0.0,
        "interes_poi_min": round(min(intereses), 4) if intereses else 0.0,
        "interes_poi_max": round(max(intereses), 4) if intereses else 0.0,
        "pois_en_estacion": pois_en_est,
        "pois_bloqueados": pois_bloq,
        "n_componentes": len(comps),
        "componente_mayor": max((len(c) for c in comps), default=0),
        "superficie_multicomponente": len(comps) > 1,
        "estaciones_mismo_componente": len(comp_est) == 1,
        "pois_alcanzables_desde_cualquier_estacion": alc_cualq,
        "pois_alcanzables_desde_base": alc_base,
        "pois_inalcanzables_desde_cualquier_estacion": len(pois) - alc_cualq,
        "pois_inalcanzables_desde_base": len(pois) - alc_base,
        "pois_en_componente_unica": comp_unica,
    }


def _resumen(filas: List[Dict]) -> Dict:
    ok = [f for f in filas if "error" not in f]
    fallos = [f for f in filas if "error" in f]
    if fallos:
        print(f"AVISO: {len(fallos)} instancias no generables (ver campo error):")
        for f in fallos:
            print(f"  instancia {f['instancia']} estrato {f['estrato']} semilla {f['semilla_mapa']}: {f['error']}")
    filas = ok

    def media(campo):
        vals = [f[campo] for f in filas]
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    n = len(filas)
    total_pois = sum(f["n_pois"] for f in filas)
    return {
        "n_instancias": len(ok) + len(fallos),
        "n_instancias_ok": len(ok),
        "n_instancias_fallo": len(fallos),
        "fallos_por_estrato": dict(Counter(f["estrato"] for f in fallos)),
        "celdas_totales_media": media("celdas_totales"),
        "celdas_interiores_media": media("celdas_interiores"),
        "superficie_bloqueada_media": media("superficie_bloqueada"),
        "superficie_transitable_media": media("superficie_transitable"),
        "mapas_toca_capa_maxima": sum(1 for f in filas if f["toca_capa_maxima"]),
        "mapas_multicomponente": sum(1 for f in filas if f["superficie_multicomponente"]),
        "mapas_estaciones_mismo_componente": sum(1 for f in filas if f["estaciones_mismo_componente"]),
        "total_pois": total_pois,
        "pois_en_estacion": sum(f["pois_en_estacion"] for f in filas),
        "pois_bloqueados": sum(f["pois_bloqueados"] for f in filas),
        "pois_inalcanzables_desde_cualquier_estacion": sum(
            f["pois_inalcanzables_desde_cualquier_estacion"] for f in filas
        ),
        "pois_inalcanzables_desde_base": sum(f["pois_inalcanzables_desde_base"] for f in filas),
        "pois_en_componente_unica": sum(f["pois_en_componente_unica"] for f in filas),
        "pois_inalcanzables_desde_cualquier_estacion_pct": round(
            100 * sum(f["pois_inalcanzables_desde_cualquier_estacion"] for f in filas) / total_pois, 2
        ) if total_pois else 0.0,
        "pois_inalcanzables_desde_base_pct": round(
            100 * sum(f["pois_inalcanzables_desde_base"] for f in filas) / total_pois, 2
        ) if total_pois else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Estadísticas del terreno (solo generación)")
    parser.add_argument("--n-por-estrato", type=int, default=30)
    parser.add_argument("--trabajadores", type=int, default=4)
    parser.add_argument("--salida", default="stats_terreno.jsonl")
    parser.add_argument("--resumen", default="resumen_terreno.json")
    parser.add_argument("--prueba", action="store_true", help="2 instancias, las mismas de --prueba del experimento")
    args = parser.parse_args()

    if args.prueba:
        rng = random.Random(0)
        instancias = []
        for j, n_pois in enumerate([3, 5]):
            cfg = config_completa(rng, 12, 12, 3, n_pois, 1.8, False, 0.06, 0.6, 2.0, 100.0, 2.0, 0.7, 0.6, 2, 3, 0.7, 0.5)
            instancias.append({"id": j, "estrato": "12x12_z3", "ancho": 12, "alto": 12, "profundidad": 3, "corrida": j, "n_pois": n_pois, "semilla_mapa": 20000 + j, "config": cfg})
        print("Modo prueba: 2 instancias, las mismas que --prueba del experimento.")
    else:
        instancias = generar_instancias(args.n_por_estrato)
        print(f"{len(instancias)} instancias (las mismas del experimento, solo terreno)")

    with Pool(args.trabajadores) as pool:
        filas = pool.map(estadisticas_instancia, instancias)
    with open(args.salida, "w") as f:
        for fila in filas:
            f.write(json.dumps(fila) + "\n")
    resumen = _resumen(filas)
    Path(args.resumen).write_text(json.dumps(resumen, indent=1))
    print(json.dumps(resumen, indent=1))
    print(f"Filas en {args.salida}, resumen en {args.resumen}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
