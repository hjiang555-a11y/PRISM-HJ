"""
Unit tests for the free-fall physics scenario.

Analytical solution (no air resistance, semi-implicit Euler integrator):
    The kinematic equations for free fall from z0=5m with g=9.8 m/s², t=1s:
        vz(t) = -g * t  →  vz(1) = -9.8 m/s
        Δz    = -½ g t²  →  Δz(1) = -4.9 m  →  z(1) = 0.1 m

    PyBullet uses a semi-implicit (symplectic) Euler integrator which gives:
        z[N] = z0 + g·dt² · N(N+1)/2  (slightly ahead of the exact solution)

    The test validates that simulation results are within 5% of the
    analytical *displacement* (not absolute position, to avoid the
    near-zero denominator when z≈0 at t=1s).
"""

from __future__ import annotations

import pytest

from src.physics.engine import PhysicsSimulator, simulate_psdl
from src.schema.psdl import (
    BoundaryType,
    ParticleObject,
    PSDL,
    SpaceBox,
    WorldSettings,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_free_fall_psdl(
    height: float = 5.0,
    mass: float = 2.0,
    t_sim: float = 1.0,
    dt: float = 0.01,
) -> PSDL:
    """Construct a PSDL document for a free-fall scenario."""
    steps = round(t_sim / dt)
    return PSDL(
        world=WorldSettings(
            gravity=[0.0, 0.0, -9.8],
            dt=dt,
            steps=steps,
            space=SpaceBox(
                min=[-50.0, -50.0, -50.0],
                max=[50.0, 50.0, 50.0],
                boundary_type=BoundaryType.elastic,
            ),
        ),
        objects=[
            ParticleObject(
                mass=mass,
                radius=0.1,
                position=[0.0, 0.0, height],
                velocity=[0.0, 0.0, 0.0],
                restitution=0.9,
            )
        ],
        query="1秒后球的位置和速度",
    )


def analytical_free_fall(z0: float, v0z: float, g: float, t: float):
    """Return (z, vz) from the exact kinematic equations."""
    z = z0 + v0z * t - 0.5 * g * t ** 2
    vz = v0z - g * t
    return z, vz


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFreeFall:
    """Verify that the PyBullet simulation matches the analytical free-fall solution."""

    def test_displacement_within_tolerance(self):
        """Vertical displacement must be within 5% of the analytical value.

        We compare *displacement* (Δz = z_final - z_initial) rather than
        absolute position to avoid the near-zero denominator at t=1 s when
        z ≈ 0.1 m.  The analytical displacement is -4.9 m; PyBullet's
        semi-implicit Euler gives ≈ -4.95 m, an error of ~1%.
        """
        g = 9.8
        z0, v0z, t = 5.0, 0.0, 1.0

        psdl = _build_free_fall_psdl(height=z0, mass=2.0, t_sim=t)
        states = simulate_psdl(psdl)

        assert len(states) == 1, "Expected exactly one particle state."
        sim_z = states[0]["position"][2]
        sim_displacement = sim_z - z0                       # should be ≈ -4.9 m
        analytical_z, _ = analytical_free_fall(z0, v0z, g, t)
        analytical_displacement = analytical_z - z0        # -4.9 m

        # 5% tolerance on the displacement magnitude
        tol = 0.05 * abs(analytical_displacement)
        assert abs(sim_displacement - analytical_displacement) <= tol, (
            f"displacement out of tolerance: sim={sim_displacement:.4f} m, "
            f"analytical={analytical_displacement:.4f} m, tol=±{tol:.4f} m"
        )

    def test_velocity_within_tolerance(self):
        """Final z-velocity must be within 5% of the analytical solution.

        With linear damping set to 0, PyBullet matches vz = -g*t exactly.
        """
        g = 9.8
        z0, v0z, t = 5.0, 0.0, 1.0

        psdl = _build_free_fall_psdl(height=z0, mass=2.0, t_sim=t)
        states = simulate_psdl(psdl)

        sim_vz = states[0]["velocity"][2]
        _, analytical_vz = analytical_free_fall(z0, v0z, g, t)

        tol = 0.05 * abs(analytical_vz)
        assert abs(sim_vz - analytical_vz) <= tol, (
            f"z velocity out of tolerance: sim={sim_vz:.4f} m/s, "
            f"analytical={analytical_vz:.4f} m/s, tol=±{tol:.4f} m/s"
        )

    def test_horizontal_components_zero(self):
        """With no horizontal forces or initial velocity, x and y must stay ≈ 0."""
        psdl = _build_free_fall_psdl()
        states = simulate_psdl(psdl)

        sim_x = states[0]["position"][0]
        sim_y = states[0]["position"][1]
        sim_vx = states[0]["velocity"][0]
        sim_vy = states[0]["velocity"][1]

        assert abs(sim_x) < 1e-4, f"x position should be ~0, got {sim_x}"
        assert abs(sim_y) < 1e-4, f"y position should be ~0, got {sim_y}"
        assert abs(sim_vx) < 1e-4, f"x velocity should be ~0, got {sim_vx}"
        assert abs(sim_vy) < 1e-4, f"y velocity should be ~0, got {sim_vy}"

    def test_mass_independence(self):
        """In the absence of air drag, all masses should fall identically."""
        psdl_light = _build_free_fall_psdl(mass=0.1)
        psdl_heavy = _build_free_fall_psdl(mass=100.0)

        states_light = simulate_psdl(psdl_light)
        states_heavy = simulate_psdl(psdl_heavy)

        z_light = states_light[0]["position"][2]
        z_heavy = states_heavy[0]["position"][2]

        assert abs(z_light - z_heavy) < 0.01, (
            f"Different masses gave different positions: {z_light:.4f} vs {z_heavy:.4f}"
        )


class TestPhysicsSimulatorDirect:
    """Lower-level tests for the PhysicsSimulator class."""

    def test_simulator_lifecycle(self):
        """Simulator should open and close without errors."""
        sim = PhysicsSimulator(gravity=[0, 0, -9.8], dt=0.01)
        sim.add_plane()
        obj = ParticleObject(mass=1.0, radius=0.1, position=[0, 0, 2], velocity=[0, 0, 0])
        body_id = sim.add_particle(obj)
        assert isinstance(body_id, int)
        sim.step(steps=10, space=SpaceBox(min=[-10, -10, -10], max=[10, 10, 10]))
        states = sim.get_particle_states()
        assert len(states) == 1
        sim.close()

    def test_boundary_elastic_reflection(self):
        """A particle moving toward a boundary should bounce back (elastic)."""
        space = SpaceBox(
            min=[0.0, 0.0, 0.0],
            max=[5.0, 5.0, 5.0],
            boundary_type=BoundaryType.elastic,
        )
        sim = PhysicsSimulator(gravity=[0, 0, 0], dt=0.01)  # no gravity
        try:
            obj = ParticleObject(
                mass=1.0, radius=0.01,
                position=[4.9, 2.5, 2.5],
                velocity=[10.0, 0.0, 0.0],  # moving toward x=5 wall
                restitution=1.0,
            )
            sim.add_particle(obj)
            # Step a few times so the particle hits the x=5 boundary
            sim.step(steps=5, space=space)
            states = sim.get_particle_states()
            # After bouncing, x velocity should be negative
            assert states[0]["velocity"][0] < 0, (
                f"Expected negative vx after elastic reflection, "
                f"got {states[0]['velocity'][0]}"
            )
        finally:
            sim.close()

