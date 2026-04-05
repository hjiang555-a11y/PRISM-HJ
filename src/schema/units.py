"""
PRISM-HJ unit / dimension system — v0.1

All physical quantities in PSDL must carry a declared unit symbol.
This module provides:

* :class:`Dimension` — enumeration of supported physical dimensions.
* :data:`UNITS` — mapping from SI symbol to its :class:`UnitInfo`.
* :exc:`DimensionError` — raised when a unit is incompatible with the
  expected dimension.
* :func:`validate_unit_for_dimension` — the main validation entry-point.
* :func:`check_quantity` — convenience wrapper that validates *and*
  returns the value unchanged (for use in Pydantic validators).

Scope (v0.1)
------------
Only the seven dimensions needed to describe classical-mechanics scenarios
are supported.  Compound dimensions (e.g. energy, pressure) will be added
in v0.2.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict


# ---------------------------------------------------------------------------
# Dimension enumeration
# ---------------------------------------------------------------------------

class Dimension(str, Enum):
    """Supported physical dimensions (v0.1)."""
    length        = "length"
    mass          = "mass"
    time          = "time"
    velocity      = "velocity"
    acceleration  = "acceleration"
    force         = "force"
    dimensionless = "dimensionless"


# ---------------------------------------------------------------------------
# Unit registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UnitInfo:
    """Metadata for a single SI unit."""
    symbol: str
    name: str
    dimension: Dimension


#: Registry of all supported SI unit symbols.
UNITS: Dict[str, UnitInfo] = {
    "m":     UnitInfo("m",     "metre",                    Dimension.length),
    "kg":    UnitInfo("kg",    "kilogram",                 Dimension.mass),
    "s":     UnitInfo("s",     "second",                   Dimension.time),
    "m/s":   UnitInfo("m/s",   "metre per second",         Dimension.velocity),
    "m/s^2": UnitInfo("m/s^2", "metre per second squared", Dimension.acceleration),
    "N":     UnitInfo("N",     "newton",                   Dimension.force),
    "1":     UnitInfo("1",     "dimensionless",            Dimension.dimensionless),
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class DimensionError(ValueError):
    """Raised when a unit symbol is incompatible with the expected dimension."""

    def __init__(self, unit_symbol: str, expected: Dimension, got: Dimension) -> None:
        super().__init__(
            f"Unit '{unit_symbol}' has dimension '{got.value}', "
            f"but '{expected.value}' was expected."
        )
        self.unit_symbol = unit_symbol
        self.expected = expected
        self.got = got


class UnknownUnitError(ValueError, KeyError):
    """Raised when a unit symbol is not in the UNITS registry."""

    def __init__(self, symbol: str) -> None:
        msg = (
            f"Unknown unit symbol '{symbol}'. "
            f"Supported symbols: {sorted(UNITS.keys())}"
        )
        # Initialize both bases; ValueError needs the message string,
        # KeyError stores it under args[0].
        ValueError.__init__(self, msg)
        self.symbol = symbol


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def get_unit_info(symbol: str) -> UnitInfo:
    """
    Return the :class:`UnitInfo` for *symbol*.

    Raises
    ------
    UnknownUnitError
        If *symbol* is not registered.
    """
    try:
        return UNITS[symbol]
    except KeyError as exc:
        raise UnknownUnitError(symbol) from exc


def validate_unit_for_dimension(unit_symbol: str, expected: Dimension) -> UnitInfo:
    """
    Assert that *unit_symbol* belongs to *expected* dimension.

    Parameters
    ----------
    unit_symbol:
        SI symbol string (e.g. ``"m/s^2"``).
    expected:
        The dimension the caller requires.

    Returns
    -------
    UnitInfo
        The resolved unit metadata (so callers can chain calls).

    Raises
    ------
    UnknownUnitError
        If the symbol is not registered.
    DimensionError
        If the unit's dimension differs from *expected*.
    """
    info = get_unit_info(unit_symbol)
    if info.dimension is not expected:
        raise DimensionError(unit_symbol, expected, info.dimension)
    return info


def check_quantity(value: float, unit_symbol: str, expected: Dimension) -> float:
    """
    Validate *unit_symbol* against *expected* and return *value* unchanged.

    Convenience wrapper for Pydantic field validators::

        @field_validator("mass")
        @classmethod
        def _check_mass(cls, v: float) -> float:
            return check_quantity(v, "kg", Dimension.mass)

    Raises
    ------
    UnknownUnitError, DimensionError
        See :func:`validate_unit_for_dimension`.
    """
    validate_unit_for_dimension(unit_symbol, expected)
    return value
