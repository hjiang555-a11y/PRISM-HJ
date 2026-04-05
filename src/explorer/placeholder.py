"""
探索模式占位模块 — src/explorer/placeholder.py

当前状态：仅做预留，不实现任何探索逻辑。

未来可在此基础上实现：
- 参数空间漫游（grid / random / bayesian）
- 批量调度模拟（多参数组合）
- 有趣性度量（极值检测、相变识别、反直觉结果、能量/动量偏差）
- 场景组合与序列（将多个 PSDL 场景串联为探索路径）
- 与 LLM 联动生成可检验假设（让 LLM 提出假设，物理引擎验证）

设计约束：
- 不侵入 engine.py / translator.py 或主执行路径
- 只通过 main.py 的 --explore 开关激活
- base_psdl 和 exploration_config 来自主程序，当前可为 None 或占位值
"""

from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict


EXPLORER_RESERVED_MESSAGE = "探索模式已预留，尚未实现。"


class ExplorerMetadata(TypedDict):
    future_capabilities: list[str]


class ExplorerResult(TypedDict):
    """
    稳定的探索模式占位结果协议。

    当前仅表达“探索模式已预留”，但结构本身可被 CLI 或未来 API 直接消费，
    以便后续替换为真实 explorer 实现时避免上层接口再次变动。
    """

    mode: Literal["explore"]
    status: Literal["reserved"]
    message: str
    base_psdl: Optional[Any]
    exploration_config: Optional[dict[str, Any]]
    results: list[Any]
    metadata: ExplorerMetadata


def explore(
    base_psdl: Optional[Any],
    exploration_config: Optional[dict[str, Any]],
) -> ExplorerResult:
    """
    占位探索接口。

    未来将用于：
    - 参数空间漫游（grid/random/bayesian）
    - 批量调度模拟
    - 有趣性度量（极值、相变、反直觉、能量偏差）
    - 场景串联探索
    - 与 LLM 联动生成可检验假设

    当前不实现探索逻辑，只返回/输出保留提示。
    该返回值是一个稳定的占位协议，用于为未来真实 explorer 的返回格式
    奠定基础，并让 CLI/上层调用方优先依赖结构化结果而非 stdout 文本。

    Parameters
    ----------
    base_psdl:
        基础 PSDL 场景文档（未来将作为探索的起点）。
        当前传入 None 或来自 --question 的最小占位值均可。
    exploration_config:
        探索配置（未来将包含参数范围、策略、度量选择等）。
        当前传入 None 或 PSDL.world.exploration_config 均可。

    Returns
    -------
    ExplorerResult
        结构化占位结果；当前 results 为空列表，未来可在保持外层结构稳定的
        前提下逐步填充真实探索结果。
    """
    result: ExplorerResult = {
        "mode": "explore",
        "status": "reserved",
        "message": EXPLORER_RESERVED_MESSAGE,
        "base_psdl": base_psdl,
        "exploration_config": exploration_config,
        "results": [],
        "metadata": {
            "future_capabilities": [
                "parameter_space_search",
                "interestingness_metrics",
                "scenario_composition",
                "llm_hypothesis_generation",
            ]
        },
    }
    print(EXPLORER_RESERVED_MESSAGE)
    return result
