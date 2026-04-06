"""
ExecutionPlan admission 状态测试 v0.1.

覆盖以下必测场景：

必测 1：capability 缺少关键 admission 输入时进入 deferred 路径
必测 2：capability admission 条件满足时进入 admitted 路径
必测 3：ExecutionPlan 中能区分 admitted / deferred / unresolved 三种状态
附加测试：admitted capability 的规则进入执行计划，deferred/unresolved 的不进入
"""

from __future__ import annotations

import pytest

from src.capabilities.common.base import CapabilitySpec
from src.capabilities.contact_interaction.mapper import build_contact_interaction_spec
from src.capabilities.contact_interaction.spec import ContactInteractionCapabilitySpec
from src.capabilities.particle_motion.mapper import build_particle_motion_spec
from src.capabilities.particle_motion.spec import ParticleMotionCapabilitySpec
from src.planning.execution_plan.builder import _judge_admission, build_execution_plan
from src.planning.execution_plan.models import ExecutionPlan
from src.problem_semantic.models import ProblemSemanticSpec


# ---------------------------------------------------------------------------
# 辅助：构造最小 ProblemSemanticSpec
# ---------------------------------------------------------------------------

def _make_minimal_problem_spec(
    entities=None,
    explicit_conditions=None,
    targets=None,
    unresolved_items=None,
) -> ProblemSemanticSpec:
    return ProblemSemanticSpec(
        source_input="test",
        entities=entities or [],
        targets_of_interest=targets or [],
        explicit_conditions=explicit_conditions or [],
        unresolved_items=unresolved_items or [],
    )


# ---------------------------------------------------------------------------
# _judge_admission 单元测试
# ---------------------------------------------------------------------------

class TestJudgeAdmission:
    """_judge_admission() 判定逻辑单元测试。"""

    def test_unresolved_when_no_entities(self):
        """applies_to_entities 为空 → unresolved。"""
        spec = ParticleMotionCapabilitySpec(
            capability_name="particle_motion",
            applies_to_entities=[],
            missing_entry_inputs=[],
        )
        assert _judge_admission(spec) == "unresolved"

    def test_deferred_when_missing_entry_inputs(self):
        """applies_to_entities 非空 且 missing_entry_inputs 非空 → deferred。"""
        spec = ParticleMotionCapabilitySpec(
            capability_name="particle_motion",
            applies_to_entities=["ball"],
            missing_entry_inputs=["mass_per_entity"],
        )
        assert _judge_admission(spec) == "deferred"

    def test_admitted_when_all_entry_inputs_present(self):
        """applies_to_entities 非空 且 missing_entry_inputs 为空 → admitted。"""
        spec = ParticleMotionCapabilitySpec(
            capability_name="particle_motion",
            applies_to_entities=["ball"],
            missing_entry_inputs=[],
        )
        assert _judge_admission(spec) == "admitted"

    def test_admitted_ignores_missing_inputs(self):
        """missing_inputs（执行层）不影响 admission 判定。"""
        spec = ParticleMotionCapabilitySpec(
            capability_name="particle_motion",
            applies_to_entities=["ball"],
            missing_entry_inputs=[],
            missing_inputs=["some_runtime_param"],
        )
        assert _judge_admission(spec) == "admitted"

    def test_deferred_multiple_missing_entry_inputs(self):
        """多个缺失入口要素 → deferred。"""
        spec = ContactInteractionCapabilitySpec(
            capability_name="contact_interaction",
            applies_to_entities=["a", "b"],
            missing_entry_inputs=["pre_collision_velocity_per_entity", "mass_per_entity"],
        )
        assert _judge_admission(spec) == "deferred"


# ---------------------------------------------------------------------------
# 必测 1：capability 缺少关键 admission 输入 → deferred 而非 admitted
# ---------------------------------------------------------------------------

class TestMissingEntryInputsGoesToDeferred:
    """必测 1：缺少关键 admission 输入时不应被 admitted。"""

    def test_particle_motion_no_conditions_is_deferred(self):
        """无任何 explicit_conditions 的粒子运动 spec → missing_entry_inputs 非空 → deferred。"""
        problem_spec = _make_minimal_problem_spec(
            entities=[{"name": "ball"}],
            explicit_conditions=[],
        )
        spec = build_particle_motion_spec(problem_spec)
        assert spec.missing_entry_inputs, "应有缺失入口要素"
        plan = build_execution_plan([spec])
        assert "particle_motion" in [d["capability_name"] for d in plan.deferred_capabilities]
        assert "particle_motion" not in plan.admitted_capabilities

    def test_deferred_capability_not_in_persistent_rules(self):
        """deferred capability 的规则不应进入 persistent_rule_plan。"""
        problem_spec = _make_minimal_problem_spec(
            entities=[{"name": "ball"}],
        )
        spec = build_particle_motion_spec(problem_spec)
        # 确保它是 deferred
        spec_with_missing = spec.model_copy(update={"missing_entry_inputs": ["mass_per_entity"]})
        plan = build_execution_plan([spec_with_missing])
        rule_names = [r["rule_name"] for r in plan.persistent_rule_plan]
        assert "constant_gravity" not in rule_names

    def test_contact_interaction_single_entity_is_deferred(self):
        """只有一个实体的接触交互 spec → at_least_two_entities 缺失 → deferred。"""
        problem_spec = _make_minimal_problem_spec(
            entities=[{"name": "ball_a"}],
            explicit_conditions=[
                {"entity": "ball_a", "name": "mass", "value": 1.0},
                {"entity": "ball_a", "name": "velocity", "value": 2.0},
            ],
        )
        spec = build_contact_interaction_spec(problem_spec)
        assert "at_least_two_entities" in spec.missing_entry_inputs
        plan = build_execution_plan([spec])
        assert "contact_interaction" in [d["capability_name"] for d in plan.deferred_capabilities]
        assert "contact_interaction" not in plan.admitted_capabilities

    def test_deferred_capability_not_in_local_rules(self):
        """deferred capability 的规则不应进入 local_rule_plan。"""
        problem_spec = _make_minimal_problem_spec(
            entities=[{"name": "ball_a"}],
            explicit_conditions=[
                {"entity": "ball_a", "name": "mass", "value": 1.0},
                {"entity": "ball_a", "name": "velocity", "value": 2.0},
            ],
        )
        spec = build_contact_interaction_spec(problem_spec)
        plan = build_execution_plan([spec])
        assert plan.local_rule_plan == []


# ---------------------------------------------------------------------------
# 必测 2：capability admission 条件满足时进入 admitted 路径
# ---------------------------------------------------------------------------

class TestFullySpecifiedCapabilityIsAdmitted:
    """必测 2：入口要素齐全时 capability 应进入 admitted。"""

    def test_particle_motion_with_all_conditions_is_admitted(self):
        """提供位置、速度、质量条件 → missing_entry_inputs 为空 → admitted。"""
        problem_spec = _make_minimal_problem_spec(
            entities=[{"name": "ball"}],
            explicit_conditions=[
                {"entity": "ball", "name": "height", "value": 10.0},
                {"entity": "ball", "name": "velocity", "value": 0.0},
                {"entity": "ball", "name": "mass", "value": 1.0},
            ],
        )
        spec = build_particle_motion_spec(problem_spec)
        assert spec.missing_entry_inputs == [], f"不应有缺失入口要素，实际: {spec.missing_entry_inputs}"
        plan = build_execution_plan([spec])
        assert "particle_motion" in plan.admitted_capabilities
        assert "particle_motion" not in [d["capability_name"] for d in plan.deferred_capabilities]

    def test_admitted_capability_in_persistent_rules(self):
        """admitted capability 的规则应进入 persistent_rule_plan。"""
        problem_spec = _make_minimal_problem_spec(
            entities=[{"name": "ball"}],
            explicit_conditions=[
                {"entity": "ball", "name": "height", "value": 10.0},
                {"entity": "ball", "name": "velocity", "value": 0.0},
                {"entity": "ball", "name": "mass", "value": 1.0},
            ],
        )
        spec = build_particle_motion_spec(problem_spec)
        plan = build_execution_plan([spec])
        rule_names = [r["rule_name"] for r in plan.persistent_rule_plan]
        assert "constant_gravity" in rule_names

    def test_contact_interaction_with_two_entities_and_conditions_is_admitted(self):
        """两个实体 + 速度 + 质量条件 → admitted。"""
        problem_spec = _make_minimal_problem_spec(
            entities=[{"name": "ball_a"}, {"name": "ball_b"}],
            explicit_conditions=[
                {"entity": "ball_a", "name": "mass", "value": 1.0},
                {"entity": "ball_b", "name": "mass", "value": 1.0},
                {"entity": "ball_a", "name": "velocity", "value": 2.0},
                {"entity": "ball_b", "name": "velocity", "value": 0.0},
            ],
        )
        spec = build_contact_interaction_spec(problem_spec)
        assert spec.missing_entry_inputs == [], f"不应有缺失入口要素，实际: {spec.missing_entry_inputs}"
        plan = build_execution_plan([spec])
        assert "contact_interaction" in plan.admitted_capabilities

    def test_admitted_capability_in_local_rules(self):
        """admitted contact_interaction 的规则应进入 local_rule_plan。"""
        problem_spec = _make_minimal_problem_spec(
            entities=[{"name": "ball_a"}, {"name": "ball_b"}],
            explicit_conditions=[
                {"entity": "ball_a", "name": "mass", "value": 1.0},
                {"entity": "ball_b", "name": "mass", "value": 1.0},
                {"entity": "ball_a", "name": "velocity", "value": 2.0},
                {"entity": "ball_b", "name": "velocity", "value": 0.0},
            ],
        )
        spec = build_contact_interaction_spec(problem_spec)
        plan = build_execution_plan([spec])
        rule_names = [r["rule_name"] for r in plan.local_rule_plan]
        assert "impulsive_collision" in rule_names

    def test_admitted_capability_in_state_set_plan(self):
        """admitted capability 的实体应进入 state_set_plan。"""
        problem_spec = _make_minimal_problem_spec(
            entities=[{"name": "ball"}],
            explicit_conditions=[
                {"entity": "ball", "name": "height", "value": 10.0},
                {"entity": "ball", "name": "velocity", "value": 0.0},
                {"entity": "ball", "name": "mass", "value": 1.0},
            ],
        )
        spec = build_particle_motion_spec(problem_spec)
        plan = build_execution_plan([spec])
        assert "ball" in plan.state_set_plan


# ---------------------------------------------------------------------------
# 必测 3：ExecutionPlan 中能区分 admitted / deferred / unresolved
# ---------------------------------------------------------------------------

class TestExecutionPlanAdmissionStateDistinction:
    """必测 3：ExecutionPlan 中三种 admission 状态的最小区分。"""

    def test_plan_has_admission_state_fields(self):
        """ExecutionPlan 应包含三个 admission 状态字段。"""
        plan = ExecutionPlan()
        assert hasattr(plan, "admitted_capabilities")
        assert hasattr(plan, "deferred_capabilities")
        assert hasattr(plan, "unresolved_admission_items")

    def test_unresolved_when_no_entities(self):
        """空实体列表 → unresolved_admission_items。"""
        spec = ParticleMotionCapabilitySpec(
            capability_name="particle_motion",
            applies_to_entities=[],
            missing_entry_inputs=[],
        )
        plan = build_execution_plan([spec])
        assert len(plan.unresolved_admission_items) == 1
        assert plan.unresolved_admission_items[0]["capability_name"] == "particle_motion"
        assert "particle_motion" not in plan.admitted_capabilities
        assert "particle_motion" not in [d["capability_name"] for d in plan.deferred_capabilities]

    def test_mixed_admission_states(self):
        """多个 capability 同时存在三种状态时均能正确分类。"""
        # admitted: particle_motion with all conditions
        admitted_spec = build_particle_motion_spec(
            _make_minimal_problem_spec(
                entities=[{"name": "ball"}],
                explicit_conditions=[
                    {"entity": "ball", "name": "height", "value": 10.0},
                    {"entity": "ball", "name": "velocity", "value": 0.0},
                    {"entity": "ball", "name": "mass", "value": 1.0},
                ],
            )
        )
        # deferred: contact_interaction missing mass
        deferred_spec = ContactInteractionCapabilitySpec(
            capability_name="contact_interaction",
            applies_to_entities=["a", "b"],
            missing_entry_inputs=["mass_per_entity"],
        )
        # unresolved: custom capability with no entities
        unresolved_spec = CapabilitySpec(
            capability_name="custom_cap",
            applies_to_entities=[],
        )

        plan = build_execution_plan([admitted_spec, deferred_spec, unresolved_spec])

        assert "particle_motion" in plan.admitted_capabilities
        assert len(plan.admitted_capabilities) == 1

        deferred_names = [d["capability_name"] for d in plan.deferred_capabilities]
        assert "contact_interaction" in deferred_names
        assert len(plan.deferred_capabilities) == 1

        unresolved_names = [u["capability_name"] for u in plan.unresolved_admission_items]
        assert "custom_cap" in unresolved_names
        assert len(plan.unresolved_admission_items) == 1

    def test_deferred_item_contains_missing_entry_inputs(self):
        """deferred_capabilities 条目应含 missing_entry_inputs 字段。"""
        spec = ContactInteractionCapabilitySpec(
            capability_name="contact_interaction",
            applies_to_entities=["a", "b"],
            missing_entry_inputs=["mass_per_entity", "pre_collision_velocity_per_entity"],
        )
        plan = build_execution_plan([spec])
        deferred = plan.deferred_capabilities[0]
        assert "missing_entry_inputs" in deferred
        assert "mass_per_entity" in deferred["missing_entry_inputs"]

    def test_unresolved_item_contains_reason(self):
        """unresolved_admission_items 条目应含 reason 字段。"""
        spec = CapabilitySpec(
            capability_name="test_cap",
            applies_to_entities=[],
        )
        plan = build_execution_plan([spec])
        item = plan.unresolved_admission_items[0]
        assert "reason" in item
        assert len(item["reason"]) > 0

    def test_empty_specs_produces_empty_admission_states(self):
        """空输入 → 三种 admission 状态均为空。"""
        plan = build_execution_plan([])
        assert plan.admitted_capabilities == []
        assert plan.deferred_capabilities == []
        assert plan.unresolved_admission_items == []

    def test_plan_notes_record_non_admitted_reasons(self):
        """deferred 和 unresolved 的原因应记录在 plan_notes 中。"""
        deferred_spec = ContactInteractionCapabilitySpec(
            capability_name="contact_interaction",
            applies_to_entities=["a", "b"],
            missing_entry_inputs=["mass_per_entity"],
        )
        unresolved_spec = CapabilitySpec(
            capability_name="unknown_cap",
            applies_to_entities=[],
        )
        plan = build_execution_plan([deferred_spec, unresolved_spec])
        notes_text = " ".join(plan.plan_notes)
        assert "contact_interaction" in notes_text
        assert "unknown_cap" in notes_text


# ---------------------------------------------------------------------------
# CapabilitySpec required_entry_inputs / missing_entry_inputs 字段验证
# ---------------------------------------------------------------------------

class TestCapabilitySpecAdmissionFields:
    """CapabilitySpec 新增 admission 字段的基本验证。"""

    def test_base_spec_has_required_entry_inputs_field(self):
        spec = CapabilitySpec(capability_name="test")
        assert hasattr(spec, "required_entry_inputs")
        assert isinstance(spec.required_entry_inputs, list)

    def test_base_spec_has_missing_entry_inputs_field(self):
        spec = CapabilitySpec(capability_name="test")
        assert hasattr(spec, "missing_entry_inputs")
        assert isinstance(spec.missing_entry_inputs, list)

    def test_particle_motion_mapper_populates_required_entry_inputs(self):
        """particle_motion mapper 应填充 required_entry_inputs。"""
        problem_spec = _make_minimal_problem_spec(entities=[{"name": "ball"}])
        spec = build_particle_motion_spec(problem_spec)
        assert len(spec.required_entry_inputs) > 0

    def test_contact_interaction_mapper_populates_required_entry_inputs(self):
        """contact_interaction mapper 应填充 required_entry_inputs。"""
        problem_spec = _make_minimal_problem_spec(
            entities=[{"name": "a"}, {"name": "b"}]
        )
        spec = build_contact_interaction_spec(problem_spec)
        assert len(spec.required_entry_inputs) > 0

    def test_missing_entry_inputs_is_subset_of_required(self):
        """missing_entry_inputs 应为 required_entry_inputs 的子集。"""
        problem_spec = _make_minimal_problem_spec(entities=[{"name": "ball"}])
        spec = build_particle_motion_spec(problem_spec)
        required_set = set(spec.required_entry_inputs)
        for item in spec.missing_entry_inputs:
            assert item in required_set, (
                f"missing_entry_inputs 包含不在 required_entry_inputs 中的项: {item}"
            )


# ---------------------------------------------------------------------------
# 向后兼容：existing behavior 不应被破坏
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """确保新增字段不破坏现有行为。"""

    def test_plan_still_has_capability_bindings(self):
        """capability_bindings 仍应记录所有 capability（无论 admission 状态）。"""
        problem_spec = _make_minimal_problem_spec(
            entities=[{"name": "ball"}],
            explicit_conditions=[
                {"entity": "ball", "name": "height", "value": 10.0},
                {"entity": "ball", "name": "velocity", "value": 0.0},
                {"entity": "ball", "name": "mass", "value": 1.0},
            ],
        )
        pm_spec = build_particle_motion_spec(problem_spec)
        unresolved_spec = CapabilitySpec(
            capability_name="unknown_cap",
            applies_to_entities=[],
        )
        plan = build_execution_plan([pm_spec, unresolved_spec])
        assert "particle_motion" in plan.capability_bindings
        assert "unknown_cap" in plan.capability_bindings

    def test_unresolved_execution_inputs_still_populated(self):
        """unresolved_execution_inputs 应仍来自各 spec 的 missing_inputs。"""
        spec = ParticleMotionCapabilitySpec(
            capability_name="particle_motion",
            applies_to_entities=["ball"],
            missing_entry_inputs=[],
            missing_inputs=["some_runtime_param"],
        )
        plan = build_execution_plan([spec])
        assert "some_runtime_param" in plan.unresolved_execution_inputs

    def test_assembly_plan_includes_deferred_and_unresolved_targets(self):
        """deferred/unresolved capability 的目标量也应进入 assembly_plan（供追溯）。"""
        deferred_spec = ContactInteractionCapabilitySpec(
            capability_name="contact_interaction",
            applies_to_entities=["a", "b"],
            missing_entry_inputs=["mass_per_entity"],
            target_mapping={"v_after": {"name": "v_after", "description": "碰后速度"}},
        )
        plan = build_execution_plan([deferred_spec])
        assert "v_after" in plan.assembly_plan
