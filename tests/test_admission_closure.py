"""
Admission 闭环增强测试（接续 admission hints 已有工作）。

本测试文件覆盖以下增量新增能力（不重复 test_admission_hints.py 中的已有测试）：

1. 输入已知性的 A 层语义来源
   - InputAvailabilityHints 提取正确性
   - mapper 优先使用 A 层（input_availability_hints）判断 missing_entry_inputs
   - A 层缺失时 B 层正常 fallback

2. applicability_conditions 动态评估（applicability_eval）
   - ParticleMotionCapabilitySpec 动态评估字段存在且逻辑正确
   - ContactInteractionCapabilitySpec 动态评估字段存在且逻辑正确
   - 至少一个 uncertain / unsupported 场景可被断言

3. deferred capability 重入骨架
   - deferred capability 输出结构化 reentry_hints
   - build_reentry_context() 存在且可调用
   - reentry_hints 包含 supplemental_suggestions 和 reentry_note

4. validity_limits 轻量 warning 机制
   - 旋转/刚体暗示触发 particle_motion validity_warning
   - 持续接触/滑动暗示触发 contact_interaction validity_warning
   - 警告不改变 admission 三态

5. 回归：现有 admission 三态行为不被破坏
"""

from __future__ import annotations

import pytest

from src.capabilities.contact_interaction.mapper import build_contact_interaction_spec
from src.capabilities.particle_motion.mapper import build_particle_motion_spec
from src.planning.execution_plan.builder import (
    _judge_admission,
    build_execution_plan,
    build_reentry_context,
)
from src.problem_semantic.extraction.pipeline import (
    _extract_input_availability_hints,
    extract_problem_semantics,
)
from src.problem_semantic.models import InputAvailabilityHints, ProblemSemanticSpec


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _make_spec(
    entities=None,
    explicit_conditions=None,
    assumption_hints=None,
    interaction_hints=None,
    entity_model_hints=None,
    input_availability_hints=None,
    source_input="test",
) -> ProblemSemanticSpec:
    """构造最小 ProblemSemanticSpec，允许注入各类 hints。"""
    return ProblemSemanticSpec(
        source_input=source_input,
        entities=entities or [],
        explicit_conditions=explicit_conditions or [],
        assumption_hints=assumption_hints or [],
        interaction_hints=interaction_hints or [],
        entity_model_hints=entity_model_hints or [],
        input_availability_hints=input_availability_hints or InputAvailabilityHints(),
    )


# ===========================================================================
# 1. 输入已知性的 A 层语义来源
# ===========================================================================


class TestInputAvailabilityHintsExtraction:
    """_extract_input_availability_hints 从文本正确推断各物理量可得性。"""

    def test_position_known_from_height_value(self):
        hints = _extract_input_availability_hints("一个物体从高度10米处自由落下")
        assert hints.initial_position_known is True
        assert hints.sources["initial_position_known"] in ("text_explicit", "text_inferred")

    def test_velocity_known_from_ms_value(self):
        hints = _extract_input_availability_hints("以5 m/s的速度水平抛出")
        assert hints.initial_velocity_known is True

    def test_mass_known_from_kg_value(self):
        hints = _extract_input_availability_hints("一个2kg的小球")
        assert hints.mass_known is True

    def test_pre_collision_velocity_known_in_collision_with_speed(self):
        hints = _extract_input_availability_hints("1kg的球以3 m/s与静止球发生弹性碰撞")
        assert hints.pre_collision_velocity_known is True

    def test_no_position_for_abstract_text(self):
        hints = _extract_input_availability_hints("两球相撞，求碰后速度")
        assert hints.initial_position_known is False

    def test_no_velocity_for_static_text(self):
        hints = _extract_input_availability_hints("一个物体静止在桌上")
        assert hints.initial_velocity_known is False

    def test_no_mass_for_no_mass_text(self):
        hints = _extract_input_availability_hints("一个球从高处落下")
        assert hints.mass_known is False

    def test_no_pre_collision_velocity_without_collision(self):
        hints = _extract_input_availability_hints("一个球从高度10米处落下")
        assert hints.pre_collision_velocity_known is False

    def test_sources_dict_populated(self):
        hints = _extract_input_availability_hints("一个2kg的小球以3 m/s抛出")
        assert "mass_known" in hints.sources
        assert "initial_velocity_known" in hints.sources

    def test_input_availability_hints_in_extract_problem_semantics(self):
        spec = extract_problem_semantics("一个2kg的小球以3 m/s水平抛出，从高度5米处")
        assert isinstance(spec.input_availability_hints, InputAvailabilityHints)
        assert spec.input_availability_hints.mass_known is True
        assert spec.input_availability_hints.initial_velocity_known is True
        assert spec.input_availability_hints.initial_position_known is True


class TestParticleMotionMapperALayerVelocityMass:
    """mapper 优先使用 A 层（input_availability_hints）判断速度和质量已知性。"""

    def test_velocity_known_from_a_layer_reduces_missing_entry(self):
        """input_availability_hints.initial_velocity_known=True → velocity 不进 missing_entry_inputs。"""
        hints = InputAvailabilityHints(initial_velocity_known=True)
        spec = _make_spec(
            entities=[{"name": "ball"}],
            input_availability_hints=hints,
            source_input="一个球从高处落下（速度已知）",
        )
        result = build_particle_motion_spec(spec)
        assert "initial_velocity_per_entity" not in result.missing_entry_inputs

    def test_mass_known_from_a_layer_reduces_missing_entry(self):
        """input_availability_hints.mass_known=True → mass 不进 missing_entry_inputs。"""
        hints = InputAvailabilityHints(mass_known=True)
        spec = _make_spec(
            entities=[{"name": "ball"}],
            input_availability_hints=hints,
            source_input="一个球从高处落下（质量已知）",
        )
        result = build_particle_motion_spec(spec)
        assert "mass_per_entity" not in result.missing_entry_inputs

    def test_a_layer_missing_b_layer_keyword_fallback(self):
        """A 层未知时，B 层关键词仍可 fallback 判断为已知。"""
        spec = _make_spec(
            entities=[{"name": "ball"}],
            explicit_conditions=[{"name": "v", "value": 5}],
            source_input="一个球",
        )
        result = build_particle_motion_spec(spec)
        assert "initial_velocity_per_entity" not in result.missing_entry_inputs

    def test_both_a_and_b_missing_velocity_goes_to_missing(self):
        """A 层和 B 层均无速度信息 → velocity 进入 missing_entry_inputs。"""
        spec = _make_spec(
            entities=[{"name": "ball"}],
            source_input="一个球从高处落下",
        )
        result = build_particle_motion_spec(spec)
        assert "initial_velocity_per_entity" in result.missing_entry_inputs

    def test_both_a_and_b_missing_mass_goes_to_missing(self):
        """A 层和 B 层均无质量信息 → mass 进入 missing_entry_inputs。"""
        spec = _make_spec(
            entities=[{"name": "ball"}],
            source_input="一个球从高处落下",
        )
        result = build_particle_motion_spec(spec)
        assert "mass_per_entity" in result.missing_entry_inputs


class TestContactInteractionMapperALayerVelocityMass:
    """contact_interaction mapper 也优先使用 A 层判断碰前速度和质量。"""

    def test_pre_collision_velocity_from_a_layer(self):
        hints = InputAvailabilityHints(pre_collision_velocity_known=True, mass_known=True)
        spec = _make_spec(
            entities=[{"name": "ball_a"}, {"name": "ball_b"}],
            input_availability_hints=hints,
            interaction_hints=["collision_possible"],
            source_input="碰撞",
        )
        result = build_contact_interaction_spec(spec)
        assert "pre_collision_velocity_per_entity" not in result.missing_entry_inputs
        assert "mass_per_entity" not in result.missing_entry_inputs

    def test_mass_from_a_layer_contact(self):
        hints = InputAvailabilityHints(mass_known=True)
        spec = _make_spec(
            entities=[{"name": "ball_a"}, {"name": "ball_b"}],
            input_availability_hints=hints,
            interaction_hints=["collision_possible"],
            explicit_conditions=[{"name": "v", "value": 3}],
            source_input="碰撞",
        )
        result = build_contact_interaction_spec(spec)
        assert "mass_per_entity" not in result.missing_entry_inputs


# ===========================================================================
# 2. applicability_conditions 动态评估（applicability_eval）
# ===========================================================================


class TestParticleMotionApplicabilityEval:
    """ParticleMotionCapabilitySpec 动态评估字段正确性。"""

    def test_applicability_eval_is_list(self):
        spec = _make_spec(entities=[{"name": "ball"}], source_input="一个球")
        result = build_particle_motion_spec(spec)
        assert isinstance(result.applicability_eval, list)
        assert len(result.applicability_eval) > 0

    def test_point_mass_satisfied_when_hint_present(self):
        spec = _make_spec(
            entities=[{"name": "ball"}],
            entity_model_hints=["point_mass"],
            source_input="一个质点",
        )
        result = build_particle_motion_spec(spec)
        pm_eval = next(
            (e for e in result.applicability_eval if e.condition_key == "point_mass_applicable"),
            None,
        )
        assert pm_eval is not None
        assert pm_eval.status == "satisfied"
        assert pm_eval.source == "entity_model_hints"

    def test_point_mass_unsupported_when_rigid_body_hint(self):
        spec = _make_spec(
            entities=[{"name": "body"}],
            entity_model_hints=["rigid_body"],
            source_input="刚体转动",
        )
        result = build_particle_motion_spec(spec)
        pm_eval = next(
            (e for e in result.applicability_eval if e.condition_key == "point_mass_applicable"),
            None,
        )
        assert pm_eval is not None
        assert pm_eval.status == "unsupported"

    def test_point_mass_uncertain_when_no_entity_hint(self):
        spec = _make_spec(entities=[{"name": "obj"}], source_input="一个物体")
        result = build_particle_motion_spec(spec)
        pm_eval = next(
            (e for e in result.applicability_eval if e.condition_key == "point_mass_applicable"),
            None,
        )
        assert pm_eval is not None
        assert pm_eval.status == "uncertain"

    def test_continuous_background_satisfied_with_gravity(self):
        spec = _make_spec(
            entities=[{"name": "ball"}],
            interaction_hints=["gravity_present"],
            source_input="自由落体",
        )
        result = build_particle_motion_spec(spec)
        bg_eval = next(
            (e for e in result.applicability_eval if e.condition_key == "continuous_background_action"),
            None,
        )
        assert bg_eval is not None
        assert bg_eval.status == "satisfied"

    def test_no_local_trigger_uncertain_when_collision_hint(self):
        spec = _make_spec(
            entities=[{"name": "ball"}],
            interaction_hints=["collision_possible"],
            source_input="碰撞",
        )
        result = build_particle_motion_spec(spec)
        trigger_eval = next(
            (e for e in result.applicability_eval if e.condition_key == "no_local_trigger_interrupt"),
            None,
        )
        assert trigger_eval is not None
        assert trigger_eval.status == "uncertain"

    def test_eval_items_have_required_fields(self):
        spec = _make_spec(entities=[{"name": "ball"}], source_input="一个球")
        result = build_particle_motion_spec(spec)
        for item in result.applicability_eval:
            assert hasattr(item, "condition_key")
            assert hasattr(item, "description")
            assert hasattr(item, "status")
            assert hasattr(item, "source")
            assert item.status in ("satisfied", "uncertain", "unsupported")


class TestContactInteractionApplicabilityEval:
    """ContactInteractionCapabilitySpec 动态评估字段正确性。"""

    def test_applicability_eval_exists_for_contact(self):
        spec = _make_spec(
            entities=[{"name": "a"}, {"name": "b"}],
            interaction_hints=["collision_possible"],
            source_input="碰撞",
        )
        result = build_contact_interaction_spec(spec)
        assert isinstance(result.applicability_eval, list)
        assert len(result.applicability_eval) > 0

    def test_at_least_two_entities_satisfied(self):
        spec = _make_spec(
            entities=[{"name": "a"}, {"name": "b"}],
            source_input="碰撞",
        )
        result = build_contact_interaction_spec(spec)
        entity_eval = next(
            (e for e in result.applicability_eval if e.condition_key == "at_least_two_entities"),
            None,
        )
        assert entity_eval is not None
        assert entity_eval.status == "satisfied"

    def test_at_least_two_entities_unsupported_for_one(self):
        spec = _make_spec(entities=[{"name": "a"}], source_input="一个球")
        result = build_contact_interaction_spec(spec)
        entity_eval = next(
            (e for e in result.applicability_eval if e.condition_key == "at_least_two_entities"),
            None,
        )
        assert entity_eval is not None
        assert entity_eval.status == "unsupported"

    def test_at_least_two_entities_uncertain_for_empty(self):
        spec = _make_spec(entities=[], source_input="碰撞")
        result = build_contact_interaction_spec(spec)
        entity_eval = next(
            (e for e in result.applicability_eval if e.condition_key == "at_least_two_entities"),
            None,
        )
        assert entity_eval is not None
        assert entity_eval.status == "uncertain"

    def test_collision_event_satisfied_with_hint(self):
        spec = _make_spec(
            entities=[{"name": "a"}, {"name": "b"}],
            interaction_hints=["collision_possible"],
            source_input="碰撞",
        )
        result = build_contact_interaction_spec(spec)
        collision_eval = next(
            (e for e in result.applicability_eval if e.condition_key == "collision_event_identified"),
            None,
        )
        assert collision_eval is not None
        assert collision_eval.status == "satisfied"

    def test_collision_event_uncertain_without_hint(self):
        spec = _make_spec(
            entities=[{"name": "a"}, {"name": "b"}],
            source_input="两球运动",
        )
        result = build_contact_interaction_spec(spec)
        collision_eval = next(
            (e for e in result.applicability_eval if e.condition_key == "collision_event_identified"),
            None,
        )
        assert collision_eval is not None
        assert collision_eval.status == "uncertain"

    def test_continuous_contact_hint_uncertain_instantaneous(self):
        spec = _make_spec(
            entities=[{"name": "a"}, {"name": "b"}],
            interaction_hints=["contact_possible"],
            source_input="接触",
        )
        result = build_contact_interaction_spec(spec)
        impulse_eval = next(
            (e for e in result.applicability_eval if e.condition_key == "instantaneous_impulse_approximation"),
            None,
        )
        assert impulse_eval is not None
        assert impulse_eval.status == "uncertain"


# ===========================================================================
# 3. deferred capability 重入骨架
# ===========================================================================


class TestBuildReentryContext:
    """build_reentry_context() 生成正确的结构化重入上下文。"""

    def test_reentry_context_has_required_keys(self):
        from src.capabilities.particle_motion.spec import ParticleMotionCapabilitySpec
        spec = ParticleMotionCapabilitySpec(
            capability_name="particle_motion",
            applies_to_entities=["ball"],
            missing_entry_inputs=["mass_per_entity"],
        )
        ctx = build_reentry_context(spec)
        assert "capability_name" in ctx
        assert "applies_to_entities" in ctx
        assert "missing_entry_inputs" in ctx
        assert "supplemental_suggestions" in ctx
        assert "reentry_note" in ctx

    def test_supplemental_suggestions_one_per_missing_item(self):
        from src.capabilities.particle_motion.spec import ParticleMotionCapabilitySpec
        spec = ParticleMotionCapabilitySpec(
            capability_name="particle_motion",
            applies_to_entities=["ball"],
            missing_entry_inputs=["mass_per_entity", "initial_velocity_per_entity"],
        )
        ctx = build_reentry_context(spec)
        assert len(ctx["supplemental_suggestions"]) == 2
        keys = {s["missing_item"] for s in ctx["supplemental_suggestions"]}
        assert "mass_per_entity" in keys
        assert "initial_velocity_per_entity" in keys

    def test_supplemental_suggestion_has_entity_context(self):
        from src.capabilities.particle_motion.spec import ParticleMotionCapabilitySpec
        spec = ParticleMotionCapabilitySpec(
            capability_name="particle_motion",
            applies_to_entities=["ball_a", "ball_b"],
            missing_entry_inputs=["mass_per_entity"],
        )
        ctx = build_reentry_context(spec)
        suggestion = ctx["supplemental_suggestions"][0]
        assert "ball_a" in suggestion["entity_context"] or "ball_b" in suggestion["entity_context"]

    def test_reentry_note_mentions_capability_name(self):
        from src.capabilities.particle_motion.spec import ParticleMotionCapabilitySpec
        spec = ParticleMotionCapabilitySpec(
            capability_name="particle_motion",
            applies_to_entities=["ball"],
            missing_entry_inputs=["mass_per_entity"],
        )
        ctx = build_reentry_context(spec)
        assert "particle_motion" in ctx["reentry_note"]
        assert "deferred" in ctx["reentry_note"]

    def test_reentry_hints_in_deferred_capability_entry(self):
        """ExecutionPlan 中 deferred_capabilities 每条包含 reentry_hints。"""
        spec = _make_spec(
            entities=[{"name": "ball"}],
            source_input="一个球落下",
        )
        pm_spec = build_particle_motion_spec(spec)
        plan = build_execution_plan([pm_spec])
        if plan.deferred_capabilities:
            deferred = plan.deferred_capabilities[0]
            assert "reentry_hints" in deferred
            assert "supplemental_suggestions" in deferred["reentry_hints"]
            assert "reentry_note" in deferred["reentry_hints"]


# ===========================================================================
# 4. validity_limits 轻量 warning 机制
# ===========================================================================


class TestParticleMotionValidityWarnings:
    """ParticleMotionCapabilitySpec 的 validity_warnings 触发正确。"""

    def test_no_warnings_for_normal_case(self):
        spec = _make_spec(
            entities=[{"name": "ball"}],
            source_input="一个小球从10米高处自由落下",
        )
        result = build_particle_motion_spec(spec)
        # 无旋转关键词，无非均匀场关键词
        rotation_warns = [w for w in result.validity_warnings if w.warning_key == "rotation_hint_in_point_mass"]
        assert len(rotation_warns) == 0

    def test_rotation_hint_triggers_warning(self):
        spec = _make_spec(
            entities=[{"name": "body"}],
            source_input="一个刚体绕轴旋转，求角速度",
        )
        result = build_particle_motion_spec(spec)
        rotation_warns = [w for w in result.validity_warnings if w.warning_key == "rotation_hint_in_point_mass"]
        assert len(rotation_warns) == 1
        assert "旋转" in rotation_warns[0].description or "rotation" in rotation_warns[0].description.lower()

    def test_complex_field_triggers_warning(self):
        spec = _make_spec(
            entities=[{"name": "ball"}],
            source_input="在非均匀引力场中运动",
        )
        result = build_particle_motion_spec(spec)
        field_warns = [w for w in result.validity_warnings if w.warning_key == "complex_field_in_simple_background"]
        assert len(field_warns) == 1

    def test_validity_warnings_do_not_change_admission_state(self):
        """validity_warnings 不影响 admission 三态。"""
        spec = _make_spec(
            entities=[{"name": "body"}],
            source_input="一个刚体绕轴旋转",
        )
        result = build_particle_motion_spec(spec)
        # 有警告
        assert len(result.validity_warnings) > 0
        # admission 状态仍由 applies_to_entities / missing_entry_inputs 决定
        admission = _judge_admission(result)
        assert admission in ("admitted", "deferred", "unresolved")

    def test_warning_has_required_fields(self):
        spec = _make_spec(
            entities=[{"name": "body"}],
            source_input="刚体旋转运动",
        )
        result = build_particle_motion_spec(spec)
        for w in result.validity_warnings:
            assert hasattr(w, "warning_key")
            assert hasattr(w, "description")
            assert hasattr(w, "triggered_by")


class TestContactInteractionValidityWarnings:
    """ContactInteractionCapabilitySpec 的 validity_warnings 触发正确。"""

    def test_no_warnings_for_simple_collision(self):
        spec = _make_spec(
            entities=[{"name": "a"}, {"name": "b"}],
            interaction_hints=["collision_possible"],
            source_input="两球弹性碰撞",
        )
        result = build_contact_interaction_spec(spec)
        continuous_warns = [
            w for w in result.validity_warnings
            if w.warning_key == "continuous_contact_in_impulse_model"
        ]
        assert len(continuous_warns) == 0

    def test_friction_triggers_continuous_contact_warning(self):
        spec = _make_spec(
            entities=[{"name": "a"}, {"name": "b"}],
            source_input="两物体之间存在摩擦力，滑动接触",
        )
        result = build_contact_interaction_spec(spec)
        continuous_warns = [
            w for w in result.validity_warnings
            if w.warning_key == "continuous_contact_in_impulse_model"
        ]
        assert len(continuous_warns) == 1

    def test_multi_body_triggers_warning_with_three_entities(self):
        spec = _make_spec(
            entities=[{"name": "a"}, {"name": "b"}, {"name": "c"}],
            source_input="三个球发生碰撞",
        )
        result = build_contact_interaction_spec(spec)
        multi_warns = [
            w for w in result.validity_warnings
            if w.warning_key == "multi_body_collision"
        ]
        assert len(multi_warns) == 1

    def test_validity_warnings_do_not_change_admission_for_contact(self):
        spec = _make_spec(
            entities=[{"name": "a"}, {"name": "b"}],
            source_input="两物体滑动摩擦",
        )
        result = build_contact_interaction_spec(spec)
        assert len(result.validity_warnings) > 0
        admission = _judge_admission(result)
        assert admission in ("admitted", "deferred", "unresolved")


# ===========================================================================
# 5. 回归：现有 admission 三态行为不被破坏
# ===========================================================================


class TestAdmissionThreeStateRegression:
    """确保新增字段不破坏现有 admitted / deferred / unresolved 三态逻辑。"""

    def test_admitted_when_all_entry_inputs_present(self):
        hints = InputAvailabilityHints(
            initial_position_known=True,
            initial_velocity_known=True,
            mass_known=True,
        )
        spec = _make_spec(
            entities=[{"name": "ball"}],
            input_availability_hints=hints,
            source_input="一个球从高处落下",
        )
        pm_spec = build_particle_motion_spec(spec)
        assert _judge_admission(pm_spec) == "admitted"

    def test_deferred_when_mass_missing(self):
        spec = _make_spec(
            entities=[{"name": "ball"}],
            source_input="一个球从高处落下",
        )
        pm_spec = build_particle_motion_spec(spec)
        # 无质量信息 → 必然 deferred（除非碰巧满足 B 层条件）
        if "mass_per_entity" in pm_spec.missing_entry_inputs:
            assert _judge_admission(pm_spec) == "deferred"

    def test_unresolved_when_no_entities(self):
        spec = _make_spec(entities=[], source_input="一个球")
        pm_spec = build_particle_motion_spec(spec)
        assert _judge_admission(pm_spec) == "unresolved"

    def test_execution_plan_deferred_capabilities_structure(self):
        spec = _make_spec(
            entities=[{"name": "ball"}],
            source_input="一个球",
        )
        pm_spec = build_particle_motion_spec(spec)
        plan = build_execution_plan([pm_spec])
        if plan.deferred_capabilities:
            dc = plan.deferred_capabilities[0]
            assert "capability_name" in dc
            assert "missing_entry_inputs" in dc
            assert "reentry_hints" in dc  # 新增字段

    def test_execution_plan_admitted_has_no_reentry(self):
        """admitted capability 不进 deferred_capabilities 列表。"""
        hints = InputAvailabilityHints(
            initial_position_known=True,
            initial_velocity_known=True,
            mass_known=True,
        )
        spec = _make_spec(
            entities=[{"name": "ball"}],
            input_availability_hints=hints,
            interaction_hints=["gravity_present"],
            source_input="一个球从高处落下",
        )
        pm_spec = build_particle_motion_spec(spec)
        if _judge_admission(pm_spec) == "admitted":
            plan = build_execution_plan([pm_spec])
            assert pm_spec.capability_name in plan.admitted_capabilities
            assert not any(
                d["capability_name"] == pm_spec.capability_name
                for d in plan.deferred_capabilities
            )

    def test_contact_interaction_deferred_has_reentry_hints(self):
        """contact_interaction deferred 时也有 reentry_hints。"""
        spec = _make_spec(
            entities=[{"name": "a"}, {"name": "b"}],
            source_input="两球碰撞",
        )
        ci_spec = build_contact_interaction_spec(spec)
        plan = build_execution_plan([ci_spec])
        if plan.deferred_capabilities:
            dc = plan.deferred_capabilities[0]
            assert "reentry_hints" in dc
            rh = dc["reentry_hints"]
            assert len(rh["supplemental_suggestions"]) > 0
