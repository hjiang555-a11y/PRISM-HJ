"""
PRISM-HJ — Natural Language → Physics Simulation

Entry point for the command-line interface.

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

from src.llm.translator import generate_answer, text_to_psdl
from src.physics.legacy.dispatcher import dispatch_with_validation

# New pipeline imports
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
# New pipeline
# ---------------------------------------------------------------------------

def _can_use_new_pipeline(question: str) -> bool:
    """Check if the question can be handled by the new execution pipeline."""
    spec = extract_problem_semantics(question)
    # New pipeline is viable when entities were extracted and unresolved items
    # have been cleared (i.e. enrichment succeeded).
    return bool(spec.entities) and not spec.unresolved_items


def run_new_pipeline(question: str) -> dict | None:
    """
    Run the new execution pipeline.

    Returns a dict with keys ``target_results``, ``trigger_records``,
    ``execution_notes`` on success, or ``None`` if the pipeline cannot
    handle this question.
    """
    try:
        # Step 1: Extract problem semantics
        spec = extract_problem_semantics(question)

        if not spec.entities:
            logger.info("新管线：实体为空，回退到旧管线")
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
            logger.info("新管线：无通过准入的能力，回退到旧管线")
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
            "新管线执行完成：admitted=%s, targets=%s",
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
        logger.warning("新管线异常，回退到旧管线: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Core pipeline (dual-route: new → old fallback)
# ---------------------------------------------------------------------------

def run_pipeline(question: str) -> None:
    """Execute the full NL → Physics → Result pipeline (dual-route)."""
    print(f"\n{'=' * 60}")
    print(f"问题: {question}")
    print("=" * 60)

    # --- Try new pipeline first ---
    new_result = run_new_pipeline(question)

    if new_result is not None:
        _print_new_pipeline_result(question, new_result)
        return

    # --- Fallback: old pipeline ---
    logger.info("使用旧管线 (dispatcher → analytic/engine)")
    _run_legacy_pipeline(question)


def _print_new_pipeline_result(question: str, result: dict) -> None:
    """Print results from the new pipeline."""
    print("\n[Pipeline: new execution pipeline]")

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

    # Generate natural language answer (completing pipeline parity with legacy route)
    try:
        logger.info("Generating natural language answer (new pipeline)...")
        answer = generate_answer(question, final_states)
        print(f"\nAnswer:\n{answer}\n")
    except Exception as exc:
        logger.warning("自然语言答案生成失败（不影响物理结果）: %s", exc)


def _run_legacy_pipeline(question: str) -> None:
    """Run the legacy (old) pipeline."""
    # Step 1: Translate natural language to PSDL (template-first, then LLM)
    logger.info("Translating natural language to PSDL...")
    psdl = text_to_psdl(question)

    logger.info("PSDL (JSON):\n%s", psdl.pretty_print())

    # Step 2: Dispatch to appropriate solver + run validation
    logger.info("Running physics simulation...")
    result = dispatch_with_validation(psdl)
    final_states = result["states"]
    solver_used = result["solver_used"]
    validation_results = result["validation_results"]

    logger.info(
        "Solver: %s | Final states: %s",
        solver_used,
        json.dumps(final_states, ensure_ascii=False),
    )

    # Print solver and validation summary (always visible to CLI user)
    print(f"\n[Pipeline: legacy (Solver: {solver_used})]")
    if validation_results:
        passed = sum(1 for r in validation_results if r["passed"])
        total = len(validation_results)
        print(f"[Validation: {passed}/{total} passed]")
        for r in validation_results:
            status = "PASS" if r["passed"] else "FAIL"
            print(f"  {r['target']}: {status} — {r['message']}")
    else:
        print("[Validation: no targets defined]")

    # Step 3: Generate natural language answer
    logger.info("Generating natural language answer...")
    answer = generate_answer(question, final_states)

    print(f"\nAnswer:\n{answer}\n")


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
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Force use of the legacy pipeline (skip new pipeline attempt).",
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
            if args.legacy:
                _run_legacy_pipeline(question)
            else:
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
