# PRISM-HJ 架构文档

## 概述

PRISM-HJ（Physical Reasoning & Inference System for Mechanics — HJ）采用**三层表示 + 规则驱动执行**架构，将"自然语言"与"确定性物理执行"完全解耦，使每一层都可独立测试、替换和审计。

---

## 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│   自然语言输入                                                │
│   "一个2kg的球从高度5米自由落体，1秒后位置和速度？"             │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  第一层：问题语义层 (Problem Semantic Layer)                   │
│  src/problem_semantic/extraction/pipeline.py                │
│  职责：从 NL 中提取实体、条件、关心目标、admission hints       │
│  产出：ProblemSemanticSpec                                   │
├─────────────────────────────────────────────────────────────┤
│  第二层：能力表示层 (Capability Representation Layer)          │
│  src/capabilities/builder.py + particle_motion/ +            │
│  contact_interaction/                                        │
│  职责：将语义输出映射为能力规格，声明规则候选与适用条件           │
│  产出：List[CapabilitySpec]                                  │
├─────────────────────────────────────────────────────────────┤
│  第三层：执行计划层 (Execution Plan Layer)                     │
│  src/planning/execution_plan/builder.py                      │
│  职责：准入判定（admitted/deferred/unresolved），编排规则计划    │
│  产出：ExecutionPlan                                         │
├─────────────────────────────────────────────────────────────┤
│  执行核心 (Execution Core)                                    │
│  src/execution/runtime/scheduler.py +                        │
│  trigger_engine.py + rules/ + state/ + assembly/             │
│  职责：时间步进演化、触发检测、状态更新、结果组装               │
│  产出：ExecutionResult                                       │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  自然语言回答层                                               │
│  src/llm/translator.py :: generate_answer()                  │
│  职责：将执行结果翻译为自然语言答案                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 第一层：问题语义层 (Problem Semantic Layer)

**模块**：`src/problem_semantic/`

- `extraction/pipeline.py` — 入口函数 `extract_problem_semantics()`
- `extraction/extractors.py` — 场景参数正则提取器
- `models.py` — `ProblemSemanticSpec` 模型定义

**职责**：
- 从自然语言中提取物理实体（`entities`）、关心目标（`targets_of_interest`）、显式条件（`explicit_conditions`）
- 识别候选能力族（`candidate_capabilities`）和候选物理领域（`candidate_domains`）
- 收集规则提取依据（`rule_extraction_inputs`）和规则执行输入（`rule_execution_inputs`）
- 提取四类准入提示（admission hints）：`entity_model_hints`、`interaction_hints`、`assumption_hints`、`query_hints`
- 记录无法解析的项目（`unresolved_items`）

**不负责**：
- 不决定使用哪条 primitive rule
- 不执行物理计算
- 不生成执行计划

**产出**：`ProblemSemanticSpec`

详见：[事件提取最小输出契约 v0.1](PRISM_event_extraction_minimum_contract_v0_1.md)

---

## 第二层：能力表示层 (Capability Representation Layer)

**模块**：`src/capabilities/`

- `builder.py` — 语义 → 能力列表路由（`build_capability_specs()`）
- `common/base.py` — `CapabilitySpec` 基类
- `common/kinds.py` — 能力种类常量
- `particle_motion/spec.py` — `ParticleMotionCapabilitySpec`
- `particle_motion/mapper.py` — 语义 → 粒子运动能力映射
- `contact_interaction/spec.py` — `ContactInteractionCapabilitySpec`
- `contact_interaction/mapper.py` — 语义 → 接触交互能力映射

**职责**：
- 针对每个候选能力族生成 `CapabilitySpec`
- 声明适用条件（`applicability_conditions`）、物理假设（`assumptions`）、有效边界（`validity_limits`）
- 声明必要入口要素（`required_entry_inputs`）并计算缺失项（`missing_entry_inputs`）
- 声明候选规则（persistent / local）

**产出**：`List[CapabilitySpec]`（当前支持 `ParticleMotionCapabilitySpec`、`ContactInteractionCapabilitySpec`）

详见：[能力适用条件与入口要素约定 v0.1](PRISM_capability_admission_conditions_and_entry_inputs_v0_1.md)

---

## 第三层：执行计划层 (Execution Plan Layer)

**模块**：`src/planning/`

- `execution_plan/models.py` — `ExecutionPlan` 模型
- `execution_plan/builder.py` — `build_execution_plan()`
- `scheduler.py` — DAG 调度器（`DAGBuilder`、`DAGScheduler`，规划中）

**职责**：
- 对每个 `CapabilitySpec` 执行三态准入判定：
  - `admitted`：适用实体非空且入口要素齐全 → 进入规则计划
  - `deferred`：适用实体非空但入口要素不全 → 暂不执行
  - `unresolved`：适用实体为空 → 无法执行
- 生成 `persistent_rule_plan` 和 `local_rule_plan`
- 编排 `assembly_plan`（结果组装目标量）
- 传播 admission hints 至执行核心

**产出**：`ExecutionPlan`

---

## 执行核心 (Execution Core)

**模块**：`src/execution/`

### 运行时调度（runtime/）

| 模块 | 职责 |
|------|------|
| `scheduler.py` | 时间步进主循环：初始化 active rule set → 每步施加持久规则 → 检查触发条件 → 汇总 state contributions → 推进状态 |
| `trigger_engine.py` | 触发条件检测：碰撞（距离阈值）、边界穿透、状态阈值 |

### 规则系统（rules/）

| 模块 | 职责 |
|------|------|
| `persistent/gravity.py` | `ConstantGravityRule`：恒定重力加速度（每步叠加 dv） |
| `persistent/drag.py` | `LinearDragRule`：线性阻力（每步叠加 dv） |
| `persistent/base.py` | `PersistentRuleExecutor` 抽象基类 |
| `local/impulsive_collision.py` | `ImpulsiveCollisionRule`：瞬时碰撞（动量守恒 + 恢复系数） |
| `local/base.py` | `LocalRuleExecutor` 抽象基类 |
| `registry.py` | `RuleRegistry`：规则注册表（injectable，支持外部扩展） |

**力累加器设计**：Scheduler 在每个时间步中，先从所有 persistent rules 收集每个实体的 dv 贡献，然后一次性叠加。规则看到的是更新前的速度（无顺序依赖）。

### 状态管理（state/）

| 模块 | 职责 |
|------|------|
| `state_set.py` | `StateSet`：多实体状态集合（position、velocity、mass） |

### 结果组装（assembly/）

| 模块 | 职责 |
|------|------|
| `result_assembler.py` | `ResultAssembler` → `ExecutionResult`（目标结果、触发记录、执行备注） |

---

## 辅助模块

### 自然语言接口（llm/）

| 模块 | 职责 |
|------|------|
| `translator.py` | `classify_scenario()`：轻量规则场景分类器；`generate_answer()`：后处理自然语言答案生成 |

### PSDL 数据模型（schema/）

| 模块 | 职责 |
|------|------|
| `psdl.py` | PSDL v0.1 核心契约（Pydantic v2）：粒子、世界、验证目标、出处引用 |
| `units.py` | SI 单位注册与量纲校验 |
| `spatiotemporal.py` | 时空区域 schema（`SpatioTemporalRegion`） |

### 后验校验（validation/）

| 模块 | 职责 |
|------|------|
| `runner.py` | `run_validation()`：仿真结果 vs 期望目标比对 |

### 出处治理（sources/）

| 模块 | 职责 |
|------|------|
| `registry.py` | 加载 `data/sources/registry.yaml`，提供分级查询 API |
| `validation.py` | `validate_source_refs()`：SourceRef 合规校验（4 条治理规则） |

---

## 数据流

```
用户输入 (自然语言)
    ↓  extract_problem_semantics()
ProblemSemanticSpec
    ↓  build_capability_specs()
List[CapabilitySpec]
    ↓  build_execution_plan()
ExecutionPlan (admitted / deferred / unresolved)
    ↓  Scheduler.run(plan, state_set, gravity_vector)
ExecutionResult (target_results, trigger_records, execution_notes)
    ↓  generate_answer()
自然语言回答
```

---

## 设计原则

1. **三层表示分离**：问题语义、能力表示、执行计划各层职责清晰，不跨层耦合
2. **规则驱动而非场景驱动**：执行核心围绕 primitive rules（重力、碰撞等），而非预定义场景类型
3. **默认 SI**：所有数值均为国际单位制；单位符号参与校验
4. **无隐式假设**：所有假设（地面、边界、阻力等）必须显式声明
5. **可信闭环优先**：新功能必须有对应测试才能合并
6. **LLM 仅翻译**：LLM 不承担任何物理计算
7. **准入防御**：CapabilitySpec 必须声明 `applicability_conditions`、`assumptions`、`validity_limits`，防止滑向个例字段堆积

---

## 相关文档

- [事件提取最小输出契约 v0.1](PRISM_event_extraction_minimum_contract_v0_1.md)
- [能力适用条件与入口要素约定 v0.1](PRISM_capability_admission_conditions_and_entry_inputs_v0_1.md)
- [新执行核心接口草案 v0.1](PRISM_execution_core_interfaces_v0_1.md)
- [分层表示架构决议（草案）](PRISM_representation_layers_architecture_decision.md)
- [出处治理政策](source_policy.md)
