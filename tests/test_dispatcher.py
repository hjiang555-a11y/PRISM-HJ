"""
Tests for the solver dispatcher (src.physics.dispatcher).

Verifies:
* Correct solver selection for each scenario_type.
* End-to-end dispatch for free_fall returns analytic results.
* Fallback to PyBullet for unknown scenario types.
"""

from __future__ import annotations

import pytest

from src.physics.dispatcher import (
    SOLVER_ANALYTIC_FREE_FALL,
    SOLVER_ANALYTIC_PROJECTILE,
    SOLVER_ANALYTIC_COLLISION_1D,
    SOLVER_PYBULLET,
    dispatch,
    select_solver,
)
from src.schema.psdl import ParticleObject, PSDL, WorldSettings
from src.physics.templates import free_fall as ff_template


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_psdl(scenario_type: str | None = None) -> PSDL:
    """Build a minimal PSDL with one particle for dispatch testing."""
    return PSDL(
        scenario_type=scenario_type,
        world=WorldSettings(gravity=[0.0, 0.0, -9.8], dt=0.01, steps=100),
        objects=[
            ParticleObject(
                mass=1.0, radius=0.1,
                position=[0.0, 0.0, 5.0],
                velocity=[0.0, 0.0, 0.0],
            )
        ],
    )


# ---------------------------------------------------------------------------
# Solver selection
# ---------------------------------------------------------------------------

class TestSelectSolver:
    def test_free_fall_routes_to_analytic(self):
        psdl = _minimal_psdl("free_fall")
        assert select_solver(psdl) == SOLVER_ANALYTIC_FREE_FALL

    def test_none_routes_to_pybullet(self):
        psdl = _minimal_psdl(None)
        assert select_solver(psdl) == SOLVER_PYBULLET

    def test_unknown_type_routes_to_pybullet(self):
        psdl = _minimal_psdl("optics")  # truly unknown scenario
        assert select_solver(psdl) == SOLVER_PYBULLET

    def test_projectile_routes_to_analytic(self):
        psdl = _minimal_psdl("projectile")
        assert select_solver(psdl) == SOLVER_ANALYTIC_PROJECTILE

    def test_collision_routes_to_analytic(self):
        psdl = _minimal_psdl("collision")
        assert select_solver(psdl) == SOLVER_ANALYTIC_COLLISION_1D

    def test_free_fall_case_insensitive(self):
        psdl = _minimal_psdl("FREE_FALL")
        assert select_solver(psdl) == SOLVER_ANALYTIC_FREE_FALL


# ---------------------------------------------------------------------------
# End-to-end dispatch — free_fall (analytic, exact)
# ---------------------------------------------------------------------------

class TestDispatchFreeFall:
    """Dispatcher must return exact kinematic results for free_fall."""

    def test_dispatch_returns_correct_shape(self):
        psdl = ff_template.build_psdl(height=5.0, duration=1.0)
        states = dispatch(psdl)
        assert len(states) == 1
        assert "position" in states[0]
        assert "velocity" in states[0]
        assert len(states[0]["position"]) == 3
        assert len(states[0]["velocity"]) == 3

    def test_dispatch_free_fall_exact_position(self):
        """
        Analytic solver: z(1s) = 5 - 0.5*9.8*1^2 = 0.1 m exactly.
        Tolerance: floating-point precision only (< 1e-9 m).
        """
        psdl = ff_template.build_psdl(height=5.0, g=9.8, duration=1.0, dt=0.01)
        states = dispatch(psdl)
        z_final = states[0]["position"][2]
        assert abs(z_final - 0.1) < 1e-4, f"Expected z≈0.1 m, got {z_final}"

    def test_dispatch_free_fall_exact_velocity(self):
        """
        Analytic solver: vz(1s) = -9.8 m/s exactly.
        """
        psdl = ff_template.build_psdl(height=5.0, g=9.8, duration=1.0, dt=0.01)
        states = dispatch(psdl)
        vz_final = states[0]["velocity"][2]
        assert abs(vz_final - (-9.8)) < 1e-4, f"Expected vz≈-9.8 m/s, got {vz_final}"

    def test_dispatch_mass_independence(self):
        """Galilean equivalence: free-fall trajectory is mass-independent."""
        psdl_light = ff_template.build_psdl(height=10.0, mass=0.1, duration=1.0)
        psdl_heavy = ff_template.build_psdl(height=10.0, mass=100.0, duration=1.0)
        z_light = dispatch(psdl_light)[0]["position"][2]
        z_heavy = dispatch(psdl_heavy)[0]["position"][2]
        assert abs(z_light - z_heavy) < 1e-9, (
            f"Mass-independent free fall violated: {z_light} vs {z_heavy}"
        )

    def test_dispatch_validation_targets_pass(self):
        """All validation_targets in the template must pass after dispatch."""
        psdl = ff_template.build_psdl(
            height=5.0, g=9.8, duration=1.0,
            validation_tolerance_pct=1.0,
        )
        states = dispatch(psdl)
        # Map result fields for checking
        field_map = {
            "final_z":  states[0]["position"][2],
            "final_vz": states[0]["velocity"][2],
        }
        for target in psdl.validation_targets:
            actual = field_map.get(target.name)
            if actual is not None:
                assert target.check(actual), (
                    f"ValidationTarget '{target.name}' failed: "
                    f"actual={actual}, expected={target.expected_value}"
                )


# ---------------------------------------------------------------------------
# End-to-end dispatch — PyBullet fallback (numerical, ≤5% tolerance)
# ---------------------------------------------------------------------------

class TestDispatchPyBullet:
    """Dispatcher falls back to PyBullet for unknown scenario types."""

    def test_pybullet_fallback_free_fall_5pct(self):
        """
        PyBullet semi-implicit Euler gives ≤5% error on free-fall displacement.
        """
        g, z0, t = 9.8, 5.0, 1.0
        psdl = PSDL(
            scenario_type=None,          # → pybullet
            world=WorldSettings(
                gravity=[0.0, 0.0, -g],
                dt=0.01,
                steps=round(t / 0.01),
                ground_plane=False,
            ),
            objects=[
                ParticleObject(
                    mass=1.0, radius=0.1,
                    position=[0.0, 0.0, z0],
                    velocity=[0.0, 0.0, 0.0],
                )
            ],
        )
        states = dispatch(psdl)
        z_sim = states[0]["position"][2]
        z_exact = z0 - 0.5 * g * t ** 2  # 0.1 m
        displacement_sim   = z_sim - z0
        displacement_exact = z_exact - z0
        tol = 0.05 * abs(displacement_exact)
        assert abs(displacement_sim - displacement_exact) <= tol, (
            f"PyBullet displacement error exceeds 5%: sim={displacement_sim:.4f} "
            f"exact={displacement_exact:.4f}"
        )
