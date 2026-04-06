"""
ParticleMotionCapabilitySpec 构造器 v0.1.

build_particle_motion_spec(problem_spec) -> ParticleMotionCapabilitySpec

从 ProblemSemanticSpec 中提取粒子运动相关信息，
构造 ParticleMotionCapabilitySpec 骨架。

当前为最小实现：
- 将所有实体转入 applies_to_entities
- 将 rule_extraction_inputs / rule_execution_inputs 直接传递
- 预置 candidate_rules: ["constant_gravity"]
- 允许 initial_state_requirements 和 background_interaction_hints 候选化
- 填充 required_entry_inputs 并计算 missing_entry_inputs（admission 层）

Admission 字段说明
-----------------
- required_entry_inputs: 粒子运动 capability 进入执行前必须已知的物理量类别
  ["initial_position_per_entity", "initial_velocity_per_entity", "mass_per_entity"]
- missing_entry_inputs: 从 ProblemSemanticSpec 中未能提取到的必要入口要素（动态计算）

信息来源三层优先级（P0 第四步明确）
------------------------------------
A. 语义层 hints（entity_model_hints / interaction_hints / assumption_hints）
   —— 来自 extraction pipeline 的结构化推断，优先消费
B. explicit_conditions 的量纲/物理量线索
   —— 条件名称关键词匹配，次优先
C. 原型阶段 fallback 默认值
   —— 仅当 A 和 B 均无信息时使用，作为最后兜底

代码结构注释标注了每段逻辑属于哪一层来源。
"""

from __future__ import annotations

import re

from src.capabilities.common.base import ApplicabilityEvalItem, ValidityWarning
from src.capabilities.particle_motion.spec import ParticleMotionCapabilitySpec
from src.problem_semantic.models import ProblemSemanticSpec

# 粒子运动 capability 进入执行前必须已知的物理量类别（准入层声明）
_REQUIRED_ENTRY_INPUTS = [
    "initial_position_per_entity",
    "initial_velocity_per_entity",
    "mass_per_entity",
]


def build_particle_motion_spec(
    problem_spec: ProblemSemanticSpec,
) -> ParticleMotionCapabilitySpec:
    """
    从 ProblemSemanticSpec 构造 ParticleMotionCapabilitySpec。

    Parameters
    ----------
    problem_spec:
        问题语义规格，由 extract_problem_semantics() 产生。

    Returns
    -------
    ParticleMotionCapabilitySpec
        粒子运动能力规格，candidate_rules 预置为 ``["constant_gravity"]``。
    """
    entity_ids = [e.get("name", f"entity_{i}") for i, e in enumerate(problem_spec.entities)]

    # 收集初始状态要求：从 explicit_conditions 中提取与实体相关的初始量
    initial_state_requirements: dict = {}
    for cond in problem_spec.explicit_conditions:
        entity = cond.get("entity")
        if entity:
            initial_state_requirements.setdefault(entity, {})[cond.get("name", "unknown")] = cond.get("value")

    # ------------------------------------------------------------------
    # 背景作用提示（background_interaction_hints）
    # 信息来源优先级：A → B → C
    # ------------------------------------------------------------------

    # A. 语义层：来自 interaction_hints（extraction pipeline 推断）
    background_hints: list = []
    if "gravity_present" in problem_spec.interaction_hints:
        background_hints.append("gravity")

    # B. 来自 rule_extraction_inputs（上层显式传入的线索，优先于 C）
    if not background_hints:
        background_hints = list(
            problem_spec.rule_extraction_inputs.get("background_interactions", [])
        )

    # C. 原型默认 fallback：A 和 B 均无信息时使用重力作为候选背景作用
    if not background_hints:
        background_hints = ["gravity"]

    missing_runtime: list = list(problem_spec.unresolved_items)

    # ------------------------------------------------------------------
    # Admission 层：计算 missing_entry_inputs
    # 对每个必要入口要素，按 A → B → C 顺序判断是否已知
    # ------------------------------------------------------------------

    # B. 来自 explicit_conditions 的量纲/物理量线索（名称关键词匹配）
    condition_names = {cond.get("name", "") for cond in problem_spec.explicit_conditions}

    missing_entry: list = []

    # --- 初始位置 ---
    # A. 语义层：来自 input_availability_hints（结构化输入可得性，admission 闭环增强）；
    #    兼容旧逻辑：如有实体初始状态要求亦视为已知
    _has_position_from_semantics = (
        problem_spec.input_availability_hints.initial_position_known
        or bool(initial_state_requirements)
    )
    # B. 显式条件关键词
    _position_keywords = {"position", "height", "x", "y", "z", "initial_position", "x0", "y0", "z0"}
    _has_position_from_conditions = bool(_position_keywords & condition_names)
    # 汇总判断
    if not _has_position_from_semantics and not _has_position_from_conditions:
        missing_entry.append("initial_position_per_entity")

    # --- 初始速度 ---
    # A. 语义层：来自 input_availability_hints（结构化输入可得性，admission 闭环增强）
    _has_velocity_from_semantics = problem_spec.input_availability_hints.initial_velocity_known
    # B. 显式条件关键词
    _velocity_keywords = {"velocity", "speed", "v", "vx", "vy", "vz", "initial_velocity", "v0", "v0x", "v0y"}
    _has_velocity_from_conditions = bool(_velocity_keywords & condition_names)
    # 汇总判断
    if not _has_velocity_from_semantics and not _has_velocity_from_conditions:
        missing_entry.append("initial_velocity_per_entity")

    # --- 质量 ---
    # A. 语义层：来自 input_availability_hints（结构化输入可得性，admission 闭环增强）
    _has_mass_from_semantics = problem_spec.input_availability_hints.mass_known
    # B. 显式条件关键词
    _mass_keywords = {"mass", "m", "mass_kg", "weight"}
    _has_mass_from_conditions = bool(_mass_keywords & condition_names)
    # 汇总判断
    if not _has_mass_from_semantics and not _has_mass_from_conditions:
        missing_entry.append("mass_per_entity")

    # ------------------------------------------------------------------
    # 准入条件字段（applicability_conditions / assumptions / validity_limits）
    # 信息来源优先级：A → C
    # ------------------------------------------------------------------

    applicability_conditions = [
        "实体可以建模为质点（无旋转、无形变）",
        "背景作用在实体运动的时空范围内连续且空间均匀",
        "实体状态演化可用连续时间微分方程描述",
        "不存在可能中断连续状态演化的局部触发事件",
    ]

    # ------------------------------------------------------------------
    # applicability_eval：结构化动态评估（Goal 2）
    # 对每条 applicability_conditions 进行动态评估，输出带 status 的结构
    # ------------------------------------------------------------------

    applicability_eval: list = []

    # 条件 1：实体是否可视为质点
    _has_rigid_body_hint = "rigid_body" in problem_spec.entity_model_hints
    _has_point_mass_hint = "point_mass" in problem_spec.entity_model_hints
    if _has_rigid_body_hint:
        applicability_eval.append(ApplicabilityEvalItem(
            condition_key="point_mass_applicable",
            description="实体可以建模为质点（无旋转、无形变）",
            status="unsupported",
            source="entity_model_hints",
            notes="entity_model_hints 包含 'rigid_body'，质点近似不适用",
        ))
    elif _has_point_mass_hint:
        applicability_eval.append(ApplicabilityEvalItem(
            condition_key="point_mass_applicable",
            description="实体可以建模为质点（无旋转、无形变）",
            status="satisfied",
            source="entity_model_hints",
            notes="entity_model_hints 包含 'point_mass'",
        ))
    else:
        applicability_eval.append(ApplicabilityEvalItem(
            condition_key="point_mass_applicable",
            description="实体可以建模为质点（无旋转、无形变）",
            status="uncertain",
            source="default",
            notes="未检测到明确实体建模 hint，默认质点近似但不确定",
        ))

    # 条件 2：是否存在持续背景作用
    _has_field_hint = "field_present" in problem_spec.interaction_hints
    _has_gravity_hint = "gravity_present" in problem_spec.interaction_hints
    if _has_field_hint:
        applicability_eval.append(ApplicabilityEvalItem(
            condition_key="continuous_background_action",
            description="背景作用在实体运动的时空范围内连续且空间均匀",
            status="uncertain",
            source="interaction_hints",
            notes="interaction_hints 包含 'field_present'，需确认场是否空间均匀",
        ))
    elif _has_gravity_hint:
        applicability_eval.append(ApplicabilityEvalItem(
            condition_key="continuous_background_action",
            description="背景作用在实体运动的时空范围内连续且空间均匀",
            status="satisfied",
            source="interaction_hints",
            notes="interaction_hints 包含 'gravity_present'，均匀重力满足条件",
        ))
    else:
        applicability_eval.append(ApplicabilityEvalItem(
            condition_key="continuous_background_action",
            description="背景作用在实体运动的时空范围内连续且空间均匀",
            status="uncertain",
            source="default",
            notes="未检测到明确背景作用 hint，无法确认",
        ))

    # 条件 3：是否适合连续状态演化
    applicability_eval.append(ApplicabilityEvalItem(
        condition_key="continuous_state_evolution",
        description="实体状态演化可用连续时间微分方程描述",
        status="satisfied",
        source="default",
        notes="粒子运动默认适合连续状态演化，除非有突变事件",
    ))

    # 条件 4：是否存在可能切断该 capability 的局部触发事件
    _has_collision_hint = "collision_possible" in problem_spec.interaction_hints
    if _has_collision_hint:
        applicability_eval.append(ApplicabilityEvalItem(
            condition_key="no_local_trigger_interrupt",
            description="不存在可能中断连续状态演化的局部触发事件",
            status="uncertain",
            source="interaction_hints",
            notes="interaction_hints 包含 'collision_possible'，可能存在碰撞中断连续演化",
        ))
    else:
        applicability_eval.append(ApplicabilityEvalItem(
            condition_key="no_local_trigger_interrupt",
            description="不存在可能中断连续状态演化的局部触发事件",
            status="satisfied",
            source="interaction_hints",
            notes="未检测到碰撞/接触 hint，连续演化不被中断",
        ))

    # assumptions 根据 semantic hints（A 层）动态调整，未知时使用原型默认值（C 层）
    assumptions: list = []

    # A. 语义层：根据 assumption_hints 推断
    if "ignore_air_resistance" in problem_spec.assumption_hints:
        # 语义层已明确忽略空气阻力
        assumptions.append("忽略空气阻力（来自语义层 assumption_hints）")
    else:
        # C. 原型默认 fallback：未指定时默认忽略空气阻力
        assumptions.append("默认忽略空气阻力（除非 background_interaction_hints 中包含 'drag'）")

    # C. 原型默认假设（与语义层无关的物理基础假设）
    assumptions.extend([
        "重力加速度恒定（g = 9.8 m/s²）",
        "质量在运动过程中保持不变",
        "质点近似：实体的旋转和形变对运动轨迹无贡献",
    ])

    validity_limits = [
        "非相对论性低速范围（v ≪ c）",
        "引力场在实体轨迹尺度上的空间非均匀性可忽略",
        "实体不经历足以打破质点近似的强旋转或大形变",
    ]

    # ------------------------------------------------------------------
    # validity_warnings：轻量警告机制（Goal 4）
    # 检测文本中可能违反 validity_limits 的信号，生成结构化警告
    # 警告不影响 admission 三态
    # ------------------------------------------------------------------

    validity_warnings: list = []
    _source_text = problem_spec.source_input.lower()

    # 警告 1：文本中出现旋转/刚体暗示，但仍按质点能力处理
    if re.search(
        r"旋转|转动|rotation|angular|转动惯量|moment\s*of\s*inertia|angular\s*velocity|角速度",
        _source_text,
    ):
        validity_warnings.append(ValidityWarning(
            warning_key="rotation_hint_in_point_mass",
            description="文本暗示旋转动力学，但仍按质点能力处理，质点近似可能不完全适用",
            triggered_by="检测到旋转/角速度相关关键词",
        ))

    # 警告 2：文本中暗示复杂场变化，但仍按简单背景作用处理
    if re.search(r"变化的场|non[\s-]*uniform\s*field|非均匀|varying\s*gravity|变化重力", _source_text):
        validity_warnings.append(ValidityWarning(
            warning_key="complex_field_in_simple_background",
            description="文本暗示非均匀或变化的场，但当前仍按均匀背景作用处理",
            triggered_by="检测到非均匀场/变化重力相关关键词",
        ))

    return ParticleMotionCapabilitySpec(
        applies_to_entities=entity_ids,
        target_mapping={t.get("name", ""): t for t in problem_spec.targets_of_interest},
        rule_extraction_inputs=problem_spec.rule_extraction_inputs,
        rule_execution_inputs=problem_spec.rule_execution_inputs,
        candidate_rules=["constant_gravity"],
        missing_inputs=missing_runtime,
        trigger_requirements=[],
        initial_state_requirements=initial_state_requirements,
        background_interaction_hints=background_hints,
        applicability_conditions=applicability_conditions,
        applicability_eval=applicability_eval,
        assumptions=assumptions,
        validity_limits=validity_limits,
        validity_warnings=validity_warnings,
        required_entry_inputs=_REQUIRED_ENTRY_INPUTS,
        missing_entry_inputs=missing_entry,
    )
