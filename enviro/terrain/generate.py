import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from ..config import get, resolve_config
from .catalogue import TERRAIN, build_registry, terrain, terrain_names
from .features import Poi, Station, place_stations
from .field import TerrainField
from .grid import Cell, cell_id, distance, movement_offsets, neighbour_offsets, parse_cell_id, reachable_cells
from .instance import Map, MapParams

MAX_AXIS = get("map").get("max_axis",64) 
MIN_AXIS = get("map").get("min_axis",5)

@dataclass(frozen=True)
class InstanceParams:
    """What varies between instances of the same config.

    Deliberately short: the knobs an experiment sweeps. Terrain costs, station
    presets and the shape of the noise field stay in the configuration in
    force, so the family of instances remains explicit and reviewable rather
    than hidden in keyword arguments.

    Attributes:
        width: Grid extent on x.
        height: Grid extent on y.
        depth: Vertical layers.
        block_rate: Probability of a boulder per cell, in [0, 1].
        poi_count: Number of points of interest.
        station_count: Stations to place (>= 1). They spread by farthest-point
            fill: first random, each next as far as possible from the placed
            ones, so extra bases actually cover new ground. Past the
            configured presets, the last preset is repeated.
        seed: Seed for the whole instance. None means an unseeded map: the
            generator draws a random seed at construction and records it.
        config_path: Alternate configuration file.
        config: Partial configuration dict from the consumer. It overrides
            the default configuration, and the file at ``config_path`` when
            both are given: nested dicts merge, lists and scalars replace.
            When absent, the default configuration (or the file) is used
            as-is. The dict is copied, never referenced.
    """
    width: int = 12
    height: int = 12
    depth: int = 3
    block_rate: float = 0.06
    poi_count: int = 3
    station_count: int = 2
    seed: Optional[int] = None
    config_path: Optional[Path] = None
    config: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if self.config_path is None and self.config is None:
            min_axis, max_axis = MIN_AXIS, MAX_AXIS
        else:
            # Axis limits come from the configuration in force, so a
            # consumer override (or file) that raises max_axis is honoured
            # instead of silently keeping the default limits.
            map_section = resolve_config(self.config_path, self.config).get("map", {})
            min_axis = map_section.get("min_axis", MIN_AXIS)
            max_axis = map_section.get("max_axis", MAX_AXIS)
        for name in ("width", "height"):
            value = getattr(self, name)
            if not min_axis <= value <= max_axis:
                raise ValueError(f"{name} must be in [{min_axis}, {max_axis}], got {value}")
        if not 0.0 <= self.block_rate <= 1.0:
            raise ValueError(f"block_rate must be in [0, 1], got {self.block_rate}")
        if self.depth < 0:
            raise ValueError(f"depth must be >= 0, got {self.depth}")
        if self.poi_count < 0:
            raise ValueError(f"poi_count must be >= 0, got {self.poi_count}")
        if self.station_count < 1:
            raise ValueError(
                f"station_count must be >= 1, got {self.station_count}."
            )
        if self.seed is not None and not isinstance(self.seed, int):
            raise ValueError(f"seed must be an int or None, got {type(self.seed).__name__}")

    @classmethod
    def from_config(cls, path: Optional[Path] = None, **overrides: Any) -> "InstanceParams":
        """Take the instance fields from the configuration in force, then apply overrides.

        The configuration in force is the default, overridden by the file at
        ``path`` (if given), overridden by the ``config`` dict in
        ``overrides`` (if given). Either source may be partial.

        Args:
            path: Alternate config file. Defaults to ``config/default.json``.
            **overrides: Any field of this class, which wins over the
                configuration in force. ``config`` here is a partial
                configuration dict, not a file.

        Returns:
            Validated parameters.
        """
        config = resolve_config(path, overrides.get("config"))
        values: Dict[str, object] = {
            "width": config["map"]["width"],
            "height": config["map"]["height"],
            "depth": config["map"]["depth"],
            "block_rate": config["map"]["block_rate"],
            "poi_count": config["poi"]["count"],
            "station_count": len(config["network"]["stations"]),
            "config_path": path,
            "config": overrides.get("config"),
        }
        values.update(overrides)
        return cls(**values)  # type: ignore[arg-type]

class MapGenerator:
    """Builds :class:`~enviro.terrain.instance.Map` instances.

    The only way to obtain parameters is
    :meth:`InstanceParams.from_config`: there is no default, no seed
    shortcut and no top-level ``generate`` helper. A map is always
    ``MapGenerator(InstanceParams.from_config(...)).create()``.

    Attributes:
        params: Instance parameters, from ``InstanceParams.from_config``.
        config: The parsed configuration in force: the default, overridden
            by the file at ``params.config_path`` (if any), overridden by
            the ``params.config`` dict (if any).
        terrain_registry: The terrain catalogue from ``config``.
        field: The terrain field in force, rebuilt by every :meth:`create`.
        map_params: The resolved spec handed to each map.
    """

    def __init__(self, params: InstanceParams) -> None:
        self.params = params
        if self.params.seed is None:
            # Unseeded map: draw a concrete seed so every downstream draw
            # (biome centers, noise parameters, placement) has something
            # deterministic to work with. The drawn seed stays on params.
            self.params = replace(self.params, seed=random.randint(0, 2**32 - 1))
        self.config = resolve_config(self.params.config_path, self.params.config)
        # The terrain catalogue in force: the config's own, not the default
        # one built at import time, so an alternate config's costs and
        # visibilities actually drive interest and observability.
        self.terrain_registry = (
            build_registry(self.config["terrain"])
            if "terrain" in self.config
            else TERRAIN
        )
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
        self._place_lava_pools(cells)
        stations = self._place_stations(cells)
        pois = self._place_pois(cells, stations)
        return Map(self.map_params, cells, stations, pois)

    #  parameters 

    def _build_field(self) -> TerrainField:
        """The terrain field, with this instance's phase offset already drawn."""
        origin = (
            self.rng.uniform(0.0, self.params.width),
            self.rng.uniform(0.0, self.params.height),
        )
        settings = dict(self.config["generation"])
        settings["seed"] = self.params.seed
        return TerrainField(
            self.params.width,
            self.params.height,
            self.params.depth,
            origin=origin,
            settings=settings,
            terrain_registry=self.terrain_registry,
        )

    def _map_params(self) -> MapParams:
        """Project the config and the instance params onto the frozen spec."""
        movement = self.config["movement"]
        poi = self.config["poi"]
        rover = self.config["rover"]
        presets = list(self.config["network"]["stations"])
        if presets:
            # More stations than presets: repeat the last one (the relay),
            # so extra stations extend the network instead of silently
            # disappearing into the slice.
            while len(presets) < self.params.station_count:
                presets.append(presets[-1])
        stations = tuple(
            (str(s["id"]), float(s["radius"]), float(s["signal"]))
            for s in presets[: self.params.station_count]
        )
        return MapParams(
            width=self.params.width,
            height=self.params.height,
            depth=self.params.depth,
            block_rate=self.params.block_rate,
            move_radius=float(movement["radius"]),
            climb_penalty=float(movement["climb_penalty"]),
            move_allow_diagonal=bool(movement.get("allow_diagonal", True)),
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
        """Terrain scattered along z: there are only blocks where there is a hill.

        For each (x, y), h = height_at(x, y) in [0, depth-1]:
        - z > h: air, no cell is created.
        - z == h: traversable surface (the flat top of the plateau).
        - z < h: solid interior of the hill, blocked. You cannot stand in
          (1,1,1) if the hill reaches (1,1,2): you have to climb up from outside.

        So the z axis only creates blocks where there are hills, and the hills
        are plateaus several flat cells deep on top (see TerrainField).
        """
        cells: Dict[str, Cell] = {}
        for x in range(self.params.width):
            for y in range(self.params.height):
                h = self.field.height_at(x, y)
                for z in range(self.params.depth):
                    if z > h:
                        continue  # air
                    id_ = cell_id(x, y, z)
                    cell = Cell(id_, (x, y, z), self.field.terrain_at(x, y, z))
                    if z < h:
                        cell.blocked = True  # solid interior
                    cells[id_] = cell
        return cells

    def _place_boulders(self, cells: Dict[str, Cell]) -> None:
        """Block surface cells independently with probability ``block_rate``.

        Only the surface can carry boulders. The interior is already blocked
        for being solid, and air does not exist as a cell.
        """
        for cell in cells.values():
            x, y, z = cell.pos
            if not self.field.is_surface(x, y, z):
                continue
            cell.blocked = self.rng.random() < self.params.block_rate

    def _place_lava_pools(self, cells: Dict[str, Cell]) -> None:
        """Flood circular pools with impassable lava.

        Pools are blobs on the surface; every lava cell is blocked so the
        rover can never step in. Runs after boulders so lava overwrites.
        """
        n_pools = int(self.config["generation"].get("lava_pools", 0))
        rmin, rmax = self.config["generation"].get("lava_pool_radius", [2, 4])
        for _ in range(n_pools):
            cx = self.rng.uniform(0, self.params.width)
            cy = self.rng.uniform(0, self.params.height)
            r = self.rng.uniform(rmin, rmax)
            for cell in cells.values():
                x, y, z = cell.pos
                if not self.field.is_surface(x, y, z):
                    continue
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    cell.true_terrain = "lava"
                    cell.blocked = True

    def _place_stations(self, cells: Dict[str, Cell]) -> Tuple[Station, ...]:
        """Place stations on the surface, as far apart as the map allows."""
        presets = self.map_params.stations
        candidates = self._surface_cells(cells)
        if not candidates:
            raise ValueError(
                "every surface cell is blocked; lower block_rate or enlarge the map"
            )

        grid = self.config.get("network", {}).get("grid")
        if grid:
            # Grid: evenly spaced points, each anchored to the nearest
            # traversable cell. For small batteries: the grid guarantees short
            # hops between neighbouring bases.
            nx, ny = int(grid[0]), int(grid[1])
            if nx < 1 or ny < 1 or nx * ny < len(presets):
                raise ValueError(
                    f"network.grid {grid} must cover {len(presets)} stations."
                )
            centers = []
            for i in range(nx):
                for j in range(ny):
                    gx = (i + 0.5) * self.params.width / nx
                    gy = (j + 0.5) * self.params.height / ny
                    best = min(candidates,
                               key=lambda c: (distance(c.pos, (gx, gy, 0)), c.id))
                    centers.append(best.pos)
            centers = centers[: len(presets)]
        else:
            centers = [self.rng.choice(candidates).pos]
            while len(centers) < len(presets):
                farthest = max(
                    candidates,
                    key=lambda c: (min(distance(c.pos, p) for p in centers), c.id),
                )
                centers.append(farthest.pos)

        return place_stations(presets, tuple(centers), self.map_params.diagonal)

    def _place_pois(
        self, cells: Dict[str, Cell], stations: Tuple[Station, ...]
    ) -> List[Poi]:
        """Place points of interest on reachable, observable, well-spread ground.

        Five rules, all about instance quality rather than realism:

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
        * **Not on a station.** A point of interest never stands on a station
          cell: it would already be visited at the start.
        """
        threshold = self.map_params.poi_min_visibility
        station_ids = {cell_id(*station.center) for station in stations}
        candidates = self._observable_cells(cells, threshold) - station_ids
        by_layer: Dict[int, List[str]] = {}
        for id_ in sorted(candidates):
            by_layer.setdefault(parse_cell_id(id_)[2], []).append(id_)

        chosen: List[str] = []
        # Layers compete on interest: the most interesting one contributes the
        # first POI. So with more layers than POIs, the points land where the
        # cost and the reward are, not on the low layers by default.
        layer_interest = {
            layer: max(self._interest(cells[id_]) for id_ in ids)
            for layer, ids in by_layer.items()
        }
        for layer in sorted(by_layer, key=lambda l: (-layer_interest[l], l)):
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
        # Normalize over the terrains a point of interest can actually stand
        # on: the band terrains. Special terrains like lava are never
        # candidates (their cells are blocked), and their extreme costs would
        # squash the normalization flat.
        band_names = [b["terrain"] for b in self.config["generation"].get("bands", [])]
        names = band_names or terrain_names(self.terrain_registry)
        costs = [terrain(name, self.terrain_registry).cost for name in names]
        span = max(costs) - min(costs)
        ground = (terrain(cell.true_terrain, self.terrain_registry).cost - min(costs)) / span if span > 0 else 0.0
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
        return self._farthest(pool, chosen)

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
        move_offsets = movement_offsets(
            self.map_params.move_radius, self.map_params.move_allow_diagonal
        )
        # Observation is about distance and clear ground, not about how the
        # rover walks: the vantage scan stays euclidean.
        view_offsets = neighbour_offsets(self.map_params.move_radius)
        starts = [c.id for c in self._surface_cells(cells)]
        reachable = reachable_cells(cells, starts, move_offsets)

        observable: Set[str] = set()
        for id_ in reachable:
            cell = cells[id_]
            x, y, z = cell.pos
            for dx, dy, dz in view_offsets:
                vantage = cells.get(cell_id(x + dx, y + dy, z + dz))
                if vantage is None or not vantage.traversable:
                    continue
                if terrain(vantage.true_terrain, self.terrain_registry).visibility >= threshold:
                    observable.add(id_)
                    break
        return observable

    def _farthest(
        self,
        candidates: Sequence[str],
        chosen: Sequence[str],
    ) -> str:
        """Candidate furthest from the points of interest already placed.

        Ties go to the RNG, so two seeds do not both get the same corner. With
        nothing placed yet the draw is uniform.
        """
        pool = list(candidates)
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
        """Traversable cells on the real surface (the top of each column).

        No longer z=0: it is z == height_at(x, y). In a stable order so
        generation stays reproducible.
        """
        out: List[Cell] = []
        for x in range(self.params.width):
            for y in range(self.params.height):
                h = self.field.height_at(x, y)
                c = cells.get(cell_id(x, y, h))
                if c is not None and c.traversable:
                    out.append(c)
        return out
