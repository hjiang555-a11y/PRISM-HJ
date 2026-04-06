"""
Tests for PRISM-HJ first-prototype minimum interface list v0.1.

Covers the minimum closed-loop pipeline:
  extract_problem_semantics -> build_capability_specs -> build_execution_plan
  -> StateSet / Scheduler / ResultAssembler
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Planning layer
# ---------------------------------------------------------------------------

from src.problem_semantic.models import ProblemSemanticSpec
from src.problem_semantic.extraction.pipeline import extract_problem_semantics
from src.capabilities.common.base import CapabilitySpec
from src.capabilities.particle_motion.spec import ParticleMotionCapabilitySpec
from src.capabilities.contact_interaction.spec import ContactInteractionCapabilitySpec
from src.capabilities.particle_motion.mapper import build_particle_motion_spec
from src.capabilities.contact_interaction.mapper import build_contact_interaction_spec
from src.capabilities.builder import build_capability_specs
from src.planning.execution_plan.models import ExecutionPlan
from src.planning.execution_plan.builder import build_execution_plan

# ---------------------------------------------------------------------------
# Runtime layer
# ---------------------------------------------------------------------------

from src.execution.state.state_set import StateSet
from src.execution.runtime.trigger_engine import TriggerEngine
from src.execution.runtime.scheduler import Scheduler
from src.execution.rules.persistent.gravity import ConstantGravityRule
from src.execution.rules.local.impulsive_collision import ImpulsiveCollisionRule
from src.execution.assembly.result_assembler import ResultAssembler, ExecutionResult


# ===========================================================================
# ProblemSemanticSpec
# ===========================================================================

class TestProblemSemanticSpec:
    def test_minimal_construction(self):
        spec = ProblemSemanticSpec(source_input="A ball falls from 10 m height.")
        assert spec.source_input == "A ball falls from 10 m height."
        assert spec.entities == []
        assert spec.candidate_capabilities == []
        assert spec.unresolved_items == []

    def test_full_construction(self):
        spec = ProblemSemanticSpec(
            source_input="Two balls collide.",
            entities=[{"name": "ball_a", "mass": 1.0}, {"name": "ball_b", "mass": 2.0}],
            targets_of_interest=[{"name": "v_after", "description": "velocity after collision"}],
            explicit_conditions=[{"name": "initial_velocity_a", "value": 3.0, "entity": "ball_a"}],
            candidate_domains=["mechanics"],
            candidate_capabilities=["particle_motion", "contact_interaction"],
            rule_extraction_inputs={"raw_text": "Two balls collide."},
            rule_execution_inputs={"restitution": 1.0},
            unresolved_items=["mass_b_pending"],
        )
        assert len(spec.entities) == 2
        assert spec.candidate_capabilities == ["particle_motion", "contact_interaction"]
        assert "mass_b_pending" in spec.unresolved_items


# ===========================================================================
# extract_problem_semantics
# ===========================================================================

class TestExtractProblemSemantics:
    def test_returns_problem_semantic_spec(self):
        result = extract_problem_semantics("A ball falls from rest at height 5 m.")
        assert isinstance(result, ProblemSemanticSpec)

    def test_source_input_preserved(self):
        text = "A ball is thrown horizontally at 10 m/s from a cliff."
        result = extract_problem_semantics(text)
        assert result.source_input == text

    def test_candidate_capabilities_preset(self):
        result = extract_problem_semantics("anything")
        assert "particle_motion" in result.candidate_capabilities
        assert "contact_interaction" in result.candidate_capabilities

    def test_raw_text_in_rule_extraction_inputs(self):
        text = "some problem"
        result = extract_problem_semantics(text)
        assert result.rule_extraction_inputs.get("raw_text") == text

    def test_unresolved_items_populated(self):
        result = extract_problem_semantics("any input")
        assert len(result.unresolved_items) > 0


# ===========================================================================
# CapabilitySpec (common base)
# ===========================================================================

class TestCapabilitySpecBase:
    def test_minimal_construction(self):
        spec = CapabilitySpec(capability_name="test_cap")
        assert spec.capability_name == "test_cap"
        assert spec.applies_to_entities == []
        assert spec.candidate_rules == []
        assert spec.missing_inputs == []

    def test_required_fields_present(self):
        spec = CapabilitySpec(
            capability_name="my_cap",
            applies_to_entities=["e1"],
            target_mapping={"speed": "v"},
            rule_extraction_inputs={"raw": "..."},
            rule_execution_inputs={"g": 9.8},
            candidate_rules=["gravity"],
            missing_inputs=["mass"],
            trigger_requirements=[{"type": "contact"}],
        )
        assert spec.applies_to_entities == ["e1"]
        assert "gravity" in spec.candidate_rules


# ===========================================================================
# ParticleMotionCapabilitySpec
# ===========================================================================

class TestParticleMotionCapabilitySpec:
    def test_default_capability_name(self):
        spec = ParticleMotionCapabilitySpec(capability_name="particle_motion")
        assert spec.capability_name == "particle_motion"

    def test_extra_fields(self):
        spec = ParticleMotionCapabilitySpec(
            capability_name="particle_motion",
            initial_state_requirements={"ball": {"position": [0, 0, 10]}},
            background_interaction_hints=["gravity"],
        )
        assert "gravity" in spec.background_interaction_hints
        assert "ball" in spec.initial_state_requirements


# ===========================================================================
# ContactInteractionCapabilitySpec
# ===========================================================================

class TestContactInteractionCapabilitySpec:
    def test_default_capability_name(self):
        spec = ContactInteractionCapabilitySpec(capability_name="contact_interaction")
        assert spec.capability_name == "contact_interaction"

    def test_extra_fields(self):
        spec = ContactInteractionCapabilitySpec(
            capability_name="contact_interaction",
            contact_pairs=[["A", "B"]],
            contact_model_hints=["elastic"],
            pre_trigger_state_requirements={"A": {"velocity": [3, 0, 0]}},
        )
        assert spec.contact_pairs == [["A", "B"]]
        assert "elastic" in spec.contact_model_hints


# ===========================================================================
# Mappers
# ===========================================================================

class TestMappers:
    def _make_problem_spec(self) -> ProblemSemanticSpec:
        return ProblemSemanticSpec(
            source_input="Ball A (1 kg, v=3 m/s) hits Ball B (2 kg, at rest).",
            entities=[{"name": "A", "mass": 1.0}, {"name": "B", "mass": 2.0}],
            targets_of_interest=[{"name": "v_A_after", "description": "A speed after collision"}],
            explicit_conditions=[
                {"name": "velocity", "value": 3.0, "entity": "A"},
                {"name": "velocity", "value": 0.0, "entity": "B"},
            ],
            candidate_domains=["mechanics"],
            candidate_capabilities=["particle_motion", "contact_interaction"],
            rule_extraction_inputs={"raw_text": "..."},
            rule_execution_inputs={"restitution": 1.0},
            unresolved_items=[],
        )

    def test_build_particle_motion_spec(self):
        spec = build_particle_motion_spec(self._make_problem_spec())
        assert isinstance(spec, ParticleMotionCapabilitySpec)
        assert "constant_gravity" in spec.candidate_rules
        assert "A" in spec.applies_to_entities
        assert "B" in spec.applies_to_entities

    def test_build_contact_interaction_spec(self):
        spec = build_contact_interaction_spec(self._make_problem_spec())
        assert isinstance(spec, ContactInteractionCapabilitySpec)
        assert "impulsive_collision" in spec.candidate_rules
        assert ["A", "B"] in spec.contact_pairs

    def test_build_capability_specs_returns_two(self):
        specs = build_capability_specs(self._make_problem_spec())
        assert len(specs) == 2
        names = [s.capability_name for s in specs]
        assert "particle_motion" in names
        assert "contact_interaction" in names


# ===========================================================================
# ExecutionPlan + builder
# ===========================================================================

class TestExecutionPlanBuilder:
    def _make_specs(self):
        problem = ProblemSemanticSpec(
            source_input="test",
            entities=[{"name": "A"}, {"name": "B"}],
            targets_of_interest=[{"name": "final_pos", "description": "final position of A"}],
            explicit_conditions=[],
            candidate_domains=["mechanics"],
            candidate_capabilities=["particle_motion", "contact_interaction"],
            rule_extraction_inputs={},
            rule_execution_inputs={},
            unresolved_items=["some_pending"],
        )
        return build_capability_specs(problem)

    def test_build_execution_plan_type(self):
        specs = self._make_specs()
        plan = build_execution_plan(specs)
        assert isinstance(plan, ExecutionPlan)

    def test_persistent_rules_present(self):
        plan = build_execution_plan(self._make_specs())
        rule_names = [r["rule_name"] for r in plan.persistent_rule_plan]
        assert "constant_gravity" in rule_names

    def test_local_rules_present(self):
        plan = build_execution_plan(self._make_specs())
        rule_names = [r["rule_name"] for r in plan.local_rule_plan]
        assert "impulsive_collision" in rule_names

    def test_trigger_plan_not_empty(self):
        plan = build_execution_plan(self._make_specs())
        assert len(plan.trigger_plan) > 0

    def test_capability_bindings(self):
        plan = build_execution_plan(self._make_specs())
        assert "particle_motion" in plan.capability_bindings
        assert "contact_interaction" in plan.capability_bindings

    def test_state_set_plan_has_entities(self):
        plan = build_execution_plan(self._make_specs())
        assert "A" in plan.state_set_plan
        assert "B" in plan.state_set_plan


# ===========================================================================
# StateSet
# ===========================================================================

class TestStateSet:
    def test_set_and_get(self):
        ss = StateSet()
        ss.set_entity_state("ball", {"position": [0, 0, 5], "velocity": [1, 0, 0], "mass": 1.0})
        state = ss.get_entity_state("ball")
        assert state["position"] == [0, 0, 5]

    def test_update_partial(self):
        ss = StateSet()
        ss.set_entity_state("ball", {"position": [0, 0, 0], "velocity": [1, 0, 0]})
        ss.update_entity_state("ball", {"velocity": [2, 0, 0]})
        assert ss.get_entity_state("ball")["velocity"] == [2, 0, 0]
        assert ss.get_entity_state("ball")["position"] == [0, 0, 0]

    def test_get_missing_entity_returns_none(self):
        ss = StateSet()
        assert ss.get_entity_state("nonexistent") is None

    def test_register_and_query_target(self):
        ss = StateSet()
        ss.register_target("final_speed", 5.0)
        assert ss.query_target_state("final_speed") == 5.0

    def test_all_entity_ids(self):
        ss = StateSet()
        ss.set_entity_state("A", {})
        ss.set_entity_state("B", {})
        ids = ss.all_entity_ids()
        assert "A" in ids
        assert "B" in ids

    def test_state_is_copy_not_reference(self):
        ss = StateSet()
        original = {"position": [0, 0, 0]}
        ss.set_entity_state("ball", original)
        original["position"] = [999, 999, 999]
        assert ss.get_entity_state("ball")["position"] == [0, 0, 0]


# ===========================================================================
# TriggerEngine
# ===========================================================================

class TestTriggerEngine:
    def test_contact_trigger_fires_when_close(self):
        engine = TriggerEngine(contact_threshold=1.0)
        ss = StateSet()
        ss.set_entity_state("A", {"position": [0.0, 0.0, 0.0], "velocity": [0, 0, 0]})
        ss.set_entity_state("B", {"position": [0.5, 0.0, 0.0], "velocity": [0, 0, 0]})
        trigger_plan = [{"type": "contact", "pairs": [["A", "B"]], "threshold": 1.0}]
        events = engine.check_triggers(ss, trigger_plan)
        assert len(events) == 1
        assert events[0]["trigger_type"] == "contact"
        assert events[0]["entity_pair"] == ["A", "B"]

    def test_contact_trigger_does_not_fire_when_far(self):
        engine = TriggerEngine(contact_threshold=1.0)
        ss = StateSet()
        ss.set_entity_state("A", {"position": [0.0, 0.0, 0.0]})
        ss.set_entity_state("B", {"position": [5.0, 0.0, 0.0]})
        trigger_plan = [{"type": "contact", "pairs": [["A", "B"]], "threshold": 1.0}]
        events = engine.check_triggers(ss, trigger_plan)
        assert events == []

    def test_no_trigger_plan_returns_empty(self):
        engine = TriggerEngine()
        ss = StateSet()
        assert engine.check_triggers(ss, []) == []


# ===========================================================================
# ConstantGravityRule
# ===========================================================================

class TestConstantGravityRule:
    def test_apply_returns_dv(self):
        rule = ConstantGravityRule()
        state = {"position": [0, 0, 10], "velocity": [0, 0, 0], "mass": 1.0}
        inputs = {"gravity_vector": [0, 0, -9.8], "dt": 0.1}
        delta = rule.apply(state, inputs)
        assert "dv" in delta
        assert abs(delta["dv"][2] - (-0.98)) < 1e-9

    def test_default_gravity_used_when_missing(self):
        rule = ConstantGravityRule()
        state = {"velocity": [0, 0, 0]}
        delta = rule.apply(state, {"dt": 1.0})
        assert abs(delta["dv"][2] - (-9.8)) < 1e-6

    def test_rule_name(self):
        assert ConstantGravityRule.rule_name == "constant_gravity"

    def test_required_inputs(self):
        assert "gravity_vector" in ConstantGravityRule.required_inputs
        assert "dt" in ConstantGravityRule.required_inputs


# ===========================================================================
# ImpulsiveCollisionRule
# ===========================================================================

class TestImpulsiveCollisionRule:
    def test_elastic_equal_mass_exchange_velocities(self):
        rule = ImpulsiveCollisionRule()
        state = {
            "A": {"mass": 1.0, "velocity": [3.0, 0.0, 0.0], "position": [0, 0, 0]},
            "B": {"mass": 1.0, "velocity": [0.0, 0.0, 0.0], "position": [0.4, 0, 0]},
        }
        inputs = {
            "restitution": 1.0,
            "contact_normal": [1.0, 0.0, 0.0],
            "entity_pair": ["A", "B"],
        }
        result = rule.apply(state, inputs)
        assert abs(result["A"]["velocity"][0] - 0.0) < 1e-9
        assert abs(result["B"]["velocity"][0] - 3.0) < 1e-9

    def test_separating_particles_not_affected(self):
        rule = ImpulsiveCollisionRule()
        state = {
            "A": {"mass": 1.0, "velocity": [-1.0, 0.0, 0.0]},
            "B": {"mass": 1.0, "velocity": [1.0, 0.0, 0.0]},
        }
        inputs = {
            "restitution": 1.0,
            "contact_normal": [1.0, 0.0, 0.0],
            "entity_pair": ["A", "B"],
        }
        result = rule.apply(state, inputs)
        # Already separating — velocities unchanged
        assert result["A"]["velocity"] == [-1.0, 0.0, 0.0]
        assert result["B"]["velocity"] == [1.0, 0.0, 0.0]

    def test_rule_name(self):
        assert ImpulsiveCollisionRule.rule_name == "impulsive_collision"

    def test_trigger_condition_type(self):
        assert ImpulsiveCollisionRule.trigger_condition_type == "contact"


# ===========================================================================
# ResultAssembler + ExecutionResult
# ===========================================================================

class TestResultAssembler:
    def test_assemble_returns_execution_result(self):
        ss = StateSet()
        ss.set_entity_state("ball", {"position": [1, 2, 3], "velocity": [0, 0, -5], "mass": 1.0})
        assembler = ResultAssembler()
        result = assembler.assemble(ss, {}, trigger_records=[])
        assert isinstance(result, ExecutionResult)

    def test_assemble_extracts_field(self):
        ss = StateSet()
        ss.set_entity_state("ball", {"position": [0, 0, 2], "velocity": [3, 0, 0]})
        assembler = ResultAssembler()
        plan = {"final_velocity": {"entity": "ball", "field": "velocity"}}
        result = assembler.assemble(ss, plan, trigger_records=[])
        assert result.target_results["final_velocity"] == [3, 0, 0]

    def test_assemble_with_trigger_records(self):
        ss = StateSet()
        assembler = ResultAssembler()
        records = [{"trigger_type": "contact", "entity_pair": ["A", "B"]}]
        result = assembler.assemble(ss, {}, trigger_records=records)
        assert result.trigger_records == records

    def test_missing_entity_records_note(self):
        ss = StateSet()
        assembler = ResultAssembler()
        plan = {"x": {"entity": "ghost", "field": "position"}}
        result = assembler.assemble(ss, plan)
        assert result.target_results["x"] is None
        assert len(result.execution_notes) > 0


# ===========================================================================
# Full minimum closed-loop integration test
# ===========================================================================

class TestMinimumClosedLoop:
    """
    Verify the full chain:
      extract_problem_semantics -> build_capability_specs -> build_execution_plan
      -> Scheduler.run -> ExecutionResult
    """

    def test_free_fall_closed_loop(self):
        """A single ball falling under gravity for a short time."""
        text = "A ball of mass 1 kg is released from rest at height 10 m."
        problem_spec = extract_problem_semantics(text)
        # Manually enrich (simulates a richer extractor)
        problem_spec.entities = [{"name": "ball"}]
        problem_spec.targets_of_interest = [
            {"name": "final_position", "description": "position after fall"}
        ]
        problem_spec.unresolved_items = []

        cap_specs = build_capability_specs(problem_spec)
        plan = build_execution_plan(cap_specs)

        # Initialise state
        ss = StateSet()
        ss.set_entity_state("ball", {"position": [0.0, 0.0, 10.0], "velocity": [0.0, 0.0, 0.0], "mass": 1.0})

        # Enrich assembly plan for position extraction
        plan.assembly_plan["final_position"] = {"entity": "ball", "field": "position"}

        scheduler = Scheduler(dt=0.01, steps=50, contact_threshold=0.5)
        result = scheduler.run(plan, ss, gravity_vector=[0.0, 0.0, -9.8])

        assert isinstance(result, ExecutionResult)
        pos = result.target_results.get("final_position")
        assert pos is not None
        # After 50 steps at dt=0.01: z = 10 - 0.5*9.8*(0.5**2) ≈ 8.775
        assert pos[2] < 10.0, "Ball should have fallen"

    def test_collision_closed_loop(self):
        """Two equal-mass balls collide head-on (elastic)."""
        text = "Ball A (1 kg, v=2 m/s) collides head-on with Ball B (1 kg, at rest)."
        problem_spec = extract_problem_semantics(text)
        problem_spec.entities = [{"name": "A"}, {"name": "B"}]
        problem_spec.unresolved_items = []

        cap_specs = build_capability_specs(problem_spec)
        plan = build_execution_plan(cap_specs)

        ss = StateSet()
        ss.set_entity_state("A", {"position": [0.0, 0.0, 0.0], "velocity": [2.0, 0.0, 0.0], "mass": 1.0})
        ss.set_entity_state("B", {"position": [0.3, 0.0, 0.0], "velocity": [0.0, 0.0, 0.0], "mass": 1.0})

        plan.assembly_plan["vel_A"] = {"entity": "A", "field": "velocity"}
        plan.assembly_plan["vel_B"] = {"entity": "B", "field": "velocity"}

        scheduler = Scheduler(dt=0.001, steps=10, contact_threshold=0.5)
        result = scheduler.run(plan, ss, gravity_vector=[0.0, 0.0, 0.0])

        assert isinstance(result, ExecutionResult)
        assert len(result.trigger_records) > 0, "Contact should have triggered"
