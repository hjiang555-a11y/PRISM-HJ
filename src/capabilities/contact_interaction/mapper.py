"""
ContactInteractionCapabilitySpec 构造器 v0.1.

build_contact_interaction_spec(problem_spec) -> ContactInteractionCapabilitySpec

从 ProblemSemanticSpec 中提取接触交互相关信息，
构造 ContactInteractionCapabilitySpec 骨架。

当前为最小实现：
- 将所有实体两两配对作为候选接触对
- 预置 candidate_rules: ["impulsive_collision"]
- contact_model_hints 候选化为 ["elastic"]
- pre_trigger_state_requirements 从 rule_execution_inputs 转入
- 填充 required_entry_inputs 并计算 missing_entry_inputs（admission 层）

Admission 字段说明
-----------------
- required_entry_inputs: 接触交互 capability 进入执行前必须已知的物理量类别
  ["at_least_two_entities", "pre_collision_velocity_per_entity", "mass_per_entity"]
- missing_entry_inputs: 从 ProblemSemanticSpec 中未能提取到的必要入口要素（动态计算）

注意：hardcoded 的 applicability_conditions / assumptions / validity_limits 是
当前原型的默认物理假设，来源于 contact_interaction 能力本身，而非从 ProblemSemanticSpec
中语义提取。后续如需基于语义线索动态调整，应从 problem_spec.rule_extraction_inputs
中读取覆盖值。
"""

from __future__ import annotations

from src.capabilities.contact_interaction.spec import ContactInteractionCapabilitySpec
from src.problem_semantic.models import ProblemSemanticSpec

# 接触交互 capability 进入执行前必须已知的物理量类别（准入层声明）
_REQUIRED_ENTRY_INPUTS = [
    "at_least_two_entities",
    "pre_collision_velocity_per_entity",
    "mass_per_entity",
]


def build_contact_interaction_spec(
    problem_spec: ProblemSemanticSpec,
) -> ContactInteractionCapabilitySpec:
    """
    从 ProblemSemanticSpec 构造 ContactInteractionCapabilitySpec。

    Parameters
    ----------
    problem_spec:
        问题语义规格，由 extract_problem_semantics() 产生。

    Returns
    -------
    ContactInteractionCapabilitySpec
        接触交互能力规格，candidate_rules 预置为 ``["impulsive_collision"]``。
    """
    entity_ids = [e.get("name", f"entity_{i}") for i, e in enumerate(problem_spec.entities)]

    # 生成候选接触对（两两配对）
    contact_pairs: list = []
    for i in range(len(entity_ids)):
        for j in range(i + 1, len(entity_ids)):
            contact_pairs.append([entity_ids[i], entity_ids[j]])

    # 从 explicit_conditions 收集触发前状态要求
    pre_trigger: dict = {}
    for cond in problem_spec.explicit_conditions:
        entity = cond.get("entity")
        if entity:
            pre_trigger.setdefault(entity, {})[cond.get("name", "unknown")] = cond.get("value")

    # 接触模型提示从 rule_extraction_inputs 中读取（优先来自语义层）
    # 默认候选弹性碰撞为原型 fallback
    contact_hints: list = list(
        problem_spec.rule_extraction_inputs.get("contact_model_hints", [])
    )
    if not contact_hints:
        # 原型默认 fallback：尚无语义线索时使用弹性碰撞作为候选模型
        contact_hints = ["elastic"]

    trigger_reqs = []
    if contact_pairs:
        trigger_reqs.append({
            "type": "contact",
            "pairs": contact_pairs,
        })

    missing_runtime: list = list(problem_spec.unresolved_items)

    # --- Admission 层：计算 missing_entry_inputs ---
    missing_entry: list = []

    # 收集明确给出条件的名称集合，用于粗粒度判断
    condition_names = {cond.get("name", "") for cond in problem_spec.explicit_conditions}

    # 检查是否至少有两个实体（接触交互的基本前提）
    if len(entity_ids) < 2:
        missing_entry.append("at_least_two_entities")

    # 判断是否有碰前速度信息
    _velocity_keywords = {"velocity", "speed", "v", "vx", "vy", "vz", "initial_velocity", "v0", "v0x", "v0y", "v_before"}
    if not (_velocity_keywords & condition_names) and not pre_trigger:
        missing_entry.append("pre_collision_velocity_per_entity")

    # 判断是否有质量信息
    _mass_keywords = {"mass", "m", "mass_kg", "weight"}
    if not (_mass_keywords & condition_names):
        missing_entry.append("mass_per_entity")

    # 准入条件字段（Capability Admission Fields）
    # 注：以下为 contact_interaction 能力本身的默认物理假设，非从语义层动态提取
    applicability_conditions = [
        "问题中存在两个或以上可识别的物理实体",
        "存在可识别的接触或碰撞事件",
        "交互可以用有限时刻的冲量近似描述（碰撞过程远短于整体运动时间尺度）",
    ]
    assumptions = [
        # 原型默认假设；若 contact_model_hints 来自语义层，碰撞类型可被覆盖
        "碰撞为完全瞬时冲击（碰撞时间 Δt → 0，冲量-动量定理适用）",
        "默认弹性碰撞（动能守恒），除非 contact_model_hints 中指定非弹性类型",
        "碰撞期间外力（如重力）的冲量相对碰撞冲量可忽略",
        "刚体近似：碰撞过程中实体不发生形变",
    ]
    validity_limits = [
        "碰撞持续时间远小于整体运动时间尺度",
        "实体间不发生持续接触（持续接触力需引入不同 capability）",
        "刚体近似在碰撞速度和材料特性下成立",
        "仅适用于两体直接接触碰撞；多体同时碰撞需显式扩展 contact_pairs",
    ]

    return ContactInteractionCapabilitySpec(
        applies_to_entities=entity_ids,
        target_mapping={t.get("name", ""): t for t in problem_spec.targets_of_interest},
        rule_extraction_inputs=problem_spec.rule_extraction_inputs,
        rule_execution_inputs=problem_spec.rule_execution_inputs,
        candidate_rules=["impulsive_collision"],
        missing_inputs=missing_runtime,
        trigger_requirements=trigger_reqs,
        contact_pairs=contact_pairs,
        contact_model_hints=contact_hints,
        pre_trigger_state_requirements=pre_trigger,
        applicability_conditions=applicability_conditions,
        assumptions=assumptions,
        validity_limits=validity_limits,
        required_entry_inputs=_REQUIRED_ENTRY_INPUTS,
        missing_entry_inputs=missing_entry,
    )
