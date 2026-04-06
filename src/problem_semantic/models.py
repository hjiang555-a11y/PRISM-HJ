"""
ProblemSemanticSpec — 问题语义层最小输出对象 v0.1.

承接输入问题的最小语义结构，用于后续构造 CapabilitySpec 和 ExecutionPlan。
支持候选化输出与未决项记录，允许部分字段不完整。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ProblemSemanticSpec(BaseModel):
    """
    问题语义层的最小输出对象。

    Attributes
    ----------
    source_input:
        原始输入文本。
    entities:
        从输入中识别出的物理实体列表。每个条目为字典，至少含 ``name``
        字段，其余字段（``mass``、``initial_position`` 等）按需填充。
    targets_of_interest:
        目标量列表。每个条目描述需要求解或查询的物理量，至少含
        ``name`` 和 ``description`` 字段。
    explicit_conditions:
        明确给出的物理条件（如初速度、高度、质量等）。每个条目为字典，
        至少含 ``name`` 和 ``value`` 字段。
    candidate_domains:
        候选物理域（如 ``"mechanics"``、``"thermodynamics"``）。允许多个
        候选，未决时可留空或标记为 ``"unknown"``。
    candidate_capabilities:
        候选能力名称列表（如 ``"particle_motion"``、
        ``"contact_interaction"``）。
    rule_extraction_inputs:
        规则提取所需的依据输入（键值对）。用于后续为规则提取器准备素材。
    rule_execution_inputs:
        规则执行所需的输入（键值对）。用于后续为规则执行器准备输入。
    unresolved_items:
        当前无法确定的字段或信息项列表。允许候选化输出时记录未决内容。
    """

    source_input: str = Field(description="原始输入文本")
    entities: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="识别出的物理实体列表",
    )
    targets_of_interest: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="需要求解或查询的目标量列表",
    )
    explicit_conditions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="明确给出的物理条件列表",
    )
    candidate_domains: List[str] = Field(
        default_factory=list,
        description="候选物理域（允许 'unknown' 占位）",
    )
    candidate_capabilities: List[str] = Field(
        default_factory=list,
        description="候选能力名称列表",
    )
    rule_extraction_inputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="规则提取所需依据（键值对）",
    )
    rule_execution_inputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="规则执行所需输入（键值对）",
    )
    unresolved_items: List[str] = Field(
        default_factory=list,
        description="当前未决或候选化的信息项",
    )
