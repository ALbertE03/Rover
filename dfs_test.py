import os
import sys

sys.path.insert(0, os.getcwd())

from enviro.terrain import InstanceParams, MapGenerator
from planificacion import Planificador
from rover import Rover, ejecutar_mision


def parte1():
    for alg in ["a_star", "dfs"]:
        print(f"--- {alg} ---")
        tot_pois = tot_pasos = 0
        for s in range(10):
            r = ejecutar_mision(
                semilla=s, algoritmo_busqueda=alg, metaheuristica="ninguna"
            )
            n = len(r["pois_entregados"])
            tot_pois += n
            tot_pasos += r["pasos"]
            print(
                f"semilla {s}: entregados {n}/{r['n_pois']}, "
                f"pasos {r['pasos']}, bateria_final {r['bateria_final']}"
            )
        print(f"TOTAL {alg}: {tot_pois} POIs en {tot_pasos} pasos")


def parte2(semilla=42):
    for alg in ["a_star", "dfs"]:
        mapa = MapGenerator(InstanceParams.from_config(seed=semilla)).create()
        rover = Rover(mapa, algoritmo_busqueda=alg)
        orden = sorted(mapa.pois.keys(), key=lambda p: -mapa.pois[p].interest)
        plan = Planificador(rover).planificar(orden)
        Planificador(rover).ejecutar(rover, plan.acciones)
        path = rover.path
        vueltas = sum(1 for i in range(2, len(path)) if path[i] == path[i - 2])
        revisitas = len(path) - len(set(path))
        print(
            f"{alg} semilla {semilla}: entregados {len(rover.delivered_pois)}, "
            f"pasos {rover.steps}, celdas en camino {len(path)}, "
            f"celdas repetidas {revisitas}, retrocesos A-B-A {vueltas}, "
            f"bateria_final {rover.battery:.1f}"
        )
        if alg == "dfs":
            print("primeros 40 pasos:", path[:40])


if __name__ == "__main__":
    parte1()
    parte2()
