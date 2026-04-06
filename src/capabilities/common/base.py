"""
CapabilitySpec 最小公共接口骨架 v0.1.

所有具体能力规格（ParticleMotionCapabilitySpec、
ContactInteractionCapabilitySpec 等）均继承此基类。

公共字段
--------
- capability_name: 能力标识名称
- applies_to_entities: 适用的实体 ID 列表
- target_mapping: 目标量映射（实体字段 -> 目标量名称）
- rule_extraction_inputs: 规则提取所需依据
- rule_execution_inputs: 规则执行所需输入
- candidate_rules: 候选规则名称列表
- missing_inputs: 当前缺失的输入项（对应准入约定中的 missing_entry_inputs）
- trigger_requirements: 触发条件列表（局部规则用）

准入条件字段（Capability Admission Fields）
------------------------------------------
- applicability_conditions: 能力适用的前提条件（定性描述）
- assumptions: 能力工作时依赖的物理假设（含理想化条件）
- validity_limits: 能力假设成立的有效边界

详见：docs/PRISM_capability_admission_conditions_and_entry_inputs_v0_1.md
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class CapabilitySpec(BaseModel):
    """
    能力表示的最小公共骨架。

    具体能力规格通过继承此类并添加特化字段来实现。
    所有字段均提供默认值，允许部分填充的候选化构造。
    """

    capability_name: str = Field(description="能力标识名称（如 'particle_motion'）")
    applies_to_entities: List[str] = Field(
        default_factory=list,
        description="本能力适用的实体 ID 列表",
    )
    target_mapping: Dict[str, Any] = Field(
        default_factory=dict,
        description="目标量映射（实体字段 -> 目标量名称）",
    )
    rule_extraction_inputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="规则提取所需依据（由 ProblemSemanticSpec 转入）",
    )
    rule_execution_inputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="规则执行所需输入（由 ProblemSemanticSpec 转入）",
    )
    candidate_rules: List[str] = Field(
        default_factory=list,
        description="候选规则名称列表（允许未决）",
    )
    missing_inputs: List[str] = Field(
        default_factory=list,
        description="当前尚未补齐的输入项",
    )
    trigger_requirements: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="触发条件描述列表（主要供局部规则使用）",
    )

    # --- 准入条件字段（Capability Admission Fields） ---
    # 详见 docs/PRISM_capability_admission_conditions_and_entry_inputs_v0_1.md

    applicability_conditions: List[str] = Field(
        default_factory=list,
        description=(
            "能力适用的前提条件（定性描述）。"
            "描述能力可被激活的物理情境前提，如'实体可建模为质点'。"
        ),
    )
    assumptions: List[str] = Field(
        default_factory=list,
        description=(
            "能力工作时依赖的物理假设（含理想化条件）。"
            "如'重力加速度恒定'、'忽略空气阻力'、'质点近似'。"
        ),
    )
    validity_limits: List[str] = Field(
        default_factory=list,
        description=(
            "能力假设成立的有效边界（定性描述）。"
            "如'非相对论性低速范围'、'碰撞时间远小于整体运动时间尺度'。"
        ),
    )
