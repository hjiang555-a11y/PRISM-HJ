"""
ExecutionPlan 构造器 v0.1.

build_execution_plan(capability_specs) -> ExecutionPlan

从一个或多个 CapabilitySpec 构造执行计划，完成：
- persistent/local rules 的基本分离
- trigger 条件组织
- assembly plan 组织
- capability admission 状态判定（admitted / deferred / unresolved）

当前最小实现：
- ParticleMotionCapabilitySpec -> persistent_rule_plan
- ContactInteractionCapabilitySpec -> local_rule_plan + trigger_plan
- 目标量从所有 spec 的 target_mapping 中汇聚到 assembly_plan
- 仅 admitted capabilities 的规则进入执行计划

Admission 判定规则
-----------------
- unresolved:  applies_to_entities 为空（无法确定作用对象）
- deferred:    applies_to_entities 非空，但 missing_entry_inputs 非空（缺少必要入口要素）
- admitted:    applies_to_entities 非空 且 missing_entry_inputs 为空

Deferred 重入骨架（admission 闭环增强）
--------------------------------------
- deferred_capabilities 中每条记录包含 ``reentry_hints`` 字段
- ``build_reentry_context(spec)`` 为 deferred capability 生成结构化补充建议和重入接口
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.capabilities.common.base import CapabilitySpec
from src.planning.execution_plan.models import ExecutionPlan

# 持续规则能力名称集合（对应 persistent_rule_plan）
_PERSISTENT_CAPABILITY_NAMES = {"particle_motion"}

# 局部规则能力名称集合（对应 local_rule_plan）
_LOCAL_CAPABILITY_NAMES = {"contact_interaction"}

# 每个 required_entry_input 对应的可读名称和建议追问方向
_ENTRY_INPUT_SUGGESTIONS: Dict[str, Dict[str, str]] = {
    "initial_position_per_entity": {
        "label": "初始位置",
        "suggestion": "请补充各实体的初始位置（如高度、坐标等）",
        "example_question": "物体的初始高度/位置是多少？",
    },
    "initial_velocity_per_entity": {
        "label": "初始速度",
        "suggestion": "请补充各实体的初始速度（如初速度大小和方向）",
        "example_question": "物体的初始速度是多少？方向如何？",
    },
    "mass_per_entity": {
        "label": "质量",
        "suggestion": "请补充各实体的质量",
        "example_question": "各物体的质量是多少（单位：kg）？",
    },
    "pre_collision_velocity_per_entity": {
        "label": "碰前速度",
        "suggestion": "请补充各实体碰撞前的速度",
        "example_question": "碰撞前各物体的速度是多少？",
    },
    "at_least_two_entities": {
        "label": "至少两个实体",
        "suggestion": "请明确问题中存在至少两个可识别的物理实体",
        "example_question": "问题中有哪些物体参与碰撞？",
    },
}


def _judge_admission(spec: CapabilitySpec) -> str:
    """
    对单个 CapabilitySpec 做最小 admission 判定。

    Returns
    -------
    str
        ``"admitted"`` | ``"deferred"`` | ``"unresolved"``

    判定规则
    --------
    - unresolved:  ``applies_to_entities`` 为空，无法确定作用对象
    - deferred:    ``applies_to_entities`` 非空，但 ``missing_entry_inputs`` 非空
    - admitted:    ``applies_to_entities`` 非空 且 ``missing_entry_inputs`` 为空
    """
    if not spec.applies_to_entities:
        return "unresolved"
    if spec.missing_entry_inputs:
        return "deferred"
    return "admitted"


def build_reentry_context(spec: CapabilitySpec) -> Dict[str, Any]:
    """
    为 deferred capability 生成结构化重入上下文。

    本函数为"补充信息后重新 admission"提供明确的重入接口。
    返回的结构包含：缺少什么、推荐追问什么、涉及哪些实体。

    Parameters
    ----------
    spec:
        处于 deferred 状态的 CapabilitySpec。

    Returns
    -------
    Dict[str, Any]
        结构化重入上下文，包含：

        - ``capability_name``: str
        - ``applies_to_entities``: List[str]  — 涉及的实体（若已知）
        - ``missing_entry_inputs``: List[str]  — 缺少的入口要素
        - ``supplemental_suggestions``: List[Dict]  — 逐项补充建议
        - ``reentry_note``: str  — 重入说明
    """
    supplemental_suggestions = []
    for missing_item in spec.missing_entry_inputs:
        hint = _ENTRY_INPUT_SUGGESTIONS.get(missing_item, {})
        if spec.applies_to_entities:
            entity_note = f"涉及实体：{', '.join(spec.applies_to_entities)}"
        else:
            entity_note = "实体尚未确定"
        supplemental_suggestions.append({
            "missing_item": missing_item,
            "label": hint.get("label", missing_item),
            "suggestion": hint.get("suggestion", f"请补充：{missing_item}"),
            "example_question": hint.get("example_question", ""),
            "entity_context": entity_note,
        })

    return {
        "capability_name": spec.capability_name,
        "applies_to_entities": list(spec.applies_to_entities),
        "missing_entry_inputs": list(spec.missing_entry_inputs),
        "supplemental_suggestions": supplemental_suggestions,
        "reentry_note": (
            f"capability '{spec.capability_name}' 当前处于 deferred 状态。"
            "补充以上缺失入口要素后，可重新调用 build_execution_plan() 进行 admission。"
        ),
    }


def build_execution_plan(capability_specs: List[CapabilitySpec]) -> ExecutionPlan:
    """
    从 CapabilitySpec 列表构造 ExecutionPlan。

    Parameters
    ----------
    capability_specs:
        由 build_capability_specs() 产生的能力规格列表。

    Returns
    -------
    ExecutionPlan
        覆盖所有输入能力的最小执行计划，包含 admission 状态区分。
    """
    state_set_plan: Dict[str, Any] = {}
    persistent_rule_plan: List[Dict[str, Any]] = []
    local_rule_plan: List[Dict[str, Any]] = []
    trigger_plan: List[Dict[str, Any]] = []
    assembly_plan: Dict[str, Any] = {}
    capability_bindings: List[str] = []
    plan_notes: List[str] = []
    unresolved: List[str] = []

    # Admission 状态承接
    admitted_capabilities: List[str] = []
    deferred_capabilities: List[Dict[str, Any]] = []
    unresolved_admission_items: List[Dict[str, Any]] = []

    for spec in capability_specs:
        capability_bindings.append(spec.capability_name)

        # --- Admission 判定 ---
        admission_status = _judge_admission(spec)

        if admission_status == "unresolved":
            unresolved_admission_items.append({
                "capability_name": spec.capability_name,
                "reason": "applies_to_entities 为空，无法确定能力作用对象",
            })
            plan_notes.append(
                f"capability '{spec.capability_name}' admission=unresolved："
                "applies_to_entities 为空，已跳过规则规划"
            )
            # unresolved capability 不进入规则计划，但仍汇聚目标量（供追溯）
            for target_name, target_desc in spec.target_mapping.items():
                assembly_plan.setdefault(target_name, {
                    "source_capability": spec.capability_name,
                    "description": target_desc,
                })
            unresolved.extend(spec.missing_inputs)
            continue

        if admission_status == "deferred":
            reentry_ctx = build_reentry_context(spec)
            deferred_capabilities.append({
                "capability_name": spec.capability_name,
                "missing_entry_inputs": list(spec.missing_entry_inputs),
                "reentry_hints": reentry_ctx,
            })
            plan_notes.append(
                f"capability '{spec.capability_name}' admission=deferred："
                f"缺少入口要素 {spec.missing_entry_inputs}，已推迟进入执行计划"
            )
            # deferred capability 不进入规则计划，但仍汇聚目标量（供追溯）
            for target_name, target_desc in spec.target_mapping.items():
                assembly_plan.setdefault(target_name, {
                    "source_capability": spec.capability_name,
                    "description": target_desc,
                })
            unresolved.extend(spec.missing_inputs)
            continue

        # admission_status == "admitted"
        admitted_capabilities.append(spec.capability_name)

        # 将实体加入状态集合规划
        for entity_id in spec.applies_to_entities:
            state_set_plan.setdefault(entity_id, {"fields": ["position", "velocity", "mass"]})

        # 分离持续规则和局部规则
        if spec.capability_name in _PERSISTENT_CAPABILITY_NAMES:
            for rule_name in spec.candidate_rules:
                persistent_rule_plan.append({
                    "rule_name": rule_name,
                    "applies_to": spec.applies_to_entities,
                    "rule_execution_inputs": spec.rule_execution_inputs,
                })

        elif spec.capability_name in _LOCAL_CAPABILITY_NAMES:
            for rule_name in spec.candidate_rules:
                local_rule_plan.append({
                    "rule_name": rule_name,
                    "trigger_type": "contact",
                    "applies_to": spec.applies_to_entities,
                    "rule_execution_inputs": spec.rule_execution_inputs,
                })
            # 将触发条件加入 trigger_plan
            for req in spec.trigger_requirements:
                trigger_plan.append(req)

        else:
            # 未知能力类型 — 记录备注，候选化处理
            plan_notes.append(
                f"capability '{spec.capability_name}' 未分类为 persistent/local，"
                "已跳过规则规划"
            )

        # 汇聚目标量到 assembly_plan
        for target_name, target_desc in spec.target_mapping.items():
            assembly_plan[target_name] = {
                "source_capability": spec.capability_name,
                "description": target_desc,
            }

        # 汇聚未决项（执行层）
        unresolved.extend(spec.missing_inputs)

    # 去重未决项
    unresolved = list(dict.fromkeys(unresolved))

    return ExecutionPlan(
        state_set_plan=state_set_plan,
        persistent_rule_plan=persistent_rule_plan,
        local_rule_plan=local_rule_plan,
        trigger_plan=trigger_plan,
        assembly_plan=assembly_plan,
        capability_bindings=capability_bindings,
        plan_notes=plan_notes,
        unresolved_execution_inputs=unresolved,
        admitted_capabilities=admitted_capabilities,
        deferred_capabilities=deferred_capabilities,
        unresolved_admission_items=unresolved_admission_items,
    )
