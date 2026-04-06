"""
LocalRuleExecutor — 局部规则执行器最小接口 v0.1.

局部规则在触发条件满足时被激活，根据触发前状态和规则输入
更新相关实体的状态。

最小接口规范
------------
- rule_name: 规则标识
- trigger_condition_type: 触发条件类型（如 "contact"）
- required_inputs: 规则执行所需的输入字段名列表
- apply(pre_trigger_state, inputs) -> Dict  (updated_state)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class LocalRuleExecutor(ABC):
    """
    局部规则执行器抽象基类。

    子类须实现 :meth:`apply`，在触发条件满足时更新状态。
    """

    #: 规则标识名称，子类须覆盖
    rule_name: str = "local_rule"

    #: 触发条件类型（如 "contact"、"threshold"），子类须覆盖
    trigger_condition_type: str = "unknown"

    #: 规则执行所需的输入字段名列表，子类须覆盖
    required_inputs: List[str] = []

    @abstractmethod
    def apply(
        self,
        pre_trigger_state: Dict[str, Any],
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        在触发条件满足时，根据触发前状态和规则输入更新状态。

        Parameters
        ----------
        pre_trigger_state:
            触发前的实体状态字典（通常含多个实体，键为实体 ID）。
        inputs:
            规则执行输入（来自 ExecutionPlan.rule_execution_inputs）。

        Returns
        -------
        Dict[str, Any]
            触发后更新的状态字典（通常含多个实体，键为实体 ID）。
        """
