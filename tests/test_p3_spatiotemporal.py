"""
Tests for P3 — 时空区域与自适应步长.

验证：
1. SpatioTemporalRegion schema（任意形状区域 + 条件谓词）
2. 自适应时间步长（事件逼近时缩小，远离时放大）
3. 中间状态查询（ResultAssembler 按 t 查询）
"""

import math

import pytest

from src.execution.assembly.result_assembler import ExecutionResult, ResultAssembler
from src.execution.runtime.scheduler import Scheduler
from src.execution.state.state_set import StateSet
from src.planning.execution_plan.models import ExecutionPlan
from src.schema.spatiotemporal import (
    AABBRegion,
    AdaptiveTimestepConfig,
    ConditionPredicate,
    HalfSpaceRegion,
    RegionShapeType,
    SpatioTemporalRegion,
    SphereRegion,
)


# =========================================================================
# SpatioTemporalRegion Schema 测试
# =========================================================================

class TestSpatioTemporalRegionSchema:
    """时空区域 schema 单元测试。"""

    def test_sphere_region_contains(self):
        """球形区域包含检测。"""
        region = SpatioTemporalRegion(
            name="test_sphere",
            shape_type=RegionShapeType.SPHERE,
            shape_params={"center": [0, 0, 0], "radius": 5.0},
        )
        state_inside = {"position": [1, 1, 1]}
        state_outside = {"position": [10, 10, 10]}
        assert region.contains_entity(state_inside, 0.0) is True
        assert region.contains_entity(state_outside, 0.0) is False

    def test_aabb_region_contains(self):
        """AABB 区域包含检测。"""
        region = SpatioTemporalRegion(
            name="test_aabb",
            shape_type=RegionShapeType.AABB,
            shape_params={
                "min_corner": [-1, -1, -1],
                "max_corner": [1, 1, 1],
            },
        )
        assert region.contains_entity({"position": [0, 0, 0]}, 0.0) is True
        assert region.contains_entity({"position": [2, 0, 0]}, 0.0) is False

    def test_half_space_region(self):
        """半空间区域包含检测。"""
        region = SpatioTemporalRegion(
            name="above_ground",
            shape_type=RegionShapeType.HALF_SPACE,
            shape_params={"normal": [0, 0, 1], "offset": 0.0},
        )
        assert region.contains_entity({"position": [0, 0, 5]}, 0.0) is True
        assert region.contains_entity({"position": [0, 0, -1]}, 0.0) is False

    def test_time_window(self):
        """时间窗口限制。"""
        region = SpatioTemporalRegion(
            name="timed_region",
            shape_type=RegionShapeType.CUSTOM,
            time_window=(1.0, 5.0),
        )
        assert region.is_active(0.0) is False
        assert region.is_active(3.0) is True
        assert region.is_active(6.0) is False

    def test_no_time_window_always_active(self):
        """无时间窗口则始终活跃。"""
        region = SpatioTemporalRegion(
            name="always_active",
            shape_type=RegionShapeType.CUSTOM,
        )
        assert region.is_active(0.0) is True
        assert region.is_active(1000.0) is True


class TestConditionPredicate:
    """条件谓词单元测试。"""

    def test_lt(self):
        pred = ConditionPredicate(field="velocity", component=2, op="lt", value=0)
        assert pred.evaluate({"velocity": [0, 0, -5]}) is True
        assert pred.evaluate({"velocity": [0, 0, 5]}) is False

    def test_ge(self):
        pred = ConditionPredicate(field="position", component=2, op="ge", value=10)
        assert pred.evaluate({"position": [0, 0, 15]}) is True
        assert pred.evaluate({"position": [0, 0, 5]}) is False

    def test_eq(self):
        pred = ConditionPredicate(field="mass", op="eq", value=1.0)
        assert pred.evaluate({"mass": 1.0}) is True
        assert pred.evaluate({"mass": 2.0}) is False

    def test_missing_field(self):
        pred = ConditionPredicate(field="nonexistent", op="lt", value=0)
        assert pred.evaluate({"velocity": [0, 0, 0]}) is False

    def test_predicate_with_region(self):
        """区域 + 谓词联合检测。"""
        region = SpatioTemporalRegion(
            name="falling_zone",
            shape_type=RegionShapeType.HALF_SPACE,
            shape_params={"normal": [0, 0, 1], "offset": 0.0},
            predicates=[
                ConditionPredicate(field="velocity", component=2, op="lt", value=0),
            ],
        )
        state_falling = {"position": [0, 0, 5], "velocity": [0, 0, -3]}
        state_rising = {"position": [0, 0, 5], "velocity": [0, 0, 3]}
        assert region.contains_entity(state_falling, 0.0) is True
        assert region.contains_entity(state_rising, 0.0) is False


class TestSphereRegionModel:
    """SphereRegion Pydantic model 测试。"""

    def test_create(self):
        s = SphereRegion(center=[0, 0, 0], radius=5.0)
        assert s.radius == 5.0

    def test_invalid_radius(self):
        with pytest.raises(Exception):
            SphereRegion(center=[0, 0, 0], radius=-1.0)


class TestAABBRegionModel:
    """AABBRegion Pydantic model 测试。"""

    def test_create(self):
        aabb = AABBRegion(min_corner=[-1, -1, -1], max_corner=[1, 1, 1])
        assert aabb.min_corner == [-1, -1, -1]


class TestHalfSpaceRegionModel:
    """HalfSpaceRegion model 测试。"""

    def test_create(self):
        hs = HalfSpaceRegion(normal=[0, 0, 1], offset=0.0)
        assert hs.normal == [0, 0, 1]


# =========================================================================
# 自适应时间步长测试
# =========================================================================

class TestAdaptiveTimestep:
    """自适应步长功能测试。"""

    def test_adaptive_config_defaults(self):
        """默认配置值。"""
        cfg = AdaptiveTimestepConfig()
        assert cfg.dt_min > 0
        assert cfg.dt_max > cfg.dt_min
        assert 0 < cfg.refinement_factor < 1
        assert cfg.coarsening_factor > 1

    def test_adaptive_timestep_refines_near_boundary(self):
        """实体接近边界时步长缩小。"""
        plan = ExecutionPlan(
            persistent_rule_plan=[
                {"rule_name": "constant_gravity", "applies_to": ["ball"]},
            ],
            trigger_plan=[
                {
                    "type": "boundary_contact",
                    "entities": ["ball"],
                    "axis": "z",
                    "threshold": 0.0,
                    "direction": "below",
                },
            ],
            assembly_plan={
                "pos": {"entity": "ball", "field": "position"},
            },
        )
        ss = StateSet()
        ss.set_entity_state("ball", {
            "position": [0, 0, 0.3],
            "velocity": [0, 0, -1],
            "mass": 1.0,
        })
        adaptive_cfg = AdaptiveTimestepConfig(
            dt_min=0.0001,
            dt_max=0.1,
            proximity_threshold=1.0,
            refinement_factor=0.5,
            coarsening_factor=2.0,
        )
        scheduler = Scheduler(
            dt=0.01, steps=10, adaptive_config=adaptive_cfg
        )
        result = scheduler.run(plan, ss)
        # 验证执行不崩溃且有历史记录
        assert len(result.state_history) > 0

    def test_adaptive_timestep_coarsens_far_from_event(self):
        """实体远离事件时步长放大。"""
        plan = ExecutionPlan(
            persistent_rule_plan=[
                {"rule_name": "constant_gravity", "applies_to": ["ball"]},
            ],
            trigger_plan=[
                {
                    "type": "boundary_contact",
                    "entities": ["ball"],
                    "axis": "z",
                    "threshold": 0.0,
                    "direction": "below",
                },
            ],
            assembly_plan={
                "pos": {"entity": "ball", "field": "position"},
            },
        )
        ss = StateSet()
        # 远离地面
        ss.set_entity_state("ball", {
            "position": [0, 0, 100],
            "velocity": [0, 0, 0],
            "mass": 1.0,
        })
        adaptive_cfg = AdaptiveTimestepConfig(
            dt_min=0.001,
            dt_max=0.05,
            proximity_threshold=2.0,
            refinement_factor=0.5,
            coarsening_factor=2.0,
        )
        scheduler = Scheduler(
            dt=0.01, steps=5, adaptive_config=adaptive_cfg
        )
        result = scheduler.run(plan, ss)
        # 远离边界时步长应该增大，总时间覆盖 > 5 * 0.01
        history = result.state_history
        assert len(history) > 1
        total_time = history[-1]["t"]
        assert total_time > 5 * 0.01  # 步长放大了

    def test_no_adaptive_uses_fixed_dt(self):
        """不开启自适应时使用固定步长。"""
        plan = ExecutionPlan(
            persistent_rule_plan=[
                {"rule_name": "constant_gravity", "applies_to": ["ball"]},
            ],
            assembly_plan={
                "vel": {"entity": "ball", "field": "velocity"},
            },
        )
        ss = StateSet()
        ss.set_entity_state("ball", {
            "position": [0, 0, 100],
            "velocity": [0, 0, 0],
            "mass": 1.0,
        })
        scheduler = Scheduler(dt=0.1, steps=10)  # 无 adaptive_config
        result = scheduler.run(plan, ss)
        history = result.state_history
        # 固定步长：总时间应精确等于 10 * 0.1 = 1.0
        assert abs(history[-1]["t"] - 1.0) < 1e-10


# =========================================================================
# 中间状态查询测试
# =========================================================================

class TestIntermediateStateQuery:
    """中间状态查询功能测试。"""

    def test_state_history_recorded(self):
        """执行后有状态历史。"""
        plan = ExecutionPlan(
            persistent_rule_plan=[
                {"rule_name": "constant_gravity", "applies_to": ["ball"]},
            ],
            assembly_plan={},
        )
        ss = StateSet()
        ss.set_entity_state("ball", {
            "position": [0, 0, 100],
            "velocity": [0, 0, 0],
            "mass": 1.0,
        })
        scheduler = Scheduler(dt=0.1, steps=10)
        result = scheduler.run(plan, ss)
        # 11 snapshots: initial + 10 steps
        assert len(result.state_history) == 11

    def test_query_at_exact_time(self):
        """精确时间命中查询。"""
        plan = ExecutionPlan(
            persistent_rule_plan=[
                {"rule_name": "constant_gravity", "applies_to": ["ball"]},
            ],
            assembly_plan={},
        )
        ss = StateSet()
        ss.set_entity_state("ball", {
            "position": [0, 0, 100],
            "velocity": [0, 0, 0],
            "mass": 1.0,
        })
        scheduler = Scheduler(dt=0.1, steps=10)
        result = scheduler.run(plan, ss)

        # 查询 t=0 时的状态
        state_0 = ResultAssembler.query_at_time(result, 0.0)
        assert state_0 is not None
        assert abs(state_0["ball"]["position"][2] - 100.0) < 1e-6

    def test_query_at_interpolated_time(self):
        """非精确时间插值查询。"""
        plan = ExecutionPlan(
            persistent_rule_plan=[
                {"rule_name": "constant_gravity", "applies_to": ["ball"]},
            ],
            assembly_plan={},
        )
        ss = StateSet()
        ss.set_entity_state("ball", {
            "position": [0, 0, 100],
            "velocity": [0, 0, 0],
            "mass": 1.0,
        })
        scheduler = Scheduler(dt=0.1, steps=10)
        result = scheduler.run(plan, ss)

        # 查询 t=0.05 的插值状态
        state_mid = ResultAssembler.query_at_time(result, 0.05)
        assert state_mid is not None
        # 应该在 t=0 和 t=0.1 之间插值
        z_at_0 = 100.0
        # 在 t=0.1: v_z = -0.98, pos_z ≈ 100 + (-0.98) * 0.1 ≈ 99.902
        z_at_01 = result.state_history[1]["entities"]["ball"]["position"][2]
        z_interp = state_mid["ball"]["position"][2]
        # 插值结果应在两者之间
        assert min(z_at_0, z_at_01) <= z_interp <= max(z_at_0, z_at_01)

    def test_query_empty_history(self):
        """空历史返回 None。"""
        result = ExecutionResult(state_history=[])
        assert ResultAssembler.query_at_time(result, 0.5) is None

    def test_stateset_query_state_at(self):
        """StateSet 直接查询中间状态。"""
        ss = StateSet()
        ss.set_entity_state("ball", {"position": [0, 0, 0], "velocity": [1, 0, 0]})
        ss.record_snapshot(0.0)
        ss.update_entity_state("ball", {"position": [1, 0, 0]})
        ss.record_snapshot(1.0)

        # 精确命中
        state = ss.query_state_at(0.0)
        assert state is not None
        assert abs(state["ball"]["position"][0]) < 1e-10

        # 插值
        state_mid = ss.query_state_at(0.5)
        assert state_mid is not None
        assert abs(state_mid["ball"]["position"][0] - 0.5) < 1e-10
