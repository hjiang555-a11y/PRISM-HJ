"""
ParticleMotionCapabilitySpec 构造器 v0.1.

build_particle_motion_spec(problem_spec) -> ParticleMotionCapabilitySpec

从 ProblemSemanticSpec 中提取粒子运动相关信息，
构造 ParticleMotionCapabilitySpec 骨架。

当前为最小实现：
- 将所有实体转入 applies_to_entities
- 将 rule_extraction_inputs / rule_execution_inputs 直接传递
- 预置 candidate_rules: ["constant_gravity"]
- 允许 initial_state_requirements 和 background_interaction_hints 候选化
"""

from __future__ import annotations

from src.capabilities.particle_motion.spec import ParticleMotionCapabilitySpec
from src.problem_semantic.models import ProblemSemanticSpec


def build_particle_motion_spec(
    problem_spec: ProblemSemanticSpec,
) -> ParticleMotionCapabilitySpec:
    """
    从 ProblemSemanticSpec 构造 ParticleMotionCapabilitySpec。

    Parameters
    ----------
    problem_spec:
        问题语义规格，由 extract_problem_semantics() 产生。

    Returns
    -------
    ParticleMotionCapabilitySpec
        粒子运动能力规格，candidate_rules 预置为 ``["constant_gravity"]``。
    """
    entity_ids = [e.get("name", f"entity_{i}") for i, e in enumerate(problem_spec.entities)]

    # 收集初始状态要求：从 explicit_conditions 中提取与实体相关的初始量
    initial_state_requirements: dict = {}
    for cond in problem_spec.explicit_conditions:
        entity = cond.get("entity")
        if entity:
            initial_state_requirements.setdefault(entity, {})[cond.get("name", "unknown")] = cond.get("value")

    # 从 rule_extraction_inputs 推断背景作用提示
    background_hints: list = list(
        problem_spec.rule_extraction_inputs.get("background_interactions", [])
    )
    if not background_hints:
        background_hints = ["gravity"]  # 默认候选重力

    missing: list = list(problem_spec.unresolved_items)

    # 准入条件字段（Capability Admission Fields）
    # 详见 docs/PRISM_capability_admission_conditions_and_entry_inputs_v0_1.md
    applicability_conditions = [
        "实体可以建模为质点（无旋转、无形变）",
        "背景作用在实体运动的时空范围内连续且空间均匀",
        "实体状态演化可用连续时间微分方程描述",
    ]
    assumptions = [
        "默认忽略空气阻力（除非 background_interaction_hints 中包含 'drag'）",
        "重力加速度恒定（g = 9.8 m/s²）",
        "质量在运动过程中保持不变",
        "质点近似：实体的旋转和形变对运动轨迹无贡献",
    ]
    validity_limits = [
        "非相对论性低速范围（v ≪ c）",
        "引力场在实体轨迹尺度上的空间非均匀性可忽略",
        "实体不经历足以打破质点近似的强旋转或大形变",
    ]

    return ParticleMotionCapabilitySpec(
        applies_to_entities=entity_ids,
        target_mapping={t.get("name", ""): t for t in problem_spec.targets_of_interest},
        rule_extraction_inputs=problem_spec.rule_extraction_inputs,
        rule_execution_inputs=problem_spec.rule_execution_inputs,
        candidate_rules=["constant_gravity"],
        missing_inputs=missing,
        trigger_requirements=[],
        initial_state_requirements=initial_state_requirements,
        background_interaction_hints=background_hints,
        applicability_conditions=applicability_conditions,
        assumptions=assumptions,
        validity_limits=validity_limits,
    )
