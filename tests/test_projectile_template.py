"""
Tests for the projectile scenario template (src.physics.templates.projectile).

Verifies:
* Template structure is valid (PSDL schema compliant).
* Analytic validation targets are correctly pre-computed.
* Default source refs comply with governance (tier_1, not NIST/ITU).
* solve_projectile returns exact kinematic results.
* dispatch routes "projectile" to the analytic solver.
"""

from __future__ import annotations

import pytest

from src.physics.analytic import solve_projectile
from src.physics.dispatcher import (
    SOLVER_ANALYTIC_PROJECTILE,
    dispatch,
    dispatch_with_validation,
    select_solver,
)
from src.schema.psdl import PSDL, ParticleObject, SourceRef
from src.physics.templates import projectile as proj_template


# ---------------------------------------------------------------------------
# Template structure
# ---------------------------------------------------------------------------

class TestProjectileTemplateStructure:
    def test_scenario_type_is_projectile(self):
        psdl = proj_template.build_psdl()
        assert psdl.scenario_type == "projectile"

    def test_schema_version(self):
        psdl = proj_template.build_psdl()
        assert psdl.schema_version == "0.1"

    def test_has_one_particle(self):
        psdl = proj_template.build_psdl()
        assert len(psdl.objects) == 1
        assert isinstance(psdl.objects[0], ParticleObject)

    def test_initial_position_uses_height(self):
        psdl = proj_template.build_psdl(height=12.0)
        assert abs(psdl.objects[0].position[2] - 12.0) < 1e-9

    def test_initial_velocity_uses_v0x(self):
        psdl = proj_template.build_psdl(v0x=5.0)
        assert abs(psdl.objects[0].velocity[0] - 5.0) < 1e-9

    def test_no_initial_vertical_velocity(self):
        psdl = proj_template.build_psdl()
        assert psdl.objects[0].velocity[2] == 0.0

    def test_gravity_is_downward(self):
        psdl = proj_template.build_psdl(g=9.8)
        assert abs(psdl.world.gravity[2] - (-9.8)) < 1e-9

    def test_ground_plane_false_by_default(self):
        psdl = proj_template.build_psdl()
        assert psdl.world.ground_plane is False

    def test_assumptions_list_not_empty(self):
        psdl = proj_template.build_psdl()
        assert len(psdl.assumptions) > 0

    def test_no_air_resistance_assumption(self):
        psdl = proj_template.build_psdl()
        assert any("air resistance" in a.lower() for a in psdl.assumptions)

    def test_validation_targets_present(self):
        psdl = proj_template.build_psdl()
        assert len(psdl.validation_targets) >= 2

    def test_validation_target_names(self):
        psdl = proj_template.build_psdl()
        names = {t.name for t in psdl.validation_targets}
        assert "final_x" in names
        assert "final_z" in names

    def test_units_are_si(self):
        psdl = proj_template.build_psdl()
        for target in psdl.validation_targets:
            assert target.unit in ("m", "m/s", "kg", "s", "m/s^2", "N")

    def test_source_refs_present(self):
        psdl = proj_template.build_psdl()
        assert len(psdl.source_refs) >= 1

    def test_default_primary_source_is_openstax(self):
        psdl = proj_template.build_psdl()
        primary = [
            r for r in psdl.source_refs
            if isinstance(r, SourceRef) and r.role == "primary_template_source"
        ]
        assert len(primary) == 1
        assert "openstax" in primary[0].source_id

    def test_nist_not_in_default_source_refs(self):
        psdl = proj_template.build_psdl()
        for ref in psdl.source_refs:
            if isinstance(ref, SourceRef):
                assert "nist" not in ref.source_id.lower()
                assert "itu" not in ref.source_id.lower()

    def test_psdl_model_validates(self):
        """Template output passes Pydantic PSDL schema validation."""
        psdl = proj_template.build_psdl()
        assert isinstance(psdl, PSDL)

    def test_module_has_scenario_type_constant(self):
        assert proj_template.scenario_type == "projectile"


# ---------------------------------------------------------------------------
# Validation targets — analytic correctness
# ---------------------------------------------------------------------------

class TestProjectileValidationTargets:
    def test_final_x_correct(self):
        """x(t) = v0x · t"""
        psdl = proj_template.build_psdl(height=10.0, v0x=5.0, duration=2.0)
        target_x = next(t for t in psdl.validation_targets if t.name == "final_x")
        expected = 5.0 * 2.0  # 10 m
        assert abs(target_x.expected_value - expected) < 1e-9

    def test_final_z_correct(self):
        """z(t) = h − ½ g t²"""
        g, h, t = 9.8, 10.0, 2.0
        psdl = proj_template.build_psdl(height=h, v0x=5.0, g=g, duration=t)
        target_z = next(t for t in psdl.validation_targets if t.name == "final_z")
        expected = h - 0.5 * g * (2.0 ** 2)  # 10 - 19.6 = -9.6 m
        assert abs(target_z.expected_value - expected) < 1e-9

    def test_final_vx_equals_v0x(self):
        """vx is constant — no horizontal force."""
        psdl = proj_template.build_psdl(v0x=8.0, duration=3.0)
        target_vx = next(t for t in psdl.validation_targets if t.name == "final_vx")
        assert abs(target_vx.expected_value - 8.0) < 1e-9

    def test_final_vz_correct(self):
        """vz(t) = −g · t"""
        g, t = 9.8, 1.5
        psdl = proj_template.build_psdl(g=g, duration=t)
        target_vz = next(t for t in psdl.validation_targets if t.name == "final_vz")
        expected = -g * 1.5
        assert abs(target_vz.expected_value - expected) < 1e-9


# ---------------------------------------------------------------------------
# Analytic solver — solve_projectile
# ---------------------------------------------------------------------------

class TestSolveProjectile:
    def test_horizontal_position_exact(self):
        """x(1s) = v0x · 1 = v0x."""
        psdl = proj_template.build_psdl(height=10.0, v0x=5.0, duration=1.0)
        states = solve_projectile(psdl)
        assert abs(states[0]["position"][0] - 5.0) < 1e-9

    def test_vertical_position_exact(self):
        """z(1s) = 10 − ½ · 9.8 · 1² = 5.1 m."""
        psdl = proj_template.build_psdl(height=10.0, v0x=5.0, g=9.8, duration=1.0)
        states = solve_projectile(psdl)
        expected_z = 10.0 - 0.5 * 9.8 * 1.0
        assert abs(states[0]["position"][2] - expected_z) < 1e-9

    def test_horizontal_velocity_unchanged(self):
        """Horizontal velocity remains constant (no horizontal force)."""
        psdl = proj_template.build_psdl(v0x=7.3, duration=2.0)
        states = solve_projectile(psdl)
        assert abs(states[0]["velocity"][0] - 7.3) < 1e-9

    def test_vertical_velocity_exact(self):
        """vz(t) = −g · t."""
        g, t = 9.8, 1.5
        psdl = proj_template.build_psdl(g=g, duration=t)
        states = solve_projectile(psdl)
        expected_vz = -g * t
        assert abs(states[0]["velocity"][2] - expected_vz) < 1e-9

    def test_mass_independence(self):
        """Projectile trajectory is mass-independent (equivalence principle)."""
        psdl_light = proj_template.build_psdl(mass=0.1, v0x=5.0, duration=1.0)
        psdl_heavy = proj_template.build_psdl(mass=100.0, v0x=5.0, duration=1.0)
        z_light = solve_projectile(psdl_light)[0]["position"][2]
        z_heavy = solve_projectile(psdl_heavy)[0]["position"][2]
        assert abs(z_light - z_heavy) < 1e-9

    def test_no_particles_raises(self):
        from src.schema.psdl import WorldSettings
        psdl = PSDL(
            scenario_type="projectile",
            world=WorldSettings(gravity=[0.0, 0.0, -9.8], dt=0.01, steps=100),
            objects=[],
        )
        with pytest.raises(ValueError, match="no ParticleObject"):
            solve_projectile(psdl)

    def test_return_format(self):
        psdl = proj_template.build_psdl()
        states = solve_projectile(psdl)
        assert len(states) == 1
        assert "position" in states[0]
        assert "velocity" in states[0]
        assert len(states[0]["position"]) == 3
        assert len(states[0]["velocity"]) == 3


# ---------------------------------------------------------------------------
# Dispatcher integration
# ---------------------------------------------------------------------------

class TestProjectileDispatcher:
    def test_projectile_routes_to_analytic(self):
        psdl = proj_template.build_psdl()
        assert select_solver(psdl) == SOLVER_ANALYTIC_PROJECTILE

    def test_dispatch_returns_correct_x(self):
        psdl = proj_template.build_psdl(height=10.0, v0x=5.0, duration=1.0)
        states = dispatch(psdl)
        assert abs(states[0]["position"][0] - 5.0) < 1e-9

    def test_dispatch_with_validation_all_pass(self):
        psdl = proj_template.build_psdl(
            height=10.0, v0x=5.0, duration=1.0,
            validation_tolerance_pct=1.0,
        )
        result = dispatch_with_validation(psdl)
        assert result["solver_used"] == SOLVER_ANALYTIC_PROJECTILE
        for r in result["validation_results"]:
            assert r["passed"], f"Validation failed for {r['target']}: {r['message']}"
