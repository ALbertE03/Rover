"""Aggregate statistics over a batch of generated terrains.

Usage:
    python main.py [count]

Generates `count` terrains (default 30) with seeds 0..count-1 under the
default configuration and prints aggregate statistics: terrain mix, column
heights, blocked cells, stations and points of interest.
"""

import sys
import time
from collections import Counter
from typing import Dict, List

from enviro.terrain import Map, generate

# Display order follows the generation bands, cheapest first.
TERRAIN_ORDER = ("plain", "sand", "rocky", "crevasse", "lava")


def summarize(maps: List[Map]) -> Dict:
    """Aggregate counters over a batch of maps."""
    stats: Dict = {
        "maps": len(maps),
        "cells": 0,
        "terrain": Counter(),
        "column_top": Counter(),
        "blocked": 0,
        "surface": 0,
        "surface_blocked": 0,
        "stations": 0,
        "pois": 0,
        "maps_reaching_top": 0,
    }
    for m in maps:
        depth = m.params.depth
        tops: Dict = {}
        for cell in m.cells.values():
            stats["cells"] += 1
            stats["terrain"][cell.true_terrain] += 1
            x, y, z = cell.pos
            if z > tops.get((x, y), -1):
                tops[(x, y)] = z
            if cell.blocked:
                stats["blocked"] += 1
        for cell in m.cells.values():
            x, y, z = cell.pos
            if z == tops[(x, y)]:
                stats["surface"] += 1
                if cell.blocked:
                    stats["surface_blocked"] += 1
        for h in tops.values():
            stats["column_top"][h] += 1
        if max(tops.values()) == depth - 1:
            stats["maps_reaching_top"] += 1
        stats["stations"] += len(m.stations)
        stats["pois"] += len(m.pois)
    return stats


def report(stats: Dict, elapsed: float) -> None:
    """Print the aggregate statistics (in Spanish)."""
    n = stats["maps"]
    print(f"Mapas generados : {n} (semillas 0..{n - 1}, config por defecto)")
    print(f"Tiempo total    : {elapsed:.2f} s ({elapsed / n:.3f} s por mapa)")
    print(f"Celdas totales  : {stats['cells']}")
    print()
    print("Terrenos (por celda):")
    for name in TERRAIN_ORDER:
        c = stats["terrain"].get(name, 0)
        print(f"  {name:9s} {c:6d}  ({100 * c / stats['cells']:5.1f} %)")
    print()
    print("Altura máxima por columna:")
    total_cols = sum(stats["column_top"].values())
    for h in sorted(stats["column_top"]):
        c = stats["column_top"][h]
        print(f"  capa {h}      {c:6d}  ({100 * c / total_cols:5.1f} %)")
    print(f"Mapas que tocan la capa máxima: "
          f"{stats['maps_reaching_top']}/{n}")
    print()
    blocked_pct = 100 * stats["blocked"] / stats["cells"]
    print(f"Celdas bloqueadas             : {stats['blocked']} ({blocked_pct:.1f} %)")
    surf_pct = 100 * stats["surface_blocked"] / stats["surface"]
    print(f"Superficie bloqueada (roca+lava): "
          f"{stats['surface_blocked']} ({surf_pct:.1f} % de la superficie)")
    print()
    print(f"Estaciones por mapa: {stats['stations'] / n:.1f}")
    print(f"POIs por mapa      : {stats['pois'] / n:.1f}")


def main(count: int) -> None:
    """Generate `count` terrains and report aggregate statistics."""
    start = time.time()
    maps = [generate(seed) for seed in range(count)]
    elapsed = time.time() - start
    report(summarize(maps), elapsed)


if __name__ == "__main__":
    count = 30
    if len(sys.argv) > 1:
        try:
            count = int(sys.argv[1])
        except ValueError:
            sys.exit(f"uso: python main.py [cantidad] (recibido {sys.argv[1]!r})")
    if count < 1:
        sys.exit("la cantidad debe ser >= 1")
    main(count)
