"""
Tests for the src.schema.units module.

Verifies dimension enumeration, unit registry, and validation functions.
"""

from __future__ import annotations

import pytest

from src.schema.units import (
    Dimension,
    DimensionError,
    UnknownUnitError,
    UNITS,
    check_quantity,
    get_unit_info,
    validate_unit_for_dimension,
)


class TestUnitRegistry:
    """All expected SI symbols must be present and correctly classified."""

    @pytest.mark.parametrize("symbol,expected_dim", [
        ("m",     Dimension.length),
        ("kg",    Dimension.mass),
        ("s",     Dimension.time),
        ("m/s",   Dimension.velocity),
        ("m/s^2", Dimension.acceleration),
        ("N",     Dimension.force),
        ("1",     Dimension.dimensionless),
    ])
    def test_unit_dimension(self, symbol: str, expected_dim: Dimension):
        info = UNITS[symbol]
        assert info.dimension is expected_dim

    def test_all_seven_units_registered(self):
        assert len(UNITS) == 7

    def test_get_unit_info_known(self):
        info = get_unit_info("m/s^2")
        assert info.symbol == "m/s^2"
        assert info.dimension is Dimension.acceleration

    def test_get_unit_info_unknown_raises(self):
        with pytest.raises(UnknownUnitError):
            get_unit_info("ft")


class TestValidateUnitForDimension:
    """validate_unit_for_dimension must accept compatible and reject incompatible pairs."""

    def test_compatible_passes(self):
        info = validate_unit_for_dimension("m", Dimension.length)
        assert info.dimension is Dimension.length

    def test_incompatible_raises_dimension_error(self):
        with pytest.raises(DimensionError) as exc_info:
            validate_unit_for_dimension("kg", Dimension.length)
        err = exc_info.value
        assert err.unit_symbol == "kg"
        assert err.expected is Dimension.length
        assert err.got is Dimension.mass

    def test_unknown_symbol_raises_unknown_unit_error(self):
        with pytest.raises(UnknownUnitError):
            validate_unit_for_dimension("lb", Dimension.mass)

    @pytest.mark.parametrize("symbol,dim", [
        ("m",     Dimension.length),
        ("kg",    Dimension.mass),
        ("s",     Dimension.time),
        ("m/s",   Dimension.velocity),
        ("m/s^2", Dimension.acceleration),
        ("N",     Dimension.force),
        ("1",     Dimension.dimensionless),
    ])
    def test_all_correct_pairs_pass(self, symbol: str, dim: Dimension):
        info = validate_unit_for_dimension(symbol, dim)
        assert info.dimension is dim


class TestCheckQuantity:
    def test_returns_value_unchanged(self):
        result = check_quantity(9.8, "m/s^2", Dimension.acceleration)
        assert result == 9.8

    def test_wrong_dimension_raises(self):
        with pytest.raises(DimensionError):
            check_quantity(1.0, "m/s", Dimension.acceleration)

    def test_unknown_unit_raises(self):
        with pytest.raises(UnknownUnitError):
            check_quantity(1.0, "mph", Dimension.velocity)


class TestDimensionEnum:
    def test_all_dimensions_accessible(self):
        expected = {
            "length", "mass", "time", "velocity",
            "acceleration", "force", "dimensionless",
        }
        actual = {d.value for d in Dimension}
        assert actual == expected

    def test_dimension_string_values(self):
        assert Dimension.acceleration.value == "acceleration"
        assert Dimension.dimensionless.value == "dimensionless"
