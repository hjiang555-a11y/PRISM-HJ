"""
Tests for P4 — DAG 调度器.

验证：
1. DAG 构建器（依赖关系编译为 DAG）
2. 条件分支路由（if-then-else 执行路径）
3. 同步点机制（多条并行分支的汇合）
4. 拓扑排序执行
"""

import pytest

from src.planning.scheduler import (
    DAGBuilder,
    DAGExecutionResult,
    DAGNode,
    DAGNodeType,
    DAGScheduler,
)


# =========================================================================
# DAGNode 单元测试
# =========================================================================

class TestDAGNode:
    """DAG 节点模型测试。"""

    def test_task_node(self):
        node = DAGNode(node_id="t1", node_type=DAGNodeType.TASK)
        assert node.node_type == DAGNodeType.TASK

    def test_condition_node(self):
        node = DAGNode(
            node_id="c1",
            node_type=DAGNodeType.CONDITION,
            condition_expr="has_drag",
            then_branch=["apply_drag"],
            else_branch=["skip_drag"],
        )
        assert node.node_type == DAGNodeType.CONDITION
        assert node.condition_expr == "has_drag"

    def test_sync_node(self):
        node = DAGNode(
            node_id="s1",
            node_type=DAGNodeType.SYNC,
            dependencies=["a", "b"],
        )
        assert node.node_type == DAGNodeType.SYNC
        assert node.dependencies == ["a", "b"]


# =========================================================================
# DAGBuilder 测试
# =========================================================================

class TestDAGBuilder:
    """DAG 构建器测试。"""

    def test_simple_linear_dag(self):
        """简单线性 DAG。"""
        builder = DAGBuilder()
        builder.add_task("a")
        builder.add_task("b", dependencies=["a"])
        builder.add_task("c", dependencies=["b"])
        dag = builder.build()
        assert len(dag) == 3
        assert dag["b"].dependencies == ["a"]
        assert dag["c"].dependencies == ["b"]

    def test_parallel_dag(self):
        """并行 DAG（多分支无互相依赖）。"""
        builder = DAGBuilder()
        builder.add_task("a")
        builder.add_task("b")
        builder.add_task("c", dependencies=["a", "b"])
        dag = builder.build()
        assert len(dag) == 3
        assert dag["c"].dependencies == ["a", "b"]

    def test_dag_with_sync(self):
        """DAG + 同步点。"""
        builder = DAGBuilder()
        builder.add_task("gravity", capability_name="particle_motion")
        builder.add_task("drag", capability_name="particle_motion")
        builder.add_sync("sync_forces", dependencies=["gravity", "drag"])
        builder.add_task("advance", dependencies=["sync_forces"])
        dag = builder.build()
        assert dag["sync_forces"].node_type == DAGNodeType.SYNC
        assert dag["advance"].dependencies == ["sync_forces"]

    def test_dag_with_condition(self):
        """DAG + 条件分支。"""
        builder = DAGBuilder()
        builder.add_task("init")
        builder.add_condition(
            "check_drag",
            condition_expr="has_drag",
            then_branch=["apply_drag"],
            else_branch=["no_drag"],
            dependencies=["init"],
        )
        builder.add_task("apply_drag", dependencies=["check_drag"])
        builder.add_task("no_drag", dependencies=["check_drag"])
        builder.add_sync("join", dependencies=["apply_drag", "no_drag"])
        dag = builder.build()
        assert dag["check_drag"].node_type == DAGNodeType.CONDITION

    def test_cycle_detection(self):
        """环路检测应抛出 ValueError。"""
        builder = DAGBuilder()
        builder.add_task("a", dependencies=["b"])
        builder.add_task("b", dependencies=["a"])
        with pytest.raises(ValueError, match="cycle"):
            builder.build()

    def test_missing_dependency(self):
        """缺失依赖应抛出 ValueError。"""
        builder = DAGBuilder()
        builder.add_task("a", dependencies=["nonexistent"])
        with pytest.raises(ValueError, match="unknown node"):
            builder.build()

    def test_missing_branch_node(self):
        """条件分支引用缺失节点应抛出 ValueError。"""
        builder = DAGBuilder()
        builder.add_condition(
            "c1",
            condition_expr="test",
            then_branch=["missing_node"],
        )
        with pytest.raises(ValueError, match="unknown"):
            builder.build()

    def test_empty_dag(self):
        """空 DAG。"""
        builder = DAGBuilder()
        dag = builder.build()
        assert len(dag) == 0

    def test_single_node(self):
        """单节点 DAG。"""
        builder = DAGBuilder()
        builder.add_task("only")
        dag = builder.build()
        assert len(dag) == 1

    def test_builder_chaining(self):
        """链式构建。"""
        builder = (
            DAGBuilder()
            .add_task("a")
            .add_task("b", dependencies=["a"])
            .add_sync("s", dependencies=["a", "b"])
        )
        dag = builder.build()
        assert len(dag) == 3


# =========================================================================
# DAGScheduler 执行测试
# =========================================================================

class TestDAGScheduler:
    """DAG 调度器执行测试。"""

    def test_linear_execution_order(self):
        """线性 DAG 按顺序执行。"""
        builder = DAGBuilder()
        builder.add_task("a")
        builder.add_task("b", dependencies=["a"])
        builder.add_task("c", dependencies=["b"])
        dag = builder.build()

        scheduler = DAGScheduler(dag)
        result = scheduler.execute()
        assert result.executed_nodes == ["a", "b", "c"]
        assert len(result.skipped_nodes) == 0

    def test_parallel_execution_layers(self):
        """并行节点在同一层执行。"""
        builder = DAGBuilder()
        builder.add_task("a")
        builder.add_task("b")
        builder.add_task("c", dependencies=["a", "b"])
        dag = builder.build()

        scheduler = DAGScheduler(dag)
        result = scheduler.execute()

        # a 和 b 应在同一层
        assert len(result.execution_order) == 2
        first_layer = set(result.execution_order[0])
        assert first_layer == {"a", "b"}
        assert result.execution_order[1] == ["c"]

    def test_condition_true_path(self):
        """条件为 True 时执行 then 分支。"""
        builder = DAGBuilder()
        builder.add_task("init")
        builder.add_condition(
            "check",
            condition_expr="has_drag",
            then_branch=["apply_drag"],
            else_branch=["skip_drag"],
            dependencies=["init"],
        )
        builder.add_task("apply_drag", dependencies=["check"])
        builder.add_task("skip_drag", dependencies=["check"])
        dag = builder.build()

        scheduler = DAGScheduler(dag)
        result = scheduler.execute(context={"has_drag": True})

        assert "apply_drag" in result.executed_nodes
        assert "skip_drag" in result.skipped_nodes

    def test_condition_false_path(self):
        """条件为 False 时执行 else 分支。"""
        builder = DAGBuilder()
        builder.add_task("init")
        builder.add_condition(
            "check",
            condition_expr="has_drag",
            then_branch=["apply_drag"],
            else_branch=["skip_drag"],
            dependencies=["init"],
        )
        builder.add_task("apply_drag", dependencies=["check"])
        builder.add_task("skip_drag", dependencies=["check"])
        dag = builder.build()

        scheduler = DAGScheduler(dag)
        result = scheduler.execute(context={"has_drag": False})

        assert "skip_drag" in result.executed_nodes
        assert "apply_drag" in result.skipped_nodes

    def test_sync_point(self):
        """同步点等待所有前驱完成。"""
        builder = DAGBuilder()
        builder.add_task("gravity")
        builder.add_task("drag")
        builder.add_sync("sync_forces", dependencies=["gravity", "drag"])
        builder.add_task("advance", dependencies=["sync_forces"])
        dag = builder.build()

        scheduler = DAGScheduler(dag)
        result = scheduler.execute()

        # sync_forces 在 gravity 和 drag 之后
        assert result.executed_nodes.index("sync_forces") > \
               result.executed_nodes.index("gravity")
        assert result.executed_nodes.index("sync_forces") > \
               result.executed_nodes.index("drag")
        # advance 在 sync_forces 之后
        assert result.executed_nodes.index("advance") > \
               result.executed_nodes.index("sync_forces")

    def test_custom_task_executor(self):
        """自定义任务执行器。"""
        results_log = []

        def my_executor(node, ctx):
            results_log.append(node.node_id)
            return {"done": True, "cap": node.capability_name}

        builder = DAGBuilder()
        builder.add_task("t1", capability_name="motion")
        builder.add_task("t2", capability_name="drag", dependencies=["t1"])
        dag = builder.build()

        scheduler = DAGScheduler(dag, task_executor=my_executor)
        result = scheduler.execute()
        assert results_log == ["t1", "t2"]
        assert result.node_results["t1"]["cap"] == "motion"
        assert result.node_results["t2"]["cap"] == "drag"

    def test_custom_condition_evaluator(self):
        """自定义条件评估器。"""
        def my_evaluator(expr, ctx):
            return expr == "always_true"

        builder = DAGBuilder()
        builder.add_condition(
            "c1",
            condition_expr="always_true",
            then_branch=["yes"],
            else_branch=["no"],
        )
        builder.add_task("yes", dependencies=["c1"])
        builder.add_task("no", dependencies=["c1"])
        dag = builder.build()

        scheduler = DAGScheduler(dag, condition_evaluator=my_evaluator)
        result = scheduler.execute()
        assert "yes" in result.executed_nodes
        assert "no" in result.skipped_nodes

    def test_empty_dag(self):
        """空 DAG 执行。"""
        scheduler = DAGScheduler({})
        result = scheduler.execute()
        assert result.executed_nodes == []

    def test_complex_dag(self):
        """
        复杂 DAG：
        init → check_drag → [apply_drag | no_drag] → sync → output
                            ↗ gravity (parallel)    ↗
        """
        builder = DAGBuilder()
        builder.add_task("init")
        builder.add_task("gravity", dependencies=["init"])
        builder.add_condition(
            "check_drag",
            condition_expr="drag_enabled",
            then_branch=["apply_drag"],
            else_branch=["no_drag"],
            dependencies=["init"],
        )
        builder.add_task("apply_drag", dependencies=["check_drag"])
        builder.add_task("no_drag", dependencies=["check_drag"])
        builder.add_sync(
            "sync",
            dependencies=["gravity", "apply_drag", "no_drag"],
        )
        builder.add_task("output", dependencies=["sync"])
        dag = builder.build()

        # with drag enabled
        scheduler = DAGScheduler(dag)
        result = scheduler.execute(context={"drag_enabled": True})

        assert "init" in result.executed_nodes
        assert "gravity" in result.executed_nodes
        assert "apply_drag" in result.executed_nodes
        assert "no_drag" in result.skipped_nodes
        assert "sync" in result.executed_nodes
        assert "output" in result.executed_nodes


# =========================================================================
# DAGExecutionResult 测试
# =========================================================================

class TestDAGExecutionResult:
    """DAG 执行结果模型测试。"""

    def test_result_model(self):
        result = DAGExecutionResult(
            executed_nodes=["a", "b"],
            skipped_nodes=["c"],
            node_results={"a": 1, "b": 2},
            execution_order=[["a"], ["b"]],
        )
        assert result.executed_nodes == ["a", "b"]
        assert result.skipped_nodes == ["c"]


# =========================================================================
# 拓扑分层测试
# =========================================================================

class TestTopologicalLayers:
    """拓扑排序分层验证。"""

    def test_diamond_dag(self):
        """菱形 DAG 分层。"""
        builder = DAGBuilder()
        builder.add_task("root")
        builder.add_task("left", dependencies=["root"])
        builder.add_task("right", dependencies=["root"])
        builder.add_task("bottom", dependencies=["left", "right"])
        dag = builder.build()

        scheduler = DAGScheduler(dag)
        result = scheduler.execute()

        # root 在第一层
        assert result.execution_order[0] == ["root"]
        # left 和 right 在第二层
        assert set(result.execution_order[1]) == {"left", "right"}
        # bottom 在第三层
        assert result.execution_order[2] == ["bottom"]

    def test_wide_parallel(self):
        """宽并行 DAG。"""
        builder = DAGBuilder()
        for i in range(5):
            builder.add_task(f"task_{i}")
        builder.add_sync("join", dependencies=[f"task_{i}" for i in range(5)])
        dag = builder.build()

        scheduler = DAGScheduler(dag)
        result = scheduler.execute()

        # 所有 task_* 在第一层
        assert len(result.execution_order[0]) == 5
        # join 在第二层
        assert result.execution_order[1] == ["join"]
