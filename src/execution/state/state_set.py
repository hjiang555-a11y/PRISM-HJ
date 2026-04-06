"""
StateSet — 运行时状态集合 v0.1.

维护一组实体的运行时状态，提供读取、写入、更新和目标查询接口。

最小能力
--------
- 保存实体状态（set_entity_state）
- 读取实体状态（get_entity_state）
- 更新实体状态（update_entity_state）
- 支持目标相关状态查询（query_target_state）

当前不要求
----------
- 复杂状态图结构
- 完整泛化的状态存储后端
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from typing import TypedDict
except ImportError:  # Python < 3.8
    from typing_extensions import TypedDict


class EntityState(TypedDict, total=False):
    """
    实体运行时状态的类型约束。

    所有字段均为可选（``total=False``），允许部分填充。
    常见字段列举如下；扩展字段可自由添加（TypedDict 开放结构）。

    Attributes
    ----------
    position:
        空间位置向量 [x, y, z]，单位 m。
    velocity:
        速度向量 [vx, vy, vz]，单位 m/s。
    mass:
        质量，单位 kg。
    """

    position: List[float]
    velocity: List[float]
    mass: float


class StateSet:
    """
    运行时状态集合。

    以字典形式存储每个实体的状态，支持按字段名读写。

    Examples
    --------
    >>> ss = StateSet()
    >>> ss.set_entity_state("ball_a", {"position": [0, 0, 5], "velocity": [0, 0, 0], "mass": 1.0})
    >>> ss.get_entity_state("ball_a")
    {'position': [0, 0, 5], 'velocity': [0, 0, 0], 'mass': 1.0}
    >>> ss.update_entity_state("ball_a", {"velocity": [0, 0, -2.0]})
    >>> ss.get_entity_state("ball_a")["velocity"]
    [0, 0, -2.0]
    """

    def __init__(self) -> None:
        self._states: Dict[str, EntityState] = {}
        # 用于存储全局查询目标（如触发事件时刻、碰撞记录等）
        self._target_registry: Dict[str, Any] = {}
        # P3: 状态历史记录 — 按时间 t 存储各实体的快照副本
        self._history: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 状态历史（P3 新增）
    # ------------------------------------------------------------------

    def record_snapshot(self, t: float) -> None:
        """
        记录当前时刻所有实体状态的快照（深拷贝）。

        Parameters
        ----------
        t:
            当前仿真时间（秒）。
        """
        snapshot: Dict[str, Any] = {"t": t, "entities": {}}
        for entity_id, state in self._states.items():
            snapshot["entities"][entity_id] = dict(state)
        self._history.append(snapshot)

    def query_state_at(self, t: float) -> Optional[Dict[str, Any]]:
        """
        查询任意时刻 t 的状态（线性插值）。

        若 t 恰好命中快照时间则直接返回；否则在相邻快照之间
        对 position 和 velocity 进行线性插值。

        Parameters
        ----------
        t:
            查询时间（秒）。

        Returns
        -------
        Optional[Dict[str, Any]]
            包含所有实体状态的字典；若历史为空则返回 None。
        """
        if not self._history:
            return None

        # 精确命中
        for snap in self._history:
            if abs(snap["t"] - t) < 1e-12:
                return dict(snap["entities"])

        # 找到相邻快照
        before: Optional[Dict[str, Any]] = None
        after: Optional[Dict[str, Any]] = None
        for snap in self._history:
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
        result: Dict[str, Any] = {}
        for entity_id in before["entities"]:
            if entity_id not in after["entities"]:
                result[entity_id] = dict(before["entities"][entity_id])
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
            result[entity_id] = interpolated
        return result

    def get_history(self) -> List[Dict[str, Any]]:
        """返回完整的状态历史记录。"""
        return list(self._history)

    # ------------------------------------------------------------------
    # 实体状态读写
    # ------------------------------------------------------------------

    def set_entity_state(self, entity_id: str, state: EntityState) -> None:
        """
        设置（覆盖）指定实体的完整状态。

        Parameters
        ----------
        entity_id:
            实体唯一标识。
        state:
            状态字典，键为字段名，值为字段值。
        """
        self._states[entity_id] = dict(state)

    def get_entity_state(self, entity_id: str) -> Optional[EntityState]:
        """
        获取指定实体的当前状态。

        Parameters
        ----------
        entity_id:
            实体唯一标识。

        Returns
        -------
        Optional[Dict[str, Any]]
            状态字典副本；若实体不存在则返回 ``None``。
        """
        state = self._states.get(entity_id)
        return dict(state) if state is not None else None

    def update_entity_state(self, entity_id: str, updates: Dict[str, Any]) -> None:
        """
        部分更新指定实体的状态（仅更新传入的字段）。

        Parameters
        ----------
        entity_id:
            实体唯一标识。
        updates:
            需要更新的字段及新值。若实体尚不存在，则创建其状态记录。
        """
        if entity_id not in self._states:
            self._states[entity_id] = {}
        self._states[entity_id].update(updates)

    def all_entity_ids(self) -> list:
        """返回当前所有已注册实体的 ID 列表。"""
        return list(self._states.keys())

    # ------------------------------------------------------------------
    # 目标量查询
    # ------------------------------------------------------------------

    def register_target(self, target_name: str, value: Any) -> None:
        """
        注册一个目标量结果（由规则执行器或 trigger engine 调用）。

        Parameters
        ----------
        target_name:
            目标量名称（与 ExecutionPlan.assembly_plan 中的键对应）。
        value:
            目标量的当前值。
        """
        self._target_registry[target_name] = value

    def query_target_state(self, target_name: str) -> Optional[Any]:
        """
        查询已注册的目标量值。

        Parameters
        ----------
        target_name:
            目标量名称。

        Returns
        -------
        Optional[Any]
            目标量值；若尚未注册则返回 ``None``。
        """
        return self._target_registry.get(target_name)
