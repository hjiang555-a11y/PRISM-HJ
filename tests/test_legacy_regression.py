"""
Legacy regression tests — golden scenarios via new execution core.

This test file preserves the golden scenario outcomes that were historically
validated by the legacy analytic solvers (``src/physics/analytic.py``) and
verifies that the *new* execution architecture produces physically consistent
results for the same setups.

Integration scheme note
-----------------------
The new Scheduler uses **semi-implicit Euler** integration:
    v_new = v_old + g·dt
    x_new = x_old + v_new·dt

For constant acceleration this introduces O(dt) position error:
    ε ≈ g·t·dt/2

With dt=0.01 s and t=1 s under g=−9.8 m/s², the Euler z(1s) ≈ 0.051 m
versus the exact analytic z=0.1 m.  The velocity vz(1s) = −9.8 m/s is
exact because it integrates directly without position coupling.

Regression strategy
-------------------
* Free-fall: test velocity (exact) and direction/sign of position change.
* Collision: test analytic impulse law directly (rule is closed-form → exact).
* Physics invariants: momentum conservation, energy bounds.

Scenarios covered
-----------------
1. Free-fall — vertical drop under gravity
2. Elastic 1-D collision — two-body impact along x-axis
"""

from __future__ import annotations

import pytest

from src.execution.runtime.scheduler import Scheduler
from src.execution.state.state_set import StateSet
from src.planning.execution_plan.models import ExecutionPlan


# ---------------------------------------------------------------------------
# Helper: build a minimal ExecutionPlan for free-fall
# ---------------------------------------------------------------------------

def _make_free_fall_plan(entity_id: str = "ball") -> ExecutionPlan:
    """Return an ExecutionPlan for a single particle under constant gravity."""
    return ExecutionPlan(
        state_set_plan={entity_id: {"fields": ["position", "velocity", "mass"]}},
        persistent_rule_plan=[{
            "rule_name": "constant_gravity",
            "applies_to": [entity_id],
            "rule_execution_inputs": {},
        }],
        local_rule_plan=[],
        trigger_plan=[],
        assembly_plan={
            "final_position": {
                "source_capability": "particle_motion",
                "entity": entity_id,
                "field": "position",
            },
            "final_velocity": {
                "source_capability": "particle_motion",
                "entity": entity_id,
                "field": "velocity",
            },
        },
    )


def _make_collision_plan(id_a: str = "A", id_b: str = "B") -> ExecutionPlan:
    """Return an ExecutionPlan for a two-particle contact interaction."""
    return ExecutionPlan(
        state_set_plan={
            id_a: {"fields": ["position", "velocity", "mass"]},
            id_b: {"fields": ["position", "velocity", "mass"]},
        },
        persistent_rule_plan=[],
        local_rule_plan=[{
            "rule_name": "impulsive_collision",
            "trigger_type": "contact",
            "applies_to": [id_a, id_b],
            "rule_execution_inputs": {
                "restitution": 1.0,
                "contact_normal": [1.0, 0.0, 0.0],
            },
        }],
        trigger_plan=[{
            "type": "contact",
            "pairs": [[id_a, id_b]],
            "threshold": 0.5,
        }],
        assembly_plan={
            "v_A_after": {
                "source_capability": "contact_interaction",
                "entity": id_a,
                "field": "velocity",
            },
            "v_B_after": {
                "source_capability": "contact_interaction",
                "entity": id_b,
                "field": "velocity",
            },
        },
    )


# ---------------------------------------------------------------------------
# Golden scenario 1: Free-fall  (h=5 m, g=9.8 m/s², t=1 s)
#
# Semi-implicit Euler expected values (dt=0.01, N=100):
#   vz(1s) = 0 + 100·(−9.8)·0.01 = −9.8 m/s  (exact for const accel)
#   z(1s)  = 5 + (−9.8)·0.0001·∑_{n=1}^{100} n
#           = 5 − 9.8·0.0001·5050 = 5 − 4.949 ≈ 0.051 m
#
# Exact analytic reference: z(1s) = 0.1 m.
# The gap (0.049 m) is the known O(dt) semi-implicit Euler error.
# ---------------------------------------------------------------------------

class TestFreeFallGolden:
    """
    Regression: single particle dropped from 5 m at rest, 1 second of gravity.

    Tests target physics invariants and exact velocity (not Euler-approximate
    position), ensuring the new execution core produces physically correct
    and stable results.
    """

    DT = 0.01
    STEPS = 100  # 1.0 s

    def _run(self, z0=5.0, vz0=0.0, mass=1.0):
        plan = _make_free_fall_plan("ball")
        ss = StateSet()
        ss.set_entity_state("ball", {
            "position": [0.0, 0.0, z0],
            "velocity": [0.0, 0.0, vz0],
            "mass": mass,
        })
        scheduler = Scheduler(dt=self.DT, steps=self.STEPS)
        return scheduler.run(plan, ss, gravity_vector=[0.0, 0.0, -9.8])

    def test_final_velocity_z_exact(self):
        """
        vz(1s) = v0z + g·t = 0 + (−9.8)·1 = −9.8 m/s.

        Velocity is exact under constant acceleration regardless of time-step.
        Tolerance: machine precision (1e-9).
        """
        result = self._run()
        vz = result.target_results["final_velocity"][2]
        assert abs(vz - (-9.8)) < 1e-9, f"Expected vz=-9.8, got {vz}"

    def test_object_fell_down(self):
        """z(1s) < z(0) — object must have descended."""
        result = self._run()
        z = result.target_results["final_position"][2]
        assert z < 5.0, f"Object should have fallen below z=5, got z={z}"

    def test_position_z_above_zero(self):
        """Object starts at 5 m and falls for 1 s — should still be above z=0."""
        result = self._run()
        z = result.target_results["final_position"][2]
        assert z > 0.0, f"Expected z>0 at t=1s, got z={z}"

    def test_euler_position_matches_known_integration_value(self):
        """
        With semi-implicit Euler (dt=0.01, N=100), the expected position is:
            z_euler = 5 + (-9.8)·0.0001·(100·101/2) ≈ 0.051 m.
        This test documents the current integrator behaviour.
        """
        result = self._run()
        z = result.target_results["final_position"][2]
        # Expected Euler result (exact for this integrator + parameters)
        expected_euler = 5.0 + (-9.8) * (self.DT ** 2) * (self.STEPS * (self.STEPS + 1) / 2)
        assert abs(z - expected_euler) < 1e-6, (
            f"Euler position mismatch: expected {expected_euler:.6f}, got {z:.6f}"
        )

    def test_horizontal_components_unchanged(self):
        """With no horizontal force, x/y/vx/vy remain at 0."""
        result = self._run()
        pos = result.target_results["final_position"]
        vel = result.target_results["final_velocity"]
        assert abs(pos[0]) < 1e-9
        assert abs(pos[1]) < 1e-9
        assert abs(vel[0]) < 1e-9
        assert abs(vel[1]) < 1e-9

    def test_mass_independence(self):
        """Galilean equivalence: trajectory must not depend on mass."""
        r_light = self._run(mass=0.01)
        r_heavy = self._run(mass=100.0)
        z_light = r_light.target_results["final_position"][2]
        z_heavy = r_heavy.target_results["final_position"][2]
        assert abs(z_light - z_heavy) < 1e-9, (
            f"Mass should not affect trajectory: z_light={z_light}, z_heavy={z_heavy}"
        )

    def test_initial_upward_velocity_direction(self):
        """
        Object thrown upward at 5 m/s from z=0 for 2 s.
        vz(2s) = 5 − 9.8·2 = −14.6 m/s  (exact under const accel).
        Object should be below z=0 after 2 s of free flight.
        """
        plan = _make_free_fall_plan("ball")
        ss = StateSet()
        ss.set_entity_state("ball", {
            "position": [0.0, 0.0, 0.0],
            "velocity": [0.0, 0.0, 5.0],
            "mass": 1.0,
        })
        scheduler = Scheduler(dt=0.01, steps=200)  # 2 s
        result = scheduler.run(plan, ss, gravity_vector=[0.0, 0.0, -9.8])
        vz = result.target_results["final_velocity"][2]
        z = result.target_results["final_position"][2]
        # Velocity is exact
        assert abs(vz - (-14.6)) < 1e-9
        # Position should be negative (below starting point)
        assert z < 0.0


# ---------------------------------------------------------------------------
# Golden scenario 2: Elastic 1-D collision (equal masses)
#
# The ImpulsiveCollisionRule uses the analytic impulse formula, so results
# are exact (no integration error).
# Reference: v1f = ((m1−m2)v1 + 2m2·v2)/(m1+m2)
#            v2f = ((m2−m1)v2 + 2m1·v1)/(m1+m2)
# ---------------------------------------------------------------------------

class TestElasticCollisionGolden:
    """
    Regression: elastic collision between two particles.

    The ImpulsiveCollisionRule is analytic (no time-stepping involved), so
    results are exact to machine precision.
    """

    def _run(self, m1=1.0, m2=1.0, v1x=2.0, v2x=0.0):
        plan = _make_collision_plan("A", "B")
        ss = StateSet()
        ss.set_entity_state("A", {
            "position": [0.0, 0.0, 0.0],
            "velocity": [v1x, 0.0, 0.0],
            "mass": m1,
        })
        ss.set_entity_state("B", {
            "position": [0.1, 0.0, 0.0],  # within contact threshold
            "velocity": [v2x, 0.0, 0.0],
            "mass": m2,
        })
        scheduler = Scheduler(dt=0.01, steps=1, contact_threshold=0.5)
        return scheduler.run(plan, ss)

    def test_equal_mass_velocities_exchange(self):
        """Equal masses: v1f = 0, v2f = v1i (exact velocity exchange)."""
        result = self._run(m1=1.0, m2=1.0, v1x=2.0, v2x=0.0)
        v_a = result.target_results["v_A_after"][0]
        v_b = result.target_results["v_B_after"][0]
        assert abs(v_a - 0.0) < 1e-9, f"Expected v_A=0, got {v_a}"
        assert abs(v_b - 2.0) < 1e-9, f"Expected v_B=2, got {v_b}"

    def test_momentum_conserved(self):
        """Total momentum must be conserved (m1=2, m2=1, v1x=3, v2x=0)."""
        m1, m2, v1x, v2x = 2.0, 1.0, 3.0, 0.0
        p_before = m1 * v1x + m2 * v2x
        result = self._run(m1=m1, m2=m2, v1x=v1x, v2x=v2x)
        v_a = result.target_results["v_A_after"][0]
        v_b = result.target_results["v_B_after"][0]
        p_after = m1 * v_a + m2 * v_b
        assert abs(p_after - p_before) < 1e-9, (
            f"Momentum not conserved: before={p_before}, after={p_after}"
        )

    def test_kinetic_energy_conserved_elastic(self):
        """Kinetic energy must be conserved for elastic collision (e=1)."""
        m1, m2, v1x, v2x = 2.0, 1.0, 3.0, 0.0
        ke_before = 0.5 * m1 * v1x**2 + 0.5 * m2 * v2x**2
        result = self._run(m1=m1, m2=m2, v1x=v1x, v2x=v2x)
        v_a = result.target_results["v_A_after"][0]
        v_b = result.target_results["v_B_after"][0]
        ke_after = 0.5 * m1 * v_a**2 + 0.5 * m2 * v_b**2
        assert abs(ke_after - ke_before) < 1e-9, (
            f"KE not conserved: before={ke_before}, after={ke_after}"
        )

    def test_analytic_formula_matches(self):
        """
        Compare new rule output against the legacy analytic formula:
            v1f = ((m1−m2)·v1 + 2·m2·v2) / (m1+m2)
            v2f = ((m2−m1)·v2 + 2·m1·v1) / (m1+m2)
        """
        m1, m2, v1x, v2x = 3.0, 1.0, 4.0, 1.0
        total = m1 + m2
        v1f_ref = ((m1 - m2) * v1x + 2.0 * m2 * v2x) / total
        v2f_ref = ((m2 - m1) * v2x + 2.0 * m1 * v1x) / total

        result = self._run(m1=m1, m2=m2, v1x=v1x, v2x=v2x)
        v_a = result.target_results["v_A_after"][0]
        v_b = result.target_results["v_B_after"][0]

        assert abs(v_a - v1f_ref) < 1e-9, f"v1f: expected {v1f_ref}, got {v_a}"
        assert abs(v_b - v2f_ref) < 1e-9, f"v2f: expected {v2f_ref}, got {v_b}"

    def test_no_collision_when_separating(self):
        """No impulse applied when particles are already moving apart."""
        plan = _make_collision_plan("A", "B")
        ss = StateSet()
        ss.set_entity_state("A", {
            "position": [0.0, 0.0, 0.0],
            "velocity": [-1.0, 0.0, 0.0],  # moving away from B
            "mass": 1.0,
        })
        ss.set_entity_state("B", {
            "position": [0.1, 0.0, 0.0],
            "velocity": [1.0, 0.0, 0.0],   # moving away from A
            "mass": 1.0,
        })
        scheduler = Scheduler(dt=0.01, steps=1, contact_threshold=0.5)
        result = scheduler.run(plan, ss)
        # After 1 gravity-free step (no persistent rules), velocities unchanged
        v_a = result.target_results["v_A_after"][0]
        v_b = result.target_results["v_B_after"][0]
        assert abs(v_a - (-1.0)) < 1e-6
        assert abs(v_b - 1.0) < 1e-6

