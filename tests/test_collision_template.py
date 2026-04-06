"""
Tests for the collision scenario template (src.physics.templates.collision).

Verifies:
* Template structure is valid (PSDL schema compliant).
* Elastic and inelastic collision analytic results are correct.
* Default source refs comply with governance (tier_1, not NIST/ITU).
* solve_collision_1d_elastic returns exact results.
* dispatch routes "collision" to the analytic solver.
"""

from __future__ import annotations

import pytest

from src.physics.analytic import solve_collision_1d_elastic
from src.physics.dispatcher import (
    SOLVER_ANALYTIC_COLLISION_1D,
    dispatch,
    dispatch_with_validation,
    select_solver,
)
from src.schema.psdl import PSDL, ParticleObject, SourceRef, WorldSettings
from src.physics.templates import collision as col_template
from src.physics.templates.collision import compute_final_velocities


# ---------------------------------------------------------------------------
# Template structure — elastic
# ---------------------------------------------------------------------------

class TestCollisionTemplateStructureElastic:
    def test_scenario_type_is_collision(self):
        psdl = col_template.build_psdl()
        assert psdl.scenario_type == "collision"

    def test_schema_version(self):
        psdl = col_template.build_psdl()
        assert psdl.schema_version == "0.1"

    def test_has_two_particles(self):
        psdl = col_template.build_psdl()
        particles = [o for o in psdl.objects if isinstance(o, ParticleObject)]
        assert len(particles) == 2

    def test_particle_masses_set(self):
        psdl = col_template.build_psdl(m1=2.0, m2=3.0)
        assert abs(psdl.objects[0].mass - 2.0) < 1e-9
        assert abs(psdl.objects[1].mass - 3.0) < 1e-9

    def test_particle_initial_velocities(self):
        psdl = col_template.build_psdl(v1x=4.0, v2x=1.0)
        assert abs(psdl.objects[0].velocity[0] - 4.0) < 1e-9
        assert abs(psdl.objects[1].velocity[0] - 1.0) < 1e-9

    def test_elastic_restitution(self):
        psdl = col_template.build_psdl(collision_type="elastic")
        assert psdl.objects[0].restitution == 1.0
        assert psdl.objects[1].restitution == 1.0

    def test_elastic_assumptions(self):
        psdl = col_template.build_psdl(collision_type="elastic")
        assumptions_lower = [a.lower() for a in psdl.assumptions]
        assert any("elastic" in a for a in assumptions_lower)
        assert any("momentum" in a for a in assumptions_lower)

    def test_validation_targets_present(self):
        psdl = col_template.build_psdl()
        assert len(psdl.validation_targets) >= 1

    def test_final_vx_target_present(self):
        psdl = col_template.build_psdl()
        names = {t.name for t in psdl.validation_targets}
        assert "final_vx" in names

    def test_source_refs_present(self):
        psdl = col_template.build_psdl()
        assert len(psdl.source_refs) >= 1

    def test_primary_source_is_tier1(self):
        psdl = col_template.build_psdl()
        primary = [
            r for r in psdl.source_refs
            if isinstance(r, SourceRef) and r.role == "primary_template_source"
        ]
        assert len(primary) == 1
        assert "openstax" in primary[0].source_id

    def test_nist_not_in_source_refs(self):
        psdl = col_template.build_psdl()
        for ref in psdl.source_refs:
            if isinstance(ref, SourceRef):
                assert "nist" not in ref.source_id.lower()
                assert "itu" not in ref.source_id.lower()

    def test_psdl_model_validates(self):
        psdl = col_template.build_psdl()
        assert isinstance(psdl, PSDL)

    def test_module_has_scenario_type_constant(self):
        assert col_template.scenario_type == "collision"


# ---------------------------------------------------------------------------
# Template structure — inelastic
# ---------------------------------------------------------------------------

class TestCollisionTemplateStructureInelastic:
    def test_inelastic_restitution_zero(self):
        psdl = col_template.build_psdl(collision_type="inelastic")
        assert psdl.objects[0].restitution == 0.0
        assert psdl.objects[1].restitution == 0.0

    def test_inelastic_assumptions(self):
        psdl = col_template.build_psdl(collision_type="inelastic")
        assumptions_lower = [a.lower() for a in psdl.assumptions]
        assert any("inelastic" in a for a in assumptions_lower)
        assert any("momentum" in a for a in assumptions_lower)

    def test_inelastic_momentum_conserved(self):
        """Perfectly inelastic: final velocity = total momentum / total mass."""
        m1, m2, v1x = 3.0, 1.0, 4.0
        psdl = col_template.build_psdl(m1=m1, m2=m2, v1x=v1x, v2x=0.0,
                                       collision_type="inelastic")
        target = next(t for t in psdl.validation_targets if t.name == "final_vx")
        expected = (m1 * v1x) / (m1 + m2)  # 3 m/s
        assert abs(target.expected_value - expected) < 1e-9


# ---------------------------------------------------------------------------
# Validation target pre-computation — elastic
# ---------------------------------------------------------------------------

class TestElasticCollisionTargets:
    def test_equal_mass_exchange_velocities(self):
        """For equal masses, elastic collision exchanges velocities."""
        psdl = col_template.build_psdl(m1=1.0, m2=1.0, v1x=3.0, v2x=0.0)
        target = next(t for t in psdl.validation_targets if t.name == "final_vx")
        # v1f = 0, v2f = 3 (velocity exchange for equal masses)
        assert abs(target.expected_value - 0.0) < 1e-9

    def test_heavy_hits_light_at_rest(self):
        """m1 >> m2: m1 barely slows, m2 accelerates to ~2*v1."""
        m1, m2, v1x = 10.0, 1.0, 2.0
        v1f, _ = compute_final_velocities(m1, m2, v1x, 0.0, "elastic")
        psdl = col_template.build_psdl(m1=m1, m2=m2, v1x=v1x, v2x=0.0)
        target = next(t for t in psdl.validation_targets if t.name == "final_vx")
        assert abs(target.expected_value - v1f) < 1e-9

    def test_arbitrary_elastic(self):
        m1, m2, v1x, v2x = 2.0, 3.0, 5.0, -1.0
        v1f, v2f = compute_final_velocities(m1, m2, v1x, v2x, "elastic")
        psdl = col_template.build_psdl(m1=m1, m2=m2, v1x=v1x, v2x=v2x)
        target = next(t for t in psdl.validation_targets if t.name == "final_vx")
        assert abs(target.expected_value - v1f) < 1e-9


# ---------------------------------------------------------------------------
# compute_final_velocities helper
# ---------------------------------------------------------------------------

class TestComputeFinalVelocities:
    def test_elastic_equal_mass(self):
        v1f, v2f = compute_final_velocities(1.0, 1.0, 3.0, 0.0)
        assert abs(v1f - 0.0) < 1e-9
        assert abs(v2f - 3.0) < 1e-9

    def test_elastic_momentum_conserved(self):
        m1, m2, v1x, v2x = 2.0, 3.0, 4.0, 1.0
        v1f, v2f = compute_final_velocities(m1, m2, v1x, v2x, "elastic")
        p_before = m1 * v1x + m2 * v2x
        p_after  = m1 * v1f  + m2 * v2f
        assert abs(p_before - p_after) < 1e-9

    def test_elastic_kinetic_energy_conserved(self):
        m1, m2, v1x, v2x = 2.0, 3.0, 4.0, 1.0
        v1f, v2f = compute_final_velocities(m1, m2, v1x, v2x, "elastic")
        ke_before = 0.5 * m1 * v1x ** 2 + 0.5 * m2 * v2x ** 2
        ke_after  = 0.5 * m1 * v1f  ** 2 + 0.5 * m2 * v2f  ** 2
        assert abs(ke_before - ke_after) < 1e-9

    def test_inelastic_equal_velocities(self):
        v1f, v2f = compute_final_velocities(2.0, 2.0, 4.0, 0.0, "inelastic")
        assert abs(v1f - v2f) < 1e-9  # same final velocity

    def test_inelastic_momentum_conserved(self):
        m1, m2, v1x, v2x = 3.0, 1.0, 2.0, -1.0
        v1f, v2f = compute_final_velocities(m1, m2, v1x, v2x, "inelastic")
        p_before = m1 * v1x + m2 * v2x
        p_after  = m1 * v1f  + m2 * v2f
        assert abs(p_before - p_after) < 1e-9


# ---------------------------------------------------------------------------
# Analytic solver — solve_collision_1d_elastic
# ---------------------------------------------------------------------------

class TestSolveCollision1DElastic:
    def test_equal_mass_velocity_exchange(self):
        psdl = col_template.build_psdl(m1=1.0, m2=1.0, v1x=3.0, v2x=0.0)
        states = solve_collision_1d_elastic(psdl)
        assert abs(states[0]["velocity"][0] - 0.0) < 1e-9
        assert abs(states[1]["velocity"][0] - 3.0) < 1e-9

    def test_momentum_conserved(self):
        m1, m2, v1x, v2x = 2.0, 3.0, 5.0, -1.0
        psdl = col_template.build_psdl(m1=m1, m2=m2, v1x=v1x, v2x=v2x)
        states = solve_collision_1d_elastic(psdl)
        p_before = m1 * v1x + m2 * v2x
        p_after  = m1 * states[0]["velocity"][0] + m2 * states[1]["velocity"][0]
        assert abs(p_before - p_after) < 1e-9

    def test_kinetic_energy_conserved(self):
        m1, m2, v1x, v2x = 2.0, 3.0, 5.0, -1.0
        psdl = col_template.build_psdl(m1=m1, m2=m2, v1x=v1x, v2x=v2x)
        states = solve_collision_1d_elastic(psdl)
        ke_before = 0.5 * m1 * v1x ** 2 + 0.5 * m2 * v2x ** 2
        ke_after  = (0.5 * m1 * states[0]["velocity"][0] ** 2
                     + 0.5 * m2 * states[1]["velocity"][0] ** 2)
        assert abs(ke_before - ke_after) < 1e-9

    def test_returns_two_states(self):
        psdl = col_template.build_psdl()
        states = solve_collision_1d_elastic(psdl)
        assert len(states) == 2

    def test_state_format(self):
        psdl = col_template.build_psdl()
        states = solve_collision_1d_elastic(psdl)
        for s in states:
            assert "position" in s
            assert "velocity" in s
            assert len(s["position"]) == 3
            assert len(s["velocity"]) == 3

    def test_too_few_particles_raises(self):
        psdl = PSDL(
            scenario_type="collision",
            world=WorldSettings(gravity=[0.0, 0.0, 0.0], dt=0.01, steps=1),
            objects=[
                ParticleObject(mass=1.0, radius=0.1,
                               position=[0.0, 0.0, 0.0],
                               velocity=[1.0, 0.0, 0.0])
            ],
        )
        with pytest.raises(ValueError, match="at least 2"):
            solve_collision_1d_elastic(psdl)


# ---------------------------------------------------------------------------
# Dispatcher integration
# ---------------------------------------------------------------------------

class TestCollisionDispatcher:
    def test_collision_routes_to_analytic(self):
        psdl = col_template.build_psdl()
        assert select_solver(psdl) == SOLVER_ANALYTIC_COLLISION_1D

    def test_dispatch_returns_two_states(self):
        psdl = col_template.build_psdl()
        states = dispatch(psdl)
        assert len(states) == 2

    def test_dispatch_with_validation_result_structure(self):
        psdl = col_template.build_psdl()
        result = dispatch_with_validation(psdl)
        assert result["solver_used"] == SOLVER_ANALYTIC_COLLISION_1D
        assert len(result["states"]) == 2
        assert "validation_results" in result

    def test_dispatch_with_validation_passes_equal_mass(self):
        psdl = col_template.build_psdl(
            m1=1.0, m2=1.0, v1x=3.0, v2x=0.0,
            validation_tolerance_pct=1.0,
        )
        result = dispatch_with_validation(psdl)
        for r in result["validation_results"]:
            assert r["passed"], f"Validation failed: {r['message']}"
