from dataclasses import dataclass
from typing import Dict, List
from ..config import get

#: Sentinel name for unsurveyed ground. Not a physical terrain.
UNKNOWN = "unknown"

@dataclass(frozen=True)
class Terrain:
    """Physical traits of one terrain type.

    Attributes:
        name: Registry key, e.g. ``"rocky"``.
        cost: Energy per grid unit travelled. Strictly positive, so crossing
            ground always costs something.
        visibility: Survey quality from this ground, in (0, 1].
        glyph: Single character used by the text renderer.
    """
    name: str
    cost: float
    visibility: float
    glyph: str

def build_registry(entries: Dict) -> Dict[str, Terrain]:
    """Validate a catalogue definition and key it by name.

    Split out from the import-time registry so a candidate catalogue can be
    checked without editing the config file or touching module state.

    Args:
        entries: ``{name: {cost, visibility, glyph}}``.

    Returns:
        The registry, including the unsurveyed sentinel.

    Raises:
        ValueError: The catalogue is empty, reserves ``unknown``, or declares
            a terrain with a non-positive cost, visibility outside (0, 1] or a
            glyph that is not one character.
    """
    if not isinstance(entries, dict) or not entries:
        raise ValueError("config section 'terrain' must be a non-empty object")

    registry: Dict[str, Terrain] = {}
    for name, spec in entries.items():
        if name == UNKNOWN:
            raise ValueError(
                f"'{UNKNOWN}' is reserved for unsurveyed ground and cannot be "
                f"declared in the terrain catalogue"
            )
        cost = float(spec["cost"])
        visibility = float(spec["visibility"])
        glyph = str(spec["glyph"])

        if cost <= 0:
            raise ValueError(
                f"terrain '{name}': cost must be > 0, got {cost}. Free ground "
                f"has no cost structure to plan around."
            )
        if not 0.0 < visibility <= 1.0:
            raise ValueError(
                f"terrain '{name}': visibility must be in (0, 1], got {visibility}"
            )
        if len(glyph) != 1:
            raise ValueError(
                f"terrain '{name}': glyph must be one character, got {glyph!r}"
            )

        registry[name] = Terrain(name, cost, visibility, glyph)

    mean = sum(t.cost for t in registry.values()) / len(registry)
    registry[UNKNOWN] = Terrain(UNKNOWN, mean, 0.0, "?")
    return registry

#: Name to terrain
TERRAIN: Dict[str, Terrain] = build_registry(get("terrain"))

def terrain(name: str) -> Terrain:
    """Look up a terrain by name.

    Args:
        name: Registry key. ``UNKNOWN`` resolves to the sentinel.

    Returns:
        The terrain.

    Raises:
        KeyError: No such terrain. The message lists what exists.
    """
    try:
        return TERRAIN[name]
    except KeyError:
        raise KeyError(f"Unknown terrain {name!r}. Available: {sorted(TERRAIN)}") from None

def terrain_names() -> List[str]:
    """Declared terrain names, excluding the unsurveyed sentinel."""
    return [name for name in TERRAIN if name != UNKNOWN]

