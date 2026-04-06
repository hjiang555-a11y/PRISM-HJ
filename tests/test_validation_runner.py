"""
Tests for the ValidationTarget auto-execution runner
(src/validation/runner.py).
"""

from __future__ import annotations

import pytest

from src.schema.psdl import ValidationTarget
from src.physics.templates.free_fall import build_psdl
from src.validation.runner import run_validation, _EXTRACTORS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_states(x=0.0, y=0.0, z=0.0, vx=0.0, vy=0.0, vz=0.0):
    return [{"position": [x, y, z], "velocity": [vx, vy, vz]}]


# ---------------------------------------------------------------------------
# Tests: extractor registry
# ---------------------------------------------------------------------------

class TestExtractors:
    def test_known_names_registered(self):
        for name in ("final_x", "final_y", "final_z", "final_vx", "final_vy", "final_vz"):
            assert name in _EXTRACTORS

    def test_final_z_extracts_correctly(self):
        states = _make_states(z=3.14)
        assert _EXTRACTORS["final_z"](states) == pytest.approx(3.14)

    def test_final_vz_extracts_correctly(self):
        states = _make_states(vz=-9.8)
        assert _EXTRACTORS["final_vz"](states) == pytest.approx(-9.8)

    def test_final_x_extracts_correctly(self):
        states = _make_states(x=1.5)
        assert _EXTRACTORS["final_x"](states) == pytest.approx(1.5)

    def test_empty_states_returns_none(self):
        assert _EXTRACTORS["final_z"]([]) is None


# ---------------------------------------------------------------------------
# Tests: run_validation output structure
# ---------------------------------------------------------------------------

class TestRunValidationOutputStructure:
    def test_returns_list(self):
        psdl = build_psdl(height=5.0, duration=1.0)
        states = _make_states(z=0.1, vz=-9.8)
        results = run_validation(psdl, states)
        assert isinstance(results, list)

    def test_result_has_required_keys(self):
        psdl = build_psdl(height=5.0, duration=1.0)
        states = _make_states(z=0.1, vz=-9.8)
        results = run_validation(psdl, states)
        required_keys = {"target", "passed", "observed", "expected", "unit",
                         "tolerance", "message"}
        for r in results:
            assert required_keys.issubset(r.keys()), (
                f"Result missing keys: {required_keys - r.keys()}"
            )

    def test_result_count_matches_targets(self):
        psdl = build_psdl(height=5.0, duration=1.0)
        states = _make_states(z=0.1, vz=-9.8)
        results = run_validation(psdl, states)
        assert len(results) == len(psdl.validation_targets)

    def test_no_targets_returns_empty_list(self):
        from src.schema.psdl import PSDL, WorldSettings, ParticleObject
        psdl = PSDL(
            scenario_type="free_fall",
            validation_targets=[],
            world=WorldSettings(),
            objects=[ParticleObject()],
        )
        results = run_validation(psdl, _make_states())
        assert results == []


# ---------------------------------------------------------------------------
# Tests: pass / fail logic
# ---------------------------------------------------------------------------

class TestFreeFallValidationPassFail:
    """Run validation on the free_fall template with exact and wrong values."""

    def test_exact_values_both_pass(self):
        # height=5.0, duration=1.0, g=9.8 → z=0.1, vz=-9.8
        psdl = build_psdl(height=5.0, duration=1.0, g=9.8)
        states = _make_states(z=0.1, vz=-9.8)
        results = run_validation(psdl, states)
        for r in results:
            assert r["passed"], f"Expected PASS but got FAIL: {r['message']}"

    def test_wrong_z_fails(self):
        psdl = build_psdl(height=5.0, duration=1.0, g=9.8)
        # z is way off — should fail
        states = _make_states(z=99.0, vz=-9.8)
        results = run_validation(psdl, states)
        z_result = next(r for r in results if r["target"] == "final_z")
        assert not z_result["passed"]

    def test_wrong_vz_fails(self):
        psdl = build_psdl(height=5.0, duration=1.0, g=9.8)
        # vz is way off — should fail
        states = _make_states(z=0.1, vz=100.0)
        results = run_validation(psdl, states)
        vz_result = next(r for r in results if r["target"] == "final_vz")
        assert not vz_result["passed"]

    def test_small_deviation_within_tolerance_passes(self):
        psdl = build_psdl(height=5.0, duration=1.0, g=9.8,
                          validation_tolerance_pct=1.0)
        # z=0.1 ± 0.5% (within 1% tolerance)
        states = _make_states(z=0.1005, vz=-9.8)
        results = run_validation(psdl, states)
        z_result = next(r for r in results if r["target"] == "final_z")
        assert z_result["passed"]

    def test_deviation_beyond_tolerance_fails(self):
        psdl = build_psdl(height=5.0, duration=1.0, g=9.8,
                          validation_tolerance_pct=1.0)
        # z=0.1 × 1.05 = 0.105 → 5% off → should fail at 1% tol
        states = _make_states(z=0.105, vz=-9.8)
        results = run_validation(psdl, states)
        z_result = next(r for r in results if r["target"] == "final_z")
        assert not z_result["passed"]


class TestValidationWithUnknownTargetName:
    def test_unknown_target_fails_gracefully(self):
        from src.schema.psdl import PSDL, WorldSettings, ParticleObject
        psdl = PSDL(
            scenario_type="free_fall",
            validation_targets=[
                ValidationTarget(
                    name="unknown_quantity",
                    expected_value=42.0,
                    tolerance_pct=1.0,
                    unit="m",
                    dimension="length",
                )
            ],
            world=WorldSettings(),
            objects=[ParticleObject()],
        )
        results = run_validation(psdl, _make_states())
        assert len(results) == 1
        assert not results[0]["passed"]
        assert "No extractor" in results[0]["message"]


class TestValidationWithEmptyStates:
    def test_empty_states_all_fail(self):
        psdl = build_psdl(height=5.0, duration=1.0)
        results = run_validation(psdl, [])
        for r in results:
            assert not r["passed"]
            assert r["observed"] is None


# ---------------------------------------------------------------------------
# Tests: result field types and values
# ---------------------------------------------------------------------------

class TestResultFieldTypes:
    def test_passed_is_bool(self):
        psdl = build_psdl()
        states = _make_states(z=0.1, vz=-9.8)
        results = run_validation(psdl, states)
        for r in results:
            assert isinstance(r["passed"], bool)

    def test_observed_is_float_or_none(self):
        psdl = build_psdl()
        states = _make_states(z=0.1, vz=-9.8)
        results = run_validation(psdl, states)
        for r in results:
            assert r["observed"] is None or isinstance(r["observed"], float)

    def test_message_is_nonempty_string(self):
        psdl = build_psdl()
        states = _make_states(z=0.1, vz=-9.8)
        results = run_validation(psdl, states)
        for r in results:
            assert isinstance(r["message"], str) and len(r["message"]) > 0
