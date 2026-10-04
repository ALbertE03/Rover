from typing import Dict, List, Optional, Tuple
from ..config import get
from .catalogue import terrain_names


class TerrainField:
    """Terrain as a function of position.

    Attributes:
        width: Grid extent on x.
        height: Grid extent on y.
        depth: Vertical layers.
        origin: Phase offset in cell units, which is the seed's only
            influence on the terrain itself.
        depth_slope: How much deeper cells trend toward the expensive end.
    """

    def __init__(
        self,
        width: int,
        height: int,
        depth: int,
        origin: Tuple[float, float] = (0.0, 0.0),
        settings: Optional[Dict] = None,
    ) -> None:
        self.width = width
        self.height = height
        self.depth = depth
        self.origin = origin
        self.depth_slope = 0.0
        self.scale = 1
        self.octaves = 1
        self.weights = {"x": 0.5, "y": 0.5}
        self.bands: List[Tuple[float, str]] = []
        self.height_scale = 2
        self.height_octaves = 1
        self.height_smooth_passes = 2
        self._heightmap: Optional[List[List[int]]] = None
        self._configure(settings if settings is not None else get("generation"))

    def _configure(self, settings: Dict) -> None:
        self.scale = settings.get("noise_scale", 2)
        self.octaves = settings.get("noise_octaves", 3)
        self.weights = dict(settings.get("axis_weights", {"x": 0.5, "y": 0.5}))
        self.depth_slope = float(settings.get("depth_slope", 0.0))
        self.bands = sorted(
            [(float(b["max"]), str(b["terrain"])) for b in settings.get("bands", [])],
            key=lambda pair: pair[0],
        )
        self.height_scale = settings.get("height_scale", 2)
        self.height_octaves = settings.get("height_octaves", 1)
        self.height_smooth_passes = settings.get("height_smooth_passes", 2)
        self._validate()

    def _validate(self) -> None:
        if not self.bands:
            raise ValueError("generation.bands must declare at least one band")
        if (not isinstance(self.scale, int) or isinstance(self.scale, bool)
                or self.scale < 1 or self.scale % 2):
            raise ValueError(
                f"generation.noise_scale must be a positive even integer, got {self.scale!r}."
            )
        if not isinstance(self.octaves, int) or isinstance(self.octaves, bool) or not 1 <= self.octaves <= 6:
            raise ValueError(
                f"generation.noise_octaves must be an integer in [1, 6], got {self.octaves!r}"
            )
        if sorted(self.weights) != ["x", "y"]:
            raise ValueError(
                f"generation.axis_weights must have exactly the keys x and y, got {sorted(self.weights)}."
            )
        total = float(self.weights["x"]) + float(self.weights["y"])
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"generation.axis_weights must sum to 1; got {total}")
        if not 0.0 <= self.depth_slope <= 1.0:
            raise ValueError(f"generation.depth_slope must be in [0, 1], got {self.depth_slope}")
        if (not isinstance(self.height_scale, int) or isinstance(self.height_scale, bool)
                or self.height_scale < 1 or self.height_scale % 2):
            raise ValueError(
                f"generation.height_scale must be a positive even integer, got {self.height_scale!r}."
            )
        if (not isinstance(self.height_octaves, int) or isinstance(self.height_octaves, bool)
                or not 1 <= self.height_octaves <= 6):
            raise ValueError(
                f"generation.height_octaves must be an integer in [1, 6], got {self.height_octaves!r}"
            )
        if (not isinstance(self.height_smooth_passes, int) or isinstance(self.height_smooth_passes, bool)
                or not 0 <= self.height_smooth_passes <= 5):
            raise ValueError(
                f"generation.height_smooth_passes must be an integer in [0, 5], got {self.height_smooth_passes!r}"
            )
        edges = [edge for edge, _ in self.bands]
        if len(set(edges)) != len(edges):
            raise ValueError(f"generation.bands must have distinct 'max' values, got {edges}.")
        known = set(terrain_names())
        for _, name in self.bands:
            if name not in known:
                raise ValueError(f"generation.bands references unknown terrain {name!r}.")

    def value(self, x: float, y: float, z: int) -> float:
        deepest = max(1, self.depth - 1)
        return min(1.0, max(0.0, self._noise(x, y) + self.depth_slope * (z / deepest)))

    def _noise(self, x: float, y: float) -> float:
        total = 0.0
        norm = 0.0
        amplitude = 1.0
        frequency = self.scale
        for _ in range(self.octaves):
            total += amplitude * (
                float(self.weights["x"]) * _wave(x * frequency, self.width)
                + float(self.weights["y"]) * _wave(y * frequency, self.height)
            )
            norm += amplitude
            amplitude *= 0.5
            frequency *= 2
        return (total / norm) if norm else 0.0

    def _height_noise(self, x: float, y: float) -> float:
        total = 0.0
        norm = 0.0
        amplitude = 1.0
        frequency = self.height_scale
        for _ in range(self.height_octaves):
            total += amplitude * (
                0.5 * _wave(x * frequency, self.width)
                + 0.5 * _wave(y * frequency, self.height)
            )
            norm += amplitude
            amplitude *= 0.5
            frequency *= 2
        return (total / norm) if norm else 0.5

    def height_at(self, x: int, y: int) -> int:
        if self.depth <= 1:
            return 0
        if self._heightmap is None:
            self._heightmap = self._build_heightmap()
        return self._heightmap[x][y]

    def heightmap(self) -> List[List[int]]:
        if self.depth <= 1:
            return [[0 for _ in range(self.height)] for _ in range(self.width)]
        if self._heightmap is None:
            self._heightmap = self._build_heightmap()
        return [row[:] for row in self._heightmap]

    def is_surface(self, x: int, y: int, z: int) -> bool:
        return z == self.height_at(x, y)

    def is_interior(self, x: int, y: int, z: int) -> bool:
        return z < self.height_at(x, y)

    def _build_heightmap(self) -> List[List[int]]:
        raw: List[List[int]] = [[0 for _ in range(self.height)] for _ in range(self.width)]
        for x in range(self.width):
            for y in range(self.height):
                n = self._height_noise(x + self.origin[0], y + self.origin[1])
                h = int(n * (self.depth - 1) + 0.5)
                raw[x][y] = max(0, min(self.depth - 1, h))
        for _ in range(self.height_smooth_passes):
            raw = self._median_smooth(raw)
        for _ in range(3):
            changed = False
            nxt = [row[:] for row in raw]
            for x in range(self.width):
                for y in range(self.height):
                    h = raw[x][y]
                    if h == 0:
                        continue
                    neigh = []
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            if dx == 0 and dy == 0:
                                continue
                            nx, ny = x + dx, y + dy
                            if 0 <= nx < self.width and 0 <= ny < self.height:
                                neigh.append(raw[nx][ny])
                    if neigh and h > max(neigh):
                        nxt[x][y] = max(neigh)
                        changed = True
            raw = nxt
            if not changed:
                break
        return raw

    def _median_smooth(self, hm: List[List[int]]) -> List[List[int]]:
        out: List[List[int]] = [[0 for _ in range(self.height)] for _ in range(self.width)]
        for x in range(self.width):
            for y in range(self.height):
                vals = []
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < self.width and 0 <= ny < self.height:
                            vals.append(hm[nx][ny])
                vals.sort()
                out[x][y] = vals[len(vals) // 2]
        return out

    def terrain_at(self, x: int, y: int, z: int) -> str:
        value = self.value(x + self.origin[0], y + self.origin[1], z)
        for edge, name in self.bands:
            if value < edge:
                return name
        return self.bands[-1][1]

    def layer_profile(self, z: int) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for x in range(self.width):
            for y in range(self.height):
                name = self.terrain_at(x, y, z)
                counts[name] = counts.get(name, 0) + 1
        return counts

    def surface_profile(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for x in range(self.width):
            for y in range(self.height):
                z = self.height_at(x, y)
                name = self.terrain_at(x, y, z)
                counts[name] = counts.get(name, 0) + 1
        return counts

    def __repr__(self) -> str:
        return (f"TerrainField({self.width}x{self.height}x{self.depth}, "
                f"scale={self.scale}, octaves={self.octaves}, "
                f"slope={self.depth_slope}, bands={len(self.bands)}, "
                f"h_scale={self.height_scale}, h_oct={self.height_octaves})")


def _wave(position: float, extent: int) -> float:
    return abs((position / max(1, extent)) % 2.0 - 1.0)
