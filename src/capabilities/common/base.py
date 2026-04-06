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
- applicability_conditions: 能力适用的前提条件（定性描述，静态文本）
- applicability_eval: 适用条件的结构化动态评估结果（新增）
- assumptions: 能力工作时依赖的物理假设（含理想化条件）
- validity_limits: 能力假设成立的有效边界
- validity_warnings: 有效边界触发的轻量警告（新增）
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

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ApplicabilityEvalItem(BaseModel):
    """
    适用条件的结构化动态评估结果（单条）。

    mapper 在构造 CapabilitySpec 时，对每条 applicability_conditions 进行
    动态评估，结果以本结构记录。这使 admission 判断可追溯，并为后续更精细的
    准入决策提供依据。

    Attributes
    ----------
    condition_key:
        条件标识键（机器可读，如 ``"point_mass_applicable"``）。
    description:
        条件的中文描述（与 applicability_conditions 中的文本对应）。
    status:
        评估状态。可能值：
        ``"satisfied"``：条件满足；
        ``"uncertain"``：无法确定，需更多信息；
        ``"unsupported"``：条件不满足，此 capability 可能不适用。
    source:
        评估依据来源（如 ``"entity_model_hints"``、``"interaction_hints"``、
        ``"entity_count"``、``"default"``）。
    notes:
        补充说明（可选）。
    """

    condition_key: str = Field(description="条件标识键（机器可读）")
    description: str = Field(description="条件描述（中文）")
    status: str = Field(
        description="评估状态：'satisfied' | 'uncertain' | 'unsupported'",
    )
    source: str = Field(description="评估依据来源")
    notes: Optional[str] = Field(default=None, description="补充说明（可选）")


class ValidityWarning(BaseModel):
    """
    有效边界触发的轻量警告（单条）。

    当问题文本中出现可能违反 capability validity_limits 的信号时，
    mapper 生成本结构记录警告。警告不改变 admission 三态，但提供
    可被测试断言的结构化信号。

    Attributes
    ----------
    warning_key:
        警告标识键（机器可读，如 ``"rotation_hint_in_point_mass"``）。
    description:
        警告描述（中文）。
    triggered_by:
        触发该警告的文本线索或条件描述。
    """

    warning_key: str = Field(description="警告标识键（机器可读）")
    description: str = Field(description="警告描述（中文）")
    triggered_by: str = Field(description="触发该警告的文本线索或条件描述")


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
            "能力适用的前提条件（定性描述，静态文本）。"
            "描述能力可被激活的物理情境前提，如'实体可建模为质点'。"
        ),
    )
    applicability_eval: List[ApplicabilityEvalItem] = Field(
        default_factory=list,
        description=(
            "适用条件的结构化动态评估结果。"
            "mapper 在构造 spec 时对每条 applicability_conditions 进行动态评估，"
            "结果以 ApplicabilityEvalItem 列表记录，状态为 'satisfied'/'uncertain'/'unsupported'。"
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
    validity_warnings: List[ValidityWarning] = Field(
        default_factory=list,
        description=(
            "有效边界触发的轻量警告列表。"
            "当文本中出现可能违反 validity_limits 的信号时由 mapper 填充。"
            "警告不改变 admission 三态，但提供可被测试断言的结构化信号。"
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
