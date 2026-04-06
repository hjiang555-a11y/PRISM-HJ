"""
PRISM-HJ — Natural Language → Physics Simulation

Entry point for the command-line interface.

Pipeline
--------
The system uses a single unified pipeline:

1. **Problem Semantic Extraction** — ``extract_problem_semantics()``
2. **Capability Spec Building** — ``build_capability_specs()``
3. **Execution Plan Generation** — ``build_execution_plan()``
4. **State Initialisation & Scheduler** — ``Scheduler.run()``
5. **Natural Language Answer** — ``generate_answer()``

Usage
-----
Single question::

    python main.py --question "一个2kg的球从高度5米自由落体，1秒后位置和速度？"

Batch mode (one question per line)::

    python main.py --file examples/questions.txt
"""

from __future__ import annotations
import argparse
import json
import logging
import sys
from pathlib import Path

from src.llm.translator import generate_answer

# Pipeline imports
from src.capabilities.builder import build_capability_specs
from src.execution.assembly.result_assembler import ExecutionResult
from src.execution.runtime.scheduler import Scheduler
from src.execution.state.state_set import StateSet
from src.planning.execution_plan.builder import build_execution_plan
from src.problem_semantic.extraction.pipeline import extract_problem_semantics

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(question: str) -> None:
    """Execute the full NL → Physics → Result pipeline."""
    print(f"\n{'=' * 60}")
    print(f"问题: {question}")
    print("=" * 60)

    result = run_execution_pipeline(question)

    if result is not None:
        _print_pipeline_result(question, result)
    else:
        print("\n[Pipeline: 语义提取未能生成可执行计划，请检查问题描述。]")


def run_execution_pipeline(question: str) -> dict | None:
    """
    Run the execution pipeline.

    Returns a dict with keys ``target_results``, ``trigger_records``,
    ``execution_notes`` on success, or ``None`` if the pipeline cannot
    handle this question.
    """
    try:
        # Step 1: Extract problem semantics
        spec = extract_problem_semantics(question)

        if not spec.entities:
            logger.info("管线：实体为空，无法继续执行")
            return None

        # Step 2: Build capability specs
        cap_specs = build_capability_specs(spec)

        # Step 3: Build execution plan (with admission hints)
        admission_hints = {
            "interaction_hints": spec.interaction_hints,
            "assumption_hints": spec.assumption_hints,
            "entity_model_hints": spec.entity_model_hints,
            "query_hints": spec.query_hints,
        }
        plan = build_execution_plan(cap_specs, admission_hints=admission_hints)

        if not plan.admitted_capabilities:
            logger.info("管线：无通过准入的能力，无法执行")
            return None

        # Step 4: Initialize state set
        state_set = StateSet()
        for entity in spec.entities:
            eid = entity["name"]
            state_set.set_entity_state(eid, {
                "position": list(entity.get("initial_position", [0, 0, 0])),
                "velocity": list(entity.get("initial_velocity", [0, 0, 0])),
                "mass": float(entity.get("mass", 1.0)),
            })

        # Step 5: Configure and run scheduler
        dt = spec.rule_execution_inputs.get("dt", 0.01)
        steps = spec.rule_execution_inputs.get("steps", 100)
        gravity = spec.rule_execution_inputs.get("gravity_vector", [0, 0, -9.8])

        scheduler = Scheduler(dt=dt, steps=steps)
        result: ExecutionResult = scheduler.run(
            plan, state_set, gravity_vector=gravity,
        )

        logger.info(
            "管线执行完成：admitted=%s, targets=%s",
            plan.admitted_capabilities,
            list(result.target_results.keys()),
        )
        return {
            "target_results": result.target_results,
            "trigger_records": result.trigger_records,
            "execution_notes": result.execution_notes,
            "state_set": state_set,
        }

    except Exception as exc:
        logger.warning("管线异常: %s", exc)
        return None


def _print_pipeline_result(question: str, result: dict) -> None:
    """Print results from the execution pipeline."""
    print("\n[Pipeline: execution pipeline]")

    target_results = result["target_results"]
    if target_results:
        print(f"[Targets: {len(target_results)} resolved]")
        for name, value in target_results.items():
            if isinstance(value, dict):
                print(f"  {name}: {json.dumps(value, ensure_ascii=False)}")
            elif isinstance(value, (list, tuple)):
                formatted = [round(v, 4) if isinstance(v, float) else v for v in value]
                print(f"  {name}: {formatted}")
            elif isinstance(value, float):
                print(f"  {name}: {value:.4f}")
            else:
                print(f"  {name}: {value}")
    else:
        print("[Targets: none resolved]")

    trigger_records = result.get("trigger_records", [])
    if trigger_records:
        print(f"[Triggers: {len(trigger_records)} events]")

    notes = result.get("execution_notes", [])
    if notes:
        for note in notes:
            print(f"  [Note] {note}")

    # Build final states for NL answer generation
    state_set: StateSet = result["state_set"]
    final_states = []
    for eid in state_set.all_entity_ids():
        s = state_set.get_entity_state(eid)
        if s:
            final_states.append(s)

    print(f"\n[Final States: {json.dumps(final_states, ensure_ascii=False)}]")

    # Generate natural language answer
    try:
        logger.info("Generating natural language answer...")
        answer = generate_answer(question, final_states)
        print(f"\nAnswer:\n{answer}\n")
    except Exception as exc:
        logger.warning("自然语言答案生成失败（不影响物理结果）: %s", exc)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prism-hj",
        description="PRISM-HJ: Natural Language → Physics Simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python main.py --question "一个2kg的球从高度5米自由落体，1秒后位置和速度？"\n'
            "  python main.py --file examples/questions.txt\n"
        ),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--question", "-q",
        type=str,
        help="A single physics question in natural language.",
    )
    group.add_argument(
        "--file", "-f",
        type=Path,
        help="Path to a text file with one question per line (batch mode).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    questions: list[str] = []

    if args.question:
        questions = [args.question]
    elif args.file:
        path: Path = args.file
        if not path.exists():
            logger.error("文件不存在: %s", path)
            return 1
        questions = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        if not questions:
            logger.error("文件为空或所有行均为注释: %s", path)
            return 1

    exit_code = 0
    for question in questions:
        try:
            run_pipeline(question)
        except ConnectionError as exc:
            logger.error(
                "连接错误: %s\n\n"
                "请确保:\n"
                "  1. ollama serve 正在运行\n"
                "  2. 已执行 ollama pull deepseek-r1:32b\n",
                exc,
            )
            exit_code = 1
        except ValueError as exc:
            logger.error("数据错误: %s", exc)
            exit_code = 1
        except KeyboardInterrupt:
            print("\n用户中断。")
            return 130

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
