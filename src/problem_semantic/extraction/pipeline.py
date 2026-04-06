"""
问题语义提取流水线 v0.1.

extract_problem_semantics(input_text) -> ProblemSemanticSpec

当前为最小骨架实现：
- 输出结构化字段骨架（候选化）
- 实体、条件、目标量提取均标记为 unresolved（待后续提取器填充）
- 候选能力预设 particle_motion 和 contact_interaction
- 不依赖 LLM，可独立运行

P0 第四步更新：新增轻量规则法提取 admission hints，填充
entity_model_hints / interaction_hints / assumption_hints / query_hints，
为 capability mapper 提供更结构化的上游语义来源。
"""

from __future__ import annotations

import re

from src.problem_semantic.models import ProblemSemanticSpec


# ---------------------------------------------------------------------------
# Admission hints 提取：轻量规则法（regex / keyword pattern matching）
# ---------------------------------------------------------------------------

def _extract_entity_model_hints(text: str) -> list[str]:
    """
    从文本中推断实体建模方式。

    返回值示例：``["point_mass"]``、``["rigid_body"]``。
    当无明确线索时返回空列表（由 mapper 自行决定 fallback）。
    """
    lower = text.lower()
    hints: list[str] = []

    # 刚体线索（优先于质点；包含旋转动力学相关关键词）
    _rigid_body_pattern = (
        r"刚体|rigid\s*body|转动|旋转|rotation|moment\s*of\s*inertia"
        r"|angular|转动惯量|角速度|angular\s*velocity"
    )
    if re.search(_rigid_body_pattern, lower):
        hints.append("rigid_body")
    # 质点线索（含球、石、物体等通用词且无刚体旋转线索）
    elif re.search(
        r"质点|particle|point\s*mass|小球|ball|stone|object|particle\s*like"
        r"|物体|box|block|物块|小物",
        lower,
    ):
        hints.append("point_mass")

    return hints


def _extract_interaction_hints(text: str) -> list[str]:
    """
    从文本中推断物理交互类型。

    返回值示例：``["gravity_present", "collision_possible"]``。
    """
    lower = text.lower()
    hints: list[str] = []

    # 重力 / 自由落体 / 竖直运动
    if re.search(
        r"重力|gravity|自由落体|free\s*fall|落地|落下|下落|抛出|抛体|projectile"
        r"|竖直|vertical|height|高度|drops?\b|falls?\b",
        lower,
    ):
        hints.append("gravity_present")

    # 碰撞 / 冲击
    if re.search(
        r"碰撞|collision|碰|撞|collide|impact|弹性碰|非弹性|inelastic|elastic",
        lower,
    ):
        hints.append("collision_possible")

    # 接触 / 摩擦（但非碰撞）
    if re.search(r"接触|contact|摩擦|friction|滑动|slide|摩", lower):
        hints.append("contact_possible")

    # 场（电场、磁场）
    if re.search(r"电场|磁场|field|electric|magnetic", lower):
        hints.append("field_present")

    return hints


def _extract_assumption_hints(text: str) -> list[str]:
    """
    从文本中推断物理假设。

    返回值示例：``["ignore_air_resistance", "elastic_collision"]``。
    无明确假设描述时返回空列表（由 mapper 使用原型默认 fallback）。
    """
    lower = text.lower()
    hints: list[str] = []

    # 忽略空气阻力
    if re.search(
        r"忽略空气阻力|不计空气阻力|no\s*air\s*resistance|ignore\s*air"
        r"|without\s*air\s*resistance|neglect\s*air",
        lower,
    ):
        hints.append("ignore_air_resistance")

    # 弹性碰撞
    if re.search(r"弹性碰撞|elastic\s*collision|完全弹性", lower):
        hints.append("elastic_collision")

    # 非弹性碰撞
    if re.search(
        r"非弹性|完全非弹性|inelastic|perfectly\s*inelastic", lower
    ):
        hints.append("inelastic_collision")

    # 光滑表面（无摩擦）
    if re.search(r"光滑|smooth|无摩擦|frictionless", lower):
        hints.append("smooth_surface")

    # 恒定重力（显式提及 g 值，或使用标准 g 值表达）
    if re.search(r"g\s*=\s*\d+(?:\.\d+)?|重力加速度恒定|constant\s*g|constant\s*gravity", lower):
        hints.append("constant_g")

    return hints


def _extract_query_hints(text: str) -> list[str]:
    """
    从文本中推断目标查询类型。

    返回值示例：``["ask_state_at_time", "ask_collision_outcome"]``。
    """
    lower = text.lower()
    hints: list[str] = []

    # 特定时刻状态（含"X秒后"、"t=X"、"after X s"等）
    if re.search(
        r"\d+\s*秒后|经过\s*\d+\s*秒|after\s+\d+\s*s|t\s*=\s*\d+|at\s+t\s*=", lower
    ):
        hints.append("ask_state_at_time")

    # 碰撞结果（碰后速度/位移/动能等）
    if re.search(
        r"碰后|碰撞后|collision\s*outcome|after\s*(?:the\s*)?collision"
        r"|velocity\s*after|speed\s*after|post[\s-]*collision",
        lower,
    ):
        hints.append("ask_collision_outcome")

    # 落地时间 / 冲击时间
    if re.search(
        r"落地时间|何时落地|落地|hits?\s*the\s*ground|time\s*to\s*(?:hit|land|reach)"
        r"|impact\s*time|when\s*does\s*it\s*(?:hit|land)",
        lower,
    ):
        hints.append("ask_impact_time")

    # 最终状态（含"最终"、"final"、"碰后"但无特定时刻）
    if re.search(r"最终|final\s+(?:state|velocity|position|speed)|结果|outcome", lower):
        if "ask_collision_outcome" not in hints:
            hints.append("ask_final_state")

    return hints


# ---------------------------------------------------------------------------
# Public pipeline entry point
# ---------------------------------------------------------------------------

def extract_problem_semantics(input_text: str) -> ProblemSemanticSpec:
    """
    从输入文本构造 ProblemSemanticSpec。

    当前最小实现返回候选化骨架，所有提取字段标记为待填充。
    上层调用者可在此基础上接入 LLM 提取器或规则提取器进行填充。

    P0 第四步：新增轻量规则法提取 admission hints，填充
    entity_model_hints / interaction_hints / assumption_hints / query_hints。

    Parameters
    ----------
    input_text:
        原始输入问题文本。

    Returns
    -------
    ProblemSemanticSpec
        候选化的问题语义规格，未决项已记录在 ``unresolved_items`` 中；
        admission hints 字段已由轻量规则法尽力填充。
    """
    entity_model_hints = _extract_entity_model_hints(input_text)
    interaction_hints = _extract_interaction_hints(input_text)
    assumption_hints = _extract_assumption_hints(input_text)
    query_hints = _extract_query_hints(input_text)

    return ProblemSemanticSpec(
        source_input=input_text,
        entities=[],
        targets_of_interest=[],
        explicit_conditions=[],
        candidate_domains=["mechanics"],
        candidate_capabilities=["particle_motion", "contact_interaction"],
        rule_extraction_inputs={
            "raw_text": input_text,
        },
        rule_execution_inputs={},
        unresolved_items=[
            "entity_extraction_pending",
            "targets_of_interest_pending",
            "explicit_conditions_pending",
            "rule_execution_inputs_pending",
        ],
        entity_model_hints=entity_model_hints,
        interaction_hints=interaction_hints,
        assumption_hints=assumption_hints,
        query_hints=query_hints,
    )
