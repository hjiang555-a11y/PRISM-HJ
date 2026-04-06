"""
build_capability_specs — 能力规格构造入口 v0.1.

build_capability_specs(problem_semantic_spec) -> list[CapabilitySpec]

从 ProblemSemanticSpec 构造第一批能力规格：
- ParticleMotionCapabilitySpec
- ContactInteractionCapabilitySpec

注意：这里是"构造能力表示"，不是"直接执行物理求解"。
"""

from __future__ import annotations

from typing import List

from src.capabilities.common.base import CapabilitySpec
from src.capabilities.contact_interaction.mapper import build_contact_interaction_spec
from src.capabilities.particle_motion.mapper import build_particle_motion_spec
from src.problem_semantic.models import ProblemSemanticSpec


def build_capability_specs(
    problem_semantic_spec: ProblemSemanticSpec,
) -> List[CapabilitySpec]:
    """
    从问题语义层输出构造第一批能力表示。

    当前输出（按顺序）：

    1. :class:`~src.capabilities.particle_motion.spec.ParticleMotionCapabilitySpec`
    2. :class:`~src.capabilities.contact_interaction.spec.ContactInteractionCapabilitySpec`

    Parameters
    ----------
    problem_semantic_spec:
        由 :func:`~src.problem_semantic.extraction.pipeline.extract_problem_semantics`
        产生的问题语义规格。

    Returns
    -------
    List[CapabilitySpec]
        能力规格列表（两个元素）。
    """
    return [
        build_particle_motion_spec(problem_semantic_spec),
        build_contact_interaction_spec(problem_semantic_spec),
    ]
