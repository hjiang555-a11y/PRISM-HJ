"""
Tests for PSDL v0.1 schema fields and unit/dimension integration.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schema.psdl import PSDL, ValidationTarget, WorldSettings
from src.schema.units import Dimension


class TestSchemaVersion:
    def test_default_schema_version(self):
        psdl = PSDL()
        assert psdl.schema_version == "0.1"

    def test_custom_schema_version(self):
        psdl = PSDL(schema_version="0.2")
        assert psdl.schema_version == "0.2"


class TestScenarioType:
    def test_default_is_none(self):
        psdl = PSDL()
        assert psdl.scenario_type is None

    def test_free_fall_scenario_type(self):
        psdl = PSDL(scenario_type="free_fall")
        assert psdl.scenario_type == "free_fall"


class TestAssumptions:
    def test_default_empty(self):
        psdl = PSDL()
        assert psdl.assumptions == []

    def test_custom_assumptions(self):
        assumptions = ["no air resistance", "point mass"]
        psdl = PSDL(assumptions=assumptions)
        assert psdl.assumptions == assumptions


class TestSourceRefs:
    def test_default_empty(self):
        assert PSDL().source_refs == []

    def test_with_refs(self):
        refs = ["Halliday Ch.2 Problem 5"]
        psdl = PSDL(source_refs=refs)
        assert psdl.source_refs == refs


class TestValidationTarget:
    def test_basic_construction(self):
        vt = ValidationTarget(
            name="final_z",
            expected_value=0.1,
            tolerance_pct=1.0,
            unit="m",
            dimension="length",
        )
        assert vt.name == "final_z"
        assert vt.unit == "m"
        assert vt.dimension == "length"

    def test_unknown_unit_raises(self):
        with pytest.raises(ValidationError):
            ValidationTarget(
                name="bad_unit",
                expected_value=1.0,
                unit="furlong",
                dimension="length",
            )

    def test_unknown_dimension_raises(self):
        with pytest.raises(ValidationError):
            ValidationTarget(
                name="bad_dim",
                expected_value=1.0,
                unit="m",
                dimension="energy",  # not in v0.1
            )

    def test_check_within_tolerance(self):
        vt = ValidationTarget(
            name="z", expected_value=5.0, tolerance_pct=5.0, unit="m", dimension="length"
        )
        assert vt.check(5.0)
        assert vt.check(5.24)   # exactly 5% above
        assert not vt.check(5.26)  # just over 5%

    def test_check_zero_expected(self):
        vt = ValidationTarget(name="vx", expected_value=0.0, tolerance_pct=1.0, unit="m/s", dimension="velocity")
        assert vt.check(0.005)   # within 1% of 1.0 (tolerance_pct/100)
        assert not vt.check(0.02)


class TestValidationTargetsInPSDL:
    def test_psdl_with_targets(self):
        psdl = PSDL(
            scenario_type="free_fall",
            validation_targets=[
                ValidationTarget(
                    name="final_z",
                    expected_value=0.1,
                    tolerance_pct=1.0,
                    unit="m",
                    dimension="length",
                )
            ],
        )
        assert len(psdl.validation_targets) == 1
        assert psdl.validation_targets[0].name == "final_z"


class TestGroundPlaneExplicit:
    def test_default_no_ground_plane(self):
        assert PSDL().world.ground_plane is False

    def test_explicit_ground_plane_true(self):
        psdl = PSDL(world=WorldSettings(ground_plane=True))
        assert psdl.world.ground_plane is True

    def test_gravity_wrong_length_raises(self):
        with pytest.raises(ValidationError):
            WorldSettings(gravity=[0.0, -9.8])  # only 2 components
