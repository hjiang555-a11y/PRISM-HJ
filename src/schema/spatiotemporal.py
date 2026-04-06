"""
SpatioTemporalRegion — 时空区域 schema v0.1.

定义任意形状空间区域 + 条件谓词 + 时间窗口，
支持自适应步长和基于区域的条件评估。

设计思路
--------
- shape:     描述空间区域形状（球形 / AABB / 半空间 / 自定义谓词）
- predicate: 条件谓词，判断实体状态是否满足区域条件
- time_window: 活跃时间范围 [t_start, t_end]
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 空间形状类型枚举
# ---------------------------------------------------------------------------

class RegionShapeType(str, Enum):
    """空间区域形状类型。"""
    SPHERE = "sphere"           # 球形区域
    AABB = "aabb"               # 轴对齐包围盒
    HALF_SPACE = "half_space"   # 半空间（平面一侧）
    CUSTOM = "custom"           # 自定义谓词


# ---------------------------------------------------------------------------
# 空间区域形状定义
# ---------------------------------------------------------------------------

class SphereRegion(BaseModel):
    """球形空间区域。"""
    center: List[float] = Field(
        description="球心坐标 [x, y, z]",
    )
    radius: float = Field(
        gt=0,
        description="半径 (m)",
    )


class AABBRegion(BaseModel):
    """轴对齐包围盒 (Axis-Aligned Bounding Box)。"""
    min_corner: List[float] = Field(
        description="包围盒最小角坐标 [x_min, y_min, z_min]",
    )
    max_corner: List[float] = Field(
        description="包围盒最大角坐标 [x_max, y_max, z_max]",
    )


class HalfSpaceRegion(BaseModel):
    """半空间区域（由平面法线和偏移定义）。"""
    normal: List[float] = Field(
        description="平面法线 [nx, ny, nz]",
    )
    offset: float = Field(
        default=0.0,
        description="平面偏移 d，满足 n·x >= d 的点在区域内",
    )


# ---------------------------------------------------------------------------
# 条件谓词
# ---------------------------------------------------------------------------

class ConditionPredicate(BaseModel):
    """
    条件谓词，用于在时空区域内做额外状态判断。

    可基于实体状态字段做数值比较、范围检查或自定义逻辑。

    Examples
    --------
    - field="velocity", component=2, op="lt", value=0  →  v_z < 0
    - field="position", component=2, op="le", value=0  →  z <= 0
    """

    field: str = Field(description="实体状态字段名（如 'velocity', 'position'）")
    component: Optional[int] = Field(
        default=None,
        description="向量分量索引（如 0=x, 1=y, 2=z）",
    )
    op: str = Field(
        default="le",
        description="比较运算符: lt, le, eq, ge, gt, ne",
    )
    value: float = Field(
        default=0.0,
        description="比较阈值",
    )

    def evaluate(self, entity_state: Dict[str, Any]) -> bool:
        """
        对实体状态评估谓词条件。

        Parameters
        ----------
        entity_state:
            实体当前状态字典。

        Returns
        -------
        bool
            谓词条件是否满足。
        """
        field_val = entity_state.get(self.field)
        if field_val is None:
            return False

        if self.component is not None and isinstance(field_val, (list, tuple)):
            if self.component >= len(field_val):
                return False
            field_val = field_val[self.component]

        _ops = {
            "lt": lambda a, b: a < b,
            "le": lambda a, b: a <= b,
            "eq": lambda a, b: a == b,
            "ge": lambda a, b: a >= b,
            "gt": lambda a, b: a > b,
            "ne": lambda a, b: a != b,
        }
        comparator = _ops.get(self.op)
        if comparator is None:
            return False
        return comparator(float(field_val), self.value)


# ---------------------------------------------------------------------------
# 时空区域
# ---------------------------------------------------------------------------

class SpatioTemporalRegion(BaseModel):
    """
    时空区域定义。

    组合空间形状、时间窗口和条件谓词，定义一个在时空中的
    有限区域，用于自适应步长控制和事件检测。

    Attributes
    ----------
    name:
        区域唯一标识。
    shape_type:
        空间区域形状类型。
    shape_params:
        形状参数字典（根据 shape_type 解释）。
    time_window:
        活跃时间范围 [t_start, t_end]，None 表示永久活跃。
    predicates:
        条件谓词列表，全部满足时视为实体"在区域内"。
    priority:
        区域优先级（高值优先），用于冲突解决。
    metadata:
        附加元数据。
    """

    name: str = Field(
        description="区域唯一标识",
    )
    shape_type: RegionShapeType = Field(
        default=RegionShapeType.CUSTOM,
        description="空间区域形状类型",
    )
    shape_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="形状参数（根据 shape_type 解释）",
    )
    time_window: Optional[Tuple[float, float]] = Field(
        default=None,
        description="活跃时间范围 [t_start, t_end]",
    )
    predicates: List[ConditionPredicate] = Field(
        default_factory=list,
        description="条件谓词列表",
    )
    priority: int = Field(
        default=0,
        description="区域优先级（高值优先）",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="附加元数据",
    )

    def is_active(self, t: float) -> bool:
        """
        判断时空区域在给定时间 t 是否活跃。

        Parameters
        ----------
        t:
            当前时间（秒）。

        Returns
        -------
        bool
            区域在该时刻是否活跃。
        """
        if self.time_window is None:
            return True
        return self.time_window[0] <= t <= self.time_window[1]

    def contains_entity(self, entity_state: Dict[str, Any], t: float) -> bool:
        """
        判断实体在给定时刻是否位于时空区域内。

        先检查时间活跃性，再检查空间位置，最后检查条件谓词。

        Parameters
        ----------
        entity_state:
            实体当前状态字典。
        t:
            当前时间（秒）。

        Returns
        -------
        bool
            实体是否在区域内。
        """
        if not self.is_active(t):
            return False

        # 空间检查
        if not self._check_spatial(entity_state):
            return False

        # 条件谓词检查（全部满足）
        for predicate in self.predicates:
            if not predicate.evaluate(entity_state):
                return False

        return True

    def _check_spatial(self, entity_state: Dict[str, Any]) -> bool:
        """根据 shape_type 检查空间位置。"""
        pos = entity_state.get("position")
        if pos is None:
            return False

        if self.shape_type == RegionShapeType.SPHERE:
            center = self.shape_params.get("center", [0, 0, 0])
            radius = self.shape_params.get("radius", 1.0)
            dist_sq = sum((a - b) ** 2 for a, b in zip(pos, center))
            return dist_sq <= radius ** 2

        elif self.shape_type == RegionShapeType.AABB:
            min_c = self.shape_params.get("min_corner", [-1, -1, -1])
            max_c = self.shape_params.get("max_corner", [1, 1, 1])
            return all(mn <= p <= mx for p, mn, mx in zip(pos, min_c, max_c))

        elif self.shape_type == RegionShapeType.HALF_SPACE:
            normal = self.shape_params.get("normal", [0, 0, 1])
            offset = self.shape_params.get("offset", 0.0)
            dot = sum(n * p for n, p in zip(normal, pos))
            return dot >= offset

        # CUSTOM: 仅依赖谓词，无空间约束
        return True


# ---------------------------------------------------------------------------
# 自适应步长参数
# ---------------------------------------------------------------------------

class AdaptiveTimestepConfig(BaseModel):
    """
    自适应步长配置。

    Attributes
    ----------
    dt_min:
        最小时间步长（秒）。
    dt_max:
        最大时间步长（秒）。
    refinement_factor:
        接近事件时步长缩小因子（0 < factor < 1）。
    coarsening_factor:
        远离事件时步长放大因子（factor > 1）。
    proximity_threshold:
        事件逼近距离阈值（米），低于此值启用步长缩小。
    """

    dt_min: float = Field(default=1e-5, gt=0, description="最小时间步长 (s)")
    dt_max: float = Field(default=0.1, gt=0, description="最大时间步长 (s)")
    refinement_factor: float = Field(
        default=0.5,
        gt=0,
        lt=1,
        description="事件逼近时步长缩小因子",
    )
    coarsening_factor: float = Field(
        default=2.0,
        gt=1,
        description="远离事件时步长放大因子",
    )
    proximity_threshold: float = Field(
        default=1.0,
        gt=0,
        description="事件逼近距离阈值 (m)",
    )
