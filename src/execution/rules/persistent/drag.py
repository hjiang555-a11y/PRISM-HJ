"""
LinearDragRule — 线性空气阻力持续规则 v0.1.

在每个演化步中对粒子施加线性阻力加速度，与重力等持续规则并行叠加。

规则逻辑
--------
线性阻力力：F = -k * v，其中 k 为阻力系数（drag_coefficient）。
加速度：a = F / m = -(k / m) * v
速度增量：dv = a * dt = -(k / m) * v * dt

apply() 返回 state_delta，仅包含 velocity 的增量贡献（dv）。
Scheduler 的 force accumulator 负责将此 dv 与其他规则的 dv 叠加后统一更新。

required_inputs
---------------
- drag_coefficient: k，阻力系数，单位 kg/s（默认 0.1）
- dt: 时间步长，单位 s
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.execution.rules.persistent.base import PersistentRuleExecutor

_DEFAULT_DRAG_COEFFICIENT: float = 0.1


class LinearDragRule(PersistentRuleExecutor):
    """
    线性空气阻力持续规则。

    在每个演化步中返回由阻力产生的速度增量（dv = -(k/m) * v * dt）。

    Examples
    --------
    >>> rule = LinearDragRule()
    >>> state = {"position": [0, 0, 10], "velocity": [0, 0, -5], "mass": 1.0}
    >>> inputs = {"drag_coefficient": 0.1, "dt": 0.1}
    >>> delta = rule.apply(state, inputs)
    >>> delta["dv"]  # -(0.1/1.0) * [0, 0, -5] * 0.1 = [0.0, 0.0, 0.05]
    [0.0, 0.0, 0.05]
    """

    rule_name: str = "linear_drag"
    required_inputs: list = ["drag_coefficient", "dt"]

    def apply(self, current_state: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算线性阻力在一个时间步内产生的速度增量。

        Parameters
        ----------
        current_state:
            当前实体状态（需含 ``velocity`` 和 ``mass`` 字段）。
        inputs:
            须含 ``drag_coefficient`` （k）和 ``dt`` （时间步）。

        Returns
        -------
        Dict[str, Any]
            ``{"dv": [dvx, dvy, dvz]}``，表示阻力产生的速度增量贡献。
        """
        k: float = float(inputs.get("drag_coefficient", _DEFAULT_DRAG_COEFFICIENT))
        dt: float = float(inputs.get("dt", 0.01))
        velocity: List[float] = list(current_state.get("velocity", [0.0, 0.0, 0.0]))
        mass: float = float(current_state.get("mass", 1.0))

        # a = -(k/m) * v，dv = a * dt
        coeff = -(k / mass) * dt if mass > 0 else 0.0
        dv = [coeff * vi for vi in velocity]
        return {"dv": dv}
