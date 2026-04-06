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
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.capabilities.common.base import CapabilitySpec
from src.capabilities.common.kinds import CapabilityKind
from src.planning.execution_plan.models import ExecutionPlan

# 持续规则能力类型集合（对应 persistent_rule_plan）
_PERSISTENT_CAPABILITY_KINDS = frozenset({CapabilityKind.PARTICLE_MOTION})

# 局部规则能力类型集合（对应 local_rule_plan）
_LOCAL_CAPABILITY_KINDS = frozenset({CapabilityKind.CONTACT_INTERACTION})


def _make_assembly_entry(
    capability_name: str,
    target_name: str,
    target_desc: Any,
) -> Dict[str, Any]:
    """
    从 target_desc 构造 assembly_plan 条目，传播 entity / field / component 字段。

    Parameters
    ----------
    capability_name:
        来源能力名称。
    target_name:
        目标量名称（仅供调用者引用，不写入返回值）。
    target_desc:
        目标量描述（来自 spec.target_mapping 的值）。可以是字符串或字典。
        若为字典，则尝试传播 ``entity``、``field``、``component`` 字段。

    Returns
    -------
    Dict[str, Any]
        assembly_plan 条目。
    """
    entry: Dict[str, Any] = {
        "source_capability": capability_name,
        "description": target_desc,
    }
    if isinstance(target_desc, dict):
        for key in ("entity", "field", "component"):
            if key in target_desc:
                entry[key] = target_desc[key]
    return entry


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


def build_execution_plan(
    capability_specs: List[CapabilitySpec],
    admission_hints: Optional[Dict[str, Any]] = None,
) -> ExecutionPlan:
    """
    从 CapabilitySpec 列表构造 ExecutionPlan。

    Parameters
    ----------
    capability_specs:
        由 build_capability_specs() 产生的能力规格列表。
    admission_hints:
        来自语义层的 admission hints（可选）。传递到 ExecutionPlan
        供 Scheduler 在运行时消费。

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
                assembly_plan.setdefault(
                    target_name,
                    _make_assembly_entry(spec.capability_name, target_name, target_desc),
                )
            unresolved.extend(spec.missing_inputs)
            continue

        if admission_status == "deferred":
            deferred_capabilities.append({
                "capability_name": spec.capability_name,
                "missing_entry_inputs": list(spec.missing_entry_inputs),
            })
            plan_notes.append(
                f"capability '{spec.capability_name}' admission=deferred："
                f"缺少入口要素 {spec.missing_entry_inputs}，已推迟进入执行计划"
            )
            # deferred capability 不进入规则计划，但仍汇聚目标量（供追溯）
            for target_name, target_desc in spec.target_mapping.items():
                assembly_plan.setdefault(
                    target_name,
                    _make_assembly_entry(spec.capability_name, target_name, target_desc),
                )
            unresolved.extend(spec.missing_inputs)
            continue

        # admission_status == "admitted"
        admitted_capabilities.append(spec.capability_name)

        # 将实体加入状态集合规划
        for entity_id in spec.applies_to_entities:
            state_set_plan.setdefault(entity_id, {"fields": ["position", "velocity", "mass"]})

        # 分离持续规则和局部规则
        if spec.capability_name in _PERSISTENT_CAPABILITY_KINDS:
            for rule_name in spec.candidate_rules:
                persistent_rule_plan.append({
                    "rule_name": rule_name,
                    "applies_to": spec.applies_to_entities,
                    "rule_execution_inputs": spec.rule_execution_inputs,
                })

        elif spec.capability_name in _LOCAL_CAPABILITY_KINDS:
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

        # 汇聚目标量到 assembly_plan，传播 entity / field / component 字段
        for target_name, target_desc in spec.target_mapping.items():
            assembly_plan[target_name] = _make_assembly_entry(
                spec.capability_name, target_name, target_desc
            )

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
        admission_hints=dict(admission_hints) if admission_hints else {},
    )
