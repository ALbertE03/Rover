import math
import random
from typing import Dict, List, Optional, Tuple
from ..config import get
from .catalogue import terrain_names
from .types import (
    BiomeCenter,
    Blob,
    Config,
    FloatGrid,
    HeightGrid,
    NoiseParams,
    NoisePipeline,
    StarParams,
    TerrainBand,
    Wave,
    XY,
)


def _biased_bands(bands: List[TerrainBand],
                  dominant: str) -> List[TerrainBand]:
    """Widen the dominant terrain's band so it clusters in its biome.

    Doubles the dominant band's width by stealing half from each neighbor.
    """
    widths: List[float] = []
    prev = 0.0
    for edge, _ in bands:
        widths.append(edge - prev)
        prev = edge
    idx = next(i for i, (_, name) in enumerate(bands) if name == dominant)
    # steal 40% from each neighbor
    for j in (idx - 1, idx + 1):
        if 0 <= j < len(widths):
            take = widths[j] * 0.4
            widths[j] -= take
            widths[idx] += take
    out: List[TerrainBand] = []
    edge = 0.0
    for w, (_, name) in zip(widths, bands):
        edge += w
        out.append((edge, name))
    out[-1] = (1.0, out[-1][1])
    return out


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
        settings: Optional[Config] = None,
    ) -> None:
        self.width = width
        self.height = height
        self.depth = depth
        self.origin = origin
        self.depth_slope = 0.0
        self.scale = 1
        self.octaves = 1
        self.weights: Dict[str, float] = {"x": 0.5, "y": 0.5}
        self.bands: List[TerrainBand] = []
        self.height_contrast = 3.0
        self._heightmap: Optional[HeightGrid] = None
        self._configure(settings if settings is not None else get("generation"))

    def _configure(self, settings: Config) -> None:
        self.scale = settings.get("noise_scale", 2)
        self.octaves = settings.get("noise_octaves", 3)
        self.weights = dict(settings.get("axis_weights", {"x": 0.5, "y": 0.5}))
        self.depth_slope = float(settings.get("depth_slope", 0.0))
        self.bands = sorted(
            [(float(b["max"]), str(b["terrain"])) for b in settings.get("bands", [])],
            key=lambda pair: pair[0],
        )
        self.height_contrast = float(settings.get("height_contrast", 3.0))
        # Biomes: K Voronoi regions, each with bands biased toward a dominant
        # terrain so types cluster into regions instead of scattering.
        self.biome_count = int(settings.get("biome_count", 0))
        self.biome_centers: List[BiomeCenter] = []
        self.biome_bands: List[List[TerrainBand]] = []
        if self.biome_count > 1:
            rng = random.Random(settings.get("seed", 0) ^ 0xB10E)
            names = [name for _, name in self.bands]
            for _ in range(self.biome_count):
                self.biome_centers.append(
                    (rng.uniform(0, self.width), rng.uniform(0, self.height)))
                dominant = rng.choice(names)
                self.biome_bands.append(_biased_bands(self.bands, dominant))
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
        if not self.height_contrast > 0.0:
            raise ValueError(
                f"generation.height_contrast must be > 0, got {self.height_contrast!r}"
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

    def _noise_seed(self) -> int:
        """Deterministic integer seed derived from the origin (that is, from the seed)."""
        return int(self.origin[0] * 1000 + self.origin[1] * 1000
                   + self.width * 131 + self.height * 17)

    def _draw_noise_params(self, rng: random.Random) -> NoiseParams:
        """Draw the parameters of the 3 noises. Everything comes from the seed."""
        #  STAR: radial arms from a random center.
        star: StarParams = {
            "cx": rng.uniform(0, self.width),
            "cy": rng.uniform(0, self.height),
            "arms": rng.randint(3, 5),
            "phase": rng.uniform(0, 2 * math.pi),
            "radial": rng.uniform(0.10, 0.30),
        }
        #  BLOBS: gaussians with a random center and sigma.
        blobs: List[Blob] = [
            (rng.uniform(0, self.width),
             rng.uniform(0, self.height),
             rng.uniform(2.0, 6.0))
            for _ in range(rng.randint(8, 14))
        ]
        #  WAVES: directional sines with random angle/frequency/phase.
        waves: List[Wave] = [
            (rng.uniform(0, math.pi),
             rng.uniform(0.08, 0.28),
             rng.uniform(0, 2 * math.pi))
            for _ in range(3)
        ]
        return star, blobs, waves

    def _star_value(self, x: float, y: float, p: StarParams) -> float:
        dx, dy = x - p["cx"], y - p["cy"]
        r = math.hypot(dx, dy)
        theta = math.atan2(dy, dx)
        return 0.5 + 0.5 * math.cos(p["arms"] * theta + p["phase"]) * math.cos(r * p["radial"])

    def _blobs_value(self, x: float, y: float, blobs: List[Blob]) -> float:
        return sum(
            math.exp(-((x - bx) ** 2 + (y - by) ** 2) / (2 * sig ** 2))
            for bx, by, sig in blobs
        )

    def _waves_value(self, x: float, y: float, waves: List[Wave]) -> float:
        return sum(
            0.5 + 0.5 * math.sin(
                2 * math.pi * (x * math.cos(a) + y * math.sin(a)) * f + ph)
            for a, f, ph in waves
        ) / len(waves)

    @staticmethod
    def _normalize(field: FloatGrid) -> FloatGrid:
        lo = min(min(row) for row in field)
        hi = max(max(row) for row in field)
        if hi - lo < 1e-9:
            return [[0.5 for _ in row] for row in field]
        return [[(v - lo) / (hi - lo) for v in row] for row in field]

    def height_at(self, x: int, y: int) -> int:
        if self.depth <= 1:
            return 0
        if self._heightmap is None:
            self._heightmap = self._build_heightmap()
        return self._heightmap[x][y]

    def heightmap(self) -> HeightGrid:
        if self.depth <= 1:
            return [[0 for _ in range(self.height)] for _ in range(self.width)]
        if self._heightmap is None:
            self._heightmap = self._build_heightmap()
        return [row[:] for row in self._heightmap]

    def noise_pipeline(self) -> NoisePipeline:
        """The 3 heightmap noises, normalized, plus their average.

        For visualization: shows what the terrain is made of before
        quantization. Deterministic for the same seed.
        """
        rng = random.Random(self._noise_seed())
        star_p, blobs_p, waves_p = self._draw_noise_params(rng)
        w, h = self.width, self.height
        fs = [[self._star_value(x, y, star_p) for y in range(h)] for x in range(w)]
        fb = [[self._blobs_value(x, y, blobs_p) for y in range(h)] for x in range(w)]
        fw = [[self._waves_value(x, y, waves_p) for y in range(h)] for x in range(w)]
        ns, nb, nw = self._normalize(fs), self._normalize(fb), self._normalize(fw)
        combined: FloatGrid = [
            [(ns[x][y] + nb[x][y] + nw[x][y]) / 3.0 for y in range(h)]
            for x in range(w)
        ]
        return {
            "star": ns,
            "blobs": nb,
            "waves": nw,
            "combined": combined,
            "star_arms": int(star_p["arms"]),
            "star_center": (round(float(star_p["cx"]), 1),
                            round(float(star_p["cy"]), 1)),
            "n_blobs": len(blobs_p),
        }

    def is_surface(self, x: int, y: int, z: int) -> bool:
        return z == self.height_at(x, y)

    def is_interior(self, x: int, y: int, z: int) -> bool:
        return z < self.height_at(x, y)

    def _build_heightmap(self) -> HeightGrid:
        """Star + blobs + waves -> average -> contrast -> quantization.

        No median passes, no peak clipping and no sub-hills: what comes out of
        the 3 noises is the final terrain.
        """
        rng = random.Random(self._noise_seed())
        star_p, blobs_p, waves_p = self._draw_noise_params(rng)
        f_star = [[self._star_value(x, y, star_p)
                   for y in range(self.height)] for x in range(self.width)]
        f_blobs = [[self._blobs_value(x, y, blobs_p)
                    for y in range(self.height)] for x in range(self.width)]
        f_waves = [[self._waves_value(x, y, waves_p)
                    for y in range(self.height)] for x in range(self.width)]
        f_star = self._normalize(f_star)
        f_blobs = self._normalize(f_blobs)
        f_waves = self._normalize(f_waves)
        raw: HeightGrid = [[0 for _ in range(self.height)] for _ in range(self.width)]
        for x in range(self.width):
            for y in range(self.height):
                n = (f_star[x][y] + f_blobs[x][y] + f_waves[x][y]) / 3.0
                # Contrast: stretch the average around 0.5 so the map uses the
                # whole [0, depth-1] range.
                n = 0.5 + (n - 0.5) * self.height_contrast
                n = max(0.0, min(1.0, n))
                h = int(n * (self.depth - 1) + 0.5)
                raw[x][y] = max(0, min(self.depth - 1, h))
        return raw

    def biome_at(self, x: int, y: int) -> int:
        """Voronoi biome index for a column, or -1 when biomes are off."""
        if not self.biome_centers:
            return -1
        best, best_d = 0, float("inf")
        for i, (cx, cy) in enumerate(self.biome_centers):
            d = (x - cx) ** 2 + (y - cy) ** 2
            if d < best_d:
                best, best_d = i, d
        return best

    def terrain_at(self, x: int, y: int, z: int) -> str:
        value = self.value(x + self.origin[0], y + self.origin[1], z)
        bands = self.bands
        b = self.biome_at(x, y)
        if b >= 0:
            bands = self.biome_bands[b]
        for edge, name in bands:
            if value < edge:
                return name
        return bands[-1][1]

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
                f"h_contrast={self.height_contrast})")


def _wave(position: float, extent: int) -> float:
    return abs((position / max(1, extent)) % 2.0 - 1.0)
