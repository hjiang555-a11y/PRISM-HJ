"""
Lightweight parameter extractor for template-first compilation.

Uses simple regex patterns to extract numeric physics parameters from natural
language questions (Chinese + English) for known scenario types.

This module is intentionally minimal — it only handles the most common problem
phrasings.  If extraction returns ``None`` for required parameters, the caller
(``text_to_psdl``) falls back to the full LLM translation path.

Supported extractors
--------------------
:func:`extract_free_fall_params`
    Returns ``{"height", "duration", "mass", "v0z"}`` or ``None``.
:func:`extract_projectile_params`
    Returns ``{"height", "v0x", "v0z", "duration", "mass"}`` or ``None``.
    For angled launches, ``v0x`` and ``v0z`` are computed from the extracted
    speed magnitude and angle; for horizontal throws ``v0z`` is 0.
:func:`extract_collision_params`
    Returns ``{"m1", "m2", "v1x", "v2x", "collision_type"}`` or ``None``.
"""

from __future__ import annotations

import math
import re
from typing import Optional

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Pattern fragment that matches an unsigned integer or decimal number.
_NUM: str = r"(\d+(?:\.\d+)?)"


def _find(pattern: str, text: str) -> Optional[float]:
    """Return the first non-None captured group as float, or ``None``."""
    m = re.search(pattern, text)
    if m:
        for g in m.groups():
            if g is not None:
                return float(g)
    return None


def _find_all(pattern: str, text: str) -> list[float]:
    """Return all first-group matches as a list of floats."""
    return [float(m) for m in re.findall(pattern, text)]


# ---------------------------------------------------------------------------
# Public extractors
# ---------------------------------------------------------------------------

def extract_free_fall_params(text: str) -> Optional[dict]:
    """
    Extract free-fall parameters from *text*.

    Returns
    -------
    dict or None
        Keys: ``height`` (m), ``duration`` (s), ``mass`` (kg), ``v0z`` (m/s).
        Returns ``None`` if the required *height* parameter cannot be found.
    """
    lower = text.lower()

    # Height (m): various Chinese and English phrasings
    height = (
        _find(r"从高度\s*" + _NUM + r"\s*(?:m|米)", lower)
        or _find(r"高度\s*(?:为|是|=)?\s*" + _NUM + r"\s*(?:m|米)", lower)
        or _find(r"在\s*" + _NUM + r"\s*(?:m|米)\s*(?:高|处)", lower)
        or _find(_NUM + r"\s*(?:m|米)\s*(?:高|处)", lower)
        or _find(r"height\s+(?:of\s+)?" + _NUM + r"\s*m\b", lower)
        or _find(r"from\s+(?:a\s+)?" + _NUM + r"\s*m\b", lower)
        or _find(r"dropped?\s+from\s+" + _NUM + r"\s*m\b", lower)
    )

    # Duration (s): "X秒后", "经过X秒", "after X s", "t=X s"
    duration = (
        _find(_NUM + r"\s*秒后", lower)
        or _find(r"经过\s*" + _NUM + r"\s*秒", lower)
        or _find(r"after\s+" + _NUM + r"\s*s(?:ec(?:ond)?s?)?\b", lower)
        or _find(r"\bt\s*=\s*" + _NUM + r"\s*s\b", lower)
    )

    # Mass (kg): "Xkg", "X千克", "X公斤"
    mass = (
        _find(_NUM + r"\s*kg", lower)
        or _find(_NUM + r"\s*(?:千克|公斤)", lower)
    )

    if height is None:
        return None  # Cannot build free-fall template without height

    return {
        "height": height,
        "duration": duration if duration is not None else 1.0,
        "mass": mass if mass is not None else 1.0,
        "v0z": 0.0,  # free fall from rest by default
    }


def extract_projectile_params(text: str) -> Optional[dict]:
    """
    Extract projectile parameters from *text*.

    Supports both horizontal-throw and angled-throw scenarios.

    For an **angled throw**, the extractor looks for an angle expression
    (Chinese: "以30度", "仰角45°"; English: "at an angle of 30 degrees",
    "launched at 45 degrees") together with an initial speed.  When an angle
    is found, ``v0x`` and ``v0z`` are derived as:

        v0x = v0 * cos(theta)
        v0z = v0 * sin(theta)

    where *theta* is the extracted angle converted to radians.

    For a **horizontal throw** (no angle found), ``v0z`` is set to 0.

    Returns
    -------
    dict or None
        Keys: ``height`` (m), ``v0x`` (m/s), ``v0z`` (m/s),
        ``duration`` (s), ``mass`` (kg).
        Returns ``None`` if *height* or an initial speed cannot be determined.
    """
    lower = text.lower()

    # Height
    height = (
        _find(r"从高度\s*" + _NUM + r"\s*(?:m|米)", lower)
        or _find(r"高度\s*(?:为|是|=)?\s*" + _NUM + r"\s*(?:m|米)", lower)
        or _find(_NUM + r"\s*(?:m|米)\s*(?:高|处)", lower)
        or _find(r"height\s+(?:of\s+)?" + _NUM + r"\s*m\b", lower)
        or _find(r"from\s+(?:a\s+)?" + _NUM + r"\s*m\b", lower)
    )

    # ---------------------------------------------------------------------------
    # Angle detection (degrees → radians)
    # ---------------------------------------------------------------------------
    # Chinese patterns: "以30度", "以45°", "仰角30度", "仰角45°", "30度角",
    #                   "以30度角", "斜抛角度30"
    # English patterns: "at an angle of 30 degrees", "at 45 degrees",
    #                   "launched at 45 degrees", "angle of 30°", "30-degree angle"
    theta_deg: Optional[float] = (
        _find(r"以\s*" + _NUM + r"\s*(?:度|°)", lower)
        or _find(r"仰角\s*" + _NUM + r"\s*(?:度|°)?", lower)
        or _find(_NUM + r"\s*(?:度|°)\s*(?:角|斜抛|抛出)?", lower)
        or _find(r"at\s+an?\s+angle\s+of\s+" + _NUM + r"\s*(?:degree|deg|°)?", lower)
        or _find(r"launched?\s+at\s+" + _NUM + r"\s*(?:degree|deg|°)", lower)
        or _find(r"at\s+" + _NUM + r"\s*(?:degree|deg|°)\b", lower)
        or _find(r"angle\s+of\s+" + _NUM + r"\s*(?:degree|deg|°)?", lower)
        or _find(_NUM + r"[\s\-]?degree\s+angle", lower)
    )
    theta_rad: float = math.radians(theta_deg) if theta_deg is not None else 0.0

    # ---------------------------------------------------------------------------
    # Speed / velocity extraction
    # ---------------------------------------------------------------------------
    if theta_deg is not None:
        # Angled throw: look for the launch speed (magnitude)
        v0 = (
            _find(r"以\s*" + _NUM + r"\s*(?:m/s|米/秒)\s*(?:的速度)?", lower)
            or _find(r"初速度\s*(?:为|是|=)?\s*" + _NUM + r"\s*(?:m/s|米/秒)?", lower)
            or _find(r"速度\s*(?:为|是|=)?\s*" + _NUM + r"\s*(?:m/s|米/秒)", lower)
            or _find(r"(?:initial\s+)?(?:launch\s+)?speed\s+(?:of\s+)?" + _NUM, lower)
            or _find(r"velocity\s+(?:of\s+)?" + _NUM + r"\s*(?:m/s)?", lower)
            or _find(r"v0?\s*=\s*" + _NUM, lower)
            or _find(_NUM + r"\s*(?:m/s|米/秒)", lower)  # fallback: first speed
        )
        if v0 is None:
            return None
        v0x = v0 * math.cos(theta_rad)
        v0z = v0 * math.sin(theta_rad)
    else:
        # Horizontal throw: extract v0x directly
        v0x = (
            _find(r"以\s*" + _NUM + r"\s*(?:m/s|米/秒)\s*(?:水平|的水平)", lower)
            or _find(r"水平.*速度.*?" + _NUM + r"\s*(?:m/s|米/秒)", lower)
            or _find(r"horizontal\s+(?:velocity|speed)\s+(?:of\s+)?" + _NUM, lower)
            or _find(r"v0?x\s*=\s*" + _NUM, lower)
            or _find(_NUM + r"\s*(?:m/s|米/秒)", lower)  # fallback: first speed
        )
        v0z = 0.0

    # Duration
    duration = (
        _find(_NUM + r"\s*秒后", lower)
        or _find(r"经过\s*" + _NUM + r"\s*秒", lower)
        or _find(r"after\s+" + _NUM + r"\s*s(?:ec(?:ond)?s?)?\b", lower)
        or _find(r"\bt\s*=\s*" + _NUM + r"\s*s\b", lower)
    )

    # Mass
    mass = (
        _find(_NUM + r"\s*kg", lower)
        or _find(_NUM + r"\s*(?:千克|公斤)", lower)
    )

    if height is None or v0x is None:
        return None  # Cannot build projectile template without both values

    return {
        "height": height,
        "v0x": v0x,
        "v0z": v0z,
        "duration": duration if duration is not None else 1.0,
        "mass": mass if mass is not None else 1.0,
    }


def extract_collision_params(text: str) -> Optional[dict]:
    """
    Extract 1-D two-particle collision parameters from *text*.

    Returns
    -------
    dict or None
        Keys: ``m1``, ``m2`` (kg), ``v1x``, ``v2x`` (m/s),
        ``collision_type`` (``"elastic"`` or ``"inelastic"``).
        Returns ``None`` if two masses and at least one velocity cannot be
        extracted.
    """
    lower = text.lower()

    # Collision type (default: elastic)
    if re.search(r"非弹性|完全非弹性|perfectly\s+inelastic|inelastic", lower):
        collision_type = "inelastic"
    else:
        collision_type = "elastic"

    # Extract all mass values: "Xkg" / "X千克" / "X公斤"
    masses = _find_all(_NUM + r"\s*(?:kg|千克|公斤)", lower)

    # Extract all velocity values: "X m/s" / "X米/秒"
    vels = _find_all(_NUM + r"\s*(?:m/s|米/秒)", lower)

    if len(masses) < 2 or len(vels) < 1:
        return None  # Need at least two masses and one velocity

    return {
        "m1": masses[0],
        "m2": masses[1],
        "v1x": vels[0],
        "v2x": vels[1] if len(vels) > 1 else 0.0,
        "collision_type": collision_type,
    }
