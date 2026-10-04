from dataclasses import dataclass
from math import ceil
from typing import Dict, Optional, Sequence, Tuple
from .catalogue import UNKNOWN, terrain

Coord = Tuple[int, int, int]


def cell_id(x: int, y: int, z: int) -> str:
    """Deterministic id for a cell, e.g. ``"z01_y04_x09"``."""
    return f"z{z:02d}_y{y:02d}_x{x:02d}"


def parse_cell_id(value: str) -> Coord:
    """Recover the position from a cell id.

    Raises:
        ValueError: The id is not in ``cell_id`` format.
    """
    try:
        z, y, x = value.split("_")
        return int(x[1:]), int(y[1:]), int(z[1:])
    except (ValueError, AttributeError):
        raise ValueError(
            f"Malformed cell id {value!r}, expected format 'z00_y00_x00'"
        ) from None


def distance(a: Coord, b: Coord) -> float:
    """Euclidean distance between two cells."""
    return sum((p - q) ** 2 for p, q in zip(a, b)) ** 0.5


def neighbour_offsets(radius: float) -> Tuple[Coord, ...]:
    """Cell offsets within ``radius`` of the origin, excluding the origin.

    The search cube grows with the radius (``ceil(radius)`` per axis) while
    the euclidean filter keeps the shape spherical, so a larger radius really
    reaches further. At radius 1.0 this is the six axis-aligned neighbours; at
    1.8 the diagonals join in, which is the single knob that changes how
    connected the map feels. Past ``sqrt(3)`` the cube keeps growing, which is
    what lets the survey radius grow with height.
    """
    if radius <= 0:
        raise ValueError(f"movement radius must be > 0, got {radius}")
    bound = ceil(radius)
    offsets = []
    for dx in range(-bound, bound + 1):
        for dy in range(-bound, bound + 1):
            for dz in range(-bound, bound + 1):
                offset = (dx, dy, dz)
                if offset != (0, 0, 0) and distance(offset, (0, 0, 0)) <= radius:
                    offsets.append(offset)
    return tuple(sorted(offsets))


@dataclass
class Cell:
    """One position on the map.

    Attributes:
        id: Cell id.
        pos: ``(x, y, z)``.
        true_terrain: What is really there. Written by the generator, read
            only when the caller surveys the cell.
        terrain: What has been revealed so far. ``UNKNOWN`` until then.
        blocked: Whether a boulder makes the cell impassable. Visible from
            anywhere: obstacles are large, terrain roughness under the wheels
            is not.
        poi_id: Point of interest standing here, if any.
    """
    id: str
    pos: Coord
    true_terrain: str
    terrain: str = UNKNOWN
    blocked: bool = False
    poi_id: Optional[str] = None

    @property
    def surveyed(self) -> bool:
        """Whether the terrain has been revealed."""
        return self.terrain != UNKNOWN

    @property
    def traversable(self) -> bool:
        """Whether a boulder blocks the cell."""
        return not self.blocked

    @property
    def cost(self) -> float:
        """Cost per grid unit. The catalogue mean while unsurveyed."""
        return terrain(self.terrain).cost

    @property
    def visibility(self) -> float:
        """Survey quality from this ground. Zero while unsurveyed."""
        return terrain(self.terrain).visibility

    def survey(self) -> None:
        """Reveal the true terrain."""
        self.terrain = self.true_terrain

    def __repr__(self) -> str:
        state = "block" if self.blocked else self.terrain
        return f"Cell({self.id}, {state})"


def reachable_cells(
    cells: Dict[str, Cell],
    starts: Sequence[str],
    offsets: Sequence[Coord],
) -> set:
    """Cells reachable from any of ``starts`` without crossing a boulder.

    Breadth first over the movement neighbourhood. Boulders are the only thing
    that separates the map into pieces, so this doubles as the connectivity
    check the generator uses to keep an instance coherent.

    Args:
        cells: The map, by id.
        starts: Origin cell ids. Ones that do not exist are ignored.
        offsets: Neighbourhood from :func:`neighbour_offsets`.

    Returns:
        Ids of every reachable cell, including the origins.
    """
    seen = {cid for cid in starts if cid in cells}
    frontier = list(seen)
    while frontier:
        x, y, z = parse_cell_id(frontier.pop())
        for dx, dy, dz in offsets:
            other = cells.get(cell_id(x + dx, y + dy, z + dz))
            if other is None or other.id in seen or not other.traversable:
                continue
            seen.add(other.id)
            frontier.append(other.id)
    return seen
