"""
ParticleMotionCapabilitySpec v0.1.

第一原型的持续背景作用能力表示。
适用场景：一个或多个粒子的基本状态推进（如匀变速运动、重力背景作用）。

在 CapabilitySpec 公共骨架基础上增加：
- initial_state_requirements: 初始状态要求（位置、速度等）
- background_interaction_hints: 背景作用提示（如重力、阻力）
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import Field

from src.capabilities.common.base import CapabilitySpec


class ParticleMotionCapabilitySpec(CapabilitySpec):
    """
    粒子运动能力规格。

    适用于需要持续背景作用（如重力）驱动的粒子状态演化场景。

    Attributes
    ----------
    initial_state_requirements:
        初始状态要求，描述各实体需要提供的初始量（如位置、速度、质量）。
        键为实体 ID，值为所需字段名列表或具体值字典。
    background_interaction_hints:
        背景作用提示列表，描述可能存在的持续背景力（如
        ``"gravity"``、``"drag"``）。允许候选化，未决时可标记为
        ``"unknown"``。
    """

    capability_name: str = Field(default="particle_motion")
    initial_state_requirements: Dict[str, Any] = Field(
        default_factory=dict,
        description="各实体所需的初始状态字段要求",
    )
    background_interaction_hints: List[str] = Field(
        default_factory=list,
        description="背景作用提示（如 'gravity'、'drag'；允许候选化）",
    )
