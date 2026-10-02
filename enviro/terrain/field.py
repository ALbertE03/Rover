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
        self._configure(settings if settings is not None else get("generation"))

    def _configure(self, settings: Dict) -> None:
        """Read and validate the field settings from a config section.

        Bands are sorted on the way in, so the order they appear in the file
        does not matter; what does matter is that their edges are distinct and
        that every one names a real terrain.
        """
        self.scale = settings.get("noise_scale", 2)
        self.octaves = settings.get("noise_octaves", 3)
        self.weights = dict(settings.get("axis_weights", {"x": 0.5, "y": 0.5}))
        self.depth_slope = float(settings.get("depth_slope", 0.0))
        self.bands = sorted(
            [(float(b["max"]), str(b["terrain"])) for b in settings.get("bands", [])],
            key=lambda pair: pair[0],
        )
        self._validate()

    def _validate(self) -> None:
        """Reject a setup that would silently skew every map it generates.

        The band thresholds are absolute numbers read against a field that is
        only centred on 0.5 when the wave completes whole periods per axis. A
        fractional frequency or weights that do not add up shifts the whole
        distribution and the map quietly turns into one terrain, which is the
        kind of bug that only shows up in a results table.
        """
        if not self.bands:
            raise ValueError("generation.bands must declare at least one band")
        if (not isinstance(self.scale, int) or isinstance(self.scale, bool)
                or self.scale < 1 or self.scale % 2):
            raise ValueError(
                f"generation.noise_scale must be a positive even integer, got "
                f"{self.scale!r}. The wave's period is two units of its "
                f"argument, so an odd scale leaves each axis covering half a "
                f"period. The field's mean then follows the phase offset, which "
                f"is exactly what the seed varies, and the terrain mix stops "
                f"being the one the bands were calibrated for."
            )
        if not isinstance(self.octaves, int) or isinstance(self.octaves, bool) or not 1 <= self.octaves <= 6:
            raise ValueError(
                f"generation.noise_octaves must be an integer in [1, 6], got {self.octaves!r}"
            )
        if sorted(self.weights) != ["x", "y"]:
            raise ValueError(
                f"generation.axis_weights must have exactly the keys x and y, got "
                f"{sorted(self.weights)}. Depth is handled by depth_slope, not by "
                f"a third noise axis."
            )
        total = float(self.weights["x"]) + float(self.weights["y"])
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"generation.axis_weights must sum to 1 so the field stays in "
                f"[0, 1]; got {total}"
            )
        if not 0.0 <= self.depth_slope <= 1.0:
            raise ValueError(
                f"generation.depth_slope must be in [0, 1], got {self.depth_slope}"
            )
        edges = [edge for edge, _ in self.bands]
        if len(set(edges)) != len(edges):
            raise ValueError(
                f"generation.bands must have distinct 'max' values, got {edges}. "
                f"Two bands sharing an edge leave it ambiguous which terrain "
                f"that range is meant to be."
            )
        known = set(terrain_names())
        for _, name in self.bands:
            if name not in known:
                raise ValueError(
                    f"generation.bands references unknown terrain {name!r}. "
                    f"Declared in the catalogue: {sorted(known)}"
                )

    # the field

    def value(self, x: float, y: float, z: int) -> float:
        """Field value at a position, including the depth ramp, in [0, 1].

        Args:
            x: Position on x, already offset by :attr:`origin`.
            y: Position on y, already offset by :attr:`origin`.
            z: Layer index.
        """
        deepest = max(1, self.depth - 1)
        return min(1.0, max(0.0, self._noise(x, y) + self.depth_slope * (z / deepest)))

    def _noise(self, x: float, y: float) -> float:
        """Multi-octave value noise in [0, 1], centred on 0.5.

        Each octave doubles the frequency and halves the amplitude: the first
        one shapes the region, the rest only add detail. The weights sum to 1,
        so the weighted sum of waves is again a value in [0, 1] and dropping an
        axis would not silently rescale the field.

        The mean is 0.5 for any phase offset, which is the property that makes
        the band thresholds meaningful. It holds because ``noise_scale`` is
        even: each axis then covers a whole number of wave periods, and a
        triangle sampled evenly across whole periods averages to its midpoint.
        Change the scale to an odd number and the offset starts dragging the
        whole map toward one end of the band table.
        """
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

    def terrain_at(self, x: int, y: int, z: int) -> str:
        """Terrain name at a cell, resolved through the bands."""
        value = self.value(x + self.origin[0], y + self.origin[1], z)
        for edge, name in self.bands:
            if value < edge:
                return name
        return self.bands[-1][1]

    def layer_profile(self, z: int) -> Dict[str, int]:
        """Terrain counts for one layer. Diagnostic for calibration."""
        counts: Dict[str, int] = {}
        for x in range(self.width):
            for y in range(self.height):
                name = self.terrain_at(x, y, z)
                counts[name] = counts.get(name, 0) + 1
        return counts

    def __repr__(self) -> str:
        return (f"TerrainField({self.width}x{self.height}x{self.depth}, "
                f"scale={self.scale}, octaves={self.octaves}, "
                f"slope={self.depth_slope}, bands={len(self.bands)})")


def _wave(position: float, extent: int) -> float:
    """A smooth per-axis wave in [0, 1]. Cheap stand-in for Perlin noise.

    Peaks at 1.0 on position 0, troughs at 0.0 on ``extent``, and repeats every
    ``2 * extent``. With frequency ``f`` the argument advances ``f / extent``
    per cell, so an axis of ``extent`` cells covers ``f / 2`` whole periods.
    """
    return abs((position / max(1, extent)) % 2.0 - 1.0)
