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
"""

from __future__ import annotations

from src.capabilities.contact_interaction.spec import ContactInteractionCapabilitySpec
from src.problem_semantic.models import ProblemSemanticSpec


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

    # 接触模型提示从 rule_extraction_inputs 中读取，默认候选弹性碰撞
    contact_hints: list = list(
        problem_spec.rule_extraction_inputs.get("contact_model_hints", [])
    )
    if not contact_hints:
        contact_hints = ["elastic"]

    trigger_reqs = []
    if contact_pairs:
        trigger_reqs.append({
            "type": "contact",
            "pairs": contact_pairs,
        })

    missing: list = list(problem_spec.unresolved_items)

    return ContactInteractionCapabilitySpec(
        applies_to_entities=entity_ids,
        target_mapping={t.get("name", ""): t for t in problem_spec.targets_of_interest},
        rule_extraction_inputs=problem_spec.rule_extraction_inputs,
        rule_execution_inputs=problem_spec.rule_execution_inputs,
        candidate_rules=["impulsive_collision"],
        missing_inputs=missing,
        trigger_requirements=trigger_reqs,
        contact_pairs=contact_pairs,
        contact_model_hints=contact_hints,
        pre_trigger_state_requirements=pre_trigger,
    )
