# 《PRISM-HJ 事件提取最小输出契约 v0.1》

> 本文档定义问题语义层（Problem Semantic Layer）的最小输出契约，规定输出对象的字段结构、职责边界与容错原则。不包含 Python 实现、dataclass 或 Pydantic 模型定义。

---

## 1. 目标

本契约定义的是问题语义层（Problem Semantic Layer）的**最小输出契约**，而不是完整执行计划。

具体地，本契约规定：

- 事件提取阶段输出对象的名称（`ProblemSemanticSpec`）；
- 该对象的最小必要字段及各字段的职责；
- 哪些字段是硬要求，哪些允许不完整；
- 输出如何服务后续两类关键信息准备：
  - **规则提取依据（rule_extraction_inputs）**
  - **规则执行输入（rule_execution_inputs）**
- 面向未来训练型提取器的接口替换位点。

---

## 2. 基本原则

1. **事件提取不以题型标签为中心**。输出不应以 `scenario_type`（如 `"free_fall"`、`"collision"`）为主要组织结构。题型标签可以作为 `candidate_capabilities` 或 `unresolved_items` 的注释存在，但不驱动输出结构。

2. **输出允许不完整**。事件提取是从往往不完整的自然语言输入中做最大努力提取。字段值可以是 candidate（候选）、unknown，或通过 `unresolved_items` 记录存疑项。允许不完整不意味着可以静默丢失信息——凡是提取时遇到的不确定项，必须记录于 `unresolved_items`。

3. **输出必须服务规则提取与规则执行输入准备**。`rule_extraction_inputs` 和 `rule_execution_inputs` 是两个独立的硬要求字段，不能缺省、不能合并，必须在输出对象中显式存在。

4. **关心目标必须单独表达**。`targets_of_interest` 是独立字段，不能用 entity 列表或 question-type 标签代替。

---

## 3. 最小输出对象：`ProblemSemanticSpec`

问题语义层的最小输出对象命名为 **`ProblemSemanticSpec`**。

> 命名约定：`Spec` 后缀表示这是一个结构化的规格描述对象，而非执行对象或状态对象。

---

## 4. 最小字段定义

以下各字段是 `ProblemSemanticSpec` 的最小必要字段集合。

---

### 4.1 `source_input`

**职责**：记录本次提取所基于的原始输入。

**最低要求**：非空字符串或结构化引用；不允许缺省。

**允许不完整的方式**：原始输入本身允许为非完整的自然语言片段；字段值应忠实记录输入原文，不做截断。

**说明**：`source_input` 的存在保证提取结果可追溯；所有后续字段的提取依据均可追溯至此。

---

### 4.2 `entities`

**职责**：记录问题中涉及的物理实体（如物体、粒子、场源）及其已知属性（如质量、电荷、几何形状）。

**最低要求**：列表，可为空（输入中无可识别实体时允许空列表）。列表中每个元素应包含实体标识符（`entity_id`）和已提取的属性。

**允许不完整的方式**：
- 属性值可标注为 `unknown`；
- 若提取存疑，对应实体或属性记录于 `unresolved_items`。

---

### 4.3 `targets_of_interest`

**职责**：记录用户明确关心的物理量或状态（如"碰撞后物体的速度"、"最高点的位置"）。

**最低要求**：列表，不允许缺省为空（若问题有可解析的关心目标，必须尽力提取）。每个元素应能标识关心的物理量类型和关联实体。

**允许不完整的方式**：
- 关心目标的具体量纲可暂时标注为 `candidate`；
- 若提取困难，记录于 `unresolved_items`，但不允许用 question-type 标签替代。

**约束**：`targets_of_interest` 不得退化为题型标签（如不得以 `"free_fall"` 代替具体关心目标）。

---

### 4.4 `explicit_conditions`

**职责**：记录输入中显式给出的物理条件（如已知量的数值、约束条件、边界条件）。

**最低要求**：列表，可为空。每个条件应包含条件类型、关联实体或变量、数值（含单位）。

**允许不完整的方式**：
- 数值允许标注为 `unknown`（条件类型可识别但数值未给出）；
- 存疑条件记录于 `unresolved_items`。

---

### 4.5 `candidate_domains`

**职责**：记录本次问题可能涉及的物理领域（如 `classical_mechanics`、`electromagnetism`）。

**最低要求**：列表，允许为空（无法识别领域时返回空列表，并在 `unresolved_items` 中记录）。列表中每个元素应为遵循规则命名规范的领域标识符。

**允许不完整的方式**：领域可标注为 `candidate`（置信度较低但有依据）。

---

### 4.6 `candidate_capabilities`

**职责**：记录本次问题中初步识别的能力族候选（如 `classical_mechanics.background.constant_gravity`、`classical_mechanics.contact.impulsive_collision`）。

**最低要求**：列表，允许为空。每个元素应遵循规则命名规范（`<domain>.<family>.<rule>`）。

**允许不完整的方式**：能力候选可标注为 `candidate`；不确定时记录于 `unresolved_items`。

**说明**：`candidate_capabilities` 的内容是规则命名标识符，不是题型标签；两者不可互换。

---

### 4.7 `rule_extraction_inputs`

**职责**：收集和记录规则提取阶段所需的依据信息——即"根据什么可以判断应该激活哪些 primitive rules"。

**最低要求**：列表，不允许缺省或省略。每个元素应标注：
- 依据来源（来自输入文本的哪部分）；
- 依据类型（如"存在持续重力作用"、"描述了接触/碰撞事件"、"给出了电场强度"）；
- 置信度（如 `high` / `medium` / `low` / `candidate`）。

**为什么是硬要求**：

规则提取过程必须有可审计的依据。如果依据不在 `ProblemSemanticSpec` 中显式记录，规则提取就成为不可验证的黑箱，也无法在未来用训练型提取器替换时保证接口的可比较性。

---

### 4.8 `rule_execution_inputs`

**职责**：收集和记录规则执行阶段所需的数值输入——即"primitive rules 在执行时需要什么数值"。

**最低要求**：列表，不允许缺省或省略。每个元素应标注：
- 关联的能力（或规则名称）；
- 输入变量名称（如 `mass`、`initial_velocity`、`g`）；
- 当前已知状态（`provided`、`derivable`、`unknown`）；
- 若已知，提供数值及单位。

**为什么是硬要求**：

规则执行依赖完整的输入准备。在问题语义层即收集已知的执行输入，一方面为后续 CapabilitySpec 填充提供基础，另一方面允许系统在执行前即可发现输入缺失，而不是在执行时才报错。

**与 `explicit_conditions` 的区别**：`explicit_conditions` 记录问题中给出的物理条件；`rule_execution_inputs` 记录规则执行时的数值需求清单（角度更面向执行）。两者内容可部分重叠，但不可互相替代。

---

### 4.9 `unresolved_items`

**职责**：记录提取过程中遇到的无法解析、存在歧义或置信度过低而无法归入其他字段的项目。

**最低要求**：列表，允许为空（无存疑项时为空列表）。每个元素应包含：
- 来源字段（原本应归入哪个字段）；
- 原始文本片段或描述；
- 无法解析的原因类型（如 `ambiguous`、`missing_value`、`unknown_domain`）。

**说明**：`unresolved_items` 不是错误日志，而是不完整性的结构化记录。它的存在允许后续处理步骤知晓哪些信息尚待确认，而不是静默丢失。

---

## 5. 强要求

以下约束是硬约束，不可省略：

1. **`rule_extraction_inputs` 是硬要求**：所有 `ProblemSemanticSpec` 输出中必须包含此字段，且内容必须尽力填充（不允许返回空列表而不在 `unresolved_items` 中记录原因）。

2. **`rule_execution_inputs` 是硬要求**：所有 `ProblemSemanticSpec` 输出中必须包含此字段，且内容必须尽力填充（即便部分输入状态为 `unknown`，也必须在此字段中列出该输入变量名）。

3. **`targets_of_interest` 不能缺省成 question type**：`targets_of_interest` 的内容必须是具体的物理量或状态描述，不允许以题型标签（如 `"free_fall"`）代替。

---

## 6. 容错原则

### 允许标注为 `candidate` 的字段

以下字段的值允许标注为 `candidate`（即有依据支撑但置信度低于确定性阈值）：

- `candidate_domains`（整体为 candidate 列表）
- `candidate_capabilities`（整体为 candidate 列表）
- `rule_extraction_inputs` 中每条依据的置信度
- `targets_of_interest` 中的量纲信息

### 允许标注为 `unknown` 的字段

以下字段的部分内容允许标注为 `unknown`：

- `entities` 中的属性值（如质量未给出）
- `explicit_conditions` 中的数值（如条件类型已知但数值未给出）
- `rule_execution_inputs` 中各输入变量的当前已知状态

### 必须记录进 `unresolved_items` 的情形

以下情形必须记录进 `unresolved_items`，不允许静默丢失：

- `candidate_domains` 无法确定任何领域；
- `targets_of_interest` 无法提取任何关心目标；
- `rule_extraction_inputs` 中某项依据存在歧义；
- `rule_execution_inputs` 中某个必须变量无法从输入中识别来源；
- 输入中存在描述但无法归入任何已知字段的物理陈述。

---

## 7. 对训练型提取器的预留

当前 Problem Semantic Layer 的提取逻辑基于规则和正则，不要求任何训练。但以下子任务接口点**必须设计为可替换的独立接口**，以支持未来引入训练型提取器：

| 接口名 | 职责 | 对应 `ProblemSemanticSpec` 字段 |
|--------|------|-------------------------------|
| `EntityExtractor` | 从输入中提取物理实体及其属性 | `entities` |
| `TargetExtractor` | 从输入中识别用户关心的物理量 | `targets_of_interest` |
| `ConditionExtractor` | 从输入中提取显式物理条件 | `explicit_conditions` |
| `CapabilityCandidateExtractor` | 识别候选能力族及物理领域 | `candidate_domains`, `candidate_capabilities` |
| `RuleHintExtractor` | 提取规则提取的依据信息 | `rule_extraction_inputs` |
| `ExecutionInputFiller` | 收集规则执行所需的数值输入 | `rule_execution_inputs` |

**约束**：
- 本轮只做文档定义，不做任何实现；
- 这些接口是**替换位点**，不是当前实现的调用栈结构；
- 每个接口的输入为 `source_input`（或前序接口的输出），输出为对应 `ProblemSemanticSpec` 字段的填充值；
- 替换为训练型实现时，只需替换对应接口，`ProblemSemanticSpec` 输出格式保持不变。

---

## 相关文档

- [分层表示架构决议](PRISM_representation_layers_architecture_decision.md)
- [新执行核心接口草案 v0.1](PRISM_execution_core_interfaces_v0_1.md)
- [架构总览](architecture.md)
