"""The single metaheuristic of the agent, for now: simulated annealing.

What it searches
-----------------
The order in which to visit the points of interest. With 5 POIs there
are 120 orders; the point of a metaheuristic here is not to beat brute
force on such a small instance, but to have a search that still works
when the POI count grows, and whose behaviour is easy to explain: it
keeps the best order ever seen, it usually moves to a better order, and
it sometimes -- with a probability that falls as the temperature falls --
moves to a worse one, which is how it escapes local optima instead of
getting stuck in the first good-looking order (for example, the "always
take the safe, already-known path" order).

Where the probability in the objective lives
---------------------------------------------
Interest itself comes from the map (``Poi.interest``) and is not random.
The probability is in the *choice*: a neighbour order is accepted
probabilistically, with probability ``exp((new - current) / T)`` when it
is worse. High-interest orders are therefore more likely to survive, but
not guaranteed to, and early on, when the temperature is high, the search
explores widely instead of greedily collapsing onto the highest-interest
POI first. If a future version wants the *reward* itself to be
probabilistic (a POI that only pays off with some probability), that
belongs in the evaluation function, not here: this class only needs a
score, higher is better.

The evaluation function is supplied by the caller (the planner's
``evaluar_orden``): it already accounts for A* leg costs, battery with
recharge detours at stations, and memory with transmit detours, so the
metaheuristic never needs to know about maps, batteries or stations.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, List, Tuple

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
