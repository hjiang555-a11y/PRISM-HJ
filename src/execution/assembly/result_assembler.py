"""
ResultAssembler — 结果组装接口 v0.1.

围绕 targets_of_interest 从运行时状态中提取目标量，
输出最终结果对象 ExecutionResult。

最小职责
--------
- 根据 assembly_plan 提取目标量
- 记录触发事件
- 输出最终结果对象

当前不要求
----------
- 完整自然语言解释
- 复杂多格式呈现
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.execution.state.state_set import StateSet


# ---------------------------------------------------------------------------
# ExecutionResult — 最小结果对象
# ---------------------------------------------------------------------------

class ExecutionResult(BaseModel):
    """
    执行结果最小对象 v0.2.

    Attributes
    ----------
    target_results:
        目标量结果字典（目标量名称 -> 值）。
    trigger_records:
        执行过程中发生的触发事件记录列表。
    execution_notes:
        执行备注（自由文本，供调试和审查）。
    state_history:
        状态历史快照列表（P3 新增，支持中间状态查询）。
    """

    target_results: Dict[str, Any] = Field(
        default_factory=dict,
        description="目标量结果（目标量名称 -> 值）",
    )
    trigger_records: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="执行过程中发生的触发事件记录",
    )
    execution_notes: List[str] = Field(
        default_factory=list,
        description="执行备注（自由文本）",
    )
    state_history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="状态历史快照列表（时间 -> 实体状态）",
    )


# ---------------------------------------------------------------------------
# ResultAssembler
# ---------------------------------------------------------------------------

class ResultAssembler:
    """
    结果组装器。

    根据 ExecutionPlan.assembly_plan 从 StateSet 中提取目标量，
    并汇聚触发记录，生成 ExecutionResult。

    Examples
    --------
    >>> from src.execution.state.state_set import StateSet
    >>> ss = StateSet()
    >>> ss.set_entity_state("ball", {"position": [0, 0, 0], "velocity": [3, 0, 4]})
    >>> assembler = ResultAssembler()
    >>> assembly_plan = {"final_speed": {"source_capability": "particle_motion", "entity": "ball", "field": "velocity"}}
    >>> result = assembler.assemble(ss, assembly_plan, trigger_records=[])
    >>> "final_speed" in result.target_results
    True
    """

    def assemble(
        self,
        state_set: StateSet,
        assembly_plan: Dict[str, Any],
        trigger_records: Optional[List[Dict[str, Any]]] = None,
    ) -> ExecutionResult:
        """
        从 StateSet 和触发记录中提取目标量，组装结果。

        Parameters
        ----------
        state_set:
            执行结束后的运行时状态集合。
        assembly_plan:
            来自 ExecutionPlan 的结果组装规划，格式为：

            .. code-block:: python

                {
                    "target_name": {
                        "source_capability": "...",
                        "entity": "entity_id",   # 可选
                        "field": "velocity",      # 可选
                        "description": {...},     # 可选
                    }
                }

        trigger_records:
            执行过程中收集的触发事件记录列表。

        Returns
        -------
        ExecutionResult
            目标量结果和触发记录的汇总。
        """
        target_results: Dict[str, Any] = {}
        notes: List[str] = []

        for target_name, plan_entry in assembly_plan.items():
            value = self._extract_target(state_set, target_name, plan_entry, notes)
            target_results[target_name] = value

        # 同时从 state_set 的 target_registry 中读取已注册的目标量
        for target_name_reg, value in state_set._target_registry.items():
            if target_name_reg not in target_results:
                target_results[target_name_reg] = value

        return ExecutionResult(
            target_results=target_results,
            trigger_records=list(trigger_records or []),
            execution_notes=notes,
            state_history=state_set.get_history(),
        )

    def _extract_target(
        self,
        state_set: StateSet,
        target_name: str,
        plan_entry: Dict[str, Any],
        notes: List[str],
    ) -> Any:
        """
        从 StateSet 中提取单个目标量。

        当前支持的提取策略：
        1. plan_entry 含 ``entity`` 和 ``field`` 和 ``component`` -> 读取向量分量
        2. plan_entry 含 ``entity`` 和 ``field``                  -> 读取完整字段值
        3. plan_entry 含 ``entity`` 无 ``field``                  -> 返回完整实体状态
        4. 其他情况                                               -> 尝试 query_target_state
        """
        entity_id: Optional[str] = plan_entry.get("entity") if isinstance(plan_entry, dict) else None
        field: Optional[str] = plan_entry.get("field") if isinstance(plan_entry, dict) else None
        component: Optional[int] = plan_entry.get("component") if isinstance(plan_entry, dict) else None

        if entity_id is not None:
            entity_state = state_set.get_entity_state(entity_id)
            if entity_state is None:
                notes.append(f"target '{target_name}': entity '{entity_id}' not found in StateSet")
                return None
            if field is not None:
                value = entity_state.get(field)
                if value is None:
                    notes.append(
                        f"target '{target_name}': field '{field}' not found "
                        f"in entity '{entity_id}'"
                    )
                    return None
                # 若指定分量索引，提取向量中的单一值
                if component is not None and isinstance(value, (list, tuple)):
                    try:
                        return value[component]
                    except IndexError:
                        notes.append(
                            f"target '{target_name}': component {component} out of range "
                            f"for field '{field}' (len={len(value)})"
                        )
                        return None
                return value
            return entity_state

        # 尝试从 target_registry 读取
        registered = state_set.query_target_state(target_name)
        if registered is not None:
            return registered

        notes.append(
            f"target '{target_name}': no entity/field specified and not in target_registry"
        )
        return None

    @staticmethod
    def query_at_time(result: ExecutionResult, t: float) -> Optional[Dict[str, Any]]:
        """
        从执行结果的状态历史中查询任意时刻 t 的状态（线性插值）。

        Parameters
        ----------
        result:
            包含 state_history 的执行结果。
        t:
            查询时间（秒）。

        Returns
        -------
        Optional[Dict[str, Any]]
            该时刻所有实体的状态字典；若无历史则返回 None。
        """
        history = result.state_history
        if not history:
            return None

        # 精确命中
        for snap in history:
            if abs(snap["t"] - t) < 1e-12:
                return dict(snap["entities"])

        # 找到相邻快照
        before: Optional[Dict[str, Any]] = None
        after: Optional[Dict[str, Any]] = None
        for snap in history:
            if snap["t"] <= t:
                if before is None or snap["t"] > before["t"]:
                    before = snap
            if snap["t"] >= t:
                if after is None or snap["t"] < after["t"]:
                    after = snap

        if before is None and after is None:
            return None
        if before is None:
            return dict(after["entities"])  # type: ignore[union-attr]
        if after is None:
            return dict(before["entities"])
        if abs(after["t"] - before["t"]) < 1e-12:
            return dict(before["entities"])

        # 线性插值
        alpha = (t - before["t"]) / (after["t"] - before["t"])
        result_state: Dict[str, Any] = {}
        for entity_id in before["entities"]:
            if entity_id not in after["entities"]:
                result_state[entity_id] = dict(before["entities"][entity_id])
                continue
            s_before = before["entities"][entity_id]
            s_after = after["entities"][entity_id]
            interpolated: Dict[str, Any] = {}
            for key in s_before:
                val_b = s_before[key]
                val_a = s_after.get(key, val_b)
                if isinstance(val_b, (list, tuple)) and isinstance(val_a, (list, tuple)):
                    interpolated[key] = [
                        vb + alpha * (va - vb)
                        for vb, va in zip(val_b, val_a)
                    ]
                elif isinstance(val_b, (int, float)) and isinstance(val_a, (int, float)):
                    interpolated[key] = val_b + alpha * (val_a - val_b)
                else:
                    interpolated[key] = val_b
            result_state[entity_id] = interpolated
        return result_state
