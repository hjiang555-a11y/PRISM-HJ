"""
Tests for P2 — 并行公理叠加（Force Accumulator + Drag Rule）.

验证：
1. Force accumulator：多个 PersistentRuleExecutor 的 dv 叠加
2. LinearDragRule：F = -kv 空气阻力
3. 重力 + 阻力并行控制的端到端验证
"""

import math

import pytest

from src.execution.assembly.result_assembler import ExecutionResult, ResultAssembler
from src.execution.rules.persistent.drag import LinearDragRule
from src.execution.rules.persistent.gravity import ConstantGravityRule
from src.execution.rules.registry import DEFAULT_RULE_REGISTRY, RuleRegistry
from src.execution.runtime.scheduler import Scheduler
from src.execution.state.state_set import StateSet
from src.planning.execution_plan.models import ExecutionPlan


# =========================================================================
# LinearDragRule 单元测试
# =========================================================================

class TestLinearDragRule:
    """线性阻力规则单元测试。"""

    def test_basic_drag(self):
        """正向速度产生负向阻力 dv。"""
        rule = LinearDragRule()
        state = {"position": [0, 0, 10], "velocity": [10, 0, 0], "mass": 1.0}
        inputs = {"drag_coefficient": 0.1, "dt": 0.1}
        delta = rule.apply(state, inputs)
        dv = delta["dv"]
        # dv = -(0.1/1.0) * [10, 0, 0] * 0.1 = [-0.1, 0, 0]
        assert abs(dv[0] - (-0.1)) < 1e-10
        assert abs(dv[1]) < 1e-10
        assert abs(dv[2]) < 1e-10

    def test_drag_opposing_velocity(self):
        """阻力方向始终与速度相反。"""
        rule = LinearDragRule()
        state = {"velocity": [0, 0, -5], "mass": 1.0}
        inputs = {"drag_coefficient": 0.1, "dt": 0.1}
        delta = rule.apply(state, inputs)
        dv = delta["dv"]
        # dv = -(0.1/1.0) * [0, 0, -5] * 0.1 = [0, 0, 0.05]
        assert dv[2] > 0  # 阻力向上（与速度方向相反）
        assert abs(dv[2] - 0.05) < 1e-10

    def test_drag_with_mass(self):
        """质量影响加速度。"""
        rule = LinearDragRule()
        state = {"velocity": [10, 0, 0], "mass": 2.0}
        inputs = {"drag_coefficient": 0.1, "dt": 0.1}
        delta = rule.apply(state, inputs)
        dv = delta["dv"]
        # dv = -(0.1/2.0) * [10, 0, 0] * 0.1 = [-0.05, 0, 0]
        assert abs(dv[0] - (-0.05)) < 1e-10

    def test_zero_velocity_no_drag(self):
        """零速度时无阻力。"""
        rule = LinearDragRule()
        state = {"velocity": [0, 0, 0], "mass": 1.0}
        inputs = {"drag_coefficient": 0.5, "dt": 0.1}
        delta = rule.apply(state, inputs)
        dv = delta["dv"]
        assert all(abs(v) < 1e-10 for v in dv)

    def test_default_coefficient(self):
        """默认阻力系数。"""
        rule = LinearDragRule()
        state = {"velocity": [10, 0, 0], "mass": 1.0}
        inputs = {"dt": 0.1}  # 无 drag_coefficient，使用默认 0.1
        delta = rule.apply(state, inputs)
        dv = delta["dv"]
        assert abs(dv[0] - (-0.1)) < 1e-10

    def test_rule_name(self):
        """规则名称正确。"""
        rule = LinearDragRule()
        assert rule.rule_name == "linear_drag"

    def test_required_inputs(self):
        """必要输入声明正确。"""
        rule = LinearDragRule()
        assert "drag_coefficient" in rule.required_inputs
        assert "dt" in rule.required_inputs


# =========================================================================
# DEFAULT_RULE_REGISTRY 中 drag 注册测试
# =========================================================================

class TestDragRegistration:
    """验证 LinearDragRule 已在默认注册表中注册。"""

    def test_drag_in_registry(self):
        assert DEFAULT_RULE_REGISTRY.get_persistent("linear_drag") is LinearDragRule


# =========================================================================
# Force Accumulator 单元测试
# =========================================================================

class TestForceAccumulator:
    """验证 force accumulator 正确叠加多规则 dv。"""

    def test_gravity_only(self):
        """仅重力时行为与之前一致。"""
        plan = ExecutionPlan(
            persistent_rule_plan=[
                {"rule_name": "constant_gravity", "applies_to": ["ball"]},
            ],
            assembly_plan={
                "velocity": {"entity": "ball", "field": "velocity"},
            },
        )
        ss = StateSet()
        ss.set_entity_state("ball", {
            "position": [0, 0, 100],
            "velocity": [0, 0, 0],
            "mass": 1.0,
        })
        scheduler = Scheduler(dt=0.1, steps=1)
        result = scheduler.run(plan, ss)
        vel = result.target_results["velocity"]
        # 1 step: dv = [0, 0, -9.8] * 0.1 = [0, 0, -0.98]
        assert abs(vel[2] - (-0.98)) < 1e-6

    def test_gravity_plus_drag_accumulation(self):
        """重力 + 阻力 dv 同步叠加。"""
        plan = ExecutionPlan(
            persistent_rule_plan=[
                {"rule_name": "constant_gravity", "applies_to": ["ball"]},
                {
                    "rule_name": "linear_drag",
                    "applies_to": ["ball"],
                    "rule_execution_inputs": {"drag_coefficient": 0.5},
                },
            ],
            assembly_plan={
                "velocity": {"entity": "ball", "field": "velocity"},
            },
        )
        ss = StateSet()
        ss.set_entity_state("ball", {
            "position": [0, 0, 100],
            "velocity": [0, 0, -10],
            "mass": 1.0,
        })
        scheduler = Scheduler(dt=0.1, steps=1)
        result = scheduler.run(plan, ss)
        vel = result.target_results["velocity"]

        # Gravity dv: [0, 0, -9.8] * 0.1 = [0, 0, -0.98]
        # Drag dv: -(0.5/1.0) * [0, 0, -10] * 0.1 = [0, 0, 0.5]
        # Total dv_z = -0.98 + 0.5 = -0.48
        # New v_z = -10 + (-0.48) = -10.48
        assert abs(vel[2] - (-10.48)) < 1e-6

    def test_force_accumulator_no_order_dependence(self):
        """规则顺序不影响叠加结果（力的叠加原理）。"""
        plan_gd = ExecutionPlan(
            persistent_rule_plan=[
                {"rule_name": "constant_gravity", "applies_to": ["ball"]},
                {
                    "rule_name": "linear_drag",
                    "applies_to": ["ball"],
                    "rule_execution_inputs": {"drag_coefficient": 0.5},
                },
            ],
            assembly_plan={"vel": {"entity": "ball", "field": "velocity"}},
        )
        plan_dg = ExecutionPlan(
            persistent_rule_plan=[
                {
                    "rule_name": "linear_drag",
                    "applies_to": ["ball"],
                    "rule_execution_inputs": {"drag_coefficient": 0.5},
                },
                {"rule_name": "constant_gravity", "applies_to": ["ball"]},
            ],
            assembly_plan={"vel": {"entity": "ball", "field": "velocity"}},
        )

        def run_plan(plan):
            ss = StateSet()
            ss.set_entity_state("ball", {
                "position": [0, 0, 100],
                "velocity": [5, 0, -10],
                "mass": 2.0,
            })
            return Scheduler(dt=0.1, steps=1).run(plan, ss)

        r1 = run_plan(plan_gd)
        r2 = run_plan(plan_dg)
        v1 = r1.target_results["vel"]
        v2 = r2.target_results["vel"]
        for a, b in zip(v1, v2):
            assert abs(a - b) < 1e-10


# =========================================================================
# 端到端：重力 + 阻力并行控制
# =========================================================================

class TestGravityPlusDragE2E:
    """重力 + 阻力同时作用的端到端验证。"""

    def test_falling_with_drag_reaches_terminal_velocity(self):
        """
        重力 + 阻力长时间演化后速度趋近终端速度。

        终端速度：v_terminal = mg/k
        m=1, g=9.8, k=0.98 → v_terminal = 10 m/s
        """
        plan = ExecutionPlan(
            persistent_rule_plan=[
                {"rule_name": "constant_gravity", "applies_to": ["ball"]},
                {
                    "rule_name": "linear_drag",
                    "applies_to": ["ball"],
                    "rule_execution_inputs": {"drag_coefficient": 0.98},
                },
            ],
            assembly_plan={
                "velocity": {"entity": "ball", "field": "velocity"},
            },
        )
        ss = StateSet()
        ss.set_entity_state("ball", {
            "position": [0, 0, 1000],
            "velocity": [0, 0, 0],
            "mass": 1.0,
        })
        # 长时间演化使速度趋近终端速度
        scheduler = Scheduler(dt=0.01, steps=5000)
        result = scheduler.run(plan, ss)
        vel = result.target_results["velocity"]
        # v_terminal = mg/k = 1*9.8/0.98 = 10 m/s（向下）
        assert abs(abs(vel[2]) - 10.0) < 0.5  # 接近终端速度

    def test_drag_slows_horizontal_motion(self):
        """阻力使水平速度衰减。"""
        plan = ExecutionPlan(
            persistent_rule_plan=[
                {
                    "rule_name": "linear_drag",
                    "applies_to": ["ball"],
                    "rule_execution_inputs": {"drag_coefficient": 0.5},
                },
            ],
            assembly_plan={
                "velocity": {"entity": "ball", "field": "velocity"},
            },
        )
        ss = StateSet()
        ss.set_entity_state("ball", {
            "position": [0, 0, 0],
            "velocity": [10, 0, 0],
            "mass": 1.0,
        })
        scheduler = Scheduler(dt=0.01, steps=1000)
        result = scheduler.run(plan, ss)
        vel = result.target_results["velocity"]
        # 纯阻力下水平速度应衰减趋近 0
        assert abs(vel[0]) < 1.0  # 显著衰减
        assert vel[0] > 0  # 保持正向

    def test_multi_entity_force_accumulation(self):
        """多实体同时受力，各自独立叠加。"""
        plan = ExecutionPlan(
            persistent_rule_plan=[
                {"rule_name": "constant_gravity", "applies_to": ["a", "b"]},
                {
                    "rule_name": "linear_drag",
                    "applies_to": ["a", "b"],
                    "rule_execution_inputs": {"drag_coefficient": 0.1},
                },
            ],
            assembly_plan={
                "va": {"entity": "a", "field": "velocity"},
                "vb": {"entity": "b", "field": "velocity"},
            },
        )
        ss = StateSet()
        ss.set_entity_state("a", {
            "position": [0, 0, 100],
            "velocity": [0, 0, 0],
            "mass": 1.0,
        })
        ss.set_entity_state("b", {
            "position": [10, 0, 100],
            "velocity": [5, 0, 0],
            "mass": 2.0,
        })
        scheduler = Scheduler(dt=0.1, steps=10)
        result = scheduler.run(plan, ss)

        va = result.target_results["va"]
        vb = result.target_results["vb"]
        # a 从静止下落：仅 z 分量变化
        assert abs(va[0]) < 1e-6
        assert va[2] < 0
        # b 有水平速度：x 分量衰减，z 分量下落
        assert vb[0] > 0  # 水平速度衰减但仍为正
        assert vb[0] < 5  # 小于初始值
        assert vb[2] < 0
