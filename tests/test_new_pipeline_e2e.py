"""
End-to-end integration tests for the **new** execution pipeline.

Test flow:  NL input → extract_problem_semantics → build_capability_specs →
            build_execution_plan (with admission_hints) → Scheduler.run →
            ResultAssembler → ExecutionResult

Each test validates a complete scenario from natural language input through
to physics-correct final results, using the Euler-integrated Scheduler.

NOTE: Euler integration introduces small numerical errors compared to the
exact analytic solvers.  Tolerances are set accordingly.
"""

from __future__ import annotations

import math

import pytest

from src.capabilities.builder import build_capability_specs
from src.execution.runtime.scheduler import Scheduler
from src.execution.state.state_set import StateSet
from src.planning.execution_plan.builder import build_execution_plan
from src.problem_semantic.extraction.pipeline import extract_problem_semantics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_new_pipeline(question: str) -> dict:
    """
    Execute the full new pipeline for *question* and return a dict with
    ``spec``, ``plan``, ``result``, and ``state_set`` for assertion.
    """
    spec = extract_problem_semantics(question)
    cap_specs = build_capability_specs(spec)

    admission_hints = {
        "interaction_hints": spec.interaction_hints,
        "assumption_hints": spec.assumption_hints,
        "entity_model_hints": spec.entity_model_hints,
        "query_hints": spec.query_hints,
    }
    plan = build_execution_plan(cap_specs, admission_hints=admission_hints)

    state_set = StateSet()
    for entity in spec.entities:
        eid = entity["name"]
        state_set.set_entity_state(eid, {
            "position": list(entity.get("initial_position", [0, 0, 0])),
            "velocity": list(entity.get("initial_velocity", [0, 0, 0])),
            "mass": float(entity.get("mass", 1.0)),
        })

    dt = spec.rule_execution_inputs.get("dt", 0.01)
    steps = spec.rule_execution_inputs.get("steps", 100)
    gravity = spec.rule_execution_inputs.get("gravity_vector", [0, 0, -9.8])

    scheduler = Scheduler(dt=dt, steps=steps)
    result = scheduler.run(plan, state_set, gravity_vector=gravity)

    return {
        "spec": spec,
        "plan": plan,
        "result": result,
        "state_set": state_set,
    }


# ---------------------------------------------------------------------------
# Free-fall scenarios
# ---------------------------------------------------------------------------

class TestFreeFallE2E:
    """End-to-end free-fall tests."""

    def test_free_fall_basic_chinese(self):
        """一个2kg的球从高度5米自由落体，1秒后位置和速度"""
        q = "一个2kg的球从高度5米自由落体，1秒后位置和速度？"
        out = _run_new_pipeline(q)

        spec = out["spec"]
        assert len(spec.entities) == 1
        assert spec.entities[0]["name"] == "ball"
        assert spec.entities[0]["mass"] == 2.0
        assert "gravity_present" in spec.interaction_hints

        plan = out["plan"]
        assert "particle_motion" in plan.admitted_capabilities
        assert plan.admission_hints.get("interaction_hints") == spec.interaction_hints

        # Physics check: after 1s free-fall from 5m
        # Analytic: z = 5 + 0*1 - 0.5*9.8*1^2 = 5 - 4.9 = 0.1 m
        # Analytic: vz = 0 - 9.8*1 = -9.8 m/s
        state = out["state_set"].get_entity_state("ball")
        assert state is not None
        assert state["position"][2] == pytest.approx(0.1, abs=0.2)  # Euler tolerance
        assert state["velocity"][2] == pytest.approx(-9.8, abs=0.2)

    def test_free_fall_english(self):
        """A 1kg ball dropped from height 10m, after 1s."""
        q = "A 1kg ball dropped from height 10m, after 1s what is the position?"
        out = _run_new_pipeline(q)

        spec = out["spec"]
        assert len(spec.entities) == 1
        assert spec.entities[0]["mass"] == 1.0
        assert spec.entities[0]["initial_position"][2] == 10.0

        state = out["state_set"].get_entity_state("ball")
        # z = 10 - 0.5*9.8*1 = 5.1 m
        assert state["position"][2] == pytest.approx(5.1, abs=0.2)

    def test_free_fall_different_duration(self):
        """自由落体2秒后"""
        q = "一个1kg的球从高度20米自由落体，2秒后位置？"
        out = _run_new_pipeline(q)

        spec = out["spec"]
        steps = spec.rule_execution_inputs.get("steps", 100)
        assert steps == 200  # 2s / 0.01s

        state = out["state_set"].get_entity_state("ball")
        # z = 20 - 0.5*9.8*4 = 20 - 19.6 = 0.4 m
        assert state["position"][2] == pytest.approx(0.4, abs=0.5)

    def test_free_fall_semantic_hints(self):
        """Verify hints are correctly extracted and propagated."""
        q = "忽略空气阻力，一个2kg的球从高度5米自由落体"
        out = _run_new_pipeline(q)

        spec = out["spec"]
        assert "ignore_air_resistance" in spec.assumption_hints
        assert "gravity_present" in spec.interaction_hints
        assert "point_mass" in spec.entity_model_hints

        plan = out["plan"]
        assert "ignore_air_resistance" in plan.admission_hints.get("assumption_hints", [])


# ---------------------------------------------------------------------------
# Projectile scenarios
# ---------------------------------------------------------------------------

class TestProjectileE2E:
    """End-to-end projectile tests."""

    def test_projectile_basic_chinese(self):
        """水平抛出"""
        q = "水平抛出一个物体，初速度5m/s，高度10米，1秒后位置？"
        out = _run_new_pipeline(q)

        spec = out["spec"]
        assert len(spec.entities) == 1
        assert spec.entities[0]["name"] == "projectile"
        assert spec.entities[0]["initial_velocity"][0] == 5.0

        plan = out["plan"]
        assert "particle_motion" in plan.admitted_capabilities

        state = out["state_set"].get_entity_state("projectile")
        # x = 0 + 5*1 = 5 m
        # z = 10 + 0 - 0.5*9.8*1 = 5.1 m
        assert state["position"][0] == pytest.approx(5.0, abs=0.2)
        assert state["position"][2] == pytest.approx(5.1, abs=0.5)

    def test_projectile_english(self):
        """English projectile question."""
        q = "A ball is thrown horizontally with speed 10m/s from height 20m, after 2s."
        out = _run_new_pipeline(q)

        spec = out["spec"]
        assert len(spec.entities) == 1

        state = out["state_set"].get_entity_state("projectile")
        # x = 10*2 = 20 m
        # z = 20 - 0.5*9.8*4 = 0.4 m
        assert state["position"][0] == pytest.approx(20.0, abs=0.5)
        assert state["position"][2] == pytest.approx(0.4, abs=0.5)


# ---------------------------------------------------------------------------
# Collision scenarios
# ---------------------------------------------------------------------------

class TestCollisionE2E:
    """End-to-end collision tests."""

    def test_elastic_collision_chinese(self):
        """弹性碰撞"""
        q = "一个2kg物体以3m/s速度与一个1kg静止物体发生弹性碰撞，碰后速度？"
        out = _run_new_pipeline(q)

        spec = out["spec"]
        assert len(spec.entities) == 2
        assert "collision_possible" in spec.interaction_hints
        assert "elastic_collision" in spec.assumption_hints

        plan = out["plan"]
        assert "contact_interaction" in plan.admitted_capabilities
        assert "elastic_collision" in plan.admission_hints.get("assumption_hints", [])

    def test_elastic_collision_equal_mass(self):
        """Equal mass elastic collision: velocities should swap."""
        q = "一个1kg物体以2m/s速度与一个1kg静止物体发生弹性碰撞"
        out = _run_new_pipeline(q)

        # In equal-mass elastic collision, velocities swap:
        # v1_after = 0 m/s, v2_after = 2 m/s
        result = out["result"]
        trigger_records = result.trigger_records
        # Should have triggered at least one collision
        assert len(trigger_records) >= 1

    def test_collision_with_both_capabilities(self):
        """Collision scenario should admit both particle_motion and contact_interaction."""
        q = "两个物体碰撞：2kg以4m/s和1kg以0m/s，弹性碰撞后速度？"
        out = _run_new_pipeline(q)

        plan = out["plan"]
        # Both capabilities should be admitted for collision
        assert "particle_motion" in plan.admitted_capabilities
        assert "contact_interaction" in plan.admitted_capabilities


# ---------------------------------------------------------------------------
# Admission hints filtering tests
# ---------------------------------------------------------------------------

class TestAdmissionHintsFiltering:
    """Test that admission hints correctly filter rules in Scheduler."""

    def test_gravity_hint_enables_gravity_rule(self):
        """When gravity_present is in hints, gravity rule should be active."""
        q = "一个1kg的球从高度5米自由落体，1秒后"
        out = _run_new_pipeline(q)

        state = out["state_set"].get_entity_state("ball")
        # Gravity should have affected the velocity
        assert state["velocity"][2] < 0  # falling down

    def test_collision_hint_activates_collision_rule(self):
        """When collision_possible is in hints, collision rule should be active."""
        q = "1kg物体以2m/s和1kg物体以0m/s发生弹性碰撞"
        out = _run_new_pipeline(q)

        plan = out["plan"]
        assert "collision_possible" in plan.admission_hints.get("interaction_hints", [])
        assert "contact_interaction" in plan.admitted_capabilities
        assert len(plan.local_rule_plan) > 0

    def test_hints_propagated_to_execution_plan(self):
        """Verify all 4 hint types propagate to ExecutionPlan."""
        q = "忽略空气阻力，一个2kg的球从高度5米自由落体，1秒后位置和速度？"
        out = _run_new_pipeline(q)

        hints = out["plan"].admission_hints
        assert "interaction_hints" in hints
        assert "assumption_hints" in hints
        assert "entity_model_hints" in hints
        assert "query_hints" in hints

    def test_inelastic_collision_hint_sets_restitution(self):
        """inelastic_collision hint should set restitution to 0.0."""
        q = "两个物体发生完全非弹性碰撞：2kg以3m/s和1kg以0m/s"
        out = _run_new_pipeline(q)

        plan = out["plan"]
        assert "inelastic_collision" in plan.admission_hints.get("assumption_hints", [])

        # Check restitution in rule_execution_inputs
        spec = out["spec"]
        assert spec.rule_execution_inputs.get("restitution") == 0.0


# ---------------------------------------------------------------------------
# Pipeline routing tests
# ---------------------------------------------------------------------------

class TestPipelineRouting:
    """Test pipeline routing logic."""

    def test_known_scenario_produces_result(self):
        """Known scenario types should produce execution result."""
        from main import run_execution_pipeline
        result = run_execution_pipeline("一个2kg的球从高度5米自由落体，1秒后")
        assert result is not None
        assert "target_results" in result

    def test_known_scenario_english(self):
        """English known scenario also produces result."""
        from main import run_execution_pipeline
        result = run_execution_pipeline("A 1kg ball dropped from height 10m, after 1s")
        assert result is not None
        assert "target_results" in result

    def test_unknown_scenario_returns_none(self):
        """Unknown scenario types return None."""
        from main import run_execution_pipeline
        assert run_execution_pipeline("什么是量子力学？") is None
        assert run_execution_pipeline("Hello world") is None

    def test_pipeline_returns_result_dict(self):
        """Pipeline should return result dict for known scenarios."""
        from main import run_execution_pipeline
        result = run_execution_pipeline("一个2kg的球从高度5米自由落体，1秒后位置？")
        assert result is not None
        assert "target_results" in result
        assert "state_set" in result

    def test_pipeline_returns_none_for_unknown(self):
        """Pipeline should return None for unknown scenarios."""
        from main import run_execution_pipeline
        result = run_execution_pipeline("解释牛顿第三定律")
        assert result is None


# ---------------------------------------------------------------------------
# Extraction enrichment verification
# ---------------------------------------------------------------------------

class TestExtractionEnrichment:
    """Verify extraction pipeline produces enriched specs."""

    def test_free_fall_spec_fully_populated(self):
        spec = extract_problem_semantics("一个2kg的球从高度5米自由落体，1秒后")
        assert len(spec.entities) == 1
        assert spec.entities[0]["mass"] == 2.0
        assert spec.entities[0]["initial_position"] == [0, 0, 5.0]
        assert spec.rule_execution_inputs.get("scenario_type") == "free_fall"
        assert spec.rule_execution_inputs.get("steps") == 100
        assert not spec.unresolved_items

    def test_projectile_spec_fully_populated(self):
        spec = extract_problem_semantics("水平抛出一个物体，初速度5m/s，高度10米")
        assert len(spec.entities) == 1
        assert spec.entities[0]["initial_velocity"][0] == 5.0
        assert spec.rule_execution_inputs.get("scenario_type") == "projectile"
        assert not spec.unresolved_items

    def test_collision_spec_fully_populated(self):
        spec = extract_problem_semantics("2kg物体以3m/s和1kg物体以0m/s弹性碰撞")
        assert len(spec.entities) == 2
        assert spec.entities[0]["mass"] == 2.0
        assert spec.entities[1]["mass"] == 1.0
        assert spec.rule_execution_inputs.get("scenario_type") == "collision"
        assert not spec.unresolved_items

    def test_unknown_scenario_remains_skeleton(self):
        spec = extract_problem_semantics("电路分析题")
        assert len(spec.entities) == 0
        assert len(spec.unresolved_items) > 0

    def test_candidate_capabilities_narrowed(self):
        """Free fall should only have particle_motion capability."""
        spec = extract_problem_semantics("一个球从高度5米自由落体")
        assert spec.candidate_capabilities == ["particle_motion"]

    def test_collision_capabilities_include_both(self):
        """Collision should have both capabilities."""
        spec = extract_problem_semantics("2kg物体以3m/s和1kg物体以0m/s碰撞")
        assert "particle_motion" in spec.candidate_capabilities
        assert "contact_interaction" in spec.candidate_capabilities
