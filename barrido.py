from __future__ import annotations

import json
import sys
from pathlib import Path

# Parameter sweep on 10 random instances (12x12, z=3, from instancias_grande.json)
# Vary one parameter at a time, up and down, around the instance's own
# random config: battery, memory, block_rate, climb_penalty,
# survey_height_bonus, POI count. Base case is the instance config itself.
VARIACIONES = {
    "bateria": [50.0, 200.0],
    "memoria": [1.0, 4.0],
    "block_rate": [0.03, 0.12],
    "climb_penalty": [0.0, 1.2],
    "survey_height_bonus": [0.0, 4.0],
    "poi_count": [3, 7],
}


def main() -> int:
    from rover import ejecutar_mision

    instancias_path = Path(sys.argv[1])
    salida = Path(sys.argv[2])
    instancias = json.loads(instancias_path.read_text())
    base = [i for i in instancias if i["ancho"] == 12 and i["profundidad"] == 3][:10]
    filas = []
    for inst in base:
        cfg_base = inst["config"]
        for nombre, valores in VARIACIONES.items():
            for valor in valores:
                cfg = json.loads(json.dumps(cfg_base))
                if nombre == "bateria":
                    cfg.setdefault("rover", {})["battery"] = valor
                elif nombre == "memoria":
                    cfg.setdefault("rover", {})["memory"] = valor
                elif nombre == "block_rate":
                    cfg["map"]["block_rate"] = valor
                elif nombre == "climb_penalty":
                    cfg["movement"]["climb_penalty"] = valor
                elif nombre == "survey_height_bonus":
                    cfg["movement"]["survey_height_bonus"] = valor
                elif nombre == "poi_count":
                    cfg.setdefault("poi", {})["count"] = valor
                try:
                    inf = ejecutar_mision(
                        semilla=inst["semilla_mapa"],
                        config=cfg,
                        algoritmo_busqueda="a_star",
                        metaheuristica="ninguna",
                    )
                    filas.append(
                        {
                            "instancia": inst["id"],
                            "parametro": nombre,
                            "valor": valor,
                            "ok": True,
                            "interes_recolectado": inf["interes_recolectado"],
                            "interes_entregado": inf["interes_entregado"],
                            "interes_total_mapa": inf["interes_total_mapa"],
                            "pasos": inf["pasos"],
                            "bateria_gastada_total": inf["bateria_gastada_total"],
                            "celdas_conocidas": inf["celdas_conocidas"],
                            "celdas_totales": inf["celdas_totales"],
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    filas.append(
                        {"instancia": inst["id"], "parametro": nombre, "valor": valor, "ok": False, "error": repr(exc)}
                    )
        # Base case for comparison
        try:
            inf = ejecutar_mision(
                semilla=inst["semilla_mapa"],
                config=cfg_base,
                algoritmo_busqueda="a_star",
                metaheuristica="ninguna",
            )
            filas.append(
                {
                    "instancia": inst["id"],
                    "parametro": "base",
                    "valor": None,
                    "ok": True,
                    "interes_recolectado": inf["interes_recolectado"],
                    "interes_entregado": inf["interes_entregado"],
                    "interes_total_mapa": inf["interes_total_mapa"],
                    "pasos": inf["pasos"],
                    "bateria_gastada_total": inf["bateria_gastada_total"],
                    "celdas_conocidas": inf["celdas_conocidas"],
                    "celdas_totales": inf["celdas_totales"],
                }
            )
        except Exception as exc:  # noqa: BLE001
            filas.append({"instancia": inst["id"], "parametro": "base", "valor": None, "ok": False, "error": repr(exc)})
        print(f"instancia {inst['id']} hecha", flush=True)
    salida.write_text("\n".join(json.dumps(f) for f in filas))
    print(f"{len(filas)} filas en {salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
