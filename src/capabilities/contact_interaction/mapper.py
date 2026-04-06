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

信息来源三层优先级（P0 第四步明确）
------------------------------------
A. 语义层 hints（interaction_hints / assumption_hints）
   —— 来自 extraction pipeline 的结构化推断，优先消费
B. explicit_conditions 的量纲/物理量线索
   —— 条件名称关键词匹配，次优先
C. 原型阶段 fallback 默认值
   —— 仅当 A 和 B 均无信息时使用，作为最后兜底

代码结构注释标注了每段逻辑属于哪一层来源。
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

    # ------------------------------------------------------------------
    # 接触模型提示（contact_model_hints）
    # 信息来源优先级：A → B → C
    # ------------------------------------------------------------------

    # A. 语义层：来自 assumption_hints（extraction pipeline 推断）
    # 注：inelastic 优先于 elastic（inelastic 是更强的约束）；
    #     若 assumption_hints 同时含两者（异常情况），以 inelastic 为准
    contact_hints: list = []
    if "inelastic_collision" in problem_spec.assumption_hints:
        contact_hints.append("inelastic")
    elif "elastic_collision" in problem_spec.assumption_hints:
        contact_hints.append("elastic")

    # B. 来自 rule_extraction_inputs（上层显式传入的线索，优先于 C）
    if not contact_hints:
        contact_hints = list(
            problem_spec.rule_extraction_inputs.get("contact_model_hints", [])
        )

    # C. 原型默认 fallback：A 和 B 均无信息时使用弹性碰撞作为候选模型
    if not contact_hints:
        contact_hints = ["elastic"]

    trigger_reqs = []
    if contact_pairs:
        trigger_reqs.append({
            "type": "contact",
            "pairs": contact_pairs,
        })

    missing_runtime: list = list(problem_spec.unresolved_items)

    # ------------------------------------------------------------------
    # Admission 层：计算 missing_entry_inputs
    # 对每个必要入口要素，按 A → B → C 顺序判断是否已知
    # ------------------------------------------------------------------

    # B. 来自 explicit_conditions 的量纲/物理量线索（名称关键词匹配）
    condition_names = {cond.get("name", "") for cond in problem_spec.explicit_conditions}

    missing_entry: list = []

    # --- 至少两个实体 ---
    # A. 语义层：interaction_hints 含 collision_possible 强烈提示有两个实体，
    #    但 admission 仍依赖实体列表实际长度（语义 hint 不能替代实体数量判断）
    if len(entity_ids) < 2:
        missing_entry.append("at_least_two_entities")

    # --- 碰前速度 ---
    # A. 语义层：当前无直接速度已知 hint（需结合 explicit_conditions 或 pre_trigger）
    _has_velocity_from_semantics = False
    # B. 显式条件关键词
    _velocity_keywords = {"velocity", "speed", "v", "vx", "vy", "vz", "initial_velocity", "v0", "v0x", "v0y", "v_before"}
    _has_velocity_from_conditions = bool(_velocity_keywords & condition_names) or bool(pre_trigger)
    # 汇总判断
    if not _has_velocity_from_semantics and not _has_velocity_from_conditions:
        missing_entry.append("pre_collision_velocity_per_entity")

    # --- 质量 ---
    # A. 语义层：当前无直接质量 hint
    _has_mass_from_semantics = False
    # B. 显式条件关键词
    _mass_keywords = {"mass", "m", "mass_kg", "weight"}
    _has_mass_from_conditions = bool(_mass_keywords & condition_names)
    # 汇总判断
    if not _has_mass_from_semantics and not _has_mass_from_conditions:
        missing_entry.append("mass_per_entity")

    # ------------------------------------------------------------------
    # 准入条件字段（applicability_conditions / assumptions / validity_limits）
    # 信息来源优先级：A → C
    # ------------------------------------------------------------------

    applicability_conditions = [
        "问题中存在两个或以上可识别的物理实体",
        "存在可识别的接触或碰撞事件",
        "交互可以用有限时刻的冲量近似描述（碰撞过程远短于整体运动时间尺度）",
    ]

    # assumptions 根据 semantic hints（A 层）动态调整，未知时使用原型默认值（C 层）
    assumptions: list = []

    # A. 语义层：根据 assumption_hints 推断碰撞类型
    if "inelastic_collision" in problem_spec.assumption_hints:
        assumptions.append("非弹性碰撞（来自语义层 assumption_hints：inelastic_collision）")
    elif "elastic_collision" in problem_spec.assumption_hints:
        assumptions.append("弹性碰撞（来自语义层 assumption_hints：elastic_collision）")
    else:
        # C. 原型默认 fallback
        assumptions.append("默认弹性碰撞（动能守恒），除非 contact_model_hints 中指定非弹性类型")

    # C. 原型默认假设（与语义层无关的物理基础假设）
    assumptions.extend([
        "碰撞为完全瞬时冲击（碰撞时间 Δt → 0，冲量-动量定理适用）",
        "碰撞期间外力（如重力）的冲量相对碰撞冲量可忽略",
        "刚体近似：碰撞过程中实体不发生形变",
    ])

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
