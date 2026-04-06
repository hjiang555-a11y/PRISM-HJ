# 《PRISM-HJ 新执行核心接口草案 v0.1》

> 本文档为接口草案，仅定义职责边界和字段规格。不包含 Python 实现、dataclass 或 Pydantic 模型定义。

---

## 1. 总体原则

- **核心执行单位不是题型，而是状态集**。执行过程围绕 target-related state sets 展开，而非预定义的场景类型（如 `free_fall`、`projectile`）。
- **规则不是 solver，而是 primitive rules**。每条规则表达一个基础物理关系，可独立声明，可与其他规则叠加共同作用，不与特定场景绑定。
- **domain 不是执行互斥条件**。`classical_mechanics`、`electromagnetism` 等 domain 是规则的命名空间，执行时 active rule set 可同时包含多个 domain 的规则。
- **事件的本质是局部规则激活**。事件不是独立的执行分支，而是特定时空条件满足时局部规则被激活的过程；条件不再满足时规则失活。

---

## 2. 六类接口

---

### 2.1 Event Extraction Interface

**职责**：从输入信息中提取执行所需的结构化规格，为后续状态集初始化和规则调度提供依据。

**输入**：
- 自然语言描述
- 结构化场景描述
- 模板提取结果（可选）

**输出**：`EventExtractionResult`，包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `candidate_domains` | list[str] | 候选物理领域，可为多值，如 `["classical_mechanics", "electromagnetism"]` |
| `entities` | list[EntitySpec] | 参与演化的实体列表（含质量、电荷等属性） |
| `target_state_set_spec` | TargetStateSetSpec | 目标状态集规格（见 2.2） |
| `persistent_rule_candidates` | list[str] | 候选持续规则名称列表（按命名规范） |
| `local_rule_candidates` | list[str] | 候选局部触发规则名称列表 |
| `spatiotemporal_conditions` | list[SpatiotemporalCondition] | 时空约束条件列表 |
| `frame_context` | FrameContextSpec | 参考系上下文 |
| `initial_conditions` | list[InitialConditionSpec] | 各实体初始状态 |

**注意**：
- `candidate_domains` 不是单值字段。一个物理场景可能同时涉及多个 domain。
- 输出中不包含 `scenario_type` 字段；旧有的场景类型分类不再作为执行路由的依据。

---

### 2.2 State Set Interface

**职责**：定义和维护目标相关实体的状态变量集合及其时空范围。

`TargetStateSetSpec` 最小组成建议：

| 字段 | 类型 | 说明 |
|------|------|------|
| `tracked_entities` | list[EntityRef] | 需要追踪状态的实体引用列表 |
| `state_variables` | list[StateVariableSpec] | 每个实体需要追踪的状态变量（位置、速度、电荷分布等） |
| `relations` | list[RelationSpec] | 实体间的关系约束（如相对位置、接触状态） |
| `time_scope` | TimeScopeSpec | 演化的时间范围（起始时刻、终止条件） |
| `space_scope` | SpaceScopeSpec | 演化的空间范围（边界、参考系） |
| `frame` | FrameRef | 主参考系引用 |

---

### 2.3 Primitive Rule Interface

**职责**：声明一条基础物理规则的激活条件、适用对象和状态贡献。

每条 `PrimitiveRuleSpec` 至少应声明：

| 字段 | 类型 | 说明 |
|------|------|------|
| `domain` | str | 所属物理领域，如 `classical_mechanics` |
| `family` | str | 规则族，如 `background`、`contact`、`field` |
| `rule_name` | str | 规则名称，如 `constant_gravity` |
| `model_tag` | str \| None | 可选物理模型标记，如 `point_mass`、`rigid_body` |
| `applies_to` | list[EntityRef] | 适用的实体引用列表（空列表表示全局适用） |
| `required_inputs` | list[str] | 计算所需的输入状态变量名称 |
| `activation_mode` | str | 激活模式（见下） |
| `preconditions` | list[TriggerConditionSpec] | 规则激活所需满足的前置条件（`triggered` / `windowed` 模式适用） |
| `state_contributions` | list[StateContributionSpec] | 规则对状态变量的贡献描述（如力、加速度增量） |
| `output_effects` | list[EffectSpec] | 规则产生的可观测效应（如速度阶跃） |

**完整规则名称**遵循命名规范：`<domain>.<family>.<rule_name>[.<model_tag>]`

**`activation_mode` 取值**：

| 值 | 含义 |
|----|------|
| `persistent` | 持续激活，始终贡献于状态演化（如重力、静电场） |
| `triggered` | 条件触发，满足 preconditions 时激活，条件不再满足时失活（如碰撞接触力） |
| `windowed` | 在指定时间窗口内激活（如有限时长的脉冲力） |

---

### 2.4 Trigger Condition Interface

**职责**：声明局部规则激活或失活所需的时空条件。

`TriggerConditionSpec` 应支持以下条件类型：

| 条件类型 | 说明 |
|----------|------|
| 时间条件 | 满足 `t >= t_start` 且/或 `t <= t_end` |
| 空间接触条件 | 两实体的几何边界发生接触 |
| 距离阈值条件 | 两实体间距离小于/大于指定阈值 |
| 区域进入/离开条件 | 实体进入或离开指定空间区域 |
| 状态阈值条件 | 某状态变量的值超过/低于指定阈值 |
| 组合条件 | 上述条件的逻辑组合（`AND` / `OR`） |

---

### 2.5 Evolution Scheduling Interface

**职责**：执行核心的控制中心，负责整个状态集演化过程的调度与推进。

`EvolutionScheduleConfig` 是 Evolution Scheduling 阶段的调度参数配置对象，指定调度运行时所需的配置。请注意：`EvolutionScheduleConfig` 是执行层面的具体调度参数对象，而非 Execution Plan Layer 的规划对象——后者为 `ExecutionPlan`（架构级规划对象，详见 [`PRISM_representation_layers_architecture_decision.md`](PRISM_representation_layers_architecture_decision.md)）；`ExecutionPlan` 编排完成后驱动本调度配置。

调度器在运行时执行以下职责：

- **初始化 active rule set**：将所有 persistent rules 加入 active rule set
- **维护 persistent rules**：persistent rules 在整个演化过程中始终处于激活状态
- **评估触发条件**：在每个时间步（或事件驱动的评估点）检查所有 triggered / windowed rules 的 preconditions
- **激活/失活 local rules**：条件满足时激活对应的 local rule，加入 active rule set；条件不再满足时失活并移除
- **汇总 state contributions**：将当前 active rule set 中所有规则对状态变量的贡献叠加
- **推进状态集更新**：根据叠加后的贡献计算下一时刻的状态
- **记录触发点和规则变更**：维护完整的触发历史和规则激活/失活记录，供 Result Assembly 使用

调度器必须支持：

- **多对象并发演化**：多个实体的状态可在同一时间步内同时更新
- **跨领域规则共同作用**：active rule set 可同时包含来自多个 domain 的规则，各规则的贡献可叠加
- **局部规则短时激活**：triggered rules 的激活窗口可以任意短，不影响其他规则的持续贡献
- **持续规则始终存在**：persistent rules 的贡献在任何时间步都不会因局部规则的激活/失活而中断

---

### 2.6 Result Assembly Interface

**职责**：从状态集演化结果、触发记录和规则历史中提取面向目标的输出。

**输入**：`AssemblyRequest`，包含：
- 演化完成的状态集快照
- 触发记录（trigger log）
- 规则激活/失活历史（rule change log）
- 目标量规格（用户关心的物理量）

**输出**：`AssemblyResult`，包含：
- 目标物理量的数值及单位
- 关键事件时间点（如碰撞发生时刻、最高点时刻）
- 可选的状态轨迹摘要

**原则**：
- 输出面向用户关心的物理量，而不是底层状态变量的原始结构
- 对于跨领域场景，输出应能反映多个 domain 规则共同作用的综合效果
- 结果中应包含足够的溯源信息，支持验证和审计

---

## 3. 多领域融合要求

以下要求在接口设计中必须被满足：

- **`candidate_domains` 不是单值**。Event Extraction 的输出中，`candidate_domains` 是一个列表，允许同时声明多个物理领域。
- **`active_rule_set` 可以跨领域**。Evolution Scheduling 维护的 active rule set 可以同时包含来自 `classical_mechanics`、`electromagnetism` 等不同 domain 的规则。
- **规则贡献必须可合成**。每条规则通过 `state_contributions` 声明自己对状态变量的贡献；调度器将多条规则的贡献线性叠加（或按物理定义的方式合成），不存在"一条规则排斥另一条"的执行逻辑。
- **未来支持 classical mechanics 与 electromagnetism 等共同作用**。例如，一个带电粒子同时受 `classical_mechanics.background.constant_gravity` 和 `electromagnetism.field.lorentz_force` 约束时，两条规则均处于 active 状态，其贡献在每个时间步叠加后共同推进状态集更新。

---

## 4. 第一批最小接口建议

以下是推荐在第一批实现中定义的最小接口名称，对应执行核心各阶段的关键数据结构：

| 接口名 | 对应阶段 | 说明 |
|--------|----------|------|
| `EventExtractionResult` | Event Extraction | 事件提取的完整输出结构 |
| `TargetStateSetSpec` | State Set | 目标状态集规格 |
| `PrimitiveRuleSpec` | Primitive Rule | 单条 primitive rule 的完整声明 |
| `TriggerConditionSpec` | Trigger Condition | 单个触发条件的规格 |
| `EvolutionScheduleConfig` | Evolution Scheduling | 调度参数配置 |
| `AssemblyRequest` | Result Assembly | 结果汇总请求 |
| `AssemblyResult` | Result Assembly | 结果汇总输出 |

这些接口名称是后续实现的锚点，命名应保持稳定。具体字段可在实现阶段根据原型验证结果调整。
