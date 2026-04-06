"""
ConstantGravityRule — 持续背景重力规则 v0.1.

第一原型持续规则：在每个演化步中对粒子施加恒定重力加速度。

规则逻辑
--------
在时间步 dt 内，使用欧拉积分更新速度（位置由 scheduler 统一推进）：

    v_new = v_old + g * dt

apply() 返回 state_delta，仅包含 velocity 的增量贡献（dv）。
Scheduler 负责将 dv 叠加到当前速度并推进位置。

required_inputs
---------------
- gravity_vector: [gx, gy, gz]，单位 m/s²（默认 [0, 0, -9.8]）
- dt: 时间步长，单位 s
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.execution.rules.persistent.base import PersistentRuleExecutor

_DEFAULT_GRAVITY: List[float] = [0.0, 0.0, -9.8]


class ConstantGravityRule(PersistentRuleExecutor):
    """
    恒定重力持续规则。

    在每个演化步中返回由重力产生的速度增量（dv = g * dt）。

    Examples
    --------
    >>> rule = ConstantGravityRule()
    >>> state = {"position": [0, 0, 10], "velocity": [0, 0, 0], "mass": 1.0}
    >>> inputs = {"gravity_vector": [0, 0, -9.8], "dt": 0.1}
    >>> delta = rule.apply(state, inputs)
    >>> delta["dv"]
    [0.0, 0.0, -0.98]
    """

    rule_name: str = "constant_gravity"
    required_inputs: list = ["gravity_vector", "dt"]

    def apply(self, current_state: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算恒定重力在一个时间步内产生的速度增量。

        Parameters
        ----------
        current_state:
            当前实体状态（需含 ``velocity`` 字段）。
        inputs:
            须含 ``gravity_vector`` （[gx, gy, gz]）和 ``dt`` （时间步）。

        Returns
        -------
        Dict[str, Any]
            ``{"dv": [dvx, dvy, dvz]}``，表示速度增量贡献。
        """
        g: List[float] = inputs.get("gravity_vector", _DEFAULT_GRAVITY)
        dt: float = float(inputs.get("dt", 0.01))
        dv = [gi * dt for gi in g]
        return {"dv": dv}
