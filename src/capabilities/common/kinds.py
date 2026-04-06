"""
CapabilityKind — 能力类型枚举 v0.1.

用类型标记替代字符串字面量比较，提供静态类型保证。

用法
----
::

    from src.capabilities.common.kinds import CapabilityKind

    if spec.capability_name == CapabilityKind.PARTICLE_MOTION:
        ...

枚举值与字符串 ``capability_name`` 兼容（等值比较）::

    CapabilityKind.PARTICLE_MOTION == "particle_motion"  # True
"""

from __future__ import annotations

from enum import Enum


class CapabilityKind(str, Enum):
    """
    已知能力类型的枚举标记。

    继承 ``str``，使枚举值可直接与字符串 ``capability_name`` 进行等值比较，
    无需调用 ``.value``。
    """

    PARTICLE_MOTION = "particle_motion"
    CONTACT_INTERACTION = "contact_interaction"
