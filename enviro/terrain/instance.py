from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple
from .catalogue import UNKNOWN, terrain, terrain_names
from .features import Poi, Station
from .grid import Cell, Coord, cell_id, distance, movement_offsets, neighbour_offsets, parse_cell_id, reachable_cells


@dataclass(frozen=True)
class MapParams:
    """Everything about one instance that is not its terrain.

    Frozen, so an instance cannot be quietly re-tuned halfway through being
    read. Terrain costs and the noise settings are not here: those come from
    ``config/default.json`` and belong to the catalogue and the field.

    Attributes:
        width: Grid extent on x.
        height: Grid extent on y.
        depth: Vertical layers.
        block_rate: Probability of a boulder per cell, in [0, 1].
        move_radius: Reach of one step, in grid units.
        climb_penalty: Extra cost per level gained, on top of terrain cost.
        survey_height_bonus: Extra survey radius at max height. At z=0 the
            survey radius is move_radius; at z=depth-1 it is
            move_radius + survey_height_bonus. The higher the ground, the more
            cells are revealed as the rover advances.
        poi_count: Number of points of interest.
        poi_min_visibility: Visibility the observer's ground needs.
        poi_interest_climb_weight: Weight of height (costly to climb,
            rewarding to survey from) in the POI interest score.
        poi_interest_ground_weight: Weight of terrain cost in the POI
            interest score.
        move_allow_diagonal: When false, steps are limited to the 4 horizontal
            neighbours (each may still gain/lose one level, so hills stay
            climbable); plan-view diagonals are excluded.
        stations: ``(id, radius, signal)`` per station.
        battery: Declared energy budget. Carried, not spent here.
        memory: Declared sample-buffer budget. Carried, not spent here.
        seed: Seed the instance came from.
    """
    width: int
    height: int
    depth: int
    block_rate: float
    move_radius: float
    climb_penalty: float
    poi_count: int
    poi_min_visibility: float
    stations: Tuple[Tuple[str, float, float], ...]
    battery: float
    memory: float
    survey_height_bonus: float = 2.0
    poi_interest_climb_weight: float = 0.6
    poi_interest_ground_weight: float = 0.4
    move_allow_diagonal: bool = True
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        for name in ("width", "height", "depth"):
            value = getattr(self, name)
            if value < 1:
                raise ValueError(f"{name} must be >= 1, got {value}")
        if not 0.0 <= self.block_rate <= 1.0:
            raise ValueError(f"block_rate must be in [0, 1], got {self.block_rate}")
        if self.move_radius <= 0:
            raise ValueError(f"move_radius must be > 0, got {self.move_radius}")
        if self.climb_penalty < 0:
            raise ValueError(f"climb_penalty must be >= 0, got {self.climb_penalty}")
        if self.survey_height_bonus < 0:
            raise ValueError(f"survey_height_bonus must be >= 0, got {self.survey_height_bonus}")
        if self.poi_count < 0:
            raise ValueError(f"poi_count must be >= 0, got {self.poi_count}")
        if not 0.0 <= self.poi_min_visibility <= 1.0:
            raise ValueError(
                f"poi_min_visibility must be in [0, 1], got {self.poi_min_visibility}"
            )
        if self.poi_interest_climb_weight < 0:
            raise ValueError(
                f"poi_interest_climb_weight must be >= 0, got {self.poi_interest_climb_weight}"
            )
        if self.poi_interest_ground_weight < 0:
            raise ValueError(
                f"poi_interest_ground_weight must be >= 0, got {self.poi_interest_ground_weight}"
            )
        if not self.stations:
            raise ValueError("at least one station is required")
        for name, radius, signal in self.stations:
            if radius < 0:
                raise ValueError(f"station '{name}': radius must be >= 0, got {radius}")
            # radius 0 = point station: the rover must stand on its cell.
            if not 0.0 < signal <= 1.0:
                raise ValueError(f"station '{name}': signal must be in (0, 1], got {signal}")
        if self.battery <= 0:
            raise ValueError(f"battery must be > 0, got {self.battery}")
        if self.memory <= 0:
            raise ValueError(f"memory must be > 0, got {self.memory}")

    @property
    def cell_count(self) -> int:
        """Cells in the grid."""
        return self.width * self.height * self.depth

    @property
    def diagonal(self) -> float:
        """Largest distance between two cells of this map."""
        return distance(
            (0, 0, 0),
            (self.width - 1, self.height - 1, self.depth - 1),
        )

    def __repr__(self) -> str:
        return (f"MapParams({self.width}x{self.height}x{self.depth}, "
                f"seed={self.seed}, pois={self.poi_count}, "
                f"stations={len(self.stations)})")


class Map:
    """A generated terrain instance.

    Attributes:
        params: Resolved parameters.
        cells: Every cell, by id.
        stations: Ground stations, in placement order.
        pois: Points of interest, by id.
    """

    def __init__(
        self,
        params: MapParams,
        cells: Dict[str, Cell],
        stations: Sequence[Station],
        pois: Sequence[Poi],
    ) -> None:
        self.params = params
        self.cells = cells
        self.stations = tuple(stations)
        self.pois = {poi.id: poi for poi in pois}
        self._offsets = movement_offsets(params.move_radius, params.move_allow_diagonal)

    #  geometry 

    def cell(self, id_: str) -> Optional[Cell]:
        """Cell with that id, or None if off the grid."""
        return self.cells.get(id_)

    def cell_at(self, pos: Coord) -> Optional[Cell]:
        """Cell at a position, or None if off the grid."""
        return self.cells.get(cell_id(*pos))

    def neighbours(self, id_: str) -> List[str]:
        """Ids of the cells one step away, in reach order."""
        cell = self.cell(id_)
        if cell is None:
            return []
        return [
            other.id
            for other in self._around(cell)
        ]

    def _around(self, cell: Cell) -> List[Cell]:
        """Cells within movement range of ``cell``."""
        x, y, z = cell.pos
        return [
            other
            for other in (
                self.cells.get(cell_id(x + dx, y + dy, z + dz))
                for dx, dy, dz in self._offsets
            )
            if other is not None
        ]

    def reachable_from(self, *ids: str) -> set:
        """Cells reachable from any of ``ids`` without crossing a boulder."""
        return reachable_cells(self.cells, list(ids), self._offsets)

    def reachable_from_surface(self) -> set:
        """Cells reachable from any traversable surface cell.

        The surface is now the real top of each column (z == height), not z=0.
        It is the "can be reached" reference: objectives are placed inside this
        set.
        """
        return self.reachable_from(*self.surface_ids())

    def surface_ids(self) -> List[str]:
        """Ids of traversable cells on the real top of each column.

        A cell is surface if it is traversable and there is no cell (traversable
        or solid) above it on the same (x, y). Air does not exist as a cell, so
        looking at z+1 is enough.
        """
        ids: List[str] = []
        for cell in self.cells.values():
            if not cell.traversable:
                continue
            x, y, z = cell.pos
            above = self.cells.get(cell_id(x, y, z + 1))
            if above is None:
                ids.append(cell.id)
        return sorted(ids)

    #  cost model 

    def cost_between(self, from_id: str, to_id: str) -> float:
        """Cost of one step between two cells.

        ::

            cost = distance * terrain_cost(destination) * (1 + climb_penalty * levels_gained)

        The destination sets the price: ground is paid for when it is entered,
        not when it is left. Climbing carries a premium on top because the
        rover is doing work against gravity; descending carries none, because
        it is not work. An unsurveyed destination is priced at the catalogue
        mean, so the figure is the expected cost of an unknown cell rather than
        a guess in either direction.

        Raises:
            KeyError: Either id is not on the map.
        """
        source = self.cell(from_id)
        target = self.cell(to_id)
        if source is None or target is None:
            raise KeyError(f"unknown cell in step {from_id!r} -> {to_id!r}")
        span = distance(source.pos, target.pos)
        climb = max(0, target.pos[2] - source.pos[2])
        return span * target.cost * (1.0 + self.params.climb_penalty * climb)

    def layer_cost(self, terrain_name: str, levels: int = 0) -> float:
        """Step cost onto a named terrain, gaining ``levels`` on the way.

        A closed form of :meth:`cost_between` for comparing terrains without
        walking the map. Not all combinations correspond to a real step; it is
        a pricing table, not a route.
        """
        base = terrain(terrain_name).cost
        return base * (1.0 + self.params.climb_penalty * max(0, levels))

    #  knowledge 

    def survey_radius_at(self, cell: Cell) -> float:
        """Discovery radius from a cell.

        Two factors, both about the observer:

        * **Height:** at z=0 it is move_radius; at the top (z=depth-1) it is
          move_radius + survey_height_bonus. The higher the ground, the further
          it sees.
        * **Visibility of the ground itself:** the radius is multiplied by the
          visibility of the ground being stood on (the same number that decides
          whether a POI is legible). On open flat ground the whole radius is
          used; in a crevasse you see little even from up high: the best
          vantage point is useless if the ground does not let you see through.

        It uses the true terrain: the observer knows what it is standing on.
        """
        if self.params.depth <= 1:
            base = self.params.move_radius
        else:
            frac = cell.pos[2] / max(1, self.params.depth - 1)
            base = self.params.move_radius + self.params.survey_height_bonus * frac
        return base * terrain(cell.true_terrain).visibility

    def _around_survey(self, cell: Cell) -> List[Cell]:
        """Cells within the discovery radius (which depends on the height)."""
        radius = self.survey_radius_at(cell)
        offsets = neighbour_offsets(radius)
        x, y, z = cell.pos
        return [
            other
            for other in (
                self.cells.get(cell_id(x + dx, y + dy, z + dz))
                for dx, dy, dz in offsets
            )
            if other is not None
        ]

    def survey(self, id_: str) -> List[str]:
        """Reveal the terrain around a cell and report what was revealed.

        The radius grows with the height and with the visibility of the ground
        itself: the higher the ground, the more cells are revealed as the rover
        advances; on open ground the whole radius is used, in crevasses you see
        little even from up high.

        Args:
            id_: Cell to observe from. Unknown ids reveal nothing.

        Returns:
            Ids of the cells whose terrain changed from unsurveyed to known.
        """
        cell = self.cell(id_)
        if cell is None:
            return []
        revealed = []
        for other in [cell, *self._around_survey(cell)]:
            if not other.surveyed:
                other.survey()
                revealed.append(other.id)
        return revealed

    def unknown_ratio(self) -> float:
        """Fraction of the map still unsurveyed."""
        if not self.cells:
            return 0.0
        return sum(1 for c in self.cells.values() if not c.surveyed) / len(self.cells)

    #  features 

    def station_at(self, pos: Coord) -> Optional[Station]:
        """The station covering a position, or None."""
        for station in self.stations:
            if station.covers(pos):
                return station
        return None

    def is_linked(self, pos: Coord) -> bool:
        """Whether any station covers a position."""
        return self.station_at(pos) is not None

    def coverage_ratio(self) -> float:
        """Fraction of the map inside station coverage."""
        if not self.cells:
            return 0.0
        return sum(
            1 for cell in self.cells.values() if self.is_linked(cell.pos)
        ) / len(self.cells)

    def observability(self, poi: Poi, from_id: str) -> bool:
        """Whether a point of interest is legible from a given cell.

        Two conditions, both about ground rather than distance: the observer has
        to be within one step of it, and the observer's own ground has to be
        clear enough to see through. That second half is the reason terrain
        carries a visibility number at all.
        """
        here = self.cell(from_id)
        target = self.cell(poi.cell_id)
        if here is None or target is None:
            return False
        threshold = poi.min_visibility
        if distance(here.pos, target.pos) > self.params.move_radius:
            return False
        return terrain(here.true_terrain).visibility >= threshold

    def vantage_points(self, poi: Poi) -> List[str]:
        """Cells this point of interest can be observed from.

        Every cell within one step's reach, not just step neighbours:
        observation is about distance and clear ground, not about how the
        rover walks.
        """
        x, y, z = parse_cell_id(poi.cell_id)
        ids = [poi.cell_id]
        for dx, dy, dz in neighbour_offsets(self.params.move_radius):
            cell = self.cells.get(cell_id(x + dx, y + dy, z + dz))
            if cell is not None:
                ids.append(cell.id)
        return [
            id_ for id_ in ids
            if self.cell(id_).traversable and self.observability(poi, id_)
        ]

    # statistics

    def terrain_distribution(self) -> Dict[str, int]:
        """Cell count per terrain, from the true map."""
        counts: Dict[str, int] = {}
        for cell in self.cells.values():
            counts[cell.true_terrain] = counts.get(cell.true_terrain, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))

    def layer_distribution(self) -> List[Dict[str, int]]:
        """Terrain counts per layer, top layer first."""
        return [
            {
                name: sum(
                    1 for cell in self.cells.values()
                    if cell.pos[2] == z and cell.true_terrain == name
                )
                for name in terrain_names()
            }
            for z in range(self.params.depth)
        ]

    def blocked_ratio(self) -> float:
        """Fraction of the map blocked by boulders."""
        if not self.cells:
            return 0.0
        return sum(1 for c in self.cells.values() if c.blocked) / len(self.cells)

    # reporting 

    def render(self) -> str:
        """Text map, one block per layer, plus a legend.

        Unsurveyed ground shows as ``?``, which is also what it costs: the
        catalogue mean. Rendering a guess as a fact would be the one thing a
        diagnostic map must never do.
        """
        ordered = sorted(terrain_names(), key=lambda n: terrain(n).cost)
        legend = "  ".join(f"{terrain(n).glyph} {n} {terrain(n).cost:.1f}" for n in ordered)
        lines = [
            f"legend: {legend}  {terrain(UNKNOWN).glyph} unsurveyed"
            f"  X boulder  O point of interest  A station",
            f"grid: {self.params.width} x {self.params.height} x {self.params.depth}"
            f"   seed: {self.params.seed}",
        ]
        for z in range(self.params.depth):
            lines.append("")
            lines.append(f"--- layer z{z:02d} ---")
            for y in range(self.params.height):
                lines.append("".join(
                    self._glyph(self.cells.get(cell_id(x, y, z)))
                    for x in range(self.params.width)
                ))
        lines.append(f"    x -> 0..{self.params.width - 1},"
                     f" y -> 0..{self.params.height - 1},"
                     f" z -> 0..{self.params.depth - 1}")
        return "\n".join(lines)

    def _glyph(self, cell: Optional[Cell]) -> str:
        """Single character for a cell, following mark precedence."""
        if cell is None:
            return " "
        if cell.poi_id:
            return "O"
        if any(station.center == cell.pos for station in self.stations):
            return "A"
        if cell.blocked:
            return "X"
        return terrain(cell.terrain).glyph

    def summary(self) -> str:
        """One-screen description of the instance."""
        p = self.params
        mix = ", ".join(f"{name} {count}" for name, count in self.terrain_distribution().items())
        stations = ", ".join(
            f"{s.id}@{s.center} r={s.effective_radius:.1f}" for s in self.stations
        )
        pois = ", ".join(f"{poi.id}@{poi.cell_id}" for poi in self.pois.values())
        return "\n".join([
            f"seed={p.seed}  grid={p.width}x{p.height}x{p.depth}  cells={len(self.cells)}",
            f"terrain: {mix}",
            f"boulders: {self.blocked_ratio():.1%}   reachable from surface:"
            f" {len(self.reachable_from_surface()) / len(self.cells):.1%}"
            f"   station coverage: {self.coverage_ratio():.1%}",
            f"stations: {stations}",
            f"points of interest ({len(self.pois)}): {pois}",
            f"declared budgets: battery {p.battery:.0f}, memory {p.memory:.0f}"
            f"   (carried by the map, not spent by it)",
            f"unsurveyed: {self.unknown_ratio():.0%}",
        ])

    def __repr__(self) -> str:
        p = self.params
        return (f"Map({p.width}x{p.height}x{p.depth}, seed={p.seed}, "
                f"cells={len(self.cells)}, pois={len(self.pois)}, "
                f"stations={len(self.stations)})")
