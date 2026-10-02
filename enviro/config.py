import json
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "default.json"

_MISSING = object()


def load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """Parse a configuration file.

    Args:
        path: File to read. Defaults to ``config/default.json``.

    Returns:
        The configuration as nested dicts.

    Raises:
        FileNotFoundError: The file does not exist.
        json.JSONDecodeError: The file is not valid JSON.
    """
    target = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not target.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {target}\n"
            f"Expected sections: map, terrain, generation, movement, network, "
            f"poi, rover."
        )
    with open(target, "r", encoding="utf-8") as handle:
        return json.load(handle)


CONFIG: Dict[str, Any] = load_config()


def get(path: str, default: Any = _MISSING) -> Any:
    """Read a value with a dotted path, e.g. ``"movement.climb_penalty"``.

    Args:
        path: Dotted key path.
        default: Returned when the path is absent. When omitted, a missing
            path raises instead of quietly yielding a zero.

    Returns:
        The resolved value.

    Raises:
        KeyError: The path does not exist and no default was given.
    """
    current: Any = CONFIG
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            if default is not _MISSING:
                return default
            raise KeyError(
                f"Missing configuration key: '{path}' (failed at '{part}'). "
                f"Available: {sorted(current) if isinstance(current, dict) else current!r}"
            )
        current = current[part]
    return current
