from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple
from .features import Poi, Station
from .grid import Cell, distance, movement_offsets

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
    def diagonal(self) -> float:
        """Largest distance between two cells of this map."""
        return distance(
            (0, 0, 0),
            (self.width - 1, self.height - 1, self.depth - 1),
        )

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

    #  cost model 

    #  knowledge 

    #  features 

    # statistics

    # reporting 

