"""
ExecutionPlan — 执行计划层最小规划对象 v0.1.

承接一个或多个 CapabilitySpec，生成统一执行安排，表达：
- 要维护哪些状态（state_set_plan）
- 哪些规则持续激活（persistent_rule_plan）
- 哪些规则局部触发（local_rule_plan）
- 何时检查触发（trigger_plan）
- 如何提取结果（assembly_plan）
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ExecutionPlan(BaseModel):
    """
    执行计划层的最小规划对象。

    Attributes
    ----------
    state_set_plan:
        状态集合规划，描述需要维护的实体及其状态字段。
        键为实体 ID，值为所需状态字段名列表或初始值字典。
    persistent_rule_plan:
        持续规则规划列表。每个条目描述一条持续激活的规则，
        至少含 ``rule_name`` 和 ``applies_to`` 字段。
    local_rule_plan:
        局部规则规划列表。每个条目描述一条局部触发的规则，
        至少含 ``rule_name``、``trigger_type`` 和 ``applies_to`` 字段。
    trigger_plan:
        触发条件规划列表。每个条目描述一个触发检查点，
        至少含 ``trigger_type`` 和 ``involved_entities`` 字段。
    assembly_plan:
        结果组装规划，描述如何从运行时状态中提取目标量。
        键为目标量名称，值为提取方式描述字典。
    capability_bindings:
        本执行计划绑定的 CapabilitySpec 名称列表（用于追溯）。
    plan_notes:
        规划备注列表（自由文本，供调试和审查）。
    unresolved_execution_inputs:
        当前未补齐的执行输入项列表。
    """

    state_set_plan: Dict[str, Any] = Field(
        default_factory=dict,
        description="需要维护的实体及其状态字段规划",
    )
    persistent_rule_plan: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="持续规则规划列表",
    )
    local_rule_plan: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="局部规则规划列表",
    )
    trigger_plan: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="触发条件规划列表",
    )
    assembly_plan: Dict[str, Any] = Field(
        default_factory=dict,
        description="结果组装规划（目标量名称 -> 提取描述）",
    )
    capability_bindings: List[str] = Field(
        default_factory=list,
        description="本执行计划绑定的 CapabilitySpec 名称列表",
    )
    plan_notes: List[str] = Field(
        default_factory=list,
        description="规划备注（自由文本）",
    )
    unresolved_execution_inputs: List[str] = Field(
        default_factory=list,
        description="当前未补齐的执行输入项",
    )
