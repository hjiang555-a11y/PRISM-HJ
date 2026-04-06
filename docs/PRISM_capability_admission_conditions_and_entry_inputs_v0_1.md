# 《PRISM-HJ 能力适用条件与入口要素约定 v0.1》

---

## 一、为什么必须约定能力适用条件与入口要素

### 1.1 不约定将带来的结构性风险

若不约定 capability 的准入条件与入口要素，系统会面临以下退化路径：

**退化一：字段个例化堆积（Case-by-Case Field Proliferation）**

每次新增 capability，开发者会自然倾向于在 `CapabilitySpec` 子类上添加一组专属字段，
专门描述该场景需要哪些参数。久而久之，`ParticleMotionCapabilitySpec` 里会长出
`height`、`duration`、`v0`；`ContactInteractionCapabilitySpec` 里会长出
`m1`、`m2`、`v1_before`、`v2_before`。这本质上是把 capability 退化为题型模板。

**退化二：ad hoc 特判增殖（Ad Hoc Flag Proliferation）**

缺乏统一准入框架时，执行层（`build_execution_plan`）将不得不为每种 capability
写特判逻辑："如果是 particle_motion，就检查这几个字段；如果是 contact_interaction，
就检查那几个字段"。这些特判随系统扩展迅速失控。

**退化三：ExecutionPlan 无法统一判断 capability 是否可进入执行**

若没有清晰的 `applicability_conditions` 和 `missing_entry_inputs`，`ExecutionPlan`
构建器就无法给出统一的 `admitted / deferred / unresolved` 分类，只能靠特例规则
逐一判断。

### 1.2 约定的核心价值

本约定为 capability 层提供统一的准入契约骨架，使得：

- 任何新 capability 都能通过填写同一组通用字段完成准入声明
- `ExecutionPlan` 构建器可统一读取准入信息决策
- capability 模型的扩展不依赖 ad hoc 个例字段，而依赖对通用结构的填充

---

## 二、本约定的适用范围

- **面向 capability，而不是面向 scenario/template**：本约定描述一类"能力"的
  通用准入条件，而非某个具体题型的参数表。例如，`ParticleMotionCapabilitySpec`
  代表的是"粒子运动"这种能力的适用范围，而不是"自由落体题需要哪些字段"。

- **是能力准入（admission）约定，不是题型字段表**：本约定不维护类似
  `free_fall → {height, v0, t}` 的映射。参数来自 `ProblemSemanticSpec`，
  capability 只声明它需要哪类输入，不规定这些输入在特定题型中叫什么名字。

---

## 三、核心概念定义

### 3.1 `required_entry_inputs`

**职责**：声明该 capability 进入执行前**必须**已知的物理量类别。

例如，`ParticleMotionCapabilitySpec` 要求每个受作用粒子必须具备初始位置、
初始速度和质量。这不是说参数名必须叫 `x0`、`v0`、`m`，而是说相应的物理量
（量纲意义上的位置、速度、质量）必须在 `ProblemSemanticSpec` 中有对应的
显式条件或可推断的来源。

在代码层，`required_entry_inputs` 已作为 `CapabilitySpec` 的正式字段（`List[str]`）
存在，声明该 capability 的必要物理量类别列表，如：
```
["initial_position_per_entity", "initial_velocity_per_entity", "mass_per_entity"]
```
各具体 capability 的 mapper 在构造时填充此字段。

### 3.2 `applicability_conditions`

**职责**：声明该 capability 可以被使用的前提条件（定性描述）。

这些条件描述的是物理情境上的必要前提，而非参数是否已知。例如：
- "实体可以建模为质点"
- "背景作用在实体轨迹范围内均匀连续"
- "存在两个或以上可识别实体"

`applicability_conditions` 是能力能否被激活的前提，而 `required_entry_inputs`
是能力激活后能否执行的数据前提。两者互补，共同构成完整的准入条件。

### 3.3 `assumptions`

**职责**：声明该 capability 工作时所依赖的物理假设（包含理想化条件）。

假设描述的是 capability 内部计算成立的前提。如果假设被违反，capability 仍可进入
执行，但结果可能不准确。例如：
- "忽略空气阻力"（默认假设，除非显式声明 drag）
- "重力加速度恒定（g = 9.8 m/s²）"
- "碰撞过程为完全瞬时冲击，忽略碰撞持续时间"

> **关于 `idealizations`**：本约定将理想化条件（idealizations）并入 `assumptions`，
> 不单独设置字段。理由：理想化条件（如"质点近似"、"刚体碰撞"）本质上是一种特殊
> 假设，单独设置字段增加认知负担而收益有限。在 `assumptions` 中可通过语义明确标注
> "理想化假设"。

### 3.4 `missing_entry_inputs`

**职责**：记录当前 `required_entry_inputs` 中尚未从 `ProblemSemanticSpec` 中
获得的项目。

`missing_entry_inputs` 是动态状态：在从 `ProblemSemanticSpec` 构建 capability
的过程中，如果某个必须的入口要素无法从语义层找到，则记入此列表。

在代码层，`missing_entry_inputs` 已作为 `CapabilitySpec` 的正式字段（`List[str]`）
存在，由各 capability 的 mapper 在构造时动态计算填充。

**字段边界说明**：

- `missing_entry_inputs`（准入层概念）：描述 capability 能否进入执行计划前
  缺少的物理量类别。非空时，capability 进入 `deferred` 状态。
- `missing_inputs`（执行层概念）：描述规则执行时尚未补齐的运行时参数，
  来自 `ProblemSemanticSpec.unresolved_items`，不直接决定 admission 状态。

### 3.5 `validity_limits`

**职责**：声明该 capability 的有效适用边界（定性描述）。

超出有效边界时，capability 的计算结果不可信。例如：
- "非相对论性低速范围（v ≪ c）"
- "接触时间远小于整体运动时间尺度"
- "实体不发生形变或旋转"

`validity_limits` 是对 `assumptions` 的补充：`assumptions` 描述"我们做了什么
假设"，`validity_limits` 描述"这些假设在什么范围内有效"。

---

## 四、与三层表示体系的关系

### 4.1 ProblemSemanticSpec（问题语义层）

`ProblemSemanticSpec` 是能力准入信息的主要来源。能力准入所需的各类要素，
均通过以下语义线索从问题语义层流入：

| 准入要素 | 来源语义线索 |
|---------|-------------|
| `required_entry_inputs` | `explicit_conditions`（显式物理条件）、`entities`（实体描述） |
| `applicability_conditions` | `entities`（实体类型暗示）、`rule_extraction_inputs`（背景/交互线索）|
| `assumptions` | `rule_extraction_inputs.background_interactions`、`rule_extraction_inputs.contact_model_hints` |
| `missing_entry_inputs` | `unresolved_items`（尚未解析的项目） |
| `validity_limits` | 问题领域特征（当前由 `candidate_domains` 提示） |

当前 `ProblemSemanticSpec` 的最小实现已提供以上线索的基本承接点：
- `entities` → 实体模型提示（entity model hints）
- `explicit_conditions` → 显式物理条件（含初始状态）
- `rule_extraction_inputs` → 规则提取线索（含背景作用、交互模型提示）
- `unresolved_items` → 未解析项目（对应 `missing_entry_inputs` 来源）

### 4.2 CapabilitySpec（能力表示层）

`CapabilitySpec` 是 capability 准入约定的主要承载者。在当前代码骨架基础上，
准入相关字段分布如下：

**公共骨架（`CapabilitySpec` 基类）**：
- `applicability_conditions`：能力适用条件（已实现）
- `assumptions`：物理假设（已实现）
- `validity_limits`：有效边界（已实现）
- `required_entry_inputs`：必要入口要素类别声明（已实现，`List[str]`）
- `missing_entry_inputs`：当前缺失的入口要素（已实现，`List[str]`，由 mapper 动态计算）
- `missing_inputs`：执行层运行时缺失参数（已有，概念上有别于 `missing_entry_inputs`）
- `candidate_rules`：候选规则（已有，反映能力在准入后的规则选项）

**具体 capability 层（子类）**：
- `initial_state_requirements`（`ParticleMotionCapabilitySpec`）：各实体初始状态要求，
  与 `required_entry_inputs` 概念对应，以字典形式存储已提取的具体值
- `pre_trigger_state_requirements`（`ContactInteractionCapabilitySpec`）：触发前状态要求，
  同上

### 4.3 ExecutionPlan（执行计划层）

`ExecutionPlan` 基于 `CapabilitySpec` 中的准入信息做执行决策。准入状态分为：

| 状态 | 说明 | 当前实现状态 |
|------|------|------------|
| `admitted` | `applies_to_entities` 非空且 `missing_entry_inputs` 为空，可进入执行 | **已实现**（`admitted_capabilities` 字段，规则进入 persistent/local plan） |
| `deferred` | `applies_to_entities` 非空但 `missing_entry_inputs` 非空，暂不执行 | **已实现**（`deferred_capabilities` 字段，含 `missing_entry_inputs` 详情） |
| `unresolved` | `applies_to_entities` 为空，作用对象不明 | **已实现**（`unresolved_admission_items` 字段，含 `reason` 说明） |

`build_execution_plan()` 中的 `_judge_admission()` 函数实现了上述三态判定逻辑：
- 仅 `admitted` 状态的 capability 的规则进入 `persistent_rule_plan` / `local_rule_plan`
- `deferred` 和 `unresolved` 的 capability 不进入规则计划，但其目标量仍汇入 `assembly_plan` 供追溯
- 所有 capability 均记录在 `capability_bindings` 中，不论 admission 状态

---

## 五、第一批 capability 准入示例

### 5.1 `ParticleMotionCapabilitySpec`

**能力语义**：适用于需要持续背景作用（如重力）驱动的一个或多个粒子的状态演化场景。

#### Required Entry Inputs（入口要素）

每个受作用粒子（`applies_to_entities` 中的实体）必须提供：

| 要素 | 物理量类别 | 说明 |
|------|-----------|------|
| 初始位置 | 位置（三维或约化维度） | 必须由 `explicit_conditions` 提供或可从问题语义层推断 |
| 初始速度 | 速度向量 | 必须由 `explicit_conditions` 提供 |
| 质量 | 标量质量 | 若问题显式声明则必须提供；若与质量无关可标记 "mass_independent" |

这些要素在代码中体现为 `initial_state_requirements`（键为实体 ID，值为所需字段）。

#### Applicability Conditions（适用条件）

1. 实体可以建模为质点（无旋转、无形变）
2. 背景作用（如重力）在实体运动的时空范围内是连续且空间均匀的
3. 实体状态的演化可以用连续时间微分方程（或其数值近似）描述
4. 不存在使得粒子运动规则在有限时刻内"切断"并替换为不同规则的触发事件
   （如存在碰撞事件，则该事件由 `ContactInteractionCapabilitySpec` 处理）

#### Assumptions（物理假设）

- 默认忽略空气阻力，除非 `background_interaction_hints` 中显式包含 `"drag"`
- 重力加速度恒定（g = 9.8 m/s²），除非问题提供不同数值
- 质点近似：实体的旋转、形变对运动轨迹无贡献（理想化假设）
- 质量在运动过程中保持不变（无质量流失、无燃料消耗，除非显式声明）

#### Validity Limits（有效边界）

- 非相对论性低速范围（v ≪ c）
- 引力场在实体轨迹尺度上的空间非均匀性可忽略
- 实体不经历足以打破质点近似的强旋转或大形变

---

### 5.2 `ContactInteractionCapabilitySpec`

**能力语义**：适用于需要检测实体间接触/相遇事件，并在触发条件满足时激活瞬时局部规则的场景。

#### Required Entry Inputs（入口要素）

每个参与接触交互的实体（`contact_pairs` 中涉及的实体）在触发点前必须已知：

| 要素 | 物理量类别 | 说明 |
|------|-----------|------|
| 触发前速度 | 速度向量 | 各参与实体在碰撞前的速度，必须由 `pre_trigger_state_requirements` 描述 |
| 质量 | 标量质量 | 各参与实体的质量，是冲量计算的必要输入 |
| 接触模型类型 | 枚举（弹性/非弹性/…） | 由 `contact_model_hints` 提供；未知时候选化为 `["elastic"]` |

这些要素在代码中体现为 `pre_trigger_state_requirements` 和 `contact_model_hints`。

#### Applicability Conditions（适用条件）

1. 问题中存在两个或以上可识别的物理实体（`applies_to_entities` 非空且至少两个）
2. 存在可识别的接触/碰撞事件（由 `trigger_requirements` 中 `type: contact` 描述）
3. 交互可以用有限时刻的冲量近似描述（碰撞过程远短于整体运动时间尺度）
4. 各实体的接触前状态在触发点处是已知的或可从 `pre_trigger_state_requirements` 推断的

#### Assumptions（物理假设）

- 碰撞为完全瞬时冲击：碰撞时间 Δt → 0，可用冲量-动量定理处理（理想化假设）
- 默认弹性碰撞（动能守恒），除非 `contact_model_hints` 中显式指定非弹性类型
- 碰撞期间外力（如重力）的冲量相对碰撞冲量可忽略
- 刚体近似：碰撞过程中实体不发生形变（理想化假设）

#### Validity Limits（有效边界）

- 碰撞持续时间远小于整体运动时间尺度
- 实体间不发生持续接触（若需建模持续接触力，需引入不同的 capability）
- 刚体近似在碰撞速度和材料特性下成立
- 仅适用于两体直接接触碰撞；多体同时碰撞需显式扩展 contact_pairs

---

## 六、当前不做的内容

以下内容不在本轮 v0.1 约定范围内：

- **不把该约定扩展为全学科完备本体**：本轮仅覆盖力学第一批 capability；
  热学、电磁学、光学等领域的 capability admission 将在后续轮次扩展。

- **不在本轮定义所有未来 capability**：`SpringInteractionCapabilitySpec`、
  `GravitationalFieldCapabilitySpec` 等未来 capability 留待后续轮次，
  本约定仅提供骨架，使得新增时有框可循。

- **不把该约定直接写成 scenario-specific parameter table**：本约定绝不维护
  "自由落体题 → {height, t, v0}"形式的题型参数映射。参数处理由
  `ProblemSemanticSpec` 通过 `explicit_conditions` 承担，capability 只声明
  入口要素的类别。

- **不在本轮实现 `validity_limits` 运行时校验**：当前 `validity_limits` 仍为
  声明性字段；轻量边界检查机制（如速度范围警告）留待后续轮次实现。

---

## 七、与第一原型的关系

本约定是为了**防止第一原型滑向个例设计**而建立的防御性结构约定。

第一原型目前的 capability 实现已经初步符合 capability-centered 设计方向
（而非 scenario-template centered），这是正确的起点。但若缺乏明确的准入契约，
后续每次新增 capability 时，开发者面对压力会自然倾向于最简单的路径——
在子类上堆积特例字段。

本约定通过以下方式锁定正确方向：

1. **最小公共骨架中新增通用准入字段**（`applicability_conditions`、`assumptions`、
   `validity_limits`），使任何新 capability 都有"正确位置"放置准入信息
2. **为第一批 capability 填写示例**，建立参考标准
3. **与 `ExecutionPlan` 概念层对齐**，即便当前不完全实现，
   也明确了 admitted/deferred/unresolved 的判断方向

第一原型虽然窄，但 capability admission 结构必须可扩展。本约定正是该可扩展性的
最小形式化基础。

---

## 八、本轮之后的准入相关尾项

以下内容是本轮 v0.1 约定后尚未完成、需在后续轮次处理的任务：

1. **`ProblemSemanticSpec` 语义线索增强（P0 第四步已完成）**：`missing_entry_inputs` 的计算
   已在 P0 第四步中增强。`ProblemSemanticSpec` 现新增四类 admission hints（`entity_model_hints`、
   `interaction_hints`、`assumption_hints`、`query_hints`），由 extraction pipeline 通过
   轻量规则法（regex / 关键词模式匹配）填充，mapper 按"A（语义 hints）→ B（explicit_conditions
   关键词）→ C（fallback 默认值）"三层优先级消费这些信息。`explicit_conditions` 关键词匹配
   降级为次优先，仅当语义层无明确 hint 时使用。

2. **`applicability_conditions` 动态推断（已部分完成）**：当前 mapper 中的 `assumptions`
   已可根据 `assumption_hints` 动态区分来源（语义层标注 vs. 原型默认 fallback）。
   完整的 `applicability_conditions` 动态推断留待后续轮次。

3. **后续 capability 准入对齐**：每当新增 capability 族时，必须按本约定格式
   填写 `required_entry_inputs`、`missing_entry_inputs`、`applicability_conditions`、
   `assumptions`、`validity_limits`，不允许省略准入层字段。

4. **`validity_limits` 轻量校验机制**：当前 `validity_limits` 仅为声明性字段；
   后续可引入轻量警告（如速度范围检查），使 capability 能在准入时主动标记越界情况。

5. **deferred capability 的重入机制**：当前 `deferred_capabilities` 记录了缺失的
   入口要素，但尚无"补充后重新进入执行计划"的机制。后续可考虑在交互循环中
   让用户或 LLM 补充缺失要素后触发重新 admission 判定。

---

## 九、P0 第四步：ProblemSemanticSpec Admission Hints 增强（v0.1 补充）

### 9.1 新增 admission hints 字段

`ProblemSemanticSpec` 现在提供四类结构化 admission hints，由 extraction pipeline
通过轻量规则法（regex / 关键词模式匹配）自动填充：

| 字段 | 说明 | 常见值 |
|------|------|--------|
| `entity_model_hints` | 实体建模方式 | `"point_mass"`、`"rigid_body"` |
| `interaction_hints` | 物理交互类型 | `"gravity_present"`、`"collision_possible"`、`"contact_possible"`、`"field_present"` |
| `assumption_hints` | 物理假设 | `"ignore_air_resistance"`、`"elastic_collision"`、`"inelastic_collision"`、`"constant_g"`、`"smooth_surface"` |
| `query_hints` | 目标查询类型 | `"ask_final_state"`、`"ask_state_at_time"`、`"ask_collision_outcome"`、`"ask_impact_time"` |

### 9.2 extraction pipeline 如何填充 hints

`extract_problem_semantics(input_text)` 调用四个专用提取函数：

- `_extract_entity_model_hints`：识别"质点/小球/particle"→ `point_mass`；"刚体/rigid body"→ `rigid_body`
- `_extract_interaction_hints`：识别"重力/落体/height/falls"→ `gravity_present`；"碰撞/collision"→ `collision_possible`
- `_extract_assumption_hints`：识别"忽略空气阻力"→ `ignore_air_resistance`；"弹性碰撞"→ `elastic_collision`；"非弹性"→ `inelastic_collision`
- `_extract_query_hints`：识别"X秒后/after X s"→ `ask_state_at_time`；"碰后"→ `ask_collision_outcome`；"落地时间"→ `ask_impact_time`

### 9.3 mapper 三层信息来源优先级

capability mapper（`particle_motion` 和 `contact_interaction`）现在明确按三层优先级消费信息：

**A 层：语义层 hints（最高优先级）**
- 来源：`ProblemSemanticSpec.interaction_hints`、`assumption_hints` 等
- 示例：`interaction_hints` 含 `gravity_present` → `background_interaction_hints = ["gravity"]`
- 示例：`assumption_hints` 含 `inelastic_collision` → `contact_model_hints = ["inelastic"]`，且 `assumptions` 中标注"来自语义层 assumption_hints"

**B 层：explicit_conditions 关键词匹配（次优先级）**
- 来源：`ProblemSemanticSpec.explicit_conditions` 中的条件名称集合
- 示例：`explicit_conditions` 含 `{"name": "height", ...}` → `initial_position_per_entity` 不缺失
- 示例：`explicit_conditions` 含 `{"name": "mass", ...}` → `mass_per_entity` 不缺失

**C 层：原型默认 fallback（最低优先级）**
- 仅当 A 层和 B 层均无信息时使用
- 示例：无 `interaction_hints` 且无 `rule_extraction_inputs["background_interactions"]` → `background_hints = ["gravity"]`
- 示例：无 `assumption_hints` 且无 `rule_extraction_inputs["contact_model_hints"]` → `contact_hints = ["elastic"]`
- 示例：无语义 hints → `assumptions` 中包含"默认忽略空气阻力"等默认描述

### 9.4 哪些 admission 判断不再只依赖关键词匹配

本轮完成后，以下 admission 判断已有结构化语义来源（不再只依赖关键词）：

1. **背景作用类型**（`background_interaction_hints`）：优先从 `interaction_hints` 读取 `gravity_present`，而不是直接 fallback 到硬编码 `["gravity"]`
2. **碰撞模型类型**（`contact_model_hints`）：优先从 `assumption_hints` 读取 `elastic_collision` / `inelastic_collision`，而不是直接 fallback 到硬编码 `["elastic"]`
3. **assumptions 来源标注**：`assumptions` 字段中现在区分"来自语义层"与"默认"两种来源，使调用方可溯源每条假设的来源层

以下内容仍保持 B 层关键词匹配（语义层暂无更好来源）：
- `initial_position_per_entity` 的缺失判断：仍依赖 `explicit_conditions` 名称关键词（`height`、`position` 等）
- `initial_velocity_per_entity` 的缺失判断：仍依赖 `explicit_conditions` 名称关键词（`velocity`、`v0` 等）
- `mass_per_entity` 的缺失判断：仍依赖 `explicit_conditions` 名称关键词（`mass`、`m` 等）
