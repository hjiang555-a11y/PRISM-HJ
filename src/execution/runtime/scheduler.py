"""
Scheduler — 执行计划驱动下的状态演化控制入口 v0.1.

根据 ExecutionPlan 驱动以下最小闭环：
1. 初始化 active persistent rules（背景重力等）
2. 逐步演化状态
3. 每步调用 TriggerEngine 检查局部触发
4. 触发时激活 LocalRuleExecutor
5. 演化结束后调用 ResultAssembler

当前不要求
----------
- 高级调度策略
- 并发执行
- 多 capability 深度耦合优化
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.execution.assembly.result_assembler import ExecutionResult, ResultAssembler
from src.execution.rules.registry import DEFAULT_RULE_REGISTRY, RuleRegistry
from src.execution.runtime.trigger_engine import TriggerEngine
from src.execution.state.state_set import StateSet
from src.planning.execution_plan.models import ExecutionPlan

logger = logging.getLogger(__name__)


class Scheduler:
    """
    状态演化调度器。

    将 ExecutionPlan 转化为时间步循环，驱动持续规则、
    触发检测和局部规则执行，最终组装结果。

    Parameters
    ----------
    dt:
        时间步长（秒）。若 ExecutionPlan 的 state_set_plan 中有全局 dt，
        则优先使用该值；否则使用此默认值。
    steps:
        最大演化步数。
    contact_threshold:
        接触触发阈值（米），传递给 TriggerEngine。
    rule_registry:
        规则注册表，默认使用内置的 DEFAULT_RULE_REGISTRY。
        传入自定义注册表可在不修改核心文件的情况下扩展规则。
    """

    def __init__(
        self,
        dt: float = 0.01,
        steps: int = 100,
        contact_threshold: float = 0.5,
        rule_registry: Optional[RuleRegistry] = None,
    ) -> None:
        self.dt = dt
        self.steps = steps
        self._trigger_engine = TriggerEngine(contact_threshold=contact_threshold)
        self._assembler = ResultAssembler()
        self._registry = rule_registry if rule_registry is not None else DEFAULT_RULE_REGISTRY

    def run(
        self,
        execution_plan: ExecutionPlan,
        state_set: StateSet,
        gravity_vector: Optional[List[float]] = None,
    ) -> ExecutionResult:
        """
        根据执行计划驱动状态演化并返回结果。

        Parameters
        ----------
        execution_plan:
            由 build_execution_plan() 构造的执行计划。
        state_set:
            已初始化实体状态的运行时状态集合。
        gravity_vector:
            重力向量（可选，默认 [0, 0, -9.8]）。若提供则覆盖规则输入
            中的重力设置。

        Returns
        -------
        ExecutionResult
            包含目标量结果和触发记录的执行结果。

        Admission Hints 消费逻辑（P1 新增）
        ------------------------------------
        Scheduler 根据 execution_plan.admission_hints 调整规则激活：

        1. interaction_hints:
           - 无 ``"gravity_present"`` → 跳过 constant_gravity 规则
           - 无 ``"collision_possible"`` → 跳过 impulsive_collision 规则
        2. assumption_hints:
           - ``"inelastic_collision"`` → 设置 restitution=0.0
           - ``"elastic_collision"``  → 设置 restitution=1.0
        """
        grav = gravity_vector if gravity_vector is not None else [0.0, 0.0, -9.8]

        # --- P1: 解析 admission hints ---
        hints = execution_plan.admission_hints
        interaction_hints: List[str] = hints.get("interaction_hints", [])
        assumption_hints: List[str] = hints.get("assumption_hints", [])

        # 调试日志：记录 entity_model_hints 和 query_hints（调试辅助）
        entity_model_hints: List[str] = hints.get("entity_model_hints", [])
        query_hints: List[str] = hints.get("query_hints", [])
        if entity_model_hints:
            logger.debug("admission hints - entity_model_hints: %s", entity_model_hints)
        if query_hints:
            logger.debug("admission hints - query_hints: %s", query_hints)

        # 判断规则是否应被激活（hints 为空时默认全部激活以保持后向兼容）
        _has_interaction_hints = bool(interaction_hints)
        _gravity_enabled = (
            not _has_interaction_hints or "gravity_present" in interaction_hints
        )
        _collision_enabled = (
            not _has_interaction_hints or "collision_possible" in interaction_hints
        )

        # 实例化持续规则执行器
        persistent_executors: List[tuple] = []  # (executor, applies_to, rule_inputs)
        for rule_entry in execution_plan.persistent_rule_plan:
            rule_name = rule_entry.get("rule_name", "")

            # P1: 根据 hints 过滤不需要的规则
            if rule_name == "constant_gravity" and not _gravity_enabled:
                logger.info("hints 过滤：跳过 constant_gravity（无 gravity_present hint）")
                continue

            executor_cls = self._registry.get_persistent(rule_name)
            if executor_cls is None:
                logger.warning("未知持续规则 '%s'，已跳过", rule_name)
                continue
            rule_inputs = dict(rule_entry.get("rule_execution_inputs", {}))
            rule_inputs.setdefault("gravity_vector", grav)
            rule_inputs.setdefault("dt", self.dt)
            persistent_executors.append(
                (executor_cls(), rule_entry.get("applies_to", []), rule_inputs)
            )

        # 实例化局部规则执行器
        local_executors: List[tuple] = []  # (executor, applies_to, rule_inputs)
        for rule_entry in execution_plan.local_rule_plan:
            rule_name = rule_entry.get("rule_name", "")

            # P1: 根据 hints 过滤不需要的规则
            if rule_name == "impulsive_collision" and not _collision_enabled:
                logger.info("hints 过滤：跳过 impulsive_collision（无 collision_possible hint）")
                continue

            executor_cls = self._registry.get_local(rule_name)
            if executor_cls is None:
                logger.warning("未知局部规则 '%s'，已跳过", rule_name)
                continue
            rule_inputs = dict(rule_entry.get("rule_execution_inputs", {}))

            # P1: 根据 assumption hints 调整碰撞恢复系数
            if rule_name == "impulsive_collision":
                if "inelastic_collision" in assumption_hints:
                    rule_inputs["restitution"] = 0.0
                    logger.info("hints 参数填充：restitution=0.0（inelastic_collision hint）")
                elif "elastic_collision" in assumption_hints:
                    rule_inputs["restitution"] = 1.0
                    logger.info("hints 参数填充：restitution=1.0（elastic_collision hint）")

            local_executors.append(
                (executor_cls(), rule_entry.get("applies_to", []), rule_inputs)
            )

        trigger_records: List[Dict[str, Any]] = []

        # 主演化循环
        for step in range(self.steps):
            # 1. 应用持续规则（更新速度 dv）
            self._apply_persistent_rules(state_set, persistent_executors)

            # 2. 推进位置：所有实体 pos += v * dt（与规则执行分离）
            self._advance_positions(state_set, self.dt)

            # 3. 检查触发条件
            triggered = self._trigger_engine.check_triggers(
                state_set, execution_plan.trigger_plan
            )

            # 4. 激活局部规则
            if triggered:
                for event in triggered:
                    self._apply_local_rules(state_set, local_executors, event, step)
                trigger_records.extend(triggered)

        # 4. 组装结果
        return self._assembler.assemble(
            state_set,
            execution_plan.assembly_plan,
            trigger_records=trigger_records,
        )

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    def _apply_persistent_rules(
        self,
        state_set: StateSet,
        executors: List[tuple],
    ) -> None:
        """对每个实体应用所有持续规则（仅更新速度）。"""
        for executor, applies_to, rule_inputs in executors:
            entities = applies_to if applies_to else state_set.all_entity_ids()
            for entity_id in entities:
                current = state_set.get_entity_state(entity_id)
                if current is None:
                    continue
                delta = executor.apply(current, rule_inputs)
                # 处理 velocity 增量（dv）
                dv = delta.get("dv")
                if dv is not None:
                    v = list(current.get("velocity", [0.0, 0.0, 0.0]))
                    v_new = [vi + dvi for vi, dvi in zip(v, dv)]
                    state_set.update_entity_state(entity_id, {"velocity": v_new})
                else:
                    # 直接合并 delta（complete state update）
                    state_set.update_entity_state(entity_id, delta)

    def _advance_positions(
        self,
        state_set: StateSet,
        dt: float,
    ) -> None:
        """推进所有实体位置：x_new = x + v * dt（独立于规则执行）。"""
        for entity_id in state_set.all_entity_ids():
            current = state_set.get_entity_state(entity_id)
            if current is None:
                continue
            pos = list(current.get("position", [0.0, 0.0, 0.0]))
            vel = list(current.get("velocity", [0.0, 0.0, 0.0]))
            pos_new = [pi + vi * dt for pi, vi in zip(pos, vel)]
            state_set.update_entity_state(entity_id, {"position": pos_new})

    def _apply_local_rules(
        self,
        state_set: StateSet,
        executors: List[tuple],
        event: Dict[str, Any],
        step: int,
    ) -> None:
        """激活与触发事件匹配的局部规则。"""
        entity_pair = event.get("entity_pair", [])
        trigger_type = event.get("trigger_type", "")

        for executor, _applies_to, rule_inputs in executors:
            if executor.trigger_condition_type != trigger_type:
                continue

            # 构造触发前状态（仅含相关实体）
            pre_state: Dict[str, Any] = {}
            for eid in entity_pair:
                s = state_set.get_entity_state(eid)
                if s is not None:
                    pre_state[eid] = s

            if len(pre_state) < 2:
                continue

            inputs = dict(rule_inputs)
            inputs["entity_pair"] = entity_pair

            updated = executor.apply(pre_state, inputs)
            for eid, new_state in updated.items():
                state_set.update_entity_state(eid, new_state)

            logger.debug(
                "局部规则 '%s' 在 step %d 触发，实体对 %s",
                executor.rule_name,
                step,
                entity_pair,
            )
