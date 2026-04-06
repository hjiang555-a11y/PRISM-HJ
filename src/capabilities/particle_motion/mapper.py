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
- 填充 required_entry_inputs 并计算 missing_entry_inputs（admission 层）

Admission 字段说明
-----------------
- required_entry_inputs: 粒子运动 capability 进入执行前必须已知的物理量类别
  ["initial_position_per_entity", "initial_velocity_per_entity", "mass_per_entity"]
- missing_entry_inputs: 从 ProblemSemanticSpec 中未能提取到的必要入口要素（动态计算）

注意：hardcoded 的 applicability_conditions / assumptions / validity_limits 是
当前原型的默认物理假设，来源于 particle_motion 能力本身，而非从 ProblemSemanticSpec
中语义提取。后续如需基于语义线索动态调整，应从 problem_spec.rule_extraction_inputs
中读取覆盖值。
"""

from __future__ import annotations

from src.capabilities.particle_motion.spec import ParticleMotionCapabilitySpec
from src.problem_semantic.models import ProblemSemanticSpec

# 粒子运动 capability 进入执行前必须已知的物理量类别（准入层声明）
_REQUIRED_ENTRY_INPUTS = [
    "initial_position_per_entity",
    "initial_velocity_per_entity",
    "mass_per_entity",
]


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
    # 来源：ProblemSemanticSpec 中的语义线索；默认候选重力为原型 fallback
    background_hints: list = list(
        problem_spec.rule_extraction_inputs.get("background_interactions", [])
    )
    if not background_hints:
        # 原型默认 fallback：尚无语义线索时使用重力作为候选背景作用
        background_hints = ["gravity"]

    missing_runtime: list = list(problem_spec.unresolved_items)

    # --- Admission 层：计算 missing_entry_inputs ---
    # 检查从 ProblemSemanticSpec 中是否能找到各必要入口要素
    missing_entry: list = []

    # 检查是否有实体可作用（applies_to_entities 将为空则在 builder 中判定 unresolved）
    # 以下检查各实体的必要入口要素

    # 收集明确给出条件的名称集合，用于粗粒度判断
    condition_names = {cond.get("name", "") for cond in problem_spec.explicit_conditions}

    # 判断是否有初始位置信息（position / height / x / y / z 等关键词）
    _position_keywords = {"position", "height", "x", "y", "z", "initial_position", "x0", "y0", "z0"}
    if not (_position_keywords & condition_names) and not initial_state_requirements:
        missing_entry.append("initial_position_per_entity")

    # 判断是否有初始速度信息（velocity / speed / v / vx / vy / vz 等关键词）
    _velocity_keywords = {"velocity", "speed", "v", "vx", "vy", "vz", "initial_velocity", "v0", "v0x", "v0y"}
    if not (_velocity_keywords & condition_names):
        missing_entry.append("initial_velocity_per_entity")

    # 判断是否有质量信息
    _mass_keywords = {"mass", "m", "mass_kg", "weight"}
    if not (_mass_keywords & condition_names):
        missing_entry.append("mass_per_entity")

    # 准入条件字段（Capability Admission Fields）
    # 注：以下为 particle_motion 能力本身的默认物理假设，非从语义层动态提取
    applicability_conditions = [
        "实体可以建模为质点（无旋转、无形变）",
        "背景作用在实体运动的时空范围内连续且空间均匀",
        "实体状态演化可用连续时间微分方程描述",
    ]
    assumptions = [
        # 原型默认假设；若 background_hints 来自语义层，此条可被覆盖
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
        missing_inputs=missing_runtime,
        trigger_requirements=[],
        initial_state_requirements=initial_state_requirements,
        background_interaction_hints=background_hints,
        applicability_conditions=applicability_conditions,
        assumptions=assumptions,
        validity_limits=validity_limits,
        required_entry_inputs=_REQUIRED_ENTRY_INPUTS,
        missing_entry_inputs=missing_entry,
    )
