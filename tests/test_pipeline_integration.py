"""
Integration tests: classifier + template path feed into text_to_psdl().

These tests verify the *template-first* compilation path introduced in v0.2:
- Recognized scenario types bypass the LLM and build PSDL from templates.
- Unrecognized queries fall through to the LLM path (tested via mock).
- The dispatcher correctly routes template-built PSDLs to analytic solvers.
"""

from __future__ import annotations

import pytest

from src.llm.translator import (
    _try_template_collision,
    _try_template_free_fall,
    _try_template_projectile,
    classify_scenario,
)
from src.physics.dispatcher import (
    SOLVER_ANALYTIC_COLLISION_1D,
    SOLVER_ANALYTIC_FREE_FALL,
    SOLVER_ANALYTIC_PROJECTILE,
    SOLVER_PYBULLET,
    dispatch_with_validation,
    select_solver,
)
from src.schema.psdl import PSDL


# ---------------------------------------------------------------------------
# Template-first path: free_fall
# ---------------------------------------------------------------------------

class TestTemplatePriorityFreeFall:
    """classify_scenario + _try_template_free_fall → PSDL without LLM."""

    def test_classify_returns_free_fall(self):
        q = "一个球从高度10米自由落体，2秒后位置？"
        assert classify_scenario(q) == "free_fall"

    def test_template_builds_psdl(self):
        q = "一个球从高度10米自由落体，2秒后位置？"
        psdl = _try_template_free_fall(q)
        assert psdl is not None
        assert psdl.scenario_type == "free_fall"

    def test_template_psdl_has_correct_height(self):
        q = "一个球从高度10米自由落体，2秒后位置？"
        psdl = _try_template_free_fall(q)
        assert psdl is not None
        particle = psdl.objects[0]
        assert abs(particle.position[2] - 10.0) < 1e-9

    def test_template_psdl_has_validation_targets(self):
        q = "从高度5米自由落体，1秒后速度？"
        psdl = _try_template_free_fall(q)
        assert psdl is not None
        assert len(psdl.validation_targets) >= 1

    def test_template_routes_to_analytic(self):
        q = "从高度5米自由落体，1秒后"
        psdl = _try_template_free_fall(q)
        assert psdl is not None
        assert select_solver(psdl) == SOLVER_ANALYTIC_FREE_FALL

    def test_template_dispatch_returns_valid_result(self):
        q = "从高度5米自由落体，1秒后"
        psdl = _try_template_free_fall(q)
        assert psdl is not None
        result = dispatch_with_validation(psdl)
        assert "states" in result
        assert "solver_used" in result
        assert "validation_results" in result
        assert result["solver_used"] == SOLVER_ANALYTIC_FREE_FALL

    def test_template_validation_passes(self):
        q = "从高度5米自由落体，1秒后"
        psdl = _try_template_free_fall(q)
        assert psdl is not None
        result = dispatch_with_validation(psdl)
        for r in result["validation_results"]:
            assert r["passed"], f"Validation failed: {r['message']}"

    def test_missing_height_returns_none(self):
        """If no height can be extracted, template path returns None."""
        q = "一个球自由落体"  # No height mentioned
        psdl = _try_template_free_fall(q)
        assert psdl is None

    @pytest.mark.parametrize(
        "query,expected_height",
        [
            ("从高度20米自由落体", 20.0),
            ("dropped from a height of 15 m", 15.0),
            ("ball falls from 8 m above", 8.0),
        ],
    )
    def test_template_height_extraction(self, query, expected_height):
        psdl = _try_template_free_fall(query)
        assert psdl is not None
        assert abs(psdl.objects[0].position[2] - expected_height) < 1e-6


# ---------------------------------------------------------------------------
# Template-first path: projectile
# ---------------------------------------------------------------------------

class TestTemplatePriorityProjectile:
    """classify_scenario + _try_template_projectile → PSDL without LLM."""

    def test_classify_returns_projectile(self):
        q = "以10 m/s水平抛出，从5米高处，2秒后位置？"
        assert classify_scenario(q) == "projectile"

    def test_template_builds_psdl(self):
        q = "以10 m/s水平抛出，从5米高处，2秒后位置？"
        psdl = _try_template_projectile(q)
        assert psdl is not None
        assert psdl.scenario_type == "projectile"

    def test_template_psdl_has_horizontal_velocity(self):
        q = "以10 m/s水平抛出，从5米高处，1秒后位置？"
        psdl = _try_template_projectile(q)
        assert psdl is not None
        vx = psdl.objects[0].velocity[0]
        assert abs(vx - 10.0) < 1e-6

    def test_template_psdl_has_validation_targets(self):
        q = "以10 m/s水平抛出，从5米高处，1秒后"
        psdl = _try_template_projectile(q)
        assert psdl is not None
        names = {t.name for t in psdl.validation_targets}
        assert "final_x" in names
        assert "final_z" in names

    def test_template_routes_to_analytic_projectile(self):
        q = "以10 m/s水平抛出，从5米高处，1秒后"
        psdl = _try_template_projectile(q)
        assert psdl is not None
        assert select_solver(psdl) == SOLVER_ANALYTIC_PROJECTILE

    def test_template_dispatch_validation_passes(self):
        q = "以10 m/s水平抛出，从5米高处，1秒后"
        psdl = _try_template_projectile(q)
        assert psdl is not None
        result = dispatch_with_validation(psdl)
        assert result["solver_used"] == SOLVER_ANALYTIC_PROJECTILE
        for r in result["validation_results"]:
            assert r["passed"], f"Validation failed: {r['message']}"

    def test_missing_params_returns_none(self):
        """If height or v0x cannot be extracted, template returns None."""
        q = "水平抛出一个球"  # No height or velocity numbers
        psdl = _try_template_projectile(q)
        assert psdl is None


# ---------------------------------------------------------------------------
# Template-first path: collision
# ---------------------------------------------------------------------------

class TestTemplatePriorityCollision:
    """classify_scenario + _try_template_collision → PSDL without LLM."""

    def test_classify_returns_collision(self):
        q = "1kg的球以2 m/s与静止的1kg球发生弹性碰撞"
        assert classify_scenario(q) == "collision"

    def test_template_builds_psdl(self):
        q = "1kg的球以2 m/s与静止的1kg球发生弹性碰撞"
        psdl = _try_template_collision(q)
        assert psdl is not None
        assert psdl.scenario_type == "collision"

    def test_template_psdl_has_two_particles(self):
        q = "1kg的球以2 m/s与静止的1kg球发生弹性碰撞"
        psdl = _try_template_collision(q)
        assert psdl is not None
        assert len(psdl.objects) == 2

    def test_template_routes_to_analytic_collision(self):
        q = "1kg的球以2 m/s与静止的1kg球发生弹性碰撞"
        psdl = _try_template_collision(q)
        assert psdl is not None
        assert select_solver(psdl) == SOLVER_ANALYTIC_COLLISION_1D

    def test_template_dispatch_returns_result(self):
        q = "1kg的球以2 m/s与静止的1kg球发生弹性碰撞"
        psdl = _try_template_collision(q)
        assert psdl is not None
        result = dispatch_with_validation(psdl)
        assert result["solver_used"] == SOLVER_ANALYTIC_COLLISION_1D
        assert len(result["states"]) == 2

    def test_missing_params_returns_none(self):
        """If fewer than 2 masses found, template returns None."""
        q = "发生碰撞"  # No masses or velocities
        psdl = _try_template_collision(q)
        assert psdl is None


# ---------------------------------------------------------------------------
# LLM fallback: dispatch_with_validation includes solver_used
# ---------------------------------------------------------------------------

class TestDispatchWithValidationResult:
    """dispatch_with_validation always returns solver_used key."""

    def test_result_has_solver_used_key(self):
        from src.templates.free_fall import build_psdl
        psdl = build_psdl(height=5.0, duration=1.0)
        result = dispatch_with_validation(psdl)
        assert "solver_used" in result

    def test_result_has_states_key(self):
        from src.templates.free_fall import build_psdl
        psdl = build_psdl(height=5.0, duration=1.0)
        result = dispatch_with_validation(psdl)
        assert "states" in result

    def test_result_has_validation_results_key(self):
        from src.templates.free_fall import build_psdl
        psdl = build_psdl(height=5.0, duration=1.0)
        result = dispatch_with_validation(psdl)
        assert "validation_results" in result

    def test_empty_validation_targets_still_runs(self):
        """Pipeline succeeds even when no validation_targets are defined."""
        psdl = PSDL(
            scenario_type="free_fall",
            world=__import__(
                "src.schema.psdl", fromlist=["WorldSettings"]
            ).WorldSettings(gravity=[0.0, 0.0, -9.8], dt=0.01, steps=100),
            objects=[
                __import__(
                    "src.schema.psdl", fromlist=["ParticleObject"]
                ).ParticleObject(
                    mass=1.0, radius=0.1,
                    position=[0.0, 0.0, 5.0],
                    velocity=[0.0, 0.0, 0.0],
                )
            ],
            validation_targets=[],
        )
        result = dispatch_with_validation(psdl)
        assert result["validation_results"] == []
        assert result["solver_used"] == SOLVER_ANALYTIC_FREE_FALL
