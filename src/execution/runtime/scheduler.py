"""
Scheduler — 执行计划驱动下的状态演化控制入口 v0.2.

根据 ExecutionPlan 驱动以下闭环：
1. 初始化 active persistent rules（背景重力、阻力等）
2. 逐步演化状态，支持自适应步长
3. 每步调用 TriggerEngine 检查局部触发
4. 触发时激活 LocalRuleExecutor
5. 记录状态历史快照（支持中间状态查询）
6. 演化结束后调用 ResultAssembler

P2 新增：Force Accumulator — 多规则 dv 叠加
P3 新增：自适应步长 + 中间状态历史
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from src.execution.assembly.result_assembler import ExecutionResult, ResultAssembler
from src.execution.rules.registry import DEFAULT_RULE_REGISTRY, RuleRegistry
from src.execution.runtime.trigger_engine import TriggerEngine
from src.execution.state.state_set import StateSet
from src.planning.execution_plan.models import ExecutionPlan
from src.schema.spatiotemporal import AdaptiveTimestepConfig

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
        adaptive_config: Optional[AdaptiveTimestepConfig] = None,
    ) -> None:
        self.dt = dt
        self.steps = steps
        self._trigger_engine = TriggerEngine(contact_threshold=contact_threshold)
        self._assembler = ResultAssembler()
        self._registry = rule_registry if rule_registry is not None else DEFAULT_RULE_REGISTRY
        self._adaptive = adaptive_config

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
        current_dt = self.dt
        t = 0.0  # 仿真时间

        # 记录初始快照
        state_set.record_snapshot(t)

        # 主演化循环
        for step in range(self.steps):
            # P3: 自适应步长 — 根据事件逼近程度调整 dt
            if self._adaptive is not None:
                current_dt = self._compute_adaptive_dt(
                    state_set, execution_plan.trigger_plan, current_dt
                )

            # 1. 应用持续规则（force accumulator 叠加所有 dv）
            self._apply_persistent_rules(state_set, persistent_executors, current_dt)

            # 2. 推进位置：所有实体 pos += v * dt（与规则执行分离）
            self._advance_positions(state_set, current_dt)

            t += current_dt

            # 记录每步快照
            state_set.record_snapshot(t)

            # 3. 检查触发条件
            triggered = self._trigger_engine.check_triggers(
                state_set, execution_plan.trigger_plan
            )

            # 4. 激活局部规则
            if triggered:
                for event in triggered:
                    self._apply_local_rules(state_set, local_executors, event, step)
                trigger_records.extend(triggered)

        # 5. 组装结果
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
        current_dt: Optional[float] = None,
    ) -> None:
        """
        对每个实体应用所有持续规则，叠加力/加速度贡献后一次性更新速度。

        Force Accumulator（P2）
        -----------------------
        多条持续规则可能同时为同一实体产生 dv 增量（如重力 + 阻力）。
        此方法先收集所有 dv 贡献，叠加后再统一写入 StateSet，
        避免前一规则更新后的状态影响后续规则的计算。
        """
        all_entities = state_set.all_entity_ids()

        # 1. 收集每个实体在本步所有规则产生的 dv 增量
        accumulated_dv: Dict[str, List[float]] = {}
        other_deltas: Dict[str, Dict[str, Any]] = {}

        for executor, applies_to, rule_inputs in executors:
            # P3: 自适应步长 — 将当前 dt 传递给规则
            effective_inputs = dict(rule_inputs)
            if current_dt is not None:
                effective_inputs["dt"] = current_dt

            entities = applies_to if applies_to else all_entities
            for entity_id in entities:
                current = state_set.get_entity_state(entity_id)
                if current is None:
                    continue
                delta = executor.apply(current, effective_inputs)
                dv = delta.get("dv")
                if dv is not None:
                    if entity_id not in accumulated_dv:
                        accumulated_dv[entity_id] = [0.0, 0.0, 0.0]
                    acc = accumulated_dv[entity_id]
                    for i, dvi in enumerate(dv):
                        acc[i] += dvi
                else:
                    # 非 dv 类 delta 直接合并
                    if entity_id not in other_deltas:
                        other_deltas[entity_id] = {}
                    other_deltas[entity_id].update(delta)

        # 2. 一次性应用叠加后的 dv
        for entity_id, total_dv in accumulated_dv.items():
            current = state_set.get_entity_state(entity_id)
            if current is None:
                continue
            v = list(current.get("velocity", [0.0, 0.0, 0.0]))
            v_new = [vi + dvi for vi, dvi in zip(v, total_dv)]
            state_set.update_entity_state(entity_id, {"velocity": v_new})

        # 3. 应用非 dv 类 delta
        for entity_id, delta in other_deltas.items():
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

    # ------------------------------------------------------------------
    # P3: 自适应步长
    # ------------------------------------------------------------------

    def _compute_adaptive_dt(
        self,
        state_set: StateSet,
        trigger_plan: List[Dict[str, Any]],
        current_dt: float,
    ) -> float:
        """
        根据实体与事件区域的距离自适应调整时间步长。

        逻辑
        ----
        - 遍历所有实体和触发条件，计算最小逼近距离
        - 距离 < proximity_threshold → 缩小步长
        - 距离 > proximity_threshold → 放大步长
        - 始终限制在 [dt_min, dt_max] 范围内
        """
        assert self._adaptive is not None
        cfg = self._adaptive

        min_proximity = float("inf")

        for condition in trigger_plan:
            trigger_type = condition.get("type", "")

            if trigger_type == "contact":
                pairs = condition.get("pairs", [])
                for pair in pairs:
                    if len(pair) < 2:
                        continue
                    state_a = state_set.get_entity_state(pair[0])
                    state_b = state_set.get_entity_state(pair[1])
                    if state_a is None or state_b is None:
                        continue
                    pos_a = state_a.get("position", [0, 0, 0])
                    pos_b = state_b.get("position", [0, 0, 0])
                    dist = math.sqrt(
                        sum((a - b) ** 2 for a, b in zip(pos_a, pos_b))
                    )
                    threshold = float(condition.get("threshold", 0.5))
                    proximity = max(0.0, dist - threshold)
                    min_proximity = min(min_proximity, proximity)

            elif trigger_type == "boundary_contact":
                axis_map = {"x": 0, "y": 1, "z": 2}
                axis_idx = axis_map.get(condition.get("axis", "z"), 2)
                boundary = float(condition.get("threshold", 0.0))
                entities = condition.get("entities", state_set.all_entity_ids())
                for eid in entities:
                    state = state_set.get_entity_state(eid)
                    if state is None:
                        continue
                    pos = state.get("position", [0, 0, 0])
                    if len(pos) > axis_idx:
                        proximity = abs(pos[axis_idx] - boundary)
                        min_proximity = min(min_proximity, proximity)

        # 调整步长
        if min_proximity < cfg.proximity_threshold:
            new_dt = current_dt * cfg.refinement_factor
        else:
            new_dt = current_dt * cfg.coarsening_factor

        # 限制在 [dt_min, dt_max]
        new_dt = max(cfg.dt_min, min(cfg.dt_max, new_dt))
        return new_dt
