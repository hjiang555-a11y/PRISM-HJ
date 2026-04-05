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

from typing import Any, Optional


def explore(
    base_psdl: Optional[Any],
    exploration_config: Optional[dict],
) -> list:
    """
    占位探索接口。

    未来将用于：
    - 参数空间漫游（grid/random/bayesian）
    - 批量调度模拟
    - 有趣性度量（极值、相变、反直觉、能量偏差）
    - 场景串联探索
    - 与 LLM 联动生成可检验假设

    当前不实现探索逻辑，只返回/输出保留提示。

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
    list
        空列表（占位返回值，未来将返回探索结果集合）。
    """
    print("探索模式已预留，尚未实现。")
    return []
