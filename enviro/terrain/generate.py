import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
from ..config import load_config,get
from .catalogue import terrain, terrain_names
from .features import Poi, Station, place_stations
from .field import TerrainField
from .grid import Cell, cell_id, distance, neighbour_offsets, parse_cell_id, reachable_cells
from .instance import Map, MapParams


MAX_AXIS = get("map").get("max_axis",64) 
MIN_AXIS = get("map").get("min_axis",5)

@dataclass(frozen=True)
class InstanceParams:
    """What varies between instances of the same config.

    Deliberately short: the knobs an experiment sweeps. Terrain costs, station
    presets and the shape of the noise field stay in ``config/default.json``,
    so the family of instances remains explicit and reviewable rather than
    hidden in keyword arguments.

    Attributes:
        width: Grid extent on x.
        height: Grid extent on y.
        depth: Vertical layers.
        block_rate: Probability of a boulder per cell, in [0, 1].
        poi_count: Number of points of interest.
        station_count: Stations to place, 1 or 2. Two is the interesting case,
            because a weak relay covers only part of what the base covers.
        seed: Seed for the whole instance. None means an unseeded map.
        config_path: Alternate configuration file.
    """
    width: int = 12
    height: int = 12
    depth: int = 3
    block_rate: float = 0.06
    poi_count: int = 3
    station_count: int = 2
    seed: Optional[int] = None
    config_path: Optional[Path] = None

    def __post_init__(self) -> None:
        for name in ("width", "height"):
            value = getattr(self, name)
            if not MIN_AXIS <= value <= MAX_AXIS:
                raise ValueError(f"{name} must be in [{MIN_AXIS}, {MAX_AXIS}], got {value}")
        if not 0.0 <= self.block_rate <= 1.0:
            raise ValueError(f"block_rate must be in [0, 1], got {self.block_rate}")
        if self.depth < 0:
            raise ValueError(f"depth must be >= 0, got {self.depth}")
        if self.poi_count < 0:
            raise ValueError(f"poi_count must be >= 0, got {self.poi_count}")
        if self.station_count not in (1, 2):
            raise ValueError(
                f"station_count must be 1 or 2, got {self.station_count}. Three "
                f"stations is a different problem, not a different instance."
            )
        if self.seed is not None and not isinstance(self.seed, int):
            raise ValueError(f"seed must be an int or None, got {type(self.seed).__name__}")

    @classmethod
    def from_config(cls, path: Optional[Path] = None, **overrides) -> "InstanceParams":
        """Take the instance fields from a JSON file, then apply overrides.

        Args:
            path: Alternate config file. Defaults to ``config/default.json``.
            **overrides: Any field of this class, which wins over the file.

        Returns:
            Validated parameters.
        """
        config = load_config(path)
        values: Dict[str, object] = {
            "width": config["map"]["width"],
            "height": config["map"]["height"],
            "depth": config["map"]["depth"],
            "block_rate": config["map"]["block_rate"],
            "poi_count": config["poi"]["count"],
            "station_count": len(config["network"]["stations"]),
            "config_path": path,
        }
        values.update(overrides)
        return cls(**values)  # type: ignore[arg-type]


class MapGenerator:
    """Builds :class:`~enviro.terrain.instance.Map` instances.

    Attributes:
        params: Instance parameters.
        config: The parsed configuration in force.
        field: The terrain field in force, rebuilt by every :meth:`create`.
        map_params: The resolved spec handed to each map.
    """

    def __init__(self, params: Optional[InstanceParams] = None,
                 seed: Optional[int] = None) -> None:
        self.params = params or InstanceParams.from_config()
        if seed is not None:
            self.params = replace(self.params, seed=seed)
        self.config = load_config(self.params.config_path)
        self.rng = random.Random(self.params.seed)
        self.field = self._build_field()
        self.map_params = self._map_params()

    # public API

    def create(self) -> Map:
        """Generate one map.

        The RNG is re-seeded and the field is rebuilt on every call, so
        ``create()`` is idempotent: the same generator hands out the same map
        as many times as needed. The rebuild matters because the field's phase
        offset is the first thing the seed draws; leaving it behind from
        construction time would make the second call a different map.
        """
        self.rng = random.Random(self.params.seed)
        self.field = self._build_field()
        cells = self._place_terrain()
        self._place_boulders(cells)
        stations = self._place_stations(cells)
        pois = self._place_pois(cells)
        return Map(self.map_params, cells, stations, pois)

    def create_from_seed(self, seed: int, **overrides) -> Map:
        """Generate a map for one seed.

        Args:
            seed: Seed to use.
            **overrides: Parameter overrides for this call only.

        Returns:
            A generated map.
        """
        return MapGenerator(replace(self.params, seed=seed, **overrides)).create()

    def batch(self, seeds: Iterable[int], **overrides) -> List[Map]:
        """Generate one map per seed.

        This is what a comparison over instances consumes: a family drawn from
        a single parameter setting, one per seed.

        Args:
            seeds: Seeds to draw.
            **overrides: Parameter overrides applied to every map.

        Returns:
            One map per seed, in order.
        """
        return [self.create_from_seed(seed, **overrides) for seed in seeds]

    def describe(self) -> str:
        """One line naming the family this generator draws from."""
        p = self.params
        return (f"{p.width}x{p.height}x{p.depth} blocks={p.block_rate} "
                f"pois={p.poi_count} stations={p.station_count} seed={p.seed}")

    #  parameters 

    def _build_field(self) -> TerrainField:
        """The terrain field, with this instance's phase offset already drawn."""
        origin = (
            self.rng.uniform(0.0, self.params.width),
            self.rng.uniform(0.0, self.params.height),
        )
        return TerrainField(
            self.params.width,
            self.params.height,
            self.params.depth,
            origin=origin,
            settings=self.config["generation"],
        )

    def _map_params(self) -> MapParams:
        """Project the config and the instance params onto the frozen spec."""
        movement = self.config["movement"]
        poi = self.config["poi"]
        rover = self.config["rover"]
        stations = tuple(
            (str(s["id"]), float(s["radius"]), float(s["signal"]))
            for s in self.config["network"]["stations"][: self.params.station_count]
        )
        return MapParams(
            width=self.params.width,
            height=self.params.height,
            depth=self.params.depth,
            block_rate=self.params.block_rate,
            move_radius=float(movement["radius"]),
            climb_penalty=float(movement["climb_penalty"]),
            poi_count=self.params.poi_count,
            poi_min_visibility=float(poi["min_visibility"]),
            poi_interest_climb_weight=float(poi.get("interest_climb_weight", 0.6)),
            poi_interest_ground_weight=float(poi.get("interest_ground_weight", 0.4)),
            stations=stations,
            battery=float(rover["battery"]),
            memory=float(rover["memory"]),
            survey_height_bonus=float(movement.get("survey_height_bonus", 2.0)),
            seed=self.params.seed,
        )

    # construction 

    def _place_terrain(self) -> Dict[str, Cell]:
        """Terreno disperso en z: solo hay bloques donde hay loma.

        Para cada (x, y), h = height_at(x, y) en [0, depth-1]:
        - z > h: aire, no se crea celda.
        - z == h: superficie transitable (cima plana de la meseta).
        - z < h: interior sólido de la loma, bloqueado. No se puede estar
          en (1,1,1) si la loma llega a (1,1,2): hay que subir por fuera.

        Así el eje z solo crea bloques donde hay lomas y las lomas son
        mesetas de varias celdas planas arriba (ver TerrainField).
        """
        cells: Dict[str, Cell] = {}
        for x in range(self.params.width):
            for y in range(self.params.height):
                h = self.field.height_at(x, y)
                for z in range(self.params.depth):
                    if z > h:
                        continue  # aire
                    id_ = cell_id(x, y, z)
                    cell = Cell(id_, (x, y, z), self.field.terrain_at(x, y, z))
                    if z < h:
                        cell.blocked = True  # interior sólido
                    cells[id_] = cell
        return cells

    def _place_boulders(self, cells: Dict[str, Cell]) -> None:
        """Block surface cells independently with probability ``block_rate``.

        Solo la superficie puede tener boulders. El interior ya está
        bloqueado por ser sólido y el aire no existe como celda.
        """
        for cell in cells.values():
            x, y, z = cell.pos
            if not self.field.is_surface(x, y, z):
                continue
            if not cell.blocked:
                cell.blocked = self.rng.random() < self.params.block_rate

    def _place_stations(self, cells: Dict[str, Cell]) -> Tuple[Station, ...]:
        """Place stations on the surface, as far apart as the map allows."""
        presets = self.map_params.stations
        candidates = self._surface_cells(cells)
        if not candidates:
            raise ValueError(
                "every surface cell is blocked; lower block_rate or enlarge the map"
            )

        centers = [self.rng.choice(candidates).pos]
        if len(presets) > 1:
            farthest = max(candidates, key=lambda c: (distance(c.pos, centers[0]), c.id))
            centers.append(farthest.pos)

        return place_stations(presets, tuple(centers), self.map_params.diagonal)

    def _place_pois(self, cells: Dict[str, Cell]) -> List[Poi]:
        """Place points of interest on reachable, observable, well-spread ground.

        Four rules, all about instance quality rather than realism:

        * **Reachable from the surface.** Nothing interesting is walled off.
        * **Observable.** Some cell next to it has ground clear enough to see
          it from, checked with the true terrain because nothing is surveyed
          yet at generation time.
        * **Interesting.** Costly to reach, rewarding to hold: high ground
          costs climbing but pays back survey radius; expensive terrain costs
          battery to stand on. Each layer contributes its most interesting
          candidate, so the bill differs per point instead of every point
          costing the same trip.
        * **Spread.** One per layer first, so depth has to be descended into,
          and each one placed as far from the others as the map allows. Two
          points of interest a cell apart are one trip, not two.
        """
        threshold = self.map_params.poi_min_visibility
        candidates = self._observable_cells(cells, threshold)
        by_layer: Dict[int, List[str]] = {}
        for id_ in sorted(candidates):
            by_layer.setdefault(parse_cell_id(id_)[2], []).append(id_)

        chosen: List[str] = []
        for layer in sorted(by_layer):
            if len(chosen) >= self.params.poi_count:
                break
            chosen.append(self._best(cells, by_layer[layer], chosen))
        spare = [id_ for ids in by_layer.values() for id_ in ids if id_ not in chosen]
        self.rng.shuffle(spare)
        while spare and len(chosen) < self.params.poi_count:
            pick = self._best_spread(cells, spare, chosen)
            chosen.append(pick)
            spare.remove(pick)

        if len(chosen) < self.params.poi_count:
            raise ValueError(
                f"only {len(chosen)} cells can host an observable point of "
                f"interest but poi_count is {self.params.poi_count}. Lower "
                f"block_rate, enlarge the map, or ask for fewer points."
            )

        pois: List[Poi] = []
        for index, id_ in enumerate(chosen):
            poi = Poi(f"poi_{index}", id_, threshold, self._interest(cells[id_]))
            cells[id_].poi_id = poi.id
            pois.append(poi)
        return pois

    def _interest(self, cell: Cell) -> float:
        """Cost/reward score of a POI candidate, in [0, 1].

        Climbing is both the cost and the reward: higher ground takes more
        work to reach and surveys further once held. Expensive terrain adds
        cost on top. Weights come from the poi config so an experiment can
        move the emphasis without touching the generator.
        """
        p = self.map_params
        total = p.poi_interest_climb_weight + p.poi_interest_ground_weight
        if total <= 0:
            return 0.0
        climb = cell.pos[2] / max(1, p.depth - 1)
        costs = [terrain(name).cost for name in terrain_names()]
        span = max(costs) - min(costs)
        ground = (terrain(cell.true_terrain).cost - min(costs)) / span if span > 0 else 0.0
        return (p.poi_interest_climb_weight * climb + p.poi_interest_ground_weight * ground) / total

    def _best(
        self,
        cells: Dict[str, Cell],
        candidates: Sequence[str],
        chosen: Sequence[str],
    ) -> str:
        """Highest-interest candidate; near-ties broken by spread.

        Candidates within 5% of the best interest count as tied, and the
        farthest of those wins, so a marginally more interesting cell does
        not pull two points of interest next to each other.
        """
        scored = [(self._interest(cells[id_]), id_) for id_ in candidates]
        best = max(score for score, _ in scored)
        pool = [id_ for score, id_ in scored if score >= best * 0.95]
        return self._farthest(cells, pool, chosen)

    def _best_spread(
        self,
        cells: Dict[str, Cell],
        spare: Sequence[str],
        chosen: Sequence[str],
    ) -> str:
        """Fill pick: half interest, half distance from what's placed."""
        interests = {id_: self._interest(cells[id_]) for id_ in spare}
        placed = [parse_cell_id(id_) for id_ in chosen]
        dists = {
            id_: min(distance(parse_cell_id(id_), pos) for pos in placed)
            for id_ in spare
        }
        imax = max(interests.values())
        dmax = max(dists.values())

        def norm(value: float, top: float) -> float:
            return value / top if top > 0 else 0.0

        scored = [
            (0.5 * norm(interests[id_], imax) + 0.5 * norm(dists[id_], dmax), id_)
            for id_ in spare
        ]
        best = max(score for score, _ in scored)
        return self.rng.choice([id_ for score, id_ in scored if score == best])

    def _observable_cells(self, cells: Dict[str, Cell], threshold: float) -> Set[str]:
        """Reachable cells that something can be observed from.

        Reachability comes from the map's own flood fill, so the guarantee is
        computed with the same rule a consumer would use, not a second
        approximation of it.
        """
        offsets = neighbour_offsets(self.map_params.move_radius)
        starts = [c.id for c in self._surface_cells(cells)]
        reachable = reachable_cells(cells, starts, offsets)

        observable: Set[str] = set()
        for id_ in reachable:
            cell = cells[id_]
            if cell.poi_id:
                continue
            x, y, z = cell.pos
            for dx, dy, dz in offsets:
                vantage = cells.get(cell_id(x + dx, y + dy, z + dz))
                if vantage is None or not vantage.traversable:
                    continue
                if terrain(vantage.true_terrain).visibility >= threshold:
                    observable.add(id_)
                    break
        return observable

    def _farthest(
        self,
        cells: Dict[str, Cell],
        candidates: Sequence[str],
        chosen: Sequence[str],
        exclude: Optional[Sequence[str]] = None,
    ) -> str:
        """Candidate furthest from the points of interest already placed.

        Ties go to the RNG, so two seeds do not both get the same corner. With
        nothing placed yet the draw is uniform.
        """
        pool = [id_ for id_ in candidates if not exclude or id_ not in exclude]
        if not pool:
            raise ValueError("no candidate left to place a point of interest on")
        if not chosen:
            return self.rng.choice(pool)
        placed = [parse_cell_id(id_) for id_ in chosen]
        scored = [
            (min(distance(parse_cell_id(id_), pos) for pos in placed), id_)
            for id_ in pool
        ]
        best = max(score for score, _ in scored)
        return self.rng.choice([id_ for score, id_ in scored if score == best])

    def _surface_cells(self, cells: Dict[str, Cell]) -> List[Cell]:
        """Celdas transitables en la superficie real (cima de cada columna).

        Ya no es z=0: es z == height_at(x, y). En orden estable para que
        la generación sea reproducible.
        """
        out: List[Cell] = []
        for x in range(self.params.width):
            for y in range(self.params.height):
                h = self.field.height_at(x, y)
                c = cells.get(cell_id(x, y, h))
                if c is not None and c.traversable:
                    out.append(c)
        return out

    def __repr__(self) -> str:
        return f"MapGenerator(seed={self.params.seed})"


def generate(seed: int, **overrides) -> Map:
    """Generate one map for a seed.

    Example:
        >>> a = generate(42)
        >>> b = generate(42)
        >>> a.summary() == b.summary()
        True
    """
    return MapGenerator(InstanceParams.from_config(seed=seed, **overrides)).create()
