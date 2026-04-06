"""
P0 第四步：admission hints 测试。

覆盖以下必测场景：

必测 1：extract_problem_semantics() 能输出新增的 admission hints
必测 2：当语义 hints 明确时，mapper 不应完全依赖 explicit_conditions 关键词匹配
必测 3：mapper 中 assumption/applicability 来源区分清晰（semantic / explicit / fallback）
必测 4：现有 admission 三态行为不被破坏
"""

from __future__ import annotations

import pytest

from src.capabilities.contact_interaction.mapper import build_contact_interaction_spec
from src.capabilities.particle_motion.mapper import build_particle_motion_spec
from src.problem_semantic.extraction.pipeline import (
    _extract_assumption_hints,
    _extract_entity_model_hints,
    _extract_interaction_hints,
    _extract_query_hints,
    extract_problem_semantics,
)
from src.problem_semantic.models import ProblemSemanticSpec


# ===========================================================================
# 必测 1：extract_problem_semantics 输出 admission hints
# ===========================================================================


class TestExtractAdmissionHints:
    """必测 1：extraction pipeline 正确填充四类 admission hints。"""

    # --- entity_model_hints ---

    def test_entity_model_hint_point_mass_from_ball(self):
        spec = extract_problem_semantics("一个小球从10米高处自由落体")
        assert "point_mass" in spec.entity_model_hints

    def test_entity_model_hint_point_mass_english(self):
        spec = extract_problem_semantics("A particle falls from height 5 m")
        assert "point_mass" in spec.entity_model_hints

    def test_entity_model_hint_rigid_body(self):
        spec = extract_problem_semantics("一个刚体绕轴转动")
        assert "rigid_body" in spec.entity_model_hints

    def test_entity_model_hint_empty_for_abstract_text(self):
        hints = _extract_entity_model_hints("solve x + y = 10")
        assert hints == []

    # --- interaction_hints ---

    def test_interaction_hint_gravity_from_free_fall_cn(self):
        spec = extract_problem_semantics("一个球从高度10米自由落体，2秒后位置？")
        assert "gravity_present" in spec.interaction_hints

    def test_interaction_hint_gravity_from_projectile(self):
        spec = extract_problem_semantics("以10 m/s水平抛出，从5米高处")
        assert "gravity_present" in spec.interaction_hints

    def test_interaction_hint_gravity_english(self):
        spec = extract_problem_semantics("A ball drops from 8 m height")
        assert "gravity_present" in spec.interaction_hints

    def test_interaction_hint_collision_cn(self):
        spec = extract_problem_semantics("1kg的球以2 m/s与静止的1kg球发生弹性碰撞")
        assert "collision_possible" in spec.interaction_hints

    def test_interaction_hint_collision_english(self):
        spec = extract_problem_semantics("Two balls collide elastically")
        assert "collision_possible" in spec.interaction_hints

    def test_interaction_hint_no_gravity_for_pure_collision(self):
        hints = _extract_interaction_hints("两球相撞，求碰后速度")
        # collision_possible 存在，gravity 不一定存在
        assert "collision_possible" in hints

    def test_interaction_hint_field_present(self):
        hints = _extract_interaction_hints("带电粒子在电场中运动")
        assert "field_present" in hints

    # --- assumption_hints ---

    def test_assumption_hint_ignore_air_resistance_cn(self):
        spec = extract_problem_semantics("忽略空气阻力，一个球从10米高处落下")
        assert "ignore_air_resistance" in spec.assumption_hints

    def test_assumption_hint_ignore_air_resistance_english(self):
        hints = _extract_assumption_hints("ignore air resistance, ball falls from 10m")
        assert "ignore_air_resistance" in hints

    def test_assumption_hint_elastic_collision_cn(self):
        spec = extract_problem_semantics("1kg与2kg发生弹性碰撞，求碰后速度")
        assert "elastic_collision" in spec.assumption_hints

    def test_assumption_hint_inelastic_collision(self):
        hints = _extract_assumption_hints("两球发生完全非弹性碰撞")
        assert "inelastic_collision" in hints

    def test_assumption_hint_smooth_surface(self):
        hints = _extract_assumption_hints("光滑水平面上两球碰撞")
        assert "smooth_surface" in hints

    def test_assumption_hint_constant_g(self):
        hints = _extract_assumption_hints("重力加速度 g = 9.8 m/s²")
        assert "constant_g" in hints

    def test_assumption_hints_empty_for_plain_text(self):
        hints = _extract_assumption_hints("两个物体相遇")
        assert hints == []

    # --- query_hints ---

    def test_query_hint_state_at_time_cn(self):
        spec = extract_problem_semantics("一个球从10米高处落下，2秒后速度是多少？")
        assert "ask_state_at_time" in spec.query_hints

    def test_query_hint_state_at_time_english(self):
        hints = _extract_query_hints("What is the velocity after 3 s?")
        assert "ask_state_at_time" in hints

    def test_query_hint_collision_outcome(self):
        hints = _extract_query_hints("碰撞后两球的速度各是多少？")
        assert "ask_collision_outcome" in hints

    def test_query_hint_impact_time(self):
        hints = _extract_query_hints("球何时落地？")
        assert "ask_impact_time" in hints

    def test_query_hint_final_state(self):
        hints = _extract_query_hints("求最终速度")
        assert "ask_final_state" in hints

    def test_query_hints_empty_for_abstract_text(self):
        hints = _extract_query_hints("solve the equation")
        assert hints == []

    # --- 完整 spec 有四类 hints 字段 ---

    def test_spec_has_all_four_hint_fields(self):
        spec = extract_problem_semantics("任意文本")
        assert hasattr(spec, "entity_model_hints")
        assert hasattr(spec, "interaction_hints")
        assert hasattr(spec, "assumption_hints")
        assert hasattr(spec, "query_hints")

    def test_spec_hints_are_lists(self):
        spec = extract_problem_semantics("任意文本")
        assert isinstance(spec.entity_model_hints, list)
        assert isinstance(spec.interaction_hints, list)
        assert isinstance(spec.assumption_hints, list)
        assert isinstance(spec.query_hints, list)


# ===========================================================================
# 必测 2：mapper 消费语义 hints，不完全依赖 explicit_conditions 关键词匹配
# ===========================================================================


class TestMapperConsumesSemanticHints:
    """必测 2：mapper 优先消费语义 hints。"""

    def test_particle_motion_background_from_interaction_hints(self):
        """interaction_hints 含 gravity_present 时，background_hints 直接为 gravity。"""
        spec = ProblemSemanticSpec(
            source_input="test",
            entities=[{"name": "ball"}],
            interaction_hints=["gravity_present"],
            # 没有 rule_extraction_inputs["background_interactions"]
        )
        cap = build_particle_motion_spec(spec)
        assert "gravity" in cap.background_interaction_hints

    def test_particle_motion_fallback_gravity_when_no_hints(self):
        """无 interaction_hints 时，fallback 为 gravity（C 层）。"""
        spec = ProblemSemanticSpec(
            source_input="test",
            entities=[{"name": "ball"}],
            interaction_hints=[],
        )
        cap = build_particle_motion_spec(spec)
        assert "gravity" in cap.background_interaction_hints

    def test_contact_interaction_elastic_from_assumption_hints(self):
        """assumption_hints 含 elastic_collision 时，contact_hints 为 elastic。"""
        spec = ProblemSemanticSpec(
            source_input="test",
            entities=[{"name": "a"}, {"name": "b"}],
            assumption_hints=["elastic_collision"],
        )
        cap = build_contact_interaction_spec(spec)
        assert cap.contact_model_hints == ["elastic"]

    def test_contact_interaction_inelastic_from_assumption_hints(self):
        """assumption_hints 含 inelastic_collision 时，contact_hints 为 inelastic。"""
        spec = ProblemSemanticSpec(
            source_input="test",
            entities=[{"name": "a"}, {"name": "b"}],
            assumption_hints=["inelastic_collision"],
        )
        cap = build_contact_interaction_spec(spec)
        assert cap.contact_model_hints == ["inelastic"]

    def test_contact_interaction_fallback_elastic_when_no_hints(self):
        """无 assumption_hints 且 rule_extraction_inputs 无 contact_model_hints 时，fallback 为 elastic（C 层）。"""
        spec = ProblemSemanticSpec(
            source_input="test",
            entities=[{"name": "a"}, {"name": "b"}],
            assumption_hints=[],
        )
        cap = build_contact_interaction_spec(spec)
        assert cap.contact_model_hints == ["elastic"]

    def test_assumption_hints_override_rule_extraction_inputs(self):
        """assumption_hints（A 层）优先于 rule_extraction_inputs（B 层）。"""
        spec = ProblemSemanticSpec(
            source_input="test",
            entities=[{"name": "a"}, {"name": "b"}],
            assumption_hints=["inelastic_collision"],
            rule_extraction_inputs={"contact_model_hints": ["elastic"]},
        )
        cap = build_contact_interaction_spec(spec)
        # A 层的 inelastic 应该覆盖 B 层的 elastic
        assert "inelastic" in cap.contact_model_hints


# ===========================================================================
# 必测 3：mapper 来源区分清晰（semantic / explicit_conditions / fallback）
# ===========================================================================


class TestMapperSourceSeparation:
    """必测 3：mapper 中三类来源可在 assumptions 中区分。"""

    def test_particle_motion_assumption_from_semantic_layer(self):
        """当 assumption_hints 含 ignore_air_resistance 时，assumptions 中应注明来自语义层。"""
        spec = ProblemSemanticSpec(
            source_input="test",
            entities=[{"name": "ball"}],
            assumption_hints=["ignore_air_resistance"],
        )
        cap = build_particle_motion_spec(spec)
        # 语义层来源的 assumption 应包含语义层标注
        semantic_assumptions = [a for a in cap.assumptions if "语义层" in a]
        assert len(semantic_assumptions) >= 1

    def test_particle_motion_assumption_fallback_when_no_semantic_hints(self):
        """无 semantic hints 时，assumptions 中应包含默认 fallback 描述。"""
        spec = ProblemSemanticSpec(
            source_input="test",
            entities=[{"name": "ball"}],
            assumption_hints=[],
        )
        cap = build_particle_motion_spec(spec)
        fallback_assumptions = [a for a in cap.assumptions if "默认" in a]
        assert len(fallback_assumptions) >= 1

    def test_contact_interaction_assumption_from_semantic_elastic(self):
        """当 assumption_hints 含 elastic_collision 时，assumptions 中应注明来自语义层。"""
        spec = ProblemSemanticSpec(
            source_input="test",
            entities=[{"name": "a"}, {"name": "b"}],
            assumption_hints=["elastic_collision"],
        )
        cap = build_contact_interaction_spec(spec)
        semantic_assumptions = [a for a in cap.assumptions if "语义层" in a]
        assert len(semantic_assumptions) >= 1

    def test_contact_interaction_assumption_from_semantic_inelastic(self):
        """当 assumption_hints 含 inelastic_collision 时，assumptions 中应注明来自语义层。"""
        spec = ProblemSemanticSpec(
            source_input="test",
            entities=[{"name": "a"}, {"name": "b"}],
            assumption_hints=["inelastic_collision"],
        )
        cap = build_contact_interaction_spec(spec)
        semantic_assumptions = [a for a in cap.assumptions if "语义层" in a]
        assert len(semantic_assumptions) >= 1

    def test_contact_interaction_assumption_fallback_when_no_hints(self):
        """无语义 hints 时，contact_interaction assumptions 中含默认 fallback。"""
        spec = ProblemSemanticSpec(
            source_input="test",
            entities=[{"name": "a"}, {"name": "b"}],
            assumption_hints=[],
        )
        cap = build_contact_interaction_spec(spec)
        fallback_assumptions = [a for a in cap.assumptions if "默认" in a]
        assert len(fallback_assumptions) >= 1

    def test_particle_motion_position_from_explicit_conditions(self):
        """explicit_conditions 有 height 关键词时，position 不进入 missing_entry（B 层）。"""
        spec = ProblemSemanticSpec(
            source_input="test",
            entities=[{"name": "ball"}],
            explicit_conditions=[{"name": "height", "value": 10.0}],
            entity_model_hints=[],
            interaction_hints=[],
            assumption_hints=[],
        )
        cap = build_particle_motion_spec(spec)
        assert "initial_position_per_entity" not in cap.missing_entry_inputs

    def test_particle_motion_velocity_from_explicit_conditions(self):
        """explicit_conditions 有 v0 关键词时，velocity 不进入 missing_entry（B 层）。"""
        spec = ProblemSemanticSpec(
            source_input="test",
            entities=[{"name": "ball"}],
            explicit_conditions=[{"name": "v0", "value": 0.0}],
        )
        cap = build_particle_motion_spec(spec)
        assert "initial_velocity_per_entity" not in cap.missing_entry_inputs

    def test_contact_interaction_velocity_from_explicit_conditions(self):
        """explicit_conditions 有 velocity 关键词时，pre_collision_velocity 不缺失（B 层）。"""
        spec = ProblemSemanticSpec(
            source_input="test",
            entities=[{"name": "a"}, {"name": "b"}],
            explicit_conditions=[{"name": "velocity", "value": 2.0}],
        )
        cap = build_contact_interaction_spec(spec)
        assert "pre_collision_velocity_per_entity" not in cap.missing_entry_inputs

    def test_particle_motion_all_three_missing_when_no_info(self):
        """无实体、无条件、无 hints 时，三个必要入口要素均缺失。"""
        spec = ProblemSemanticSpec(source_input="test")
        cap = build_particle_motion_spec(spec)
        for required in ["initial_position_per_entity", "initial_velocity_per_entity", "mass_per_entity"]:
            assert required in cap.missing_entry_inputs


# ===========================================================================
# 必测 4：现有 admission 三态行为不被破坏
# ===========================================================================


class TestAdmissionTriStateUnchanged:
    """必测 4：admitted / deferred / unresolved 三态逻辑不受 hints 影响。"""

    def test_unresolved_when_no_entities_with_hints(self):
        """有 interaction_hints 但无实体 → 仍然 unresolved。"""
        from src.planning.execution_plan.builder import _judge_admission
        from src.capabilities.particle_motion.spec import ParticleMotionCapabilitySpec

        spec = ParticleMotionCapabilitySpec(
            capability_name="particle_motion",
            applies_to_entities=[],  # 无实体
            missing_entry_inputs=[],
        )
        assert _judge_admission(spec) == "unresolved"

    def test_deferred_when_missing_entry_with_hints(self):
        """有 assumption_hints 但 missing_entry_inputs 非空 → deferred。"""
        from src.planning.execution_plan.builder import _judge_admission
        from src.capabilities.particle_motion.spec import ParticleMotionCapabilitySpec

        spec = ParticleMotionCapabilitySpec(
            capability_name="particle_motion",
            applies_to_entities=["ball"],
            missing_entry_inputs=["mass_per_entity"],
        )
        assert _judge_admission(spec) == "deferred"

    def test_admitted_when_full_info_with_hints(self):
        """有完整 hints 且 missing_entry_inputs 为空 → admitted。"""
        from src.planning.execution_plan.builder import _judge_admission
        from src.capabilities.particle_motion.spec import ParticleMotionCapabilitySpec

        spec = ParticleMotionCapabilitySpec(
            capability_name="particle_motion",
            applies_to_entities=["ball"],
            missing_entry_inputs=[],
        )
        assert _judge_admission(spec) == "admitted"

    def test_build_execution_plan_with_semantic_hints(self):
        """通过 semantic hints 构造的 spec，build_execution_plan 能正常区分三态。"""
        from src.planning.execution_plan.builder import build_execution_plan

        # 提供完整信息（实体 + 位置 + 速度 + 质量），应 admitted
        problem_spec = ProblemSemanticSpec(
            source_input="一个球从10米高处自由落体",
            entities=[{"name": "ball"}],
            explicit_conditions=[
                {"name": "height", "value": 10.0, "entity": "ball"},
                {"name": "v0", "value": 0.0},
                {"name": "mass", "value": 1.0},
            ],
            interaction_hints=["gravity_present"],
            assumption_hints=["ignore_air_resistance"],
        )
        from src.capabilities.particle_motion.mapper import build_particle_motion_spec
        cap = build_particle_motion_spec(problem_spec)
        plan = build_execution_plan([cap])

        assert cap.capability_name in plan.admitted_capabilities
        assert cap.capability_name not in plan.deferred_capabilities
        assert cap.capability_name not in plan.unresolved_admission_items

    def test_build_execution_plan_deferred_with_semantic_hints_but_missing_mass(self):
        """有 interaction_hints，有实体，但缺 mass → deferred。"""
        from src.planning.execution_plan.builder import build_execution_plan

        problem_spec = ProblemSemanticSpec(
            source_input="一个球从高处落下",
            entities=[{"name": "ball"}],
            explicit_conditions=[
                {"name": "height", "value": 5.0, "entity": "ball"},
                {"name": "v0", "value": 0.0},
                # 缺 mass
            ],
            interaction_hints=["gravity_present"],
        )
        from src.capabilities.particle_motion.mapper import build_particle_motion_spec
        cap = build_particle_motion_spec(problem_spec)
        plan = build_execution_plan([cap])

        deferred_names = [d["capability_name"] for d in plan.deferred_capabilities]
        assert cap.capability_name in deferred_names

    def test_contact_interaction_deferred_when_only_one_entity(self):
        """只有一个实体 → contact_interaction 进入 deferred（at_least_two_entities 缺失）。"""
        from src.planning.execution_plan.builder import build_execution_plan

        problem_spec = ProblemSemanticSpec(
            source_input="一个球运动",
            entities=[{"name": "ball"}],
            assumption_hints=["elastic_collision"],
        )
        from src.capabilities.contact_interaction.mapper import build_contact_interaction_spec
        cap = build_contact_interaction_spec(problem_spec)
        plan = build_execution_plan([cap])

        deferred_names = [d["capability_name"] for d in plan.deferred_capabilities]
        assert cap.capability_name in deferred_names

    def test_contact_interaction_admitted_with_two_entities_and_full_conditions(self):
        """两个实体 + velocity + mass → contact_interaction admitted。"""
        from src.planning.execution_plan.builder import build_execution_plan

        problem_spec = ProblemSemanticSpec(
            source_input="1kg球以2m/s与静止1kg球弹性碰撞",
            entities=[{"name": "a"}, {"name": "b"}],
            explicit_conditions=[
                {"name": "velocity", "value": 2.0, "entity": "a"},
                {"name": "mass", "value": 1.0},
            ],
            assumption_hints=["elastic_collision"],
        )
        from src.capabilities.contact_interaction.mapper import build_contact_interaction_spec
        cap = build_contact_interaction_spec(problem_spec)
        plan = build_execution_plan([cap])

        assert cap.capability_name in plan.admitted_capabilities
