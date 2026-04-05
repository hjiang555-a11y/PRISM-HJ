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
from src.physics.dispatcher import dispatch_with_validation

# Explorer module is imported lazily inside run_explore() to keep the
# deterministic simulation path completely free of exploration code.
# See src/explorer/placeholder.py for future extension notes.

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Explore pipeline (placeholder — does not enter deterministic main path)
# ---------------------------------------------------------------------------

def run_explore(question: str) -> None:
    """
    Enter the exploration placeholder path.

    当前行为：调用 explore() 占位函数并输出提示，然后返回，不进入
    deterministic simulate_psdl() / dispatch_with_validation() 主路径。

    未来演进方向：
    - 从 question 构建 base_psdl（模板或 LLM 生成）
    - 从 world.exploration_config 或命令行参数构建 exploration_config
    - 调用真正的参数空间漫游、有趣性度量、场景串联等逻辑
    - 将探索结果汇总后输出或存储
    """
    # Import lazily to keep the deterministic main path clean.
    from src.explorer import explore

    print(f"\n{'=' * 60}")
    print(f"探索模式 — 问题: {question}")
    print("=" * 60)

    # base_psdl: 未来将由 text_to_psdl(question) 生成；
    # exploration_config: 未来将从 PSDL.world.exploration_config 或额外参数读取。
    # 当前均传入 None 作为占位值。
    explore(base_psdl=None, exploration_config=None)


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def run_pipeline(question: str) -> None:
    """Execute the full NL → PSDL → Simulation → Validation → NL pipeline."""
    print(f"\n{'=' * 60}")
    print(f"问题: {question}")
    print("=" * 60)

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
    print(f"\n[Solver: {solver_used}]")
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
            '  python main.py --explore --question "任何问题"  # 进入探索占位路径\n'
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
        "--explore",
        action="store_true",
        default=False,
        help=(
            "进入探索模式（当前为预留占位，尚未实现）。"
            "激活时不进入确定性模拟主路径。"
            "需配合 --question 使用。"
        ),
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

    # --explore: route to the exploration placeholder path (no deterministic simulation)
    if args.explore:
        question = args.question or ""
        run_explore(question)
        return 0

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
