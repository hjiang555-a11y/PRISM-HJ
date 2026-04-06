PRISM-HJ：时空驱动的自然语言物理模拟

![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)

PRISM-HJ 是一个以时空为核心控制变量的物理模拟系统。它将自然语言描述的物理问题自动解析为时空事件序列，根据包含时空条件，触发对应的物理公理（牛顿定律、动量守恒等），并以并行、条件分支或串行方式调用这些公理，最终返回自然语言答案，完全依赖已知物理定律和时空显式建模。

**核心理念**：token承载的内容太少，需要形成中间事件类型的描述才能对应物理实在，对应公理调用；时空是物理过程的承载条件，任何现象都发生在特定的时空坐标上，公理的调用由时空条件决定符合现实情况。关心的问题应有明确的描述，包含在一个结构化参量集合里，是事件描述的不可缺少部分。

---

## 目录

- [时空驱动的设计哲学](#时空驱动的设计哲学)
- [系统架构](#系统架构)
- [管线数据流](#管线数据流)
- [公理与时空条件映射](#公理与时空条件映射)
- [当前实现状态](#当前实现状态)
- [使用示例](#使用示例)
- [项目结构](#项目结构)
- [扩展与定制](#扩展与定制)
- [已知限制](#已知限制)
- [贡献与许可](#贡献与许可)

---

## 时空驱动的设计哲学

### 为什么以时空为核心？

- **物理定律本质上是时空中的约束关系**：牛顿第二定律描述加速度如何随时间改变位置；碰撞发生在特定空间点与时刻；场在时空连续域中定义。
- **自然语言中的物理问题天然包含时空信息**："1秒后""当球碰到地面时""在x>10的区域"都是时空条件。
- **控制复杂性**：将复杂的物理场景分解为时空片段，每个片段内公理可独立或并行求解，通过时空边界条件衔接。

### 时空控制的基本单元

| 概念 | 定义 | 示例 |
|------|------|------|
| 时空坐标 | (t,x,y,z) 或广义坐标 | 第2秒、高度5米处 |
| 事件 | 时空坐标上发生的物理状态变化 | 碰撞、进入/离开边界、力场开启 |
| 时空区域 | 连续的时空集合 | 自由落体区间、弹簧振动区间 |
| 触发条件 | 事件发生的时空判据 | z <= 0（触地）、t == 1.0 |
| 演化调度 | 按时间顺序或空间顺序执行公理 | 先自由落体，碰撞后反弹 |

### 公理调用的控制模式

系统支持三种时空驱动的控制模式：

1. **串行（Sequential）**：公理按时序先后执行，前一阶段输出作为后一阶段的初始条件。
   示例：自由落体 → 触地碰撞 → 反弹上升。

2. **并行（Parallel）**：多个公理在同一时空区域内同时生效，状态叠加。
   示例：重力 + 空气阻力同时作用于同一质点。

3. **条件触发（Conditional）**：当时空坐标满足谓词时，动态切换或激活公理。
   示例：当 x > 10 时开启阻力，否则无阻力。

---

## 系统架构

系统采用**三层表示 + 规则驱动执行**架构：

```
自然语言输入
     │
     ▼
┌─────────────────────────────────┐
│  问题语义层                       │
│  (Problem Semantic Layer)         │
│  提取实体、条件、关心目标、hints    │
│  产出：ProblemSemanticSpec        │
└─────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────┐
│  能力表示层                       │
│  (Capability Representation)      │
│  生成能力规格、声明规则候选        │
│  产出：List[CapabilitySpec]       │
└─────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────┐
│  执行计划层                       │
│  (Execution Plan Layer)           │
│  准入判定、编排规则计划            │
│  产出：ExecutionPlan              │
└─────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────┐
│  执行核心                         │
│  时间步进 → 持久规则施加           │
│  → 触发检测 → 状态更新            │
│  产出：ExecutionResult            │
└─────────────────────────────────┘
     │
     ▼
  自然语言答案 (generate_answer)
```

### 核心模块与职责

| 模块 | 路径 | 职责 |
|------|------|------|
| 时空语义提取 | `src/problem_semantic/` | 从自然语言中抽取实体、条件、关心目标，生成 ProblemSemanticSpec |
| 能力映射器 | `src/capabilities/` | 将物理公理封装为可调用的规则，声明适用时空条件 |
| 执行计划 | `src/planning/` | 准入判定（admitted/deferred/unresolved），编排规则计划 |
| 演化调度器 | `src/execution/runtime/scheduler.py` | 时间步进主循环，协调持久规则与局部规则 |
| 触发检测 | `src/execution/runtime/trigger_engine.py` | 碰撞、边界穿透等触发条件检测 |
| 规则系统 | `src/execution/rules/` | 持久规则（重力、阻力）+ 局部规则（碰撞） |
| 结果组装 | `src/execution/assembly/result_assembler.py` | 按时间步或事件点存储状态快照 |

---

## 管线数据流

```python
# 第一层：语义提取
spec = extract_problem_semantics(question)
# → ProblemSemanticSpec (entities, conditions, hints, ...)

# 第二层：能力映射
cap_specs = build_capability_specs(spec)
# → List[CapabilitySpec]

# 第三层：执行计划
plan = build_execution_plan(cap_specs, admission_hints=hints)
# → ExecutionPlan (admitted_capabilities, rule_plans, ...)

# 执行核心
result = Scheduler(dt=0.01, steps=100).run(plan, state_set, gravity_vector)
# → ExecutionResult (target_results, trigger_records, execution_notes)

# 自然语言回答
answer = generate_answer(question, final_states)
```

### 子模块详细流程

**1. 问题语义提取** (`src/problem_semantic/extraction/pipeline.py`)
- 入口：`extract_problem_semantics(question)`
- 调用 `classify_scenario()` 识别场景类型 → 调度 scenario handler
- Handler 正则提取物理参数 → 构建 entities → 提取 4 类 admission hints
- 填充 `rule_execution_inputs`（dt, steps, gravity_vector, scenario_type）
- 标记 `unresolved_items`（若参数提取不全）

**2. 能力映射** (`src/capabilities/builder.py`)
- 入口：`build_capability_specs(spec)`
- 遍历 `candidate_capabilities` → 对应 mapper 生成 CapabilitySpec
- 从 spec 中读取实体、条件、hints 填充能力字段
- 计算 `missing_entry_inputs`（入口要素缺失项）

**3. 执行计划生成** (`src/planning/execution_plan/builder.py`)
- 入口：`build_execution_plan(cap_specs, admission_hints)`
- 三态准入判定：admitted / deferred / unresolved
- 仅 admitted 的 capability 进入 `persistent_rule_plan` / `local_rule_plan`
- 传播 admission hints 至执行核心

**4. 运行时执行** (`src/execution/runtime/scheduler.py`)
- 入口：`Scheduler(dt, steps).run(plan, state_set, gravity_vector)`
- 初始化 active rule set → 时间步循环：
  - 收集持久规则 dv → 叠加更新速度 → 推进位置
  - TriggerEngine 检测触发 → 执行局部规则
- ResultAssembler 组装最终结果

---

## 公理与时空条件映射

### 1. 自由落体（匀加速运动）

| 属性 | 内容 |
|------|------|
| 对应公理 | 牛顿第二定律：a = g（常数） |
| 时空条件 | 物体在空中（z > 0），未与其他物体接触 |
| 控制模式 | 串行片段 |
| 实现模块 | `src/execution/rules/persistent/gravity.py` → `ConstantGravityRule` |

### 2. 弹性/非弹性碰撞

| 属性 | 内容 |
|------|------|
| 对应公理 | 动量守恒 + 恢复系数 |
| 时空条件 | 两物体质心距离 ≤ 半径之和 |
| 控制模式 | 条件触发（瞬时事件） |
| 实现模块 | `src/execution/rules/local/impulsive_collision.py` → `ImpulsiveCollisionRule` |

### 3. 线性阻力

| 属性 | 内容 |
|------|------|
| 对应公理 | F = -k·v（线性阻力） |
| 时空条件 | 整个运动区间 |
| 控制模式 | 并行（与重力叠加） |
| 实现模块 | `src/execution/rules/persistent/drag.py` → `LinearDragRule` |

### 4. 矩形边界约束

| 属性 | 内容 |
|------|------|
| 对应公理 | 法向速度反向 × 恢复系数 |
| 时空条件 | 粒子坐标超出边界 |
| 控制模式 | 条件触发（瞬时反弹） |

### 待扩展公理

| 公理 | 控制模式 | 状态 |
|------|----------|------|
| 弹簧振子 | 串行 | 待定 |
| 万有引力 | 并行 | 待定 |
| 电磁力 | 并行/条件 | 待定 |

---

## 当前实现状态

基于 2026-04-06 代码重整。系统采用统一管线。

### ✅ 已完成

| 功能 | 说明 |
|------|------|
| PSDL 数据模型 | Pydantic v2 schema，含粒子、世界、验证目标、出处引用 |
| 时空语义提取 | 正则+关键词提取，输出 ProblemSemanticSpec（含 4 类 admission hints） |
| 能力表示层 | ParticleMotionCapabilitySpec / ContactInteractionCapabilitySpec |
| 执行计划生成 | ExecutionPlan 支持 admitted / deferred / unresolved 三态准入 |
| 规则执行器 | 持久规则（重力、线性阻力）+ 局部规则（碰撞） |
| 力累加器 | 每步收集所有 persistent rules 的 dv 贡献，一次叠加 |
| 运行时调度器 | Scheduler 时间步进 + TriggerEngine 触发检测 |
| 统一管线 | main.py 单一管线入口 |
| 后验校验 | run_validation() 对比仿真结果与期望目标 |
| 出处治理 | SourceRef 分级（Tier 1/2/标准），4 条合规校验规则 |
| DAG 调度器骨架 | DAGBuilder + DAGScheduler（拓扑排序、条件分支、同步点） |

### 🚧 部分完成

| 项目 | 当前能力 | 待完善 |
|------|---------|--------|
| 并行公理叠加 | 力累加器已实现 | 扩展更多规则类型 |
| 时空区域定义 | 仅 AABB 边界框 | 圆形、多边形区域 |
| 时间离散化 | 固定步长 | 自适应步长 |
| 时空结果查询 | 仅最终状态 | 任意时空坐标查询 |

### 📅 规划中

- 全功能 DAG 调度器集成
- 时空连续性检查
- 多时空尺度模拟
- 训练型提取器（替换正则提取器）

---

## 使用示例

### 示例 1：自由落体 + 碰撞

```bash
python main.py --question "一个2kg的球从高度5米自由落体，撞到地面后反弹，恢复系数0.8，求第一次触地后的速度。"
```

系统处理流程：
1. **语义提取**：识别实体（ball, mass=2kg）、初始位置（z=5m）、碰撞事件、恢复系数 0.8
2. **能力映射**：生成 ParticleMotionCapabilitySpec + ContactInteractionCapabilitySpec
3. **执行计划**：两个能力均 admitted
4. **调度执行**：Scheduler 步进 → TriggerEngine 检测触地 → 碰撞规则计算碰后速度

### 示例 2：边界反弹

```bash
python main.py --question "一个球在1x1x1的立方体盒子中，初速度(1,1,1)，重力不计，求球第一次碰到x=1边界后的速度。"
```

### 示例 3：并行叠加

```bash
python main.py --question "球受重力和空气阻力（k=0.1），初速度竖直向上20m/s，求最高点时间。"
```

---

## 项目结构

```
PRISM-HJ/
├── LICENSE
├── README.md
├── requirements.txt
├── main.py                          # 主入口（CLI）— 统一管线
├── src/
│   ├── problem_semantic/            # 第一层：时空语义提取
│   │   ├── models.py                # ProblemSemanticSpec 模型
│   │   └── extraction/              # 提取管线
│   │       ├── pipeline.py          # 入口：extract_problem_semantics()
│   │       └── extractors.py        # 场景参数正则提取器
│   ├── capabilities/                # 第二层：能力表示
│   │   ├── builder.py               # 语义 → 能力列表路由
│   │   ├── common/                  # 公共骨架
│   │   │   ├── base.py              # CapabilitySpec 基类
│   │   │   └── kinds.py             # 能力种类常量
│   │   ├── particle_motion/         # 粒子运动能力
│   │   │   ├── spec.py              # ParticleMotionCapabilitySpec
│   │   │   └── mapper.py            # 语义 → 粒子运动能力映射
│   │   └── contact_interaction/     # 接触交互能力
│   │       ├── spec.py              # ContactInteractionCapabilitySpec
│   │       └── mapper.py            # 语义 → 接触交互能力映射
│   ├── planning/                    # 第三层：执行计划生成
│   │   ├── execution_plan/          # 计划构建与准入逻辑
│   │   │   ├── models.py            # ExecutionPlan 模型
│   │   │   └── builder.py           # 能力列表 → 执行计划
│   │   └── scheduler.py             # DAG 调度器（DAGBuilder + DAGScheduler）
│   ├── execution/                   # 执行核心（规则驱动演化）
│   │   ├── rules/                   # 规则执行器
│   │   │   ├── registry.py          # RuleRegistry（injectable）
│   │   │   ├── persistent/          # 持久规则（每步施加）
│   │   │   │   ├── base.py          # PersistentRuleExecutor（ABC）
│   │   │   │   ├── gravity.py       # ConstantGravityRule
│   │   │   │   └── drag.py          # LinearDragRule
│   │   │   └── local/               # 局部规则（触发式）
│   │   │       ├── base.py          # LocalRuleExecutor（ABC）
│   │   │       └── impulsive_collision.py  # ImpulsiveCollisionRule
│   │   ├── state/                   # 状态管理
│   │   │   └── state_set.py         # StateSet — 多实体状态集合
│   │   ├── runtime/                 # 运行时调度
│   │   │   ├── scheduler.py         # Scheduler — 时间步进主循环
│   │   │   └── trigger_engine.py    # TriggerEngine — 触发检测
│   │   └── assembly/                # 结果组装
│   │       └── result_assembler.py  # ResultAssembler → ExecutionResult
│   ├── schema/                      # PSDL 数据模型
│   │   ├── psdl.py                  # PSDL v0.1 核心契约
│   │   ├── units.py                 # SI 单位注册与量纲校验
│   │   └── spatiotemporal.py        # 时空区域 schema
│   ├── llm/                         # 自然语言接口（Ollama HTTP API）
│   │   └── translator.py            # classify_scenario; generate_answer
│   ├── validation/                  # 后验校验
│   │   └── runner.py                # run_validation()
│   └── sources/                     # 出处注册与治理
│       ├── registry.py              # 加载 data/sources/registry.yaml
│       └── validation.py            # SourceRef 合规校验
├── data/
│   └── sources/registry.yaml        # 出处分级定义（Tier 1/2/标准）
├── tests/                           # 单元测试（377 项）
├── examples/
│   └── questions.txt                # 示例物理问题
└── docs/                            # 设计文档
    ├── architecture.md              # 架构总览
    ├── PRISM_event_extraction_minimum_contract_v0_1.md
    ├── PRISM_capability_admission_conditions_and_entry_inputs_v0_1.md
    ├── PRISM_execution_core_interfaces_v0_1.md
    ├── PRISM_representation_layers_architecture_decision.md
    └── source_policy.md
```

---

## 扩展与定制

### 添加新公理

1. 定义公理的时空适用范围：在 `CapabilitySpec` 中填写 `applicability_conditions`
2. 指定控制模式：并行（与重力叠加）或条件触发（速度阈值）
3. 在 `execution/rules/persistent/` 或 `execution/rules/local/` 中实现规则执行器
4. 在 `RuleRegistry` 中注册：`registry.register_persistent("rule_name", RuleClass)`
5. 更新 extraction pipeline 中的 scenario handler

### 自定义触发条件

1. 在 `execution/runtime/trigger_engine.py` 中定义新触发类型
2. 将事件注册到调度器

### 调整调度策略

修改 `execution/runtime/scheduler.py` 中的执行循环，支持：
- 基于优先级的调度
- 时间步长自适应
- 事件驱动的动态重排

---

## 已知限制

| 限制 | 影响 |
|------|------|
| 仅支持球形粒子 | 无法处理角动量 |
| 边界仅 AABB | 无法处理复杂几何区域 |
| 无流体/柔性体 | 不支持连续介质 |
| 时间步长固定 | 事件时刻精度有限 |
| 正则提取器 | 场景覆盖有限 |

---

## 贡献与许可

### 贡献指南

- 代码符合 PEP 8
- 新功能需包含单元测试（`tests/` 目录）
- 添加新公理时，同步更新本 README 中的"公理与时空条件映射"
- 提交前运行 `pytest tests/`

### 许可证

Apache 2.0。详见 LICENSE 文件。

### 致谢

- DeepSeek 提供开源模型
- Ollama 简化本地部署
