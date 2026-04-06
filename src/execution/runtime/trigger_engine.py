"""
TriggerEngine — 触发条件检测接口 v0.1.

检查局部规则的触发条件是否满足，并将触发事件列表
反馈给 Scheduler。

第一原型最小支持
----------------
- 接触/相遇类 trigger（基于实体间距离 <= 接触阈值）

当前不要求
----------
- 复杂事件队列
- 精确时间步内的触发时刻插值
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from src.execution.state.state_set import StateSet


def _distance(pos_a: List[float], pos_b: List[float]) -> float:
    """计算两点间欧氏距离（要求两向量等长）。"""
    if len(pos_a) != len(pos_b):
        raise ValueError(
            f"Position vectors must have the same length, "
            f"got {len(pos_a)} and {len(pos_b)}"
        )
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(pos_a, pos_b)))


class TriggerEngine:
    """
    触发条件检测引擎。

    根据 trigger_plan 中声明的触发条件，检查当前 StateSet 中
    各实体是否满足激活条件，并返回已触发事件列表。

    Examples
    --------
    >>> engine = TriggerEngine()
    >>> # 触发计划：检查 A 和 B 的接触
    >>> trigger_plan = [{"type": "contact", "pairs": [["A", "B"]], "threshold": 0.5}]
    """

    def __init__(self, contact_threshold: float = 0.5) -> None:
        """
        Parameters
        ----------
        contact_threshold:
            默认接触判断阈值（两实体中心距离，单位 m）。
            可被 trigger_plan 条目中的 ``threshold`` 字段覆盖。
        """
        self._default_threshold = contact_threshold

    def check_triggers(
        self,
        state_set: StateSet,
        trigger_plan: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        检查当前状态中是否有触发条件满足。

        Parameters
        ----------
        state_set:
            当前运行时状态集合。
        trigger_plan:
            来自 ExecutionPlan 的触发条件列表。每个条目至少含
            ``type`` 字段，接触类型还须含 ``pairs`` 字段。

        Returns
        -------
        List[Dict[str, Any]]
            已触发事件列表。每个条目含：

            - ``trigger_type``: 触发类型（如 ``"contact"``、``"boundary_contact"``）
            - ``entity_pair``: 触发的实体对 ``[id_a, id_b]``（仅 contact 类型）
            - ``entity``: 触发的实体 ID（仅 boundary_contact 类型）
            - ``details``: 附加信息字典（如距离、z 坐标）
        """
        triggered: List[Dict[str, Any]] = []

        for condition in trigger_plan:
            trigger_type = condition.get("type", "unknown")

            if trigger_type == "contact":
                events = self._check_contact(state_set, condition)
                triggered.extend(events)
            elif trigger_type == "boundary_contact":
                events = self._check_boundary_contact(state_set, condition)
                triggered.extend(events)
            # 未来可在此扩展其他 trigger 类型

        return triggered

    def _check_contact(
        self,
        state_set: StateSet,
        condition: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """检查接触触发条件。"""
        threshold: float = float(condition.get("threshold", self._default_threshold))
        pairs: List[List[str]] = condition.get("pairs", [])
        events: List[Dict[str, Any]] = []

        for pair in pairs:
            if len(pair) < 2:
                continue
            id_a, id_b = pair[0], pair[1]
            state_a = state_set.get_entity_state(id_a)
            state_b = state_set.get_entity_state(id_b)

            if state_a is None or state_b is None:
                continue

            pos_a: Optional[List[float]] = state_a.get("position")
            pos_b: Optional[List[float]] = state_b.get("position")
            if pos_a is None or pos_b is None:
                continue

            dist = _distance(pos_a, pos_b)
            if dist <= threshold:
                events.append({
                    "trigger_type": "contact",
                    "entity_pair": [id_a, id_b],
                    "details": {"distance": dist},
                })

        return events

    def _check_boundary_contact(
        self,
        state_set: StateSet,
        condition: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        检查实体与空间边界的接触触发条件。

        支持地面（z=0）及任意轴向平面边界。

        触发计划条目格式::

            {
                "type": "boundary_contact",
                "entities": ["ball"],         # 要检测的实体列表
                "axis": "z",                  # 边界法线轴（"x"/"y"/"z"）
                "threshold": 0.0,             # 边界坐标值（默认 0.0 = 地面）
                "direction": "below",         # "below"（z<=threshold）或 "above"（z>=threshold）
            }

        Parameters
        ----------
        state_set:
            当前运行时状态集合。
        condition:
            触发计划条目，见上方格式说明。

        Returns
        -------
        List[Dict[str, Any]]
            已触发事件列表，每个条目含 ``trigger_type``、``entity``、``details``。
        """
        _AXIS_INDEX = {"x": 0, "y": 1, "z": 2}

        axis: str = condition.get("axis", "z")
        axis_idx: int = _AXIS_INDEX.get(axis, 2)
        boundary: float = float(condition.get("threshold", 0.0))
        direction: str = condition.get("direction", "below")
        entities: List[str] = condition.get("entities", [])

        # 若未指定实体，检测所有已注册实体
        if not entities:
            entities = state_set.all_entity_ids()

        events: List[Dict[str, Any]] = []
        for entity_id in entities:
            state = state_set.get_entity_state(entity_id)
            if state is None:
                continue
            pos: Optional[List[float]] = state.get("position")
            if pos is None or len(pos) <= axis_idx:
                continue
            coord = pos[axis_idx]
            triggered = (
                coord <= boundary if direction == "below" else coord >= boundary
            )
            if triggered:
                events.append({
                    "trigger_type": "boundary_contact",
                    "entity": entity_id,
                    "details": {axis: coord, "boundary": boundary, "direction": direction},
                })

        return events
