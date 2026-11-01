from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

Evaluar = Callable[[List[str]], float]


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

        while len(cache) < self.presupuesto:
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
