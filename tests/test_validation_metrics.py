"""
Tests for derived validation metrics: max_height, range, time_of_flight.

Coverage matrix
---------------
A. Runner layer — extractor registry
   1. max_height registered in _PSDL_EXTRACTORS
   2. range registered in _PSDL_EXTRACTORS
   3. time_of_flight registered in _PSDL_EXTRACTORS

B. free_fall scenarios
   4. max_height — pure drop (v0z=0): equals initial height
   5. max_height — upward throw (v0z>0): z0 + v0z²/(2g)
   6. range — pure vertical motion: 0.0
   7. time_of_flight — correct simulation duration

C. projectile (horizontal throw) scenarios
   8. range — equals v0x × t
   9. time_of_flight — correct simulation duration
  10. max_height — equals initial height (v0z=0)

D. Pipeline / compatibility
  11. Existing final_x / final_z / final_vx / final_vz targets unaffected
  12. include_derived_metrics=False (default) keeps original target count
  13. Derived metrics pass end-to-end via dispatch_with_validation
  14. Unknown target name still fails gracefully (regression guard)
"""

from __future__ import annotations

import pytest

from src.physics.legacy.dispatcher import dispatch_with_validation
from src.physics.legacy.templates.free_fall import build_psdl as ff_build
from src.physics.legacy.templates.projectile import build_psdl as proj_build
from src.validation.runner import _PSDL_EXTRACTORS, run_validation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _states(x=0.0, y=0.0, z=0.0, vx=0.0, vy=0.0, vz=0.0):
    return [{"position": [x, y, z], "velocity": [vx, vy, vz]}]


# ---------------------------------------------------------------------------
# A. Runner layer — registry
# ---------------------------------------------------------------------------

class TestPSDLExtractorRegistry:
    def test_max_height_registered(self):
        assert "max_height" in _PSDL_EXTRACTORS

    def test_range_registered(self):
        assert "range" in _PSDL_EXTRACTORS

    def test_time_of_flight_registered(self):
        assert "time_of_flight" in _PSDL_EXTRACTORS


# ---------------------------------------------------------------------------
# B. free_fall derived metrics
# ---------------------------------------------------------------------------

class TestFreeFallDerivedMetrics:
    """Validate derived metrics for the free_fall template."""

    def test_max_height_pure_drop(self):
        """Pure drop: v0z=0, max_height should equal initial height."""
        psdl = ff_build(height=10.0, v0z=0.0, duration=1.0,
                        include_derived_metrics=True)
        states = _states(z=0.2)  # final z after drop (not used for max_height)
        results = run_validation(psdl, states)
        mh = next(r for r in results if r["target"] == "max_height")
        assert mh["passed"], f"Expected PASS: {mh['message']}"
        assert mh["observed"] == pytest.approx(10.0)

    def test_max_height_upward_throw(self):
        """Upward throw: v0z>0, max_height = z0 + v0z²/(2g)."""
        h, v0z, g = 0.0, 10.0, 9.8
        expected_max_h = h + v0z ** 2 / (2.0 * g)
        psdl = ff_build(height=h, v0z=v0z, g=g, duration=0.5,
                        include_derived_metrics=True)
        states = _states(z=0.0)
        results = run_validation(psdl, states)
        mh = next(r for r in results if r["target"] == "max_height")
        assert mh["observed"] == pytest.approx(expected_max_h, rel=1e-6)
        assert mh["passed"], f"Expected PASS: {mh['message']}"

    def test_range_free_fall_is_zero(self):
        """Pure vertical free-fall: no horizontal displacement → range = 0."""
        psdl = ff_build(height=5.0, duration=1.0,
                        include_derived_metrics=True)
        states = _states(x=0.0, z=0.1)
        results = run_validation(psdl, states)
        rng = next(r for r in results if r["target"] == "range")
        assert rng["observed"] == pytest.approx(0.0, abs=1e-9)
        # expected_value is 0; check() uses absolute comparison for zero
        assert rng["passed"], f"Expected PASS: {rng['message']}"

    def test_time_of_flight_free_fall(self):
        """time_of_flight = dt × steps = simulation duration."""
        psdl = ff_build(height=5.0, duration=2.0, dt=0.01,
                        include_derived_metrics=True)
        states = _states(z=-14.6)
        results = run_validation(psdl, states)
        tof = next(r for r in results if r["target"] == "time_of_flight")
        assert tof["observed"] == pytest.approx(2.0, rel=1e-6)
        assert tof["passed"], f"Expected PASS: {tof['message']}"

    def test_derived_metrics_count(self):
        """include_derived_metrics=True adds 3 extra targets."""
        psdl_base = ff_build(height=5.0, duration=1.0)
        psdl_with = ff_build(height=5.0, duration=1.0,
                             include_derived_metrics=True)
        assert len(psdl_with.validation_targets) == len(psdl_base.validation_targets) + 3

    def test_include_derived_metrics_false_keeps_default(self):
        """Default (False) must not alter existing target count."""
        psdl_default = ff_build(height=5.0, duration=1.0)
        psdl_false = ff_build(height=5.0, duration=1.0,
                              include_derived_metrics=False)
        assert len(psdl_default.validation_targets) == len(psdl_false.validation_targets)


# ---------------------------------------------------------------------------
# C. projectile derived metrics
# ---------------------------------------------------------------------------

class TestProjectileDerivedMetrics:
    """Validate derived metrics for the projectile (horizontal throw) template."""

    def test_range_projectile(self):
        """Horizontal range = v0x × t."""
        v0x, duration = 10.0, 2.0
        expected_range = v0x * duration   # = 20.0 m
        psdl = proj_build(height=20.0, v0x=v0x, duration=duration,
                          include_derived_metrics=True)
        # Simulate: final x = v0x*t = 20.0
        states = _states(x=expected_range, z=0.4)
        results = run_validation(psdl, states)
        rng = next(r for r in results if r["target"] == "range")
        assert rng["observed"] == pytest.approx(expected_range, rel=1e-6)
        assert rng["passed"], f"Expected PASS: {rng['message']}"

    def test_time_of_flight_projectile(self):
        """time_of_flight = simulation duration."""
        psdl = proj_build(height=10.0, v0x=5.0, duration=1.5, dt=0.01,
                          include_derived_metrics=True)
        states = _states(x=7.5, z=0.0)
        results = run_validation(psdl, states)
        tof = next(r for r in results if r["target"] == "time_of_flight")
        assert tof["observed"] == pytest.approx(1.5, rel=1e-6)
        assert tof["passed"], f"Expected PASS: {tof['message']}"

    def test_max_height_horizontal_throw(self):
        """Horizontal throw has v0z=0: max_height equals initial height."""
        height = 15.0
        psdl = proj_build(height=height, v0x=10.0, duration=1.0,
                          include_derived_metrics=True)
        states = _states(x=10.0, z=0.1)
        results = run_validation(psdl, states)
        mh = next(r for r in results if r["target"] == "max_height")
        assert mh["observed"] == pytest.approx(height, rel=1e-6)
        assert mh["passed"], f"Expected PASS: {mh['message']}"

    def test_derived_metrics_count_projectile(self):
        """include_derived_metrics=True adds 3 extra targets."""
        psdl_base = proj_build(height=5.0, duration=1.0)
        psdl_with = proj_build(height=5.0, duration=1.0,
                               include_derived_metrics=True)
        assert len(psdl_with.validation_targets) == len(psdl_base.validation_targets) + 3

    def test_include_derived_metrics_false_projectile_keeps_default(self):
        """Default (False) must not alter existing target count."""
        psdl_default = proj_build(height=5.0, duration=1.0)
        psdl_false = proj_build(height=5.0, duration=1.0,
                                include_derived_metrics=False)
        assert len(psdl_default.validation_targets) == len(psdl_false.validation_targets)


# ---------------------------------------------------------------------------
# D. Pipeline / compatibility
# ---------------------------------------------------------------------------

class TestDerivedMetricsPipelineCompatibility:
    """Ensure new metrics co-exist with existing targets and pipeline."""

    def test_existing_final_targets_unaffected_free_fall(self):
        """final_z and final_vz still present and named correctly."""
        psdl = ff_build(height=5.0, duration=1.0,
                        include_derived_metrics=True)
        names = [t.name for t in psdl.validation_targets]
        assert "final_z" in names
        assert "final_vz" in names

    def test_existing_final_targets_unaffected_projectile(self):
        """final_x, final_z, final_vx, final_vz still present."""
        psdl = proj_build(height=5.0, duration=1.0,
                          include_derived_metrics=True)
        names = [t.name for t in psdl.validation_targets]
        for expected_name in ("final_x", "final_z", "final_vx", "final_vz"):
            assert expected_name in names

    def test_dispatch_with_validation_free_fall_derived(self):
        """End-to-end: dispatch_with_validation passes all targets including derived."""
        psdl = ff_build(height=5.0, duration=1.0,
                        include_derived_metrics=True)
        result = dispatch_with_validation(psdl)
        vr = result["validation_results"]
        # All targets should pass (analytic solver → exact results)
        for r in vr:
            assert r["passed"], f"Target {r['target']} FAILED: {r['message']}"

    def test_dispatch_with_validation_projectile_derived(self):
        """End-to-end: dispatch_with_validation passes all targets including derived."""
        psdl = proj_build(height=10.0, v0x=5.0, duration=1.0,
                          include_derived_metrics=True)
        result = dispatch_with_validation(psdl)
        vr = result["validation_results"]
        for r in vr:
            assert r["passed"], f"Target {r['target']} FAILED: {r['message']}"

    def test_unknown_target_still_fails_gracefully(self):
        """Regression: unknown target name still returns passed=False."""
        from src.schema.psdl import PSDL, WorldSettings, ParticleObject, ValidationTarget
        psdl = PSDL(
            scenario_type="free_fall",
            validation_targets=[
                ValidationTarget(
                    name="nonexistent_metric",
                    expected_value=1.0,
                    tolerance_pct=1.0,
                    unit="m",
                    dimension="length",
                )
            ],
            world=WorldSettings(),
            objects=[ParticleObject()],
        )
        results = run_validation(psdl, _states())
        assert len(results) == 1
        assert not results[0]["passed"]
        assert "No extractor" in results[0]["message"]
