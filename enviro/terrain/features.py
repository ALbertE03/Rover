from dataclasses import dataclass
from typing import Tuple
from .grid import Coord

@dataclass(frozen=True)
class Station:
    """A ground station: a single cell.

    A station has no range and no signal quality: the rover must stand
    exactly on its cell to link, transmit or recharge.
    """
    id: str
    center: Coord

@dataclass(frozen=True)
class Poi:
    """A point of interest: a scientifically interesting place on the map.

    It is terrain, not a task. Nothing here schedules it or rewards visiting
    it; the generator only guarantees that the ground around it is good enough
    to observe it from, which is the property that makes the visibility
    numbers on terrain mean anything.

    Attributes:
        id: Objective name.
        cell_id: Where it sits.
        min_visibility: Survey quality the observer's own ground needs before
            the point is legible from there.
        interest: Cost/reward score in [0, 1] assigned at generation: costly
            to reach (high ground, expensive terrain), rewarding to hold
            (high ground surveys further). Two points with the same score are
            not the same trip.
    """
    id: str
    cell_id: str
    min_visibility: float = 0.0
    interest: float = 0.0

def place_stations(
    presets: Tuple[str, ...],
    centers: Tuple[Coord, ...],
) -> Tuple[Station, ...]:
    """Build stations from ids and centers, one station per preset."""
    return tuple(Station(name, center) for name, center in zip(presets, centers))
