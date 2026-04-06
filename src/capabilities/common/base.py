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
- missing_inputs: 规则执行层尚未补齐的运行时输入项
- trigger_requirements: 触发条件列表（局部规则用）

准入条件字段（Capability Admission Fields）
------------------------------------------
- applicability_conditions: 能力适用的前提条件（定性描述）
- assumptions: 能力工作时依赖的物理假设（含理想化条件）
- validity_limits: 能力假设成立的有效边界
- required_entry_inputs: 能力进入执行前必须已知的物理量类别列表
- missing_entry_inputs: required_entry_inputs 中当前仍缺失的项（动态状态）

字段边界说明
-----------
- ``required_entry_inputs`` / ``missing_entry_inputs``：准入层概念，
  描述 capability 能否进入执行计划（admission 判断依据）。
- ``missing_inputs``：执行层概念，描述规则执行时尚未补齐的运行时输入，
  不直接决定 capability 是否被 admitted。

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
        description=(
            "规则执行层尚未补齐的运行时输入项（执行层概念，不直接决定 admission 状态）。"
            "与 missing_entry_inputs 的区别：missing_inputs 描述规则执行时缺少的参数，"
            "而 missing_entry_inputs 描述 capability 进入执行计划前缺少的准入要素。"
        ),
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
    required_entry_inputs: List[str] = Field(
        default_factory=list,
        description=(
            "能力进入执行前必须已知的物理量类别列表（准入层概念）。"
            "描述 capability 能够被 admitted 所需的最低数据前提，"
            "如 ['initial_position_per_entity', 'mass_per_entity']。"
            "不规定具体参数名，只声明物理量类别。"
        ),
    )
    missing_entry_inputs: List[str] = Field(
        default_factory=list,
        description=(
            "required_entry_inputs 中当前仍缺失的项（动态状态，准入层概念）。"
            "在从 ProblemSemanticSpec 构建 capability 时，若某必要入口要素"
            "无法从语义层找到，则记入此列表。"
            "非空时，capability 进入 deferred 状态而非 admitted。"
        ),
    )
