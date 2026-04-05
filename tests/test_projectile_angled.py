"""
Tests for angled-launch projectile support.

Coverage matrix
---------------
A. Template / parameter extraction
   1.  build_psdl with v0+theta yields correct v0x / v0z decomposition
   2.  build_psdl with v0+theta=0 equals original horizontal throw
   3.  build_psdl with explicit v0z (no theta) also works
   4.  Assumptions list updated for angled vs. horizontal throws
   5.  Source refs stay OpenStax / MIT OCW; no NIST / ITU
   6.  schema_version, scenario_type, ground_plane, gravity unchanged
   7.  include_derived_metrics=True with angled launch: max_height above height
   8.  include_derived_metrics=True with horizontal throw: max_height = height

B. Analytic solver (solve_projectile)
   9.  v0x / v0z decomposition is correct via solver
  10.  x(t) = v0x * t  (exact)
  11.  z(t) = height + v0z*t + ½ g_z t²  (exact)
  12.  vx(t) = v0x  (constant)
  13.  vz(t) = v0z + g_z * t  (linear)
  14.  45° launch: x_final = z_final when height=0, same duration

C. Derived metrics (angled projectile)
  15.  max_height > height when v0z > 0
  16.  max_height formula: height + v0z²/(2g)
  17.  range = x_final (same definition as horizontal throw)
  18.  time_of_flight = simulation duration
  19.  End-to-end dispatch_with_validation passes for angled projectile

D. Classifier / extractor (NL → params)
  20.  Chinese "以30度抛出" → theta_deg recognised
  21.  Chinese "仰角45°" → theta_deg recognised
  22.  English "at an angle of 30 degrees" → theta_deg recognised
  23.  English "launched at 45 degrees" → theta_deg recognised
  24.  Horizontal throw text (no angle) → v0z = 0
  25.  classify_scenario: "斜抛" → "projectile"
  26.  classify_scenario: "仰角" → "projectile"
  27.  classify_scenario: "launched at an angle" → "projectile"

E. Pipeline (classifier → template → dispatch → validation)
  28.  Horizontal throw text still passes full pipeline
  29.  free_fall path unaffected
"""

from __future__ import annotations

import math

import pytest

from src.physics.analytic import solve_projectile
from src.physics.dispatcher import dispatch_with_validation
from src.templates.extractor import extract_projectile_params
from src.templates.projectile import build_psdl
from src.llm.translator import classify_scenario
from src.validation.runner import run_validation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _states(x=0.0, y=0.0, z=0.0, vx=0.0, vy=0.0, vz=0.0):
    return [{"position": [x, y, z], "velocity": [vx, vy, vz]}]


# ---------------------------------------------------------------------------
# A. Template construction
# ---------------------------------------------------------------------------

class TestAngledProjectileTemplate:
    def test_v0_theta_decomposition(self):
        """v0 + theta → v0x = v0*cos(theta), v0z = v0*sin(theta)."""
        v0, theta_deg = 20.0, 30.0
        theta = math.radians(theta_deg)
        psdl = build_psdl(height=0.0, v0=v0, theta=theta)
        obj = psdl.objects[0]
        assert abs(obj.velocity[0] - v0 * math.cos(theta)) < 1e-9
        assert abs(obj.velocity[2] - v0 * math.sin(theta)) < 1e-9

    def test_v0_theta_zero_equals_horizontal(self):
        """v0 + theta=0 must yield v0x=v0, v0z=0 (horizontal throw)."""
        v0 = 15.0
        psdl_angled = build_psdl(height=5.0, v0=v0, theta=0.0)
        psdl_horiz = build_psdl(height=5.0, v0x=v0)
        obj_a = psdl_angled.objects[0]
        obj_h = psdl_horiz.objects[0]
        assert abs(obj_a.velocity[0] - obj_h.velocity[0]) < 1e-9
        assert abs(obj_a.velocity[2] - obj_h.velocity[2]) < 1e-9

    def test_explicit_v0z_works(self):
        """Caller can pass v0x and v0z directly without using v0/theta."""
        psdl = build_psdl(height=0.0, v0x=10.0, v0z=5.0)
        obj = psdl.objects[0]
        assert abs(obj.velocity[0] - 10.0) < 1e-9
        assert abs(obj.velocity[2] - 5.0) < 1e-9

    def test_assumptions_mention_angle_when_v0z_nonzero(self):
        """Angled launch should appear in assumptions."""
        psdl = build_psdl(height=0.0, v0=20.0, theta=math.radians(45.0))
        assert any("angled" in a.lower() for a in psdl.assumptions)

    def test_assumptions_mention_horizontal_when_v0z_zero(self):
        """Horizontal throw assumptions unchanged from original."""
        psdl = build_psdl(height=5.0, v0x=10.0)
        assert any("horizontal" in a.lower() for a in psdl.assumptions)

    def test_source_refs_no_nist_itu(self):
        """Source refs must not include NIST or ITU."""
        from src.schema.psdl import SourceRef
        psdl = build_psdl(height=0.0, v0=20.0, theta=math.radians(30.0))
        for ref in psdl.source_refs:
            if isinstance(ref, SourceRef):
                assert "nist" not in ref.source_id.lower()
                assert "itu" not in ref.source_id.lower()

    def test_source_refs_include_openstax(self):
        from src.schema.psdl import SourceRef
        psdl = build_psdl(height=5.0, v0=20.0, theta=math.radians(30.0))
        ids = [r.source_id for r in psdl.source_refs if isinstance(r, SourceRef)]
        assert any("openstax" in sid for sid in ids)

    def test_scenario_type_still_projectile(self):
        psdl = build_psdl(height=0.0, v0=10.0, theta=math.radians(45.0))
        assert psdl.scenario_type == "projectile"

    def test_gravity_unchanged(self):
        psdl = build_psdl(height=0.0, v0=10.0, theta=math.radians(45.0), g=9.8)
        assert abs(psdl.world.gravity[2] - (-9.8)) < 1e-9

    def test_ground_plane_false(self):
        psdl = build_psdl(height=5.0, v0=10.0, theta=math.radians(30.0))
        assert psdl.world.ground_plane is False

    def test_max_height_above_initial_when_v0z_positive(self):
        """include_derived_metrics: max_height > height when v0z > 0."""
        height, v0, theta_deg, g = 5.0, 20.0, 45.0, 9.8
        theta = math.radians(theta_deg)
        v0z = v0 * math.sin(theta)
        expected_max_h = height + v0z ** 2 / (2.0 * g)
        psdl = build_psdl(height=height, v0=v0, theta=theta, g=g,
                          include_derived_metrics=True)
        mh = next(t for t in psdl.validation_targets if t.name == "max_height")
        assert mh.expected_value == pytest.approx(expected_max_h, rel=1e-9)
        assert mh.expected_value > height

    def test_max_height_equals_height_for_horizontal(self):
        """Horizontal throw: max_height equals initial height."""
        height = 10.0
        psdl = build_psdl(height=height, v0x=10.0, include_derived_metrics=True)
        mh = next(t for t in psdl.validation_targets if t.name == "max_height")
        assert mh.expected_value == pytest.approx(height, rel=1e-9)

    def test_validation_targets_names(self):
        psdl = build_psdl(height=5.0, v0=20.0, theta=math.radians(30.0))
        names = {t.name for t in psdl.validation_targets}
        for expected in ("final_x", "final_z", "final_vx", "final_vz"):
            assert expected in names

    def test_psdl_model_validates(self):
        from src.schema.psdl import PSDL
        psdl = build_psdl(height=0.0, v0=20.0, theta=math.radians(45.0))
        assert isinstance(psdl, PSDL)


# ---------------------------------------------------------------------------
# B. Analytic solver
# ---------------------------------------------------------------------------

class TestSolveProjectileAngled:
    """solve_projectile handles angled launches because it reads v0x/v0z
    directly from the PSDL particle's velocity field."""

    def _psdl_45(self, v0=20.0, height=0.0, duration=1.0, g=9.8):
        theta = math.radians(45.0)
        return build_psdl(height=height, v0=v0, theta=theta, g=g, duration=duration)

    def test_vx_decomposition(self):
        """vx from solver equals v0 * cos(45°)."""
        v0 = 20.0
        psdl = self._psdl_45(v0=v0)
        states = solve_projectile(psdl)
        expected_vx = v0 * math.cos(math.radians(45.0))
        assert abs(states[0]["velocity"][0] - expected_vx) < 1e-5

    def test_x_position_exact(self):
        """x(t) = v0x * t."""
        v0, duration = 20.0, 2.0
        theta = math.radians(30.0)
        psdl = build_psdl(height=0.0, v0=v0, theta=theta, duration=duration)
        t = psdl.world.dt * psdl.world.steps
        states = solve_projectile(psdl)
        expected_x = v0 * math.cos(theta) * t
        assert abs(states[0]["position"][0] - expected_x) < 1e-5

    def test_z_position_exact(self):
        """z(t) = height + v0z*t + ½*g_z*t²."""
        v0, theta_deg, height, g, duration = 20.0, 45.0, 5.0, 9.8, 1.0
        theta = math.radians(theta_deg)
        psdl = build_psdl(height=height, v0=v0, theta=theta, g=g, duration=duration)
        t = psdl.world.dt * psdl.world.steps
        v0z = v0 * math.sin(theta)
        expected_z = height + v0z * t - 0.5 * g * t ** 2
        states = solve_projectile(psdl)
        assert abs(states[0]["position"][2] - expected_z) < 1e-5

    def test_vx_constant(self):
        """Horizontal velocity must be constant (no horizontal force)."""
        psdl = self._psdl_45(v0=20.0, duration=2.0)
        states = solve_projectile(psdl)
        expected_vx = 20.0 * math.cos(math.radians(45.0))
        assert abs(states[0]["velocity"][0] - expected_vx) < 1e-5

    def test_vz_linear(self):
        """vz(t) = v0z + g_z * t."""
        v0, theta_deg, g, duration = 20.0, 30.0, 9.8, 1.5
        theta = math.radians(theta_deg)
        psdl = build_psdl(height=0.0, v0=v0, theta=theta, g=g, duration=duration)
        t = psdl.world.dt * psdl.world.steps
        v0z = v0 * math.sin(theta)
        expected_vz = v0z - g * t
        states = solve_projectile(psdl)
        assert abs(states[0]["velocity"][2] - expected_vz) < 1e-5

    def test_45_degree_symmetry(self):
        """45° launch from height=0: x_final and z_final satisfy kinematics."""
        v0, g, duration = 20.0, 9.8, 1.0
        theta = math.radians(45.0)
        psdl = build_psdl(height=0.0, v0=v0, theta=theta, g=g, duration=duration)
        t = psdl.world.dt * psdl.world.steps
        states = solve_projectile(psdl)
        v0x = v0 * math.cos(theta)
        v0z = v0 * math.sin(theta)
        assert abs(states[0]["position"][0] - v0x * t) < 1e-5
        assert abs(states[0]["position"][2] - (v0z * t - 0.5 * g * t ** 2)) < 1e-5


# ---------------------------------------------------------------------------
# C. Derived metrics (angled)
# ---------------------------------------------------------------------------

class TestAngledDerivedMetrics:
    def test_max_height_greater_than_initial(self):
        """max_height > height when v0z > 0."""
        height, v0, theta_deg, g = 5.0, 20.0, 45.0, 9.8
        theta = math.radians(theta_deg)
        psdl = build_psdl(height=height, v0=v0, theta=theta, g=g,
                          include_derived_metrics=True)
        from src.physics.dispatcher import dispatch
        states = dispatch(psdl)
        results = run_validation(psdl, states)
        mh = next(r for r in results if r["target"] == "max_height")
        assert mh["observed"] > height
        assert mh["passed"], f"max_height FAIL: {mh['message']}"

    def test_max_height_formula(self):
        """max_height = height + v0z²/(2g) for v0z > 0."""
        height, v0, theta_deg, g = 2.0, 15.0, 30.0, 9.8
        theta = math.radians(theta_deg)
        v0z = v0 * math.sin(theta)
        expected = height + v0z ** 2 / (2.0 * g)
        psdl = build_psdl(height=height, v0=v0, theta=theta, g=g,
                          include_derived_metrics=True)
        from src.physics.dispatcher import dispatch
        states = dispatch(psdl)
        results = run_validation(psdl, states)
        mh = next(r for r in results if r["target"] == "max_height")
        assert mh["observed"] == pytest.approx(expected, rel=1e-6)

    def test_range_definition_consistent(self):
        """range = x_final - x0 (consistent with horizontal throw definition)."""
        v0, theta_deg, duration = 20.0, 30.0, 2.0
        theta = math.radians(theta_deg)
        psdl = build_psdl(height=5.0, v0=v0, theta=theta, duration=duration,
                          include_derived_metrics=True)
        from src.physics.dispatcher import dispatch
        states = dispatch(psdl)
        results = run_validation(psdl, states)
        rng = next(r for r in results if r["target"] == "range")
        assert rng["passed"], f"range FAIL: {rng['message']}"

    def test_time_of_flight(self):
        """time_of_flight = simulation duration."""
        duration = 2.5
        psdl = build_psdl(height=5.0, v0=20.0, theta=math.radians(45.0),
                          duration=duration, dt=0.01,
                          include_derived_metrics=True)
        from src.physics.dispatcher import dispatch
        states = dispatch(psdl)
        results = run_validation(psdl, states)
        tof = next(r for r in results if r["target"] == "time_of_flight")
        assert tof["observed"] == pytest.approx(duration, rel=1e-6)
        assert tof["passed"], f"time_of_flight FAIL: {tof['message']}"

    def test_dispatch_with_validation_angled_all_pass(self):
        """End-to-end: all targets pass for a 45° angled projectile."""
        psdl = build_psdl(height=5.0, v0=20.0, theta=math.radians(45.0),
                          duration=1.0, include_derived_metrics=True)
        result = dispatch_with_validation(psdl)
        for r in result["validation_results"]:
            assert r["passed"], f"Target {r['target']} FAILED: {r['message']}"


# ---------------------------------------------------------------------------
# D. Classifier / Extractor
# ---------------------------------------------------------------------------

class TestAngledExtractor:
    """extract_projectile_params recognises angle patterns."""

    def test_chinese_degree_pattern(self):
        """'以30度抛出' extracts theta and non-zero v0z."""
        text = "以20m/s的速度以30度角从高度5m处抛出，1秒后位置？"
        params = extract_projectile_params(text)
        assert params is not None, "Extraction returned None"
        assert abs(params["v0z"]) > 0.0, "v0z should be non-zero for angled throw"
        theta = math.radians(30.0)
        expected_v0z = 20.0 * math.sin(theta)
        assert abs(params["v0z"] - expected_v0z) < 0.01

    def test_chinese_elevation_angle(self):
        """'仰角45°' extracts theta correctly."""
        text = "以15m/s的初速度、仰角45°从5米高处斜抛，求2秒后的位置。"
        params = extract_projectile_params(text)
        assert params is not None
        assert abs(params["v0z"]) > 0.0

    def test_english_angle_of(self):
        """'at an angle of 30 degrees' → non-zero v0z."""
        text = "A ball is launched at an angle of 30 degrees from height 10m with speed 20 m/s after 1s."
        params = extract_projectile_params(text)
        assert params is not None
        assert abs(params["v0z"]) > 0.0

    def test_english_launched_at(self):
        """'launched at 45 degrees' → non-zero v0z."""
        text = "Object launched at 45 degrees with speed 10 m/s from height 5m, find position after 1s."
        params = extract_projectile_params(text)
        assert params is not None
        assert abs(params["v0z"]) > 0.0

    def test_horizontal_throw_has_zero_v0z(self):
        """Text without angle → v0z = 0 (backward compatible)."""
        text = "以10m/s水平速度从高度5m处抛出，2秒后位置？"
        params = extract_projectile_params(text)
        assert params is not None
        assert params["v0z"] == pytest.approx(0.0, abs=1e-9)

    def test_v0z_key_present_in_result(self):
        """Extractor always returns 'v0z' key."""
        text = "以10m/s水平抛出，高度5m，1秒后？"
        params = extract_projectile_params(text)
        assert params is not None
        assert "v0z" in params


class TestAngledClassifier:
    """classify_scenario handles angled projectile patterns."""

    def test_classify_xie_pao(self):
        assert classify_scenario("斜抛运动，初速度20m/s，仰角30度") == "projectile"

    def test_classify_yang_jiao(self):
        assert classify_scenario("仰角45°以20m/s速度抛出") == "projectile"

    def test_classify_english_angle(self):
        assert classify_scenario("launched at an angle of 30 degrees") == "projectile"

    def test_classify_launched_at_45(self):
        assert classify_scenario("A ball launched at 45 degrees with 20 m/s") == "projectile"


# ---------------------------------------------------------------------------
# E. Pipeline compatibility
# ---------------------------------------------------------------------------

class TestPipelineCompatibility:
    def test_horizontal_throw_pipeline_still_passes(self):
        """Original horizontal-throw path remains unbroken."""
        from src.templates.projectile import build_psdl as proj_build
        psdl = proj_build(height=10.0, v0x=5.0, duration=1.0,
                          include_derived_metrics=True)
        result = dispatch_with_validation(psdl)
        for r in result["validation_results"]:
            assert r["passed"], f"Target {r['target']} FAILED: {r['message']}"

    def test_free_fall_unaffected(self):
        """free_fall path must not be changed by projectile extension."""
        from src.templates.free_fall import build_psdl as ff_build
        psdl = ff_build(height=5.0, duration=1.0, include_derived_metrics=True)
        result = dispatch_with_validation(psdl)
        for r in result["validation_results"]:
            assert r["passed"], f"Target {r['target']} FAILED: {r['message']}"

    def test_angled_projectile_pipeline_e2e(self):
        """Full pipeline for a 45° angled projectile passes all targets."""
        psdl = build_psdl(
            height=5.0, v0=20.0, theta=math.radians(45.0),
            g=9.8, duration=1.0,
            include_derived_metrics=True,
        )
        result = dispatch_with_validation(psdl)
        from src.physics.dispatcher import SOLVER_ANALYTIC_PROJECTILE
        assert result["solver_used"] == SOLVER_ANALYTIC_PROJECTILE
        for r in result["validation_results"]:
            assert r["passed"], f"Target {r['target']} FAILED: {r['message']}"

    def test_extractor_output_feeds_template(self):
        """Extractor output can be passed directly to build_psdl."""
        text = "以20m/s的速度以30度角从高度5m处斜抛，1秒后位置？"
        params = extract_projectile_params(text)
        assert params is not None
        psdl = build_psdl(**params)
        assert psdl.scenario_type == "projectile"
        assert psdl.objects[0].velocity[2] != 0.0  # v0z non-zero
