"""
问题语义提取流水线 v0.1.

extract_problem_semantics(input_text) -> ProblemSemanticSpec

当前为最小骨架实现：
- 输出结构化字段骨架（候选化）
- 实体、条件、目标量提取均标记为 unresolved（待后续提取器填充）
- 候选能力预设 particle_motion 和 contact_interaction
- 不依赖 LLM，可独立运行
"""

from __future__ import annotations

from src.problem_semantic.models import ProblemSemanticSpec


def extract_problem_semantics(input_text: str) -> ProblemSemanticSpec:
    """
    从输入文本构造 ProblemSemanticSpec。

    当前最小实现返回候选化骨架，所有提取字段标记为待填充。
    上层调用者可在此基础上接入 LLM 提取器或规则提取器进行填充。

    Parameters
    ----------
    input_text:
        原始输入问题文本。

    Returns
    -------
    ProblemSemanticSpec
        候选化的问题语义规格，未决项已记录在 ``unresolved_items`` 中。
    """
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
    )
