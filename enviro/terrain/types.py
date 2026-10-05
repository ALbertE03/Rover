"""Shared type aliases for the terrain package.

All structural types live here so modules import them instead of repeating
``List[List[float]]`` and friends. Nothing in this module imports from the
package, so there are no cycles.
"""
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
NoiseParams = Tuple[StarParams, List[Blob], List[Wave]]


class NoisePipeline(TypedDict):
    """What :meth:`TerrainField.noise_pipeline` hands back.

    A TypedDict rather than ``Dict[str, ...]`` because the grids and the
    scalar metadata travel in the same mapping: a plain dict would have to
    collapse to ``object`` and every reader would lose the element type.
    """
    star: FloatGrid
    blobs: FloatGrid
    waves: FloatGrid
    combined: FloatGrid
    star_arms: int
    star_center: Tuple[float, float]
    n_blobs: int
