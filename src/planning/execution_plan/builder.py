"""
ExecutionPlan 构造器 v0.1.

build_execution_plan(capability_specs) -> ExecutionPlan

从一个或多个 CapabilitySpec 构造执行计划，完成：
- persistent/local rules 的基本分离
- trigger 条件组织
- assembly plan 组织

当前最小实现：
- ParticleMotionCapabilitySpec -> persistent_rule_plan
- ContactInteractionCapabilitySpec -> local_rule_plan + trigger_plan
- 目标量从所有 spec 的 target_mapping 中汇聚到 assembly_plan
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.capabilities.common.base import CapabilitySpec
from src.planning.execution_plan.models import ExecutionPlan

# 持续规则能力名称集合（对应 persistent_rule_plan）
_PERSISTENT_CAPABILITY_NAMES = {"particle_motion"}

# 局部规则能力名称集合（对应 local_rule_plan）
_LOCAL_CAPABILITY_NAMES = {"contact_interaction"}


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
        覆盖所有输入能力的最小执行计划。
    """
    state_set_plan: Dict[str, Any] = {}
    persistent_rule_plan: List[Dict[str, Any]] = []
    local_rule_plan: List[Dict[str, Any]] = []
    trigger_plan: List[Dict[str, Any]] = []
    assembly_plan: Dict[str, Any] = {}
    capability_bindings: List[str] = []
    plan_notes: List[str] = []
    unresolved: List[str] = []

    for spec in capability_specs:
        capability_bindings.append(spec.capability_name)

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

        # 汇聚未决项
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
    )
