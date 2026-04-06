"""
ContactInteractionCapabilitySpec v0.1.

第一原型的局部交互能力表示。
适用场景：接触/相遇条件触发的局部规则（如瞬时碰撞）。

在 CapabilitySpec 公共骨架基础上增加：
- contact_pairs: 接触实体对列表
- contact_model_hints: 接触模型提示（如弹性碰撞、完全非弹性碰撞）
- pre_trigger_state_requirements: 触发前所需的状态字段要求
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import Field

from src.capabilities.common.base import CapabilitySpec


class ContactInteractionCapabilitySpec(CapabilitySpec):
    """
    接触交互能力规格。

    适用于需要检测接触/相遇并在满足触发条件时激活局部规则的场景。

    Attributes
    ----------
    contact_pairs:
        接触实体对列表，每个元素为两个实体 ID 的列表（如
        ``[["ball_a", "ball_b"]]``）。
    contact_model_hints:
        接触模型提示，描述接触类型（如 ``"elastic"``、
        ``"perfectly_inelastic"``）。允许候选化。
    pre_trigger_state_requirements:
        触发前所需的状态字段要求，描述局部规则激活前需要已知的量
        （如碰前速度、质量）。
    """

    capability_name: str = Field(default="contact_interaction")
    contact_pairs: List[List[str]] = Field(
        default_factory=list,
        description="接触实体对列表（每对为两个实体 ID）",
    )
    contact_model_hints: List[str] = Field(
        default_factory=list,
        description="接触模型提示（如 'elastic'、'perfectly_inelastic'；允许候选化）",
    )
    pre_trigger_state_requirements: Dict[str, Any] = Field(
        default_factory=dict,
        description="触发前各实体需要已知的状态字段要求",
    )
