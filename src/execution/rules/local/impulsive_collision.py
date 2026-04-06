"""
ImpulsiveCollisionRule — 瞬时碰撞局部规则 v0.2.

第一原型局部规则：在接触触发时，对两个或更多粒子执行一维弹性或非弹性碰撞。

规则逻辑
--------
使用动量守恒 + 恢复系数（coefficient of restitution）方程：

    v1_after = ((m1 - e*m2) * v1 + (1+e) * m2 * v2) / (m1 + m2)
    v2_after = ((m2 - e*m1) * v2 + (1+e) * m1 * v1) / (m1 + m2)

其中 e 为恢复系数（e=1 弹性碰撞，e=0 完全非弹性碰撞）。
当前只处理沿碰撞法线方向（默认 z 轴）的速度分量，其余方向不变。

多体碰撞（N > 2）
-----------------
当 entity_pair 包含超过两个实体时，对所有两两组合依次施加冲量：
每对实体满足接触条件时开启新处理支路，结果依次叠加（串行结算）。
这与"原则上多少个体都一样处理"的设计一致，无需线程。

required_inputs
---------------
- restitution: 恢复系数 [0, 1]（默认 1.0 弹性碰撞）
- contact_normal: [nx, ny, nz]，碰撞法线方向（默认 [0, 0, 1]）
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.execution.rules.local.base import LocalRuleExecutor

_DEFAULT_NORMAL: List[float] = [0.0, 0.0, 1.0]


def _dot(a: List[float], b: List[float]) -> float:
    return sum(ai * bi for ai, bi in zip(a, b))


def _scale(s: float, v: List[float]) -> List[float]:
    return [s * vi for vi in v]


def _add(a: List[float], b: List[float]) -> List[float]:
    return [ai + bi for ai, bi in zip(a, b)]


def _sub(a: List[float], b: List[float]) -> List[float]:
    return [ai - bi for ai, bi in zip(a, b)]


class ImpulsiveCollisionRule(LocalRuleExecutor):
    """
    瞬时碰撞局部规则。

    在两粒子接触触发时，沿碰撞法线方向执行冲量交换，
    返回碰后两粒子的更新状态。

    pre_trigger_state 须含以下两个实体键，每个实体状态须含：
    - velocity: [vx, vy, vz]
    - mass: float

    Examples
    --------
    >>> rule = ImpulsiveCollisionRule()
    >>> state = {
    ...     "A": {"mass": 1.0, "velocity": [2.0, 0, 0], "position": [0, 0, 0]},
    ...     "B": {"mass": 1.0, "velocity": [0.0, 0, 0], "position": [1, 0, 0]},
    ... }
    >>> inputs = {"restitution": 1.0, "contact_normal": [1, 0, 0], "entity_pair": ["A", "B"]}
    >>> result = rule.apply(state, inputs)
    >>> result["A"]["velocity"]
    [0.0, 0, 0]
    >>> result["B"]["velocity"]
    [2.0, 0, 0]
    """

    rule_name: str = "impulsive_collision"
    trigger_condition_type: str = "contact"
    required_inputs: list = ["restitution", "contact_normal", "entity_pair"]

    def apply(
        self,
        pre_trigger_state: Dict[str, Any],
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        执行冲量碰撞，返回碰后状态。

        支持两体（标准情形）和多体（N > 2）碰撞。多体时对所有两两组合
        依次施加冲量（串行结算，无线程）。

        Parameters
        ----------
        pre_trigger_state:
            触发前状态字典，键为实体 ID，值含 ``mass`` 和 ``velocity``。
        inputs:
            须含 ``entity_pair`` (两个或更多实体 ID)、``restitution``、
            ``contact_normal``。

        Returns
        -------
        Dict[str, Any]
            碰后更新的状态字典（与 pre_trigger_state 同结构，仅更新
            相关实体的 velocity）。
        """
        pair: List[str] = inputs.get("entity_pair", list(pre_trigger_state.keys())[:2])
        if len(pair) < 2:
            return dict(pre_trigger_state)

        e: float = float(inputs.get("restitution", 1.0))
        n: List[float] = list(inputs.get("contact_normal", _DEFAULT_NORMAL))

        # 以当前状态副本为起点，依次处理所有两两组合（N-body 串行结算）
        updated = {k: dict(v) for k, v in pre_trigger_state.items()}

        for i in range(len(pair)):
            for j in range(i + 1, len(pair)):
                id_a, id_b = pair[i], pair[j]
                state_a = updated.get(id_a)
                state_b = updated.get(id_b)
                if state_a is None or state_b is None:
                    continue

                m1: float = float(state_a["mass"])
                m2: float = float(state_b["mass"])
                v1: List[float] = list(state_a["velocity"])
                v2: List[float] = list(state_b["velocity"])

                # 相对速度在法线方向的投影
                v_rel_n = _dot(_sub(v1, v2), n)

                # 若两粒子已在分离或无相对速度（v_rel_n <= 0），不施加冲量
                if v_rel_n <= 0:
                    continue

                # 冲量大小 j = -(1+e) * v_rel_n / (1/m1 + 1/m2)
                j = (1.0 + e) * v_rel_n / (1.0 / m1 + 1.0 / m2)

                v1_after = _sub(v1, _scale(j / m1, n))
                v2_after = _add(v2, _scale(j / m2, n))

                updated[id_a]["velocity"] = v1_after
                updated[id_b]["velocity"] = v2_after

        return updated
