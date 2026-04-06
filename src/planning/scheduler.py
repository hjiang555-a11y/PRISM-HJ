"""
DAGScheduler — 高层 DAG 构建器与调度器 v0.1.

将能力依赖关系编译为有向无环图（DAG），支持：
- 条件分支路由（if-then-else 执行路径）
- 同步点机制（多条并行分支的汇合）
- 拓扑排序执行

设计思路
--------
DAG 中的每个节点代表一个执行阶段（DAGNode），可以是：
- TASK:      普通执行任务（单一能力或规则集合）
- CONDITION: 条件分支节点（根据谓词路由到 then/else 分支）
- SYNC:      同步点节点（等待所有前驱完成后再继续）

DAGScheduler 将 CapabilitySpec 依赖关系编译为 DAG，然后
按拓扑排序执行节点，支持并行分支和条件路由。
"""

from __future__ import annotations

from collections import defaultdict, deque
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 节点类型
# ---------------------------------------------------------------------------

class DAGNodeType(str, Enum):
    """DAG 节点类型。"""
    TASK = "task"               # 普通执行任务
    CONDITION = "condition"     # 条件分支节点
    SYNC = "sync"               # 同步点节点


# ---------------------------------------------------------------------------
# DAG 节点
# ---------------------------------------------------------------------------

class DAGNode(BaseModel):
    """
    DAG 中的单个执行节点。

    Attributes
    ----------
    node_id:
        节点唯一标识。
    node_type:
        节点类型（TASK / CONDITION / SYNC）。
    capability_name:
        关联的能力名称（TASK 节点）。
    dependencies:
        前驱节点 ID 列表。
    metadata:
        附加元数据（规则参数、条件表达式等）。
    then_branch:
        条件为 True 时的后继节点 ID 列表（仅 CONDITION 节点）。
    else_branch:
        条件为 False 时的后继节点 ID 列表（仅 CONDITION 节点）。
    condition_expr:
        条件表达式字符串（仅 CONDITION 节点）。
    """

    node_id: str
    node_type: DAGNodeType = DAGNodeType.TASK
    capability_name: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    then_branch: List[str] = Field(default_factory=list)
    else_branch: List[str] = Field(default_factory=list)
    condition_expr: Optional[str] = None


# ---------------------------------------------------------------------------
# DAG 执行结果
# ---------------------------------------------------------------------------

class DAGExecutionResult(BaseModel):
    """DAG 执行结果。"""
    executed_nodes: List[str] = Field(
        default_factory=list,
        description="已执行节点 ID 列表（按执行顺序）",
    )
    skipped_nodes: List[str] = Field(
        default_factory=list,
        description="因条件分支跳过的节点 ID 列表",
    )
    node_results: Dict[str, Any] = Field(
        default_factory=dict,
        description="各节点的执行结果",
    )
    execution_order: List[List[str]] = Field(
        default_factory=list,
        description="分层执行顺序（每层内可并行）",
    )


# ---------------------------------------------------------------------------
# DAG 构建器
# ---------------------------------------------------------------------------

class DAGBuilder:
    """
    从能力依赖关系构建 DAG。

    Examples
    --------
    >>> builder = DAGBuilder()
    >>> builder.add_task("gravity", capability_name="particle_motion")
    >>> builder.add_task("drag", capability_name="particle_motion", dependencies=["gravity"])
    >>> builder.add_sync("sync_forces", dependencies=["gravity", "drag"])
    >>> dag = builder.build()
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, DAGNode] = {}

    def add_task(
        self,
        node_id: str,
        capability_name: Optional[str] = None,
        dependencies: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DAGBuilder:
        """添加普通任务节点。"""
        self._nodes[node_id] = DAGNode(
            node_id=node_id,
            node_type=DAGNodeType.TASK,
            capability_name=capability_name,
            dependencies=dependencies or [],
            metadata=metadata or {},
        )
        return self

    def add_condition(
        self,
        node_id: str,
        condition_expr: str,
        then_branch: Optional[List[str]] = None,
        else_branch: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DAGBuilder:
        """添加条件分支节点。"""
        self._nodes[node_id] = DAGNode(
            node_id=node_id,
            node_type=DAGNodeType.CONDITION,
            condition_expr=condition_expr,
            then_branch=then_branch or [],
            else_branch=else_branch or [],
            dependencies=dependencies or [],
            metadata=metadata or {},
        )
        return self

    def add_sync(
        self,
        node_id: str,
        dependencies: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DAGBuilder:
        """添加同步点节点。"""
        self._nodes[node_id] = DAGNode(
            node_id=node_id,
            node_type=DAGNodeType.SYNC,
            dependencies=dependencies or [],
            metadata=metadata or {},
        )
        return self

    def build(self) -> Dict[str, DAGNode]:
        """
        构建并验证 DAG，返回节点字典。

        Raises
        ------
        ValueError
            若 DAG 存在环路或缺失依赖。
        """
        # 验证依赖引用
        for node_id, node in self._nodes.items():
            for dep in node.dependencies:
                if dep not in self._nodes:
                    raise ValueError(
                        f"Node '{node_id}' depends on unknown node '{dep}'"
                    )
            for branch_id in node.then_branch + node.else_branch:
                if branch_id not in self._nodes:
                    raise ValueError(
                        f"Condition node '{node_id}' references unknown "
                        f"branch node '{branch_id}'"
                    )

        # 检测环路
        if self._has_cycle():
            raise ValueError("DAG contains a cycle")

        return dict(self._nodes)

    def _has_cycle(self) -> bool:
        """使用 DFS 检测环路。"""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {nid: WHITE for nid in self._nodes}

        def dfs(nid: str) -> bool:
            color[nid] = GRAY
            node = self._nodes[nid]
            for dep in node.dependencies:
                if color[dep] == GRAY:
                    return True
                if color[dep] == WHITE and dfs(dep):
                    return True
            color[nid] = BLACK
            return False

        for nid in self._nodes:
            if color[nid] == WHITE:
                if dfs(nid):
                    return True
        return False


# ---------------------------------------------------------------------------
# DAG 调度器
# ---------------------------------------------------------------------------

class DAGScheduler:
    """
    DAG 调度器：按拓扑排序执行 DAG 节点。

    支持条件分支路由和同步点汇合。

    Parameters
    ----------
    nodes:
        由 DAGBuilder.build() 构造的节点字典。
    task_executor:
        任务执行函数，接受 (node, context) 返回执行结果。
    condition_evaluator:
        条件评估函数，接受 (condition_expr, context) 返回 bool。
    """

    def __init__(
        self,
        nodes: Dict[str, DAGNode],
        task_executor: Optional[Callable[[DAGNode, Dict[str, Any]], Any]] = None,
        condition_evaluator: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
    ) -> None:
        self._nodes = nodes
        self._task_executor = task_executor or self._default_executor
        self._condition_evaluator = condition_evaluator or self._default_evaluator

    def execute(self, context: Optional[Dict[str, Any]] = None) -> DAGExecutionResult:
        """
        按拓扑排序执行 DAG。

        Parameters
        ----------
        context:
            执行上下文（传递给 task_executor 和 condition_evaluator）。

        Returns
        -------
        DAGExecutionResult
            执行结果，包含已执行和跳过的节点。
        """
        ctx = dict(context) if context else {}
        executed: List[str] = []
        skipped: List[str] = []
        node_results: Dict[str, Any] = {}
        execution_order: List[List[str]] = []

        # 拓扑排序（Kahn's algorithm），返回分层执行顺序
        layers = self._topological_layers()

        # 被条件分支禁用的节点
        disabled: Set[str] = set()

        for layer in layers:
            layer_executed: List[str] = []
            for node_id in layer:
                if node_id in disabled:
                    skipped.append(node_id)
                    continue

                node = self._nodes[node_id]

                # 检查所有前驱是否已执行（或被跳过）
                deps_met = all(
                    dep in executed or dep in skipped
                    for dep in node.dependencies
                )
                if not deps_met:
                    skipped.append(node_id)
                    continue

                if node.node_type == DAGNodeType.CONDITION:
                    # 评估条件
                    cond_result = self._condition_evaluator(
                        node.condition_expr or "", ctx
                    )
                    node_results[node_id] = {"condition": cond_result}
                    executed.append(node_id)
                    layer_executed.append(node_id)

                    # 路由：禁用未选分支
                    if cond_result:
                        for nid in node.else_branch:
                            disabled.add(nid)
                    else:
                        for nid in node.then_branch:
                            disabled.add(nid)

                elif node.node_type == DAGNodeType.SYNC:
                    # 同步点：等待所有前驱完成
                    node_results[node_id] = {"sync": True}
                    executed.append(node_id)
                    layer_executed.append(node_id)

                else:  # TASK
                    result = self._task_executor(node, ctx)
                    node_results[node_id] = result
                    executed.append(node_id)
                    layer_executed.append(node_id)

            if layer_executed:
                execution_order.append(layer_executed)

        return DAGExecutionResult(
            executed_nodes=executed,
            skipped_nodes=skipped,
            node_results=node_results,
            execution_order=execution_order,
        )

    def _topological_layers(self) -> List[List[str]]:
        """
        按拓扑排序分层，同层节点可并行执行。

        Returns
        -------
        List[List[str]]
            分层节点 ID 列表。
        """
        # 计算入度
        in_degree: Dict[str, int] = {nid: 0 for nid in self._nodes}
        # 构建 adjacency（谁依赖谁 → 反向：谁完成后可以解锁谁）
        successors: Dict[str, List[str]] = defaultdict(list)

        for nid, node in self._nodes.items():
            for dep in node.dependencies:
                successors[dep].append(nid)
                in_degree[nid] += 1

        # BFS 分层
        layers: List[List[str]] = []
        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)

        while queue:
            layer = list(queue)
            layers.append(layer)
            next_queue: deque = deque()
            for nid in layer:
                for succ in successors[nid]:
                    in_degree[succ] -= 1
                    if in_degree[succ] == 0:
                        next_queue.append(succ)
            queue = next_queue

        return layers

    @staticmethod
    def _default_executor(node: DAGNode, context: Dict[str, Any]) -> Any:
        """默认任务执行器：返回节点元数据。"""
        return {"node_id": node.node_id, "status": "completed"}

    @staticmethod
    def _default_evaluator(condition_expr: str, context: Dict[str, Any]) -> bool:
        """默认条件评估器：从上下文中查找条件值。"""
        return bool(context.get(condition_expr, False))
