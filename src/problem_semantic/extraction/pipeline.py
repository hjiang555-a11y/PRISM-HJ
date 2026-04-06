"""
问题语义提取流水线 v0.2.

extract_problem_semantics(input_text) -> ProblemSemanticSpec

当前为最小骨架实现：
- 输出结构化字段骨架（候选化）
- 实体、条件、目标量提取均标记为 unresolved（待后续提取器填充）
- 候选能力预设 particle_motion 和 contact_interaction
- 不依赖 LLM，可独立运行

P0 第四步更新：新增轻量规则法提取 admission hints，填充
entity_model_hints / interaction_hints / assumption_hints / query_hints，
为 capability mapper 提供更结构化的上游语义来源。

v0.2 更新：对已知场景类型（free_fall / projectile / collision），利用
regex extractors + classify_scenario 填充 entities、explicit_conditions、
targets_of_interest 和 rule_execution_inputs，实现 fully populated spec。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from src.problem_semantic.models import ProblemSemanticSpec

logger = logging.getLogger(__name__)

_DEFAULT_GRAVITY: list[float] = [0, 0, -9.8]
_DEFAULT_DT: float = 0.01


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
        r"质点|particle|point\s*mass|小球|球|ball|stone|object|particle\s*like"
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
# Enrichment: populate spec fields from regex extractors
# ---------------------------------------------------------------------------

def _enrich_from_extractors(spec: ProblemSemanticSpec) -> ProblemSemanticSpec:
    """
    Best-effort enrichment of *spec* using regex extractors and scenario
    classification.

    If the scenario is recognised and numeric parameters can be extracted,
    populates ``entities``, ``explicit_conditions``, ``targets_of_interest``,
    ``rule_execution_inputs``, and ``candidate_capabilities``.  Otherwise
    the spec is returned unchanged (skeleton mode).
    """
    from src.llm.translator import classify_scenario
    from src.problem_semantic.extraction.extractors import (
        extract_collision_params,
        extract_free_fall_params,
        extract_projectile_params,
    )

    scenario: Optional[str] = classify_scenario(spec.source_input)
    if scenario is None:
        return spec

    # ----- free_fall -----
    if scenario == "free_fall":
        params = extract_free_fall_params(spec.source_input)
        if params is None:
            return spec

        h = params["height"]
        dur = params["duration"]
        mass = params["mass"]
        v0z = params["v0z"]

        spec.entities = [
            {
                "name": "ball",
                "mass": mass,
                "initial_position": [0, 0, h],
                "initial_velocity": [0, 0, v0z],
            },
        ]

        # Use standardised condition names that capability mappers recognise
        # (mappers check for keywords: "height"/"position", "velocity"/"v0",
        #  "mass"/"m" in the condition name set)
        spec.explicit_conditions = [
            {"name": "height", "value": h, "entity": "ball"},
            {"name": "mass", "value": mass, "entity": "ball"},
            {"name": "initial_velocity", "value": [0, 0, v0z], "entity": "ball"},
        ]

        spec.targets_of_interest = [
            {"name": "final_z", "description": "落体最终高度"},
            {"name": "final_vz", "description": "落体最终速度(z)"},
        ]

        spec.rule_execution_inputs = {
            "scenario_type": "free_fall",
            "gravity_vector": list(_DEFAULT_GRAVITY),
            "dt": _DEFAULT_DT,
            "steps": round(dur / _DEFAULT_DT),
        }

        spec.candidate_capabilities = ["particle_motion"]

    # ----- projectile -----
    elif scenario == "projectile":
        params = extract_projectile_params(spec.source_input)
        if params is None:
            return spec

        h = params["height"]
        v0x = params["v0x"]
        dur = params["duration"]
        mass = params["mass"]

        spec.entities = [
            {
                "name": "projectile",
                "mass": mass,
                "initial_position": [0, 0, h],
                "initial_velocity": [v0x, 0, 0],
            },
        ]

        spec.explicit_conditions = [
            {"name": "height", "value": h, "entity": "projectile"},
            {"name": "velocity", "value": [v0x, 0, 0], "entity": "projectile"},
            {"name": "mass", "value": mass, "entity": "projectile"},
        ]

        spec.targets_of_interest = [
            {"name": "final_x", "description": "抛体最终水平位置"},
            {"name": "final_z", "description": "抛体最终高度"},
            {"name": "final_vz", "description": "抛体最终竖直速度"},
        ]

        spec.rule_execution_inputs = {
            "scenario_type": "projectile",
            "gravity_vector": list(_DEFAULT_GRAVITY),
            "dt": _DEFAULT_DT,
            "steps": round(dur / _DEFAULT_DT),
        }

        spec.candidate_capabilities = ["particle_motion"]

    # ----- collision -----
    elif scenario == "collision":
        params = extract_collision_params(spec.source_input)
        if params is None:
            return spec

        m1 = params["m1"]
        m2 = params["m2"]
        v1x = params["v1x"]
        v2x = params["v2x"]
        ctype = params["collision_type"]

        spec.entities = [
            {
                "name": "ball_a",
                "mass": m1,
                "initial_position": [0, 0, 0],
                "initial_velocity": [v1x, 0, 0],
            },
            {
                "name": "ball_b",
                "mass": m2,
                "initial_position": [1, 0, 0],
                "initial_velocity": [v2x, 0, 0],
            },
        ]

        spec.explicit_conditions = [
            {"name": "mass", "value": m1, "entity": "ball_a"},
            {"name": "velocity", "value": v1x, "entity": "ball_a"},
            {"name": "mass", "value": m2, "entity": "ball_b"},
            {"name": "velocity", "value": v2x, "entity": "ball_b"},
        ]

        spec.targets_of_interest = [
            {"name": "final_v1x", "description": "碰后物体A速度(x)"},
            {"name": "final_v2x", "description": "碰后物体B速度(x)"},
        ]

        spec.rule_execution_inputs = {
            "scenario_type": "collision",
            "restitution": 1.0 if ctype == "elastic" else 0.0,
            "contact_normal": [1, 0, 0],
            "dt": _DEFAULT_DT,
            "steps": 100,
        }

        spec.candidate_capabilities = ["particle_motion", "contact_interaction"]

    else:
        return spec

    # Store scenario_type in rule_extraction_inputs
    spec.rule_extraction_inputs["scenario_type"] = scenario

    # Remove resolved unresolved_items
    _resolved = {
        "entity_extraction_pending",
        "targets_of_interest_pending",
        "explicit_conditions_pending",
        "rule_execution_inputs_pending",
    }
    spec.unresolved_items = [
        item for item in spec.unresolved_items if item not in _resolved
    ]

    return spec


# ---------------------------------------------------------------------------
# Public pipeline entry point
# ---------------------------------------------------------------------------

def extract_problem_semantics(input_text: str) -> ProblemSemanticSpec:
    """
    从输入文本构造 ProblemSemanticSpec。

    对已知场景类型（free_fall / projectile / collision），利用 regex
    extractors 和 classify_scenario 填充 entities、explicit_conditions、
    targets_of_interest 和 rule_execution_inputs。未识别场景时返回
    候选化骨架（skeleton mode）。

    Parameters
    ----------
    input_text:
        原始输入问题文本。

    Returns
    -------
    ProblemSemanticSpec
        尽力填充的问题语义规格。未决项记录在 ``unresolved_items`` 中；
        admission hints 字段已由轻量规则法尽力填充。
    """
    entity_model_hints = _extract_entity_model_hints(input_text)
    interaction_hints = _extract_interaction_hints(input_text)
    assumption_hints = _extract_assumption_hints(input_text)
    query_hints = _extract_query_hints(input_text)

    spec = ProblemSemanticSpec(
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

    spec = _enrich_from_extractors(spec)

    return spec
