"""
PersistentRuleExecutor — 持续规则执行器最小接口 v0.1.

持续规则在每个演化步中均被调用，根据当前状态和规则输入
计算状态推进所需的贡献（state_delta）或直接返回更新后的状态。

最小接口规范
------------
- rule_name: 规则标识
- required_inputs: 规则执行所需的输入字段名列表
- apply(current_state, inputs) -> Dict  (state_delta 或 updated_state)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class PersistentRuleExecutor(ABC):
    """
    持续规则执行器抽象基类。

    子类须实现 :meth:`apply`，返回 state_delta 或 updated_state 字典。
    """

    #: 规则标识名称，子类须覆盖
    rule_name: str = "persistent_rule"

    #: 规则执行所需的输入字段名列表，子类须覆盖
    required_inputs: List[str] = []

    @abstractmethod
    def apply(self, current_state: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        根据当前状态和规则输入计算状态推进贡献。

        Parameters
        ----------
        current_state:
            当前实体状态字典（至少含 required_inputs 中声明的字段）。
        inputs:
            规则执行输入（来自 ExecutionPlan.rule_execution_inputs）。

        Returns
        -------
        Dict[str, Any]
            state_delta（增量更新字典）或 updated_state（完整状态字典）。
        """
