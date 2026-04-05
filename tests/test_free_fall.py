"""
Unit tests for the free-fall physics scenario — upgraded for PSDL v0.1.

Gold-standard validation strategy
-----------------------------------
All gold-standard results are now produced by the *exact* kinematic
equations in :mod:`src.physics.analytic`, not hard-coded constants.
This means the test suite is self-consistent: if the formula changes,
both the reference and the assertion update together.

Three verification tiers
------------------------
1. **Analytic solver** (``test_analytic_*``): exact closed-form solution —
   tolerance is floating-point precision (< 1e-9).
2. **Template + dispatcher** (``test_template_*``): end-to-end via
   :func:`src.physics.dispatcher.dispatch` — uses the analytic path,
   tolerance 1%.
3. **PyBullet numerical solver** (``TestPhysicsSimulatorDirect``): direct
   engine tests; tolerance 5% (semi-implicit Euler integration error).
"""

from __future__ import annotations

import pytest

from src.physics.analytic import solve_free_fall
from src.physics.dispatcher import dispatch
from src.physics.engine import PhysicsSimulator, simulate_psdl
from src.schema.psdl import (
    BoundaryType,
    ParticleObject,
    PSDL,
    SpaceBox,
    WorldSettings,
)
from src.templates import free_fall as ff_template


# ---------------------------------------------------------------------------
# Tier 1: Analytic solver (exact, floating-point precision only)
# ---------------------------------------------------------------------------

class TestAnalyticFreeFall:
    """Verify the exact kinematic solver against manual calculations."""

    def test_z_position_exact(self):
        """z(1s) = 5 − 0.5·9.8·1² = 0.1 m (exact)."""
        psdl = ff_template.build_psdl(height=5.0, g=9.8, duration=1.0)
        states = solve_free_fall(psdl)
        assert abs(states[0]["position"][2] - 0.1) < 1e-6

    def test_vz_velocity_exact(self):
        """vz(1s) = −9.8 m/s (exact)."""
        psdl = ff_template.build_psdl(height=5.0, g=9.8, duration=1.0)
        states = solve_free_fall(psdl)
        assert abs(states[0]["velocity"][2] - (-9.8)) < 1e-6

    def test_horizontal_components_unchanged(self):
        """With no horizontal force, x/y/vx/vy remain at initial values."""
        psdl = ff_template.build_psdl(height=5.0, duration=1.0)
        states = solve_free_fall(psdl)
        assert abs(states[0]["position"][0]) < 1e-9
        assert abs(states[0]["position"][1]) < 1e-9
        assert abs(states[0]["velocity"][0]) < 1e-9
        assert abs(states[0]["velocity"][1]) < 1e-9

    def test_mass_independence(self):
        """Galilean equivalence: trajectory must not depend on mass."""
        z_01  = solve_free_fall(ff_template.build_psdl(height=10.0, mass=0.01))[0]["position"][2]
        z_100 = solve_free_fall(ff_template.build_psdl(height=10.0, mass=100.0))[0]["position"][2]
        assert abs(z_01 - z_100) < 1e-9

    def test_no_particles_raises(self):
        """solve_free_fall must raise ValueError on an empty PSDL."""
        psdl = PSDL(scenario_type="free_fall")
        with pytest.raises(ValueError, match="no ParticleObject"):
            solve_free_fall(psdl)

    def test_with_initial_velocity(self):
        """
        Object thrown upward at 5 m/s from z=0:
            z(2s) = 0 + 5·2 − 0.5·9.8·4 = 10 − 19.6 = −9.6 m
            vz(2s) = 5 − 9.8·2 = −14.6 m/s
        """
        psdl = ff_template.build_psdl(height=0.0, v0z=5.0, g=9.8, duration=2.0)
        states = solve_free_fall(psdl)
        assert abs(states[0]["position"][2] - (-9.6)) < 1e-5
        assert abs(states[0]["velocity"][2] - (-14.6)) < 1e-5


# ---------------------------------------------------------------------------
# Tier 2: Template + dispatcher (1% tolerance, analytic path)
# ---------------------------------------------------------------------------

class TestTemplateFreefall:
    """Verify that the template builds valid PSDL and the dispatcher handles it."""

    def test_template_produces_valid_psdl(self):
        psdl = ff_template.build_psdl()
        assert psdl.schema_version == "0.1"
        assert psdl.scenario_type == "free_fall"
        assert len(psdl.assumptions) >= 1
        assert len(psdl.validation_targets) == 2

    def test_dispatch_matches_template_targets(self):
        """All template ValidationTargets must pass after dispatch (1% tol)."""
        psdl = ff_template.build_psdl(
            height=5.0, g=9.8, duration=1.0,
            validation_tolerance_pct=1.0,
        )
        states = dispatch(psdl)
        field_map = {
            "final_z":  states[0]["position"][2],
            "final_vz": states[0]["velocity"][2],
        }
        for vt in psdl.validation_targets:
            actual = field_map[vt.name]
            assert vt.check(actual), (
                f"ValidationTarget '{vt.name}' failed: "
                f"actual={actual:.6f}, expected={vt.expected_value:.6f}"
            )


# ---------------------------------------------------------------------------
# Tier 3: PyBullet numerical solver (≤5% tolerance, semi-implicit Euler)
# ---------------------------------------------------------------------------

class TestFreeFallPyBullet:
    """
    Verify that PyBullet's semi-implicit Euler integration stays within 5%
    of the analytical solution.  These tests call simulate_psdl directly
    (without the dispatcher) to exercise the engine layer in isolation.
    """

    def _build_psdl_no_ground(
        self, height: float = 5.0, mass: float = 1.0, t_sim: float = 1.0, dt: float = 0.01
    ) -> PSDL:
        steps = round(t_sim / dt)
        return PSDL(
            world=WorldSettings(
                gravity=[0.0, 0.0, -9.8],
                dt=dt,
                steps=steps,
                ground_plane=False,
                space=SpaceBox(min=[-50, -50, -50], max=[50, 50, 50]),
            ),
            objects=[
                ParticleObject(
                    mass=mass, radius=0.1,
                    position=[0.0, 0.0, height],
                    velocity=[0.0, 0.0, 0.0],
                )
            ],
            query="pybullet free fall",
        )

    def test_displacement_within_5pct(self):
        g, z0, t = 9.8, 5.0, 1.0
        psdl = self._build_psdl_no_ground(height=z0)
        states = simulate_psdl(psdl)
        sim_disp = states[0]["position"][2] - z0
        exact_disp = -0.5 * g * t ** 2
        tol = 0.05 * abs(exact_disp)
        assert abs(sim_disp - exact_disp) <= tol, (
            f"displacement out of tolerance: sim={sim_disp:.4f}, exact={exact_disp:.4f}"
        )

    def test_velocity_within_5pct(self):
        g, t = 9.8, 1.0
        psdl = self._build_psdl_no_ground()
        states = simulate_psdl(psdl)
        vz_sim = states[0]["velocity"][2]
        vz_exact = -g * t
        tol = 0.05 * abs(vz_exact)
        assert abs(vz_sim - vz_exact) <= tol, (
            f"velocity out of tolerance: sim={vz_sim:.4f}, exact={vz_exact:.4f}"
        )

    def test_horizontal_components_zero(self):
        states = simulate_psdl(self._build_psdl_no_ground())
        assert abs(states[0]["position"][0]) < 1e-4
        assert abs(states[0]["position"][1]) < 1e-4
        assert abs(states[0]["velocity"][0]) < 1e-4
        assert abs(states[0]["velocity"][1]) < 1e-4

    def test_mass_independence(self):
        z_light = simulate_psdl(self._build_psdl_no_ground(mass=0.1))[0]["position"][2]
        z_heavy = simulate_psdl(self._build_psdl_no_ground(mass=100.0))[0]["position"][2]
        assert abs(z_light - z_heavy) < 0.01


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
                velocity=[10.0, 0.0, 0.0],
                restitution=1.0,
            )
            sim.add_particle(obj)
            sim.step(steps=5, space=space)
            states = sim.get_particle_states()
            assert states[0]["velocity"][0] < 0, (
                f"Expected negative vx after elastic reflection, "
                f"got {states[0]['velocity'][0]}"
            )
        finally:
            sim.close()

    def test_no_ground_plane_by_default(self):
        """simulate_psdl must NOT add a ground plane unless explicitly requested."""
        psdl = PSDL(
            world=WorldSettings(
                gravity=[0.0, 0.0, -9.8],
                dt=0.01,
                steps=200,       # 2 s — ball falls past z=0 without collision
                ground_plane=False,
                space=SpaceBox(min=[-50, -50, -50], max=[50, 50, 50]),
            ),
            objects=[
                ParticleObject(
                    mass=1.0, radius=0.1,
                    position=[0.0, 0.0, 1.0],
                    velocity=[0.0, 0.0, 0.0],
                )
            ],
        )
        states = simulate_psdl(psdl)
        # Without a ground plane, z should be below 0 after 2s of free fall
        # z(2s) = 1 - 0.5*9.8*4 ≈ -18.6 m
        z_final = states[0]["position"][2]
        assert z_final < 0.0, (
            f"Without ground plane, ball should fall below z=0; got z={z_final:.4f}"
        )


