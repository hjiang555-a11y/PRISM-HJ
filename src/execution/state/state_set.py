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
