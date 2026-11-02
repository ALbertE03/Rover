from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

Evaluar = Callable[[List[str]], float]


@dataclass
class RandomSearch:
    """Random search over POI visit orders, conference metaheuristics.

    The simplest baseline in the conference: sample random orders,
    keep the best ever seen. It uses no neighbourhood and no memory
    beyond the best order, so any other metaheuristic must beat it
    to be worth its complexity. It stops at ``presupuesto``
    evaluations, like the other metaheuristics.
    """

    evaluar: Evaluar
    presupuesto: int = 100
    semilla: int = 7

    def optimizar(
        self, orden_inicial: List[str]
    ) -> Tuple[List[str], float, List[float]]:
        rng = random.Random(self.semilla)
        mejor = list(orden_inicial)
        mejor_puntuacion = self.evaluar(mejor)
        historial = [mejor_puntuacion]
        evaluaciones = 1
        while evaluaciones < self.presupuesto and len(orden_inicial) >= 2:
            candidato = list(orden_inicial)
            rng.shuffle(candidato)
            puntuacion = self.evaluar(candidato)
            evaluaciones += 1
            if puntuacion > mejor_puntuacion:
                mejor, mejor_puntuacion = candidato, puntuacion
            historial.append(mejor_puntuacion)
        return mejor, mejor_puntuacion, historial


@dataclass
class HillClimbing:
    """Hill climbing over POI visit orders, conference metaheuristics.

    Start from the initial order, try swap neighbours, move only to a
    strictly better neighbour, and stop at a local optimum or at
    ``presupuesto`` evaluations. It is the local-search baseline:
    fast and greedy, with no mechanism to escape a local optimum,
    which is exactly what simulated annealing and tabu search add.
    """

    evaluar: Evaluar
    presupuesto: int = 100
    semilla: int = 7

    def optimizar(
        self, orden_inicial: List[str]
    ) -> Tuple[List[str], float, List[float]]:
        rng = random.Random(self.semilla)
        actual = list(orden_inicial)
        puntuacion_actual = self.evaluar(actual)
        historial = [puntuacion_actual]
        evaluaciones = 1
        while evaluaciones < self.presupuesto and len(actual) >= 2:
            i, j = rng.sample(range(len(actual)), 2)
            vecino = list(actual)
            vecino[i], vecino[j] = vecino[j], vecino[i]
            puntuacion = self.evaluar(vecino)
            evaluaciones += 1
            if puntuacion > puntuacion_actual:
                actual, puntuacion_actual = vecino, puntuacion
            historial.append(puntuacion_actual)
        return actual, puntuacion_actual, historial


@dataclass
class SimulatedAnnealing:
    """Simulated annealing over POI visit orders.

    Attributes:
        evaluar: Score of an order, higher is better.
        temperatura_inicial: Starting temperature. It must be on the
            scale of score differences: the planner's score is
            ``interest * 100 - travel cost``, so differences of a few
            tens are common, and 20.0 lets early worse moves through
            with a reasonable probability without accepting everything.
        enfriamiento: Temperature multiplier per iteration (0 < x < 1).
        iteraciones: Number of neighbour orders tried.
        semilla: Seed for reproducibility.
    """

    evaluar: Evaluar
    temperatura_inicial: float = 20.0
    enfriamiento: float = 0.98
    iteraciones: int = 300
    semilla: int = 7

    def _vecino(self, orden: List[str], rng: random.Random) -> List[str]:
        """A neighbour order: usually a swap, sometimes a segment reversal."""
        vecino = list(orden)
        if len(vecino) < 2:
            return vecino
        if rng.random() < 0.3 and len(vecino) >= 3:
            i = rng.randrange(len(vecino) - 1)
            j = rng.randrange(i + 1, len(vecino))
            vecino[i : j + 1] = reversed(vecino[i : j + 1])
        else:
            i, j = rng.sample(range(len(vecino)), 2)
            vecino[i], vecino[j] = vecino[j], vecino[i]
        return vecino

    def optimizar(
        self, orden_inicial: List[str]
    ) -> Tuple[List[str], float, List[float]]:
        """Search for a better order than ``orden_inicial``.

        Returns ``(best_order, best_score, history)`` where ``history``
        is the best score seen after each iteration. The best order ever
        seen is always returned, never the last one tried, so the result
        can never be worse than the starting order.
        """
        rng = random.Random(self.semilla)
        actual = list(orden_inicial)
        puntuacion_actual = self.evaluar(actual)
        mejor = list(actual)
        mejor_puntuacion = puntuacion_actual
        historial: List[float] = []
        temperatura = self.temperatura_inicial
        for _ in range(self.iteraciones):
            vecino = self._vecino(actual, rng)
            puntuacion_vecino = self.evaluar(vecino)
            diferencia = puntuacion_vecino - puntuacion_actual
            if diferencia >= 0 or rng.random() < math.exp(
                diferencia / max(temperatura, 1e-9)
            ):
                actual, puntuacion_actual = vecino, puntuacion_vecino
                if puntuacion_actual > mejor_puntuacion:
                    mejor, mejor_puntuacion = list(actual), puntuacion_actual
            historial.append(mejor_puntuacion)
            temperatura *= self.enfriamiento
        return mejor, mejor_puntuacion, historial


@dataclass
class AlgoritmoGenetico:
    """Genetic algorithm over POI visit orders.

    A population of orders evolves by tournament selection (the better
    of a few random individuals becomes a parent), order crossover
    (a segment from one parent, the rest in the other parent's order, so
    the child is always a valid permutation with no repeated POI) and
    swap mutation. The best individuals survive unchanged (elitism), so
    the population's best score never goes down.

    The budget is counted in evaluations, not generations: evaluation
    results are cached by order, so an order evaluated twice costs one
    unit of budget. The search stops as soon as ``presupuesto``
    distinct orders have been evaluated, which is what makes its budget
    equal to simulated annealing's and tabu search's in an experiment.
    """

    evaluar: Evaluar
    presupuesto: int = 300
    poblacion: int = 20
    elites: int = 2
    probabilidad_mutacion: float = 0.2
    semilla: int = 7

    def _cruce(self, padre: List[str], madre: List[str], rng: random.Random) -> List[str]:
        if len(padre) < 2:
            return list(padre)
        i = rng.randrange(len(padre) - 1)
        j = rng.randrange(i + 1, len(padre))
        segmento = padre[i : j + 1]
        resto = [x for x in madre if x not in segmento]
        return resto[:i] + segmento + resto[i:]

    def _mutar(self, orden: List[str], rng: random.Random) -> List[str]:
        if len(orden) >= 2 and rng.random() < self.probabilidad_mutacion:
            orden = list(orden)
            i, j = rng.sample(range(len(orden)), 2)
            orden[i], orden[j] = orden[j], orden[i]
        return orden

    def optimizar(
        self, orden_inicial: List[str]
    ) -> Tuple[List[str], float, List[float]]:
        rng = random.Random(self.semilla)
        cache: Dict[Tuple[str, ...], float] = {}

        def puntuar(orden: List[str]) -> float:
            clave = tuple(orden)
            if clave not in cache:
                cache[clave] = self.evaluar(list(orden))
            return cache[clave]

        poblacion: List[List[str]] = [list(orden_inicial)]
        while len(poblacion) < self.poblacion:
            vecino = list(orden_inicial)
            rng.shuffle(vecino)
            poblacion.append(vecino)
        puntuaciones = [puntuar(o) for o in poblacion]
        mejor_idx = max(range(len(poblacion)), key=lambda i: puntuaciones[i])
        mejor = list(poblacion[mejor_idx])
        mejor_puntuacion = puntuaciones[mejor_idx]
        historial = [mejor_puntuacion]

        def torneo() -> List[str]:
            candidatos = rng.sample(range(len(poblacion)), min(3, len(poblacion)))
            ganador = max(candidatos, key=lambda i: puntuaciones[i])
            return list(poblacion[ganador])

        # Defensa: si el presupuesto supera el número de permutaciones
        # posibles (con 5 POI, 5! = 120), el bucle anterior nunca
        # terminaría; en ese caso se detiene al agotarlas.
        max_distintos = 1
        for n in range(2, len(orden_inicial) + 1):
            max_distintos *= n
        while len(cache) < self.presupuesto and len(cache) < max_distintos:
            ordenados = sorted(
                range(len(poblacion)), key=lambda i: -puntuaciones[i]
            )
            nueva = [list(poblacion[i]) for i in ordenados[: self.elites]]
            while len(nueva) < self.poblacion and len(cache) < self.presupuesto:
                hijo = self._cruce(torneo(), torneo(), rng)
                hijo = self._mutar(hijo, rng)
                nueva.append(hijo)
            poblacion = nueva
            puntuaciones = [puntuar(o) for o in poblacion]
            idx = max(range(len(poblacion)), key=lambda i: puntuaciones[i])
            if puntuaciones[idx] > mejor_puntuacion:
                mejor = list(poblacion[idx])
                mejor_puntuacion = puntuaciones[idx]
            historial.append(mejor_puntuacion)
        return mejor, mejor_puntuacion, historial


@dataclass
class BusquedaTabu:
    """Tabu search over POI visit orders.

    At each iteration it samples several neighbour orders (swaps) and
    moves to the best one that is not tabu, unless that move beats the
    best score ever seen (aspiration: a tabu move that improves the
    global best is allowed). A move -- the pair of positions swapped --
    stays tabu for ``tenencia`` iterations, so the search cannot
    immediately undo its last step and bounce between two orders. Like
    the genetic algorithm, it stops at ``presupuesto`` evaluations.
    """

    evaluar: Evaluar
    presupuesto: int = 300
    vecinos_por_iteracion: int = 20
    tenencia: int = 10
    semilla: int = 7

    def optimizar(
        self, orden_inicial: List[str]
    ) -> Tuple[List[str], float, List[float]]:
        rng = random.Random(self.semilla)
        actual = list(orden_inicial)
        puntuacion_actual = self.evaluar(actual)
        mejor = list(actual)
        mejor_puntuacion = puntuacion_actual
        historial = [mejor_puntuacion]
        evaluaciones = 1
        # Tabu entries are (position_a, position_b, iteration_when_free).
        tabu: Dict[Tuple[int, int], int] = {}
        iteracion = 0
        while evaluaciones < self.presupuesto and len(actual) >= 2:
            iteracion += 1
            mejor_vecino = None
            mejor_vecino_puntuacion = float("-inf")
            mejor_movimiento = None
            for _ in range(self.vecinos_por_iteracion):
                if evaluaciones >= self.presupuesto:
                    break
                i, j = rng.sample(range(len(actual)), 2)
                movimiento = (min(i, j), max(i, j))
                vecino = list(actual)
                vecino[i], vecino[j] = vecino[j], vecino[i]
                puntuacion = self.evaluar(vecino)
                evaluaciones += 1
                es_tabu = tabu.get(movimiento, 0) >= iteracion
                aspira = puntuacion > mejor_puntuacion
                if es_tabu and not aspira:
                    continue
                if puntuacion > mejor_vecino_puntuacion:
                    mejor_vecino = vecino
                    mejor_vecino_puntuacion = puntuacion
                    mejor_movimiento = movimiento
            if mejor_vecino is None:
                break
            actual = mejor_vecino
            puntuacion_actual = mejor_vecino_puntuacion
            if mejor_movimiento is not None:
                tabu[mejor_movimiento] = iteracion + self.tenencia
            if puntuacion_actual > mejor_puntuacion:
                mejor = list(actual)
                mejor_puntuacion = puntuacion_actual
            historial.append(mejor_puntuacion)
        return mejor, mejor_puntuacion, historial


@dataclass
class ColoniaHormigas:
    """Ant colony optimisation over POI visit orders, conference swarm.

    Each ant builds an order step by step: from the last POI chosen,
    the next POI is drawn with probability proportional to
    (pheromone on the last->next edge) ** alfa, with no heuristic
    term (beta = 0), because the only quality signal available before
    execution is the order score itself. After each iteration,
    pheromones evaporate by factor (1 - rho) and the best order of
    the iteration deposits pheromone proportional to its score
    (shifted to be positive). This is the conference ACO construction
    rule adapted to permutations: pheromone lives on POI->POI edges,
    not on cells, so a good pair of consecutive POIs is reused.
    """

    evaluar: Evaluar
    presupuesto: int = 100
    hormigas: int = 10
    alfa: float = 1.0
    rho: float = 0.3
    semilla: int = 7

    def optimizar(
        self, orden_inicial: List[str]
    ) -> Tuple[List[str], float, List[float]]:
        rng = random.Random(self.semilla)
        n = len(orden_inicial)
        if n < 2:
            puntuacion = self.evaluar(list(orden_inicial))
            return list(orden_inicial), puntuacion, [puntuacion]
        # Pheromone on directed edges (i -> j), indexed by POI position
        # in orden_inicial (identity is by POI id, not position).
        feromona: Dict[Tuple[str, str], float] = {}
        for a in orden_inicial:
            for b in orden_inicial:
                if a != b:
                    feromona[(a, b)] = 1.0
        mejor = list(orden_inicial)
        mejor_puntuacion = self.evaluar(mejor)
        historial = [mejor_puntuacion]
        evaluaciones = 1
        while evaluaciones < self.presupuesto:
            mejor_iter = None
            mejor_iter_puntuacion = float("-inf")
            for _ in range(self.hormigas):
                if evaluaciones >= self.presupuesto:
                    break
                restante = list(orden_inicial)
                actual_poi = rng.choice(restante)
                orden = [actual_poi]
                restante.remove(actual_poi)
                while restante:
                    pesos = [
                        feromona.get((actual_poi, c), 1.0) ** self.alfa
                        for c in restante
                    ]
                    total = sum(pesos)
                    r = rng.random() * total
                    elegido = restante[-1]
                    for c, w in zip(restante, pesos):
                        r -= w
                        if r <= 0:
                            elegido = c
                            break
                    orden.append(elegido)
                    restante.remove(elegido)
                    actual_poi = elegido
                puntuacion = self.evaluar(orden)
                evaluaciones += 1
                if puntuacion > mejor_iter_puntuacion:
                    mejor_iter, mejor_iter_puntuacion = orden, puntuacion
                if puntuacion > mejor_puntuacion:
                    mejor, mejor_puntuacion = list(orden), puntuacion
            # Evaporation, then reinforcement by the best of the iteration.
            for clave in feromona:
                feromona[clave] *= 1.0 - self.rho
            if mejor_iter is not None:
                refuerzo = max(0.0, mejor_iter_puntuacion) + 1.0
                for a, b in zip(mejor_iter, mejor_iter[1:]):
                    feromona[(a, b)] = feromona.get((a, b), 0.0) + refuerzo
            historial.append(mejor_puntuacion)
        return mejor, mejor_puntuacion, historial
