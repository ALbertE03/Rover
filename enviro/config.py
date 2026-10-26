import copy
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


def merge_config(
    base: Dict[str, Any], override: Dict[str, Any]
) -> Dict[str, Any]:
    """Deep-merge an override over a base configuration.

    Nested dicts merge key by key; every other value (scalars, lists)
    replaces the base value wholesale, so a list override never extends
    the default list. Neither input is mutated: the result is a copy.

    Args:
        base: Configuration to start from, usually the default.
        override: Partial configuration with the keys to change.

    Returns:
        The merged configuration.
    """
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_config(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def resolve_config(
    path: Optional[Path] = None,
    override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve the configuration in force.

    Precedence, lowest to highest: the default file, the file at ``path``
    (if given), the ``override`` dict (if given). Either source may be
    partial: missing keys fall back to the lower-precedence source. With
    neither source, the result is the default configuration.

    Args:
        path: Alternate configuration file, or None for the default file.
        override: Partial configuration dict from the consumer, or None.

    Returns:
        The effective configuration.

    Raises:
        TypeError: The override is not a dict.
    """
    config = load_config()
    if path is not None:
        config = merge_config(config, load_config(path))
    if override is not None:
        if not isinstance(override, dict):
            raise TypeError(
                f"config override must be a dict, got {type(override).__name__}"
            )
        config = merge_config(config, override)
    return config


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
