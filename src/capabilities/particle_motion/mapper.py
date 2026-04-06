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
    # A. 语义层：如有实体初始状态要求则认为已知
    _has_position_from_semantics = bool(initial_state_requirements)
    # B. 显式条件关键词
    _position_keywords = {"position", "height", "x", "y", "z", "initial_position", "x0", "y0", "z0"}
    _has_position_from_conditions = bool(_position_keywords & condition_names)
    # 汇总判断
    if not _has_position_from_semantics and not _has_position_from_conditions:
        missing_entry.append("initial_position_per_entity")

    # --- 初始速度 ---
    # A. 语义层：当前语义层尚无直接"速度已知"的结构化 hint，留待后续扩展
    _has_velocity_from_semantics = False
    # B. 显式条件关键词
    _velocity_keywords = {"velocity", "speed", "v", "vx", "vy", "vz", "initial_velocity", "v0", "v0x", "v0y"}
    _has_velocity_from_conditions = bool(_velocity_keywords & condition_names)
    # 汇总判断
    if not _has_velocity_from_semantics and not _has_velocity_from_conditions:
        missing_entry.append("initial_velocity_per_entity")

    # --- 质量 ---
    # A. 语义层：当前无直接质量 hint（质量信息主要来自数值条件）
    _has_mass_from_semantics = False
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
    ]

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
        assumptions=assumptions,
        validity_limits=validity_limits,
        required_entry_inputs=_REQUIRED_ENTRY_INPUTS,
        missing_entry_inputs=missing_entry,
    )
