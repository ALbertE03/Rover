from typing import Any, Dict, List, Tuple, TypedDict

# A 2D grid of floats, indexed [x][y].
FloatGrid = List[List[float]]

# A 2D grid of heights, indexed [x][y].
HeightGrid = List[List[int]]

# One terrain band: (exclusive upper edge, terrain name).
TerrainBand = Tuple[float, str]

# Plan-view position.
XY = Tuple[int, int]

# 3D cell position.
XYZ = Tuple[int, int, int]

# Biome center in cell units.
BiomeCenter = Tuple[float, float]

# Raw config mapping.
Config = Dict[str, Any]

class StarParams(TypedDict):
    cx: float
    cy: float
    arms: int
    phase: float
    radial: float

# One gaussian blob: (center_x, center_y, sigma).
Blob = Tuple[float, float, float]

# One directional wave: (angle, frequency, phase).
Wave = Tuple[float, float, float]

# The three noise parameter sets drawn per seed.
# The seed-drawn mixture weights (star, blobs, waves), summing to 1.
NoiseParams = Tuple[StarParams, List[Blob], List[Wave], Tuple[float, float, float]]
