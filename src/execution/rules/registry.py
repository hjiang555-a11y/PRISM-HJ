"""
RuleRegistry — 可注入式规则注册表 v0.1.

将规则注册与 Scheduler 核心逻辑解耦，支持外部扩展而无需修改核心文件。

用法
----
使用默认注册表（内置规则已预注册）::

    from src.execution.rules.registry import DEFAULT_RULE_REGISTRY
    scheduler = Scheduler(rule_registry=DEFAULT_RULE_REGISTRY)

注册自定义规则::

    from src.execution.rules.registry import RuleRegistry
    from src.execution.rules.persistent.base import PersistentRuleExecutor

    class MyCustomRule(PersistentRuleExecutor):
        rule_name = "my_rule"
        ...

    registry = RuleRegistry()
    registry.register_persistent("my_rule", MyCustomRule)
    scheduler = Scheduler(rule_registry=registry)
"""

from __future__ import annotations

from typing import Dict, Optional, Type

from src.execution.rules.local.base import LocalRuleExecutor
from src.execution.rules.local.impulsive_collision import ImpulsiveCollisionRule
from src.execution.rules.persistent.base import PersistentRuleExecutor
from src.execution.rules.persistent.drag import LinearDragRule
from src.execution.rules.persistent.gravity import ConstantGravityRule


class RuleRegistry:
    """
    可注入式规则注册表。

    分别维护持续规则（PersistentRuleExecutor）和局部规则
    （LocalRuleExecutor）的名称 -> 类映射，供 Scheduler 在实例化时
    查找对应执行器类。

    Attributes
    ----------
    persistent:
        持续规则注册表（rule_name -> executor 类）。
    local:
        局部规则注册表（rule_name -> executor 类）。
    """

    def __init__(self) -> None:
        self.persistent: Dict[str, Type[PersistentRuleExecutor]] = {}
        self.local: Dict[str, Type[LocalRuleExecutor]] = {}

    def register_persistent(
        self,
        rule_name: str,
        executor_cls: Type[PersistentRuleExecutor],
    ) -> None:
        """
        注册一个持续规则执行器。

        Parameters
        ----------
        rule_name:
            规则名称（与 ExecutionPlan.persistent_rule_plan 中的 ``rule_name`` 对应）。
        executor_cls:
            实现 :class:`~src.execution.rules.persistent.base.PersistentRuleExecutor`
            接口的执行器类。
        """
        self.persistent[rule_name] = executor_cls

    def register_local(
        self,
        rule_name: str,
        executor_cls: Type[LocalRuleExecutor],
    ) -> None:
        """
        注册一个局部规则执行器。

        Parameters
        ----------
        rule_name:
            规则名称（与 ExecutionPlan.local_rule_plan 中的 ``rule_name`` 对应）。
        executor_cls:
            实现 :class:`~src.execution.rules.local.base.LocalRuleExecutor`
            接口的执行器类。
        """
        self.local[rule_name] = executor_cls

    def get_persistent(
        self, rule_name: str
    ) -> Optional[Type[PersistentRuleExecutor]]:
        """返回持续规则执行器类；未注册则返回 None。"""
        return self.persistent.get(rule_name)

    def get_local(
        self, rule_name: str
    ) -> Optional[Type[LocalRuleExecutor]]:
        """返回局部规则执行器类；未注册则返回 None。"""
        return self.local.get(rule_name)


# ---------------------------------------------------------------------------
# 默认注册表（内置规则预注册，向后兼容）
# ---------------------------------------------------------------------------

DEFAULT_RULE_REGISTRY = RuleRegistry()
DEFAULT_RULE_REGISTRY.register_persistent("constant_gravity", ConstantGravityRule)
DEFAULT_RULE_REGISTRY.register_persistent("linear_drag", LinearDragRule)
DEFAULT_RULE_REGISTRY.register_local("impulsive_collision", ImpulsiveCollisionRule)
