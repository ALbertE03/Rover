from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def resumen(valores):
    n = len(valores)
    if n == 0:
        return {"n": 0}
    media = sum(valores) / n
    var = sum((x - media) ** 2 for x in valores) / (n - 1) if n > 1 else 0.0
    desv = math.sqrt(var)
    se = desv / math.sqrt(n) if n > 0 else 0.0
    ordenados = sorted(valores)
    mediana = ordenados[n // 2] if n % 2 else (ordenados[n // 2 - 1] + ordenados[n // 2]) / 2
    return {
        "n": n,
        "media": round(media, 3),
        "desv": round(desv, 3),
        "mediana": round(mediana, 3),
        "min": round(min(valores), 3),
        "max": round(max(valores), 3),
        "ic95_inf": round(media - 1.96 * se, 3),
        "ic95_sup": round(media + 1.96 * se, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entrada", required=True)
    parser.add_argument("--salida", required=True)
    args = parser.parse_args()
    filas = [json.loads(l) for l in Path(args.entrada).read_text().splitlines() if l.strip()]
    misiones = [r for r in filas if "poi" not in r and r.get("ok")]
    legs = [r for r in filas if "poi" in r and r.get("ok")]
    out = Path(args.salida)
    out.mkdir(parents=True, exist_ok=True)
    stats = {}

    # Search missions: group by algorithm, and by (size, depth, algorithm)
    busquedas = sorted({r["busqueda"] for r in misiones if r["meta"] == "ninguna"})
    stats["busquedas"] = {}
    for bus in busquedas:
        grupo = [r for r in misiones if r["meta"] == "ninguna" and r["busqueda"] == bus]
        stats["busquedas"][bus] = {
            campo: resumen([r[campo] for r in grupo])
            for campo in ["interes_recolectado", "interes_entregado", "bateria_gastada_total", "pasos", "nodos_expandidos", "tiempo_segundos"]
        }
        stats["busquedas"][bus]["cobertura_media"] = round(
            sum(r["interes_entregado"] / r["interes_total_mapa"] for r in grupo if r["interes_total_mapa"] > 0) / len(grupo), 3
        )
        stats["busquedas"][bus]["entrega_completa_frac"] = round(
            sum(1 for r in grupo if abs(r["interes_entregado"] - r["interes_total_mapa"]) < 1e-6) / len(grupo), 3
        )
    # Paired battery difference vs A*, per instance (search missions only)
    por_inst = defaultdict(dict)
    for r in misiones:
        if r["meta"] == "ninguna":
            por_inst[r["instancia"]][r["busqueda"]] = r["bateria_gastada_total"]
    stats["diferencia_bateria_vs_astar"] = {}
    for bus in busquedas:
        diffs = [
            d[bus] - d["a_star"]
            for d in por_inst.values()
            if bus in d and "a_star" in d
        ]
        stats["diferencia_bateria_vs_astar"][bus] = resumen(diffs)

    # Meta missions
    metas = sorted({r["meta"] for r in misiones if r["meta"] != "ninguna"})
    stats["metas"] = {}
    for meta in metas:
        grupo = [r for r in misiones if r["meta"] == meta]
        stats["metas"][meta] = {
            campo: resumen([r[campo] for r in grupo])
            for campo in ["interes_recolectado", "interes_entregado", "bateria_gastada_total", "pasos", "tiempo_segundos"]
        }
        stats["metas"][meta]["cobertura_media"] = round(
            sum(r["interes_entregado"] / r["interes_total_mapa"] for r in grupo if r["interes_total_mapa"] > 0) / len(grupo), 3
        )
    por_inst_meta = defaultdict(dict)
    for r in misiones:
        if r["meta"] != "ninguna":
            por_inst_meta[r["instancia"]][r["meta"]] = r["bateria_gastada_total"]
    stats["diferencia_bateria_meta_vs_random"] = {}
    for meta in metas:
        diffs = [
            d[meta] - d["random"]
            for d in por_inst_meta.values()
            if meta in d and "random" in d
        ]
        stats["diferencia_bateria_meta_vs_random"][meta] = resumen(diffs)

    # By size/depth: search battery and meta interest
    stats["por_tamano"] = {}
    for ancho in sorted({r["ancho"] for r in misiones}):
        for prof in sorted({r["profundidad"] for r in misiones if r["ancho"] == ancho}):
            clave = f"{ancho}x{ancho}_z{prof}"
            grupo_bus = [r for r in misiones if r["meta"] == "ninguna" and r["ancho"] == ancho and r["profundidad"] == prof]
            grupo_meta = [r for r in misiones if r["meta"] != "ninguna" and r["ancho"] == ancho and r["profundidad"] == prof]
            stats["por_tamano"][clave] = {
                "busqueda_bateria": {bus: resumen([r["bateria_gastada_total"] for r in grupo_bus if r["busqueda"] == bus]) for bus in busquedas},
                "meta_interes_entregado": {meta: resumen([r["interes_entregado"] for r in grupo_meta if r["meta"] == meta]) for meta in metas},
                "meta_bateria": {meta: resumen([r["bateria_gastada_total"] for r in grupo_meta if r["meta"] == meta]) for meta in metas},
            }

    # Legs
    stats["legs"] = {}
    for bus in sorted({r["busqueda"] for r in legs}):
        grupo = [r for r in legs if r["busqueda"] == bus]
        stats["legs"][bus] = {
            "exito_frac": round(sum(1 for r in grupo if r["ok"]) / len(grupo), 3),
            "coste": resumen([r["coste"] for r in grupo if r["coste"] is not None]),
            "pasos": resumen([r["pasos"] for r in grupo if r["pasos"] is not None]),
            "nodos": resumen([r["nodos_expandidos"] for r in grupo if r["nodos_expandidos"] is not None]),
            "tiempo": resumen([r["tiempo_segundos"] for r in grupo]),
        }
    (out / "estadisticas_grande.json").write_text(json.dumps(stats, indent=1))

    # Figures
    plt.rcParams.update({"font.size": 9})
    # Fig 1: battery by search algorithm
    fig, ax = plt.subplots(figsize=(8, 4))
    vals = [stats["busquedas"][b]["bateria_gastada_total"]["media"] for b in busquedas]
    ax.bar(busquedas, vals)
    ax.set_ylabel("Batería total media")
    ax.set_title("Batería total media por algoritmo de búsqueda (270 instancias)")
    fig.tight_layout()
    fig.savefig(out / "fig_bateria_busqueda_grande.png", dpi=200)
    plt.close(fig)
    # Fig 2: interest delivered by metaheuristic
    fig, ax = plt.subplots(figsize=(8, 4))
    vals = [stats["metas"][m]["interes_entregado"]["media"] for m in metas]
    ax.bar(metas, vals)
    ax.set_ylabel("Interés entregado medio")
    ax.set_title("Interés entregado medio por metaheurística (270 instancias, A*)")
    fig.tight_layout()
    fig.savefig(out / "fig_interes_meta_grande.png", dpi=200)
    plt.close(fig)
    # Fig 3: battery by size, A* vs greedy vs beam
    fig, ax = plt.subplots(figsize=(8, 4))
    claves = sorted(stats["por_tamano"])
    for bus in ["a_star", "greedy", "beam", "bfs"]:
        vals = [stats["por_tamano"][c]["busqueda_bateria"][bus]["media"] for c in claves]
        ax.plot(claves, vals, marker="o", label=bus)
    ax.set_ylabel("Batería media")
    ax.legend()
    ax.set_title("Batería por tamaño y profundidad (búsqueda, sin meta)")
    fig.tight_layout()
    fig.savefig(out / "fig_bateria_tamano.png", dpi=200)
    plt.close(fig)
    # Fig 4: leg cost by search
    fig, ax = plt.subplots(figsize=(8, 4))
    legs_bus = sorted(stats["legs"])
    vals = [stats["legs"][b]["coste"]["media"] for b in legs_bus]
    ax.bar(legs_bus, vals)
    ax.set_ylabel("Coste medio del leg")
    ax.set_title("Coste medio por leg base→POI (1350 legs)")
    fig.tight_layout()
    fig.savefig(out / "fig_coste_leg.png", dpi=200)
    plt.close(fig)
    print(f"misiones ok: {len(misiones)}, legs ok: {len(legs)}")
    print(json.dumps(stats["busquedas"], indent=1)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
