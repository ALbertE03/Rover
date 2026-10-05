from dataclasses import dataclass
from typing import Tuple
from .grid import Coord, distance


@dataclass(frozen=True)
class Station:
    """A ground station and the area it covers.

    Coverage is a sphere, which is what makes depth matter to the network: a
    station that blankets the surface leaves the lower layers uncovered, and
    the gap is a property of the terrain rather than an accident.

    Range shrinks with signal quality::

        effective_radius = radius * signal

    Attributes:
        id: Station name.
        center: Antenna position.
        radius: Nominal range in grid units. 0 means a point station: the
            rover must stand on its cell to link.
        signal: Link quality in (0, 1].
    """
    id: str
    center: Coord
    radius: float
    signal: float

    @property
    def effective_radius(self) -> float:
        """Range actually usable at this signal quality."""
        return self.radius * self.signal

    def covers(self, pos: Coord) -> bool:
        """Whether the station reaches ``pos``."""
        return distance(self.center, pos) <= self.effective_radius

    def __repr__(self) -> str:
        return f"Station({self.id}, center={self.center}, r={self.effective_radius:.1f})"


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

    def __repr__(self) -> str:
        return f"Poi({self.id} @ {self.cell_id})"


def place_stations(
    presets: Tuple[Tuple[str, float, float], ...],
    centers: Tuple[Coord, ...],
    max_radius: float,
) -> Tuple[Station, ...]:
    """Build stations from presets, capping each range to the world size.

    A radius wider than the map is not a stronger network, it is a number that
    has stopped meaning anything: every cell is covered either way, so coverage
    can no longer tell two topologies apart.

    Args:
        presets: ``(id, radius, signal)`` per station, in placement order.
        centers: Antenna positions, one per preset.
        max_radius: Largest distance between two cells in this map.

    Returns:
        One station per preset.
    """
    return tuple(
        Station(name, center, min(radius, max_radius), signal)
        for (name, radius, signal), center in zip(presets, centers)
    )
