"""
Source registry loader — runtime constraint enforcement (v0.2).

Loads ``data/sources/registry.yaml`` once and exposes query helpers used by
:mod:`src.sources.validation` to enforce tier governance rules at runtime.

The registry is cached after the first load via :func:`functools.lru_cache`
so repeated calls incur no I/O overhead.

Tiers
-----
``tier_1_authoritative``
    Approved primary template sources for classical mechanics problems.
``tier_2_high_quality_educational``
    Secondary / conceptual references only.
``standards_only``
    Unit definitions and metrology ONLY — forbidden as mechanics template
    sources (NIST, ITU).
``pending``
    Awaiting review; must not appear in production PSDL documents.
"""

from __future__ import annotations

import functools
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# Path to the registry file relative to this module.
_REGISTRY_PATH: Path = (
    Path(__file__).parents[2] / "data" / "sources" / "registry.yaml"
)

# Scenario types treated as "classical mechanics" for source tier enforcement.
MECHANICS_SCENARIO_TYPES: frozenset[str] = frozenset(
    {"free_fall", "projectile", "collision"}
)


@functools.lru_cache(maxsize=1)
def _load_raw() -> Dict[str, Any]:
    """Load and parse the registry YAML file (cached)."""
    if not _REGISTRY_PATH.exists():
        raise FileNotFoundError(
            f"Source registry not found at {_REGISTRY_PATH}. "
            "Ensure data/sources/registry.yaml exists."
        )
    with _REGISTRY_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    sources: List[Dict[str, Any]] = data.get("sources", [])
    registry = {entry["id"]: entry for entry in sources}
    logger.debug("Source registry loaded: %d entries.", len(registry))
    return registry


def get_all_sources() -> Dict[str, Any]:
    """Return the full registry as a ``{source_id: entry}`` dict."""
    return _load_raw()


def get_source(source_id: str) -> Optional[Dict[str, Any]]:
    """Return the registry entry for *source_id*, or ``None`` if not found."""
    return _load_raw().get(source_id)


def source_exists(source_id: str) -> bool:
    """Return ``True`` if *source_id* is present in the registry."""
    return source_id in _load_raw()


def get_tier(source_id: str) -> Optional[str]:
    """Return the tier string for *source_id*, or ``None`` if not found."""
    entry = get_source(source_id)
    return entry["tier"] if entry else None


def get_allowed_uses(source_id: str) -> List[str]:
    """Return the ``allowed_uses`` list for *source_id* (empty if not found)."""
    entry = get_source(source_id)
    return list(entry.get("allowed_uses", [])) if entry else []
