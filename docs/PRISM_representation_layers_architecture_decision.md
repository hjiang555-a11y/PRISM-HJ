# 《PRISM-HJ 问题语义、能力表示与执行计划分层：架构决议（草案）》

> 本文档为架构决议草案，定义分层表示体系的职责边界与约束。不包含 Python 实现、dataclass 或 Pydantic 模型定义。

---

## 1. 背景

PRISM-HJ 早期以 `scenario_type`（如 `free_fall`、`projectile`、`collision`）为中心，通过 template + solver 映射直接路由到对应解析求解器。这一结构在早期有明确价值，但已无法承载以下需求：

- 不同物理领域的规则需要同时作用于同一状态集（跨域规则叠加）；
- 用户问题的语义不能总是归入预定义题型（开放性问题）；
- 事件提取的输出必须同时服务于规则提取和规则执行准备，而不只是生成一个题型标签；
- 未来可能引入训练型提取器替换当前的规则/正则提取逻辑，接口位点必须预留。

在向 state-set and rule-oriented execution core 的迁移中（详见 [`PRISM_execution_core_rearchitecture.md`](PRISM_execution_core_rearchitecture.md)），单一 scenario/solver 路径无法区分问题语义解析、能力候选表示和最终执行计划这三个本质不同的关注点。因此，引入分层表示体系成为必要的架构决策。

---

## 2. 采用三层表示体系

本架构决议明确采用以下三层表示体系：

| 层次 | 名称 | 英文标识 |
|------|------|----------|
| 第一层 | 问题语义层 | Problem Semantic Layer |
| 第二层 | 能力表示层 | Capability Representation Layer |
| 第三层 | 执行计划层 | Execution Plan Layer |

三层之间的数据流方向为：

```
输入（自然语言 / 结构化描述）
        ↓
Problem Semantic Layer（问题语义解析，生成 ProblemSemanticSpec）
        ↓
Capability Representation Layer（能力候选识别，生成 CapabilitySpec per capability family）
        ↓
Execution Plan Layer（执行计划编排，生成 ExecutionPlan，驱动 Evolution Scheduling 与 Result Assembly）
        ↓
规则驱动演化 + Result Assembly
```

---

## 3. 三层职责

### 3.1 Problem Semantic Layer（问题语义层）

**负责**：
- 从输入中提取问题所描述的物理实体（entities）；
- 识别用户关心的目标（targets_of_interest）；
- 提取显式给定的条件（explicit_conditions，如已知量、约束、边界）；
- 识别候选物理领域（candidate_domains）；
- 初步识别候选能力族（candidate_capabilities）；
- 收集规则提取所需的依据信息（rule_extraction_inputs）；
- 收集规则执行所需的输入信息（rule_execution_inputs）；
- 记录无法解析或存疑的项目（unresolved_items）。

**不负责**：
- 决定使用哪条 primitive rule；
- 决定 active rule set 的具体构成；
- 执行任何物理计算；
- 生成最终执行计划。

**主要产出**：`ProblemSemanticSpec`（详见 [`PRISM_event_extraction_minimum_contract_v0_1.md`](PRISM_event_extraction_minimum_contract_v0_1.md)）

---

### 3.2 Capability Representation Layer（能力表示层）

**负责**：
- 接收来自 Problem Semantic Layer 的输出；
- 针对每个候选能力族，生成对应的 `CapabilitySpec`；
- 声明该能力族所需的 persistent rules 和 local rules 候选；
- 声明规则激活所需的 trigger conditions；
- 声明规则提取所需的依据（rule_extraction_inputs per capability）；
- 声明规则执行所需的输入（rule_execution_inputs per capability）；
- 标注能力之间是否存在耦合关系（coupling hints）。

**不负责**：
- 执行规则激活逻辑；
- 执行物理演化计算；
- 生成最终时间步调度配置。

**主要产出**：per-capability-family `CapabilitySpec`（见第 4 节）

---

### 3.3 Execution Plan Layer（执行计划层）

**负责**：
- 接收来自 Capability Representation Layer 的输出；
- 将各 CapabilitySpec 整合为统一的 `ExecutionPlan`；
- 处理耦合能力的联合执行安排（强耦合）或分别计划与结果汇总（弱耦合）；
- 生成 `AssemblyRequest`，明确结果汇总的目标量；
- 为 Evolution Scheduling 提供可直接执行的配置。

**不负责**：
- 重新解析问题语义；
- 修改 CapabilitySpec 的内容；
- 承担 rule extraction 的决策逻辑。

**主要产出**：`ExecutionPlan`（当前为架构级规划对象；对应下游 Evolution Scheduling 配置与 `AssemblyRequest`，接口详见 [`PRISM_execution_core_interfaces_v0_1.md`](PRISM_execution_core_interfaces_v0_1.md)）

---

## 4. 中层能力表示是核心

Capability Representation Layer 是三层中最需要精细设计的层。其设计原则如下：

### 4.1 不同能力族允许拥有不同 CapabilitySpec

不同物理能力族（如 `constant_gravity`、`lorentz_force`、`impulsive_collision`）的所需输入、规则结构和触发逻辑差异显著。强行用单一统一格式表达所有能力族，会导致结构臃肿或信息丢失。

因此，本架构允许不同能力族拥有各自适配的 `CapabilitySpec` 格式。

### 4.2 不能完全碎片化：必须共享最小公共骨架

允许分化不意味着完全碎片化。所有 `CapabilitySpec` 必须共享以下最小公共骨架：

| 字段 | 说明 |
|------|------|
| `capability_id` | 能力唯一标识符（遵循规则命名规范） |
| `applies_to` | 适用的实体引用列表 |
| `rule_extraction_inputs` | 规则提取所需的依据信息（见第 5 节） |
| `rule_execution_inputs` | 规则执行所需的输入（见第 5 节） |
| `activation_mode` | 激活模式（`persistent` / `triggered` / `windowed`） |
| `coupling_hints` | 与其他能力的耦合关系标注（可为空） |

在最小公共骨架之外，各能力族可按需扩展字段。

---

## 5. 强要求：所有表示层都必须考虑两类信息

这是本架构决议的核心硬约束，在三个层次的所有输出结构中均必须显式体现：

### 5.1 `rule_extraction_inputs`（规则提取依据）

**定义**：在 rule extraction 阶段，用于判断应激活哪些 primitive rules 的依据信息。

**为什么必须显式表示**：

规则提取不是凭空推理，而是依赖特定的物理线索（如"存在重力"、"有接触事件"、"场强已知"）。如果这些依据不在问题语义层和能力层显式表示，规则提取过程就成了一个不可审计的黑箱。显式表示规则提取依据，是保证规则提取可解释、可替换（包括未来替换为训练型提取器）的前提。

**在各层中的位置**：
- Problem Semantic Layer：`ProblemSemanticSpec.rule_extraction_inputs`（粗粒度，领域级依据）
- Capability Representation Layer：`CapabilitySpec.rule_extraction_inputs`（细粒度，能力级依据）
- Execution Plan Layer：不再新增，直接引用上层输出。

---

### 5.2 `rule_execution_inputs`（规则执行所需输入）

**定义**：在 rule execution 阶段，primitive rules 实际计算所需的数值输入（如质量、初速度、场强、时间范围等）。

**为什么必须显式表示**：

规则执行时需要的输入必须在执行前完整准备好。如果规则执行所需的输入不在 CapabilitySpec 中显式声明，Evolution Scheduling 就无法在执行前验证输入完整性，也无法在输入缺失时给出可定位的错误信息。显式表示规则执行输入，是保证执行前可验证、执行过程可追溯的前提。

**在各层中的位置**：
- Problem Semantic Layer：`ProblemSemanticSpec.rule_execution_inputs`（已知/已提取的执行输入，可能不完整）
- Capability Representation Layer：`CapabilitySpec.rule_execution_inputs`（每条能力规则所需的完整输入列表，含已填充和待填充项）
- Execution Plan Layer：最终执行前，所有 `required` 输入必须已填充；缺失项必须提前报告，不允许静默跳过。

---

## 6. 关于多种格式的立场

本架构明确不采用单一万能事件格式（one-size-fits-all event schema）。具体立场：

- **不强求所有能力族使用相同中层格式**：不同能力族的 CapabilitySpec 可以在骨架之外有各自的字段扩展。
- **允许不同能力族使用不同中层表示格式**：能力族之间的表示差异是合理的，反映了物理规律本身的异构性。
- **顶层语义尽量统一**：Problem Semantic Layer 的输出格式（`ProblemSemanticSpec`）在所有场景下保持一致，提供统一的语义接口。
- **中层按能力分化**：Capability Representation Layer 允许不同能力族的 `CapabilitySpec` 按需定制，但须遵守第 4.2 节中的最小公共骨架约束。
- **底层执行再收敛**：Execution Plan Layer 负责将各 CapabilitySpec 整合为统一的 `ExecutionPlan`，实现底层执行逻辑的收敛。

---

## 7. 关于耦合与非耦合能力

### 7.1 基本立场

能力之间不默认强耦合。大多数情况下，两个能力族（如重力和碰撞）可以被视为弱耦合——它们共同作用于同一状态集，但其规则可以在同一时间步内各自独立贡献，无需联合计算。

### 7.2 弱耦合能力

弱耦合能力可以：
- 分别生成各自的 `CapabilitySpec`；
- 分别参与 active rule set；
- 各自的结果通过 Result Assembly 汇总；
- 不需要联合执行逻辑。

弱耦合是默认假设，适用于绝大多数经典力学与多域叠加场景。

### 7.3 强耦合能力

强耦合能力（如某些量子场效应或高度非线性的多体相互作用）未来可能需要联合执行，即两条规则的贡献不能简单线性叠加，而是需要联合求解。

**本轮不实现强耦合能力的联合执行逻辑**。`coupling_hints` 字段在 CapabilitySpec 中预留位点，供未来使用。

### 7.4 耦合判断是独立问题

"当前场景中的能力是强耦合还是弱耦合"是一个独立的判断问题，需要专门的机制（可能基于规则声明的 `state_contributions` 字段进行冲突检测）来处理。这一判断逻辑本轮不实现，但在接口设计中必须为其预留接口位点（`coupling_hints`）。

---

## 8. 关心目标（targets_of_interest）

`targets_of_interest` 是三层表示体系的核心关切之一：

- **必须在 Problem Semantic Layer 中单独抽取**：它不是 entity 列表的附属信息，而是驱动整个执行和结果汇总方向的核心依据。
- **贯穿三层表示**：Problem Semantic Layer 提取原始 targets_of_interest，Capability Representation Layer 将其与规则能力对应，Execution Plan Layer 将其转化为 AssemblyRequest 的目标量规格。
- **不能退化为 question-type 分类**：`targets_of_interest` 的内容是"用户关心的物理量或状态"（如"碰撞后的速度"、"最高点位置"），不是题型标签（如"free_fall"、"collision"）。题型标签不能替代关心目标。

---

## 9. 关于训练型提取的立场

### 9.1 当前不要求训练

当前 Problem Semantic Layer 的提取逻辑基于规则/正则，不要求任何训练过程。

### 9.2 必须预留训练型提取器的接口位点

未来的训练型提取器需要能够平滑替换当前的规则提取逻辑，而不是重构整个 Problem Semantic Layer。为此：

- 各子任务提取接口（如 EntityExtractor、TargetExtractor、ConditionExtractor 等，详见 [`PRISM_event_extraction_minimum_contract_v0_1.md`](PRISM_event_extraction_minimum_contract_v0_1.md) 第 7 节）必须设计为可替换单元，而非内联逻辑。
- 接口定义应允许未来将具体实现从规则型切换到模型型，输出格式保持不变。

### 9.3 训练接口预留的是替换位点

预留训练接口，意味着在当前文档中明确这些子任务是可替换的独立接口点，而不是现在就绑定任何模型或训练框架。本轮只在文档中标注替换位点，不做任何实现。

---

## 10. 与旧结构的关系

| 旧结构 | 新定位 |
|--------|--------|
| `free_fall`、`projectile`、`collision` 模块 | 继续保留，当前定位为 **legacy / reference / testing-oriented modules**；不删除、不修改，作为历史参考和测试基准，不代表执行核心长期方向 |
| `scenario_type` 字段 | 在 PSDL 契约中作为兼容性保留，不在新执行核心中承担路由作用 |
| template + solver 映射 | 保留为 legacy 路径，不再代表长期执行核心本体方向 |
| `dispatcher.py` 路由逻辑 | 近期保留，随新执行核心成熟逐步替换 |

---

## 相关文档

- [执行核心重构总纲](PRISM_execution_core_rearchitecture.md)
- [新执行核心接口草案 v0.1](PRISM_execution_core_interfaces_v0_1.md)
- [事件提取最小输出契约 v0.1](PRISM_event_extraction_minimum_contract_v0_1.md)
- [架构总览](architecture.md)
