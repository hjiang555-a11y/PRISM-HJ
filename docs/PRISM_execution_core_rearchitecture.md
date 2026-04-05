# 《PRISM-HJ 执行核心重构总纲（草案）》

---

## 1. 背景与动机

PRISM-HJ 早期以 `scenario_type` 为中心组织执行流程。具体做法是：

- 将用户问题归类为 `free_fall`、`projectile`、`collision` 等预定义场景类型；
- 通过 template + solver 映射，将场景类型直接路由到对应解析求解器；
- PSDL 契约中的 `scenario_type` 字段既是分类标签，也是执行路由的依据。

这个结构在早期有明确价值：实现简单、可测试性强、对常见力学题型覆盖完整。但随着系统向更广泛物理领域（电磁学、热力学等）扩展的需求越来越清晰，以 scenario/solver 为中心的结构暴露出如下不足：

1. **扩展性有限**：每新增一类物理场景，都需要新增对应的 solver 和路由逻辑，不具备统一的组织原则。
2. **场景类型划分不严谨**：`free_fall` 与 `projectile` 在物理上并非并列的基本类型，而是相同背景规则在不同初始条件下的特例。
3. **无法表达规则叠加**：碰撞等局部接触事件叠加于背景作用之上，而非替代背景作用；现有结构无法清晰区分持续作用与局部触发作用。
4. **跨领域规则无法共同作用**：当一个状态集同时受经典力学和电磁学规则影响时，现有路由结构无法表达这种叠加。

---

## 2. 新核心原则

重构后的执行核心遵循以下原则：

- **系统不再以题型或 solver 为中心**。执行核心的组织单元是物理状态，而非题型分类。
- **核心是 target-related state sets**。系统针对一组目标相关的实体及其状态变量进行演化，而非针对抽象题型执行预定义流程。
- **规则不是 solver，而是 primitive rules**。每条规则表达一个基础物理关系，可独立声明、独立激活，可与其他规则叠加共同作用。
- **时间和空间条件是核心**。规则的激活与失活受时空条件约束；spatiotemporal conditions 不是附加信息，而是执行调度的核心依据。
- **事件的本质是局部规则激活**。所谓"事件"，是指在特定时空条件满足时，某一组局部规则被激活；事件结束时，这些规则失活。
- **persistent interactions 与 local interactions 需要分离**。持续作用（如重力、电场）始终贡献于状态演化；局部作用（如碰撞、接触力）仅在满足触发条件时短暂激活。

---

## 3. 经典力学中的重解释

在新框架下，经典力学的常见场景需要被重新定位：

- **自由落体不是与斜抛并列的基本物理类型**。两者更接近同一背景规则（`classical_mechanics.background.constant_gravity`）在不同初始条件和坐标表达下的特例。区别仅在于初始水平速度是否为零，而非物理规律的差异。
- **碰撞/接触是背景作用上的附加规则，而不是替代背景作用的整体切换**。碰撞发生时，背景重力仍然持续作用；碰撞只是额外激活了一组局部接触规则（`classical_mechanics.contact.impulsive_collision`），这些规则在碰撞完成后失活。

这一重解释的意义在于：系统不再需要为每种"题型"分配独立求解器，而是通过 active rule set 的组合来描述任意物理过程。

---

## 4. 新执行核心架构

新执行核心围绕以下三个主要阶段组织：

### 4.1 Event Extraction（事件提取）

从输入（自然语言、结构化描述或模板结果）中提取：

- 涉及的实体（entities）
- 目标状态集规格（target state set specification）
- 候选领域（candidate domains）
- 时空条件（spatiotemporal conditions）
- 持续规则候选（persistent rule candidates）
- 局部规则候选（local rule candidates）
- 参考系上下文（frame context）
- 初始条件（initial conditions）

Event Extraction 的输出不是 `scenario_type`，而是一个结构化的规则候选集和状态集规格。

### 4.2 Rule-Oriented Evolution（规则驱动演化）

Evolution Scheduling 负责：

- 初始化 active rule set（包含所有 persistent rules）
- 在每个时间步评估触发条件
- 激活或失活 local rules
- 汇总所有 active rules 对状态变量的贡献
- 推进状态集更新
- 记录触发点、规则变更历史

演化过程支持：

- 多实体并发演化
- 跨领域规则共同作用（active rule set 可同时包含来自多个 domain 的规则）
- 局部规则的短时激活与失活
- Persistent rules 的持续贡献

### 4.3 Result Assembly（结果汇总）

从演化完成的状态集、触发记录和规则历史中，提取面向目标的结果。输出面向用户关心的物理量，而不是执行内部的状态变量结构。

---

## 5. 多学科扩展

执行核心的设计必须支持多学科规则共同作用：

- **未来可能出现跨领域共同作用**。例如，一个带电粒子在重力场和电磁场中运动，其状态演化同时受 `classical_mechanics.background.constant_gravity` 和 `electromagnetism.field.lorentz_force` 约束。
- **domain 是规则组织维度，不是执行排他维度**。`classical_mechanics`、`electromagnetism`、`thermodynamics` 等是规则的命名空间和分类维度，不代表执行时的互斥选择。
- **真正调度的是跨领域 active rule set**。Evolution Scheduling 在任意时刻维护的是一个可能包含多个 domain 规则的 active rule set；各规则对状态变量的贡献可以叠加。

---

## 6. 规则命名原则

为保证规则的可识别性、可组合性和跨 domain 一致性，推荐以下命名结构：

```
<domain>.<family>.<rule>[.<model>]
```

其中：

- `domain`：物理领域，如 `classical_mechanics`、`electromagnetism`、`thermodynamics`
- `family`：规则族，如 `background`（背景持续作用）、`contact`（接触/碰撞）、`field`（场作用）、`transfer`（传输过程）
- `rule`：具体规则名称
- `model`（可选）：物理模型标记，如 `point_mass`、`rigid_body`、`ideal_gas`

示例：

| 规则名 | 说明 |
|--------|------|
| `classical_mechanics.background.constant_gravity` | 匀强重力场持续作用 |
| `classical_mechanics.background.constant_gravity.point_mass` | 质点近似下的匀强重力 |
| `classical_mechanics.contact.impulsive_collision` | 冲量碰撞（局部触发） |
| `classical_mechanics.contact.normal_force` | 接触法向力（条件激活） |
| `electromagnetism.field.lorentz_force` | 洛伦兹力（电磁场作用） |
| `electromagnetism.field.coulomb_interaction` | 库仑相互作用 |
| `thermodynamics.transfer.heat_conduction` | 热传导（持续传输） |
| `time_frequency_metrology.clock_offset_evolution` | 时钟偏差演化 |

---

## 7. 与旧结构的关系

现有结构的定位调整如下：

- **现有 `free_fall`、`projectile`、`collision` 模块暂时保留**，不删除、不修改。
- **当前定位为 legacy / reference / testing-oriented modules**：
  - 作为历史参考，说明早期以场景类型为中心的执行方式；
  - 作为测试基准，验证基础运动学结果的正确性；
  - 不再代表执行核心的长期方向。
- **将来随着新状态集与规则系统成熟**，这些模块可能进一步降级（如移入 `legacy/` 目录）或移除。

`PSDL` 契约层和 `units` 框架在新架构中仍然有效；schema 中的 `scenario_type` 字段作为兼容性保留，但在新执行核心中不再承担路由作用。

---

## 8. 迁移策略

推荐按以下步骤推进重构：

1. **固定理论与术语**：确立"state sets / primitive rules / persistent interactions / local interactions / active rule set / result assembly / cross-domain rule composition"等核心术语，形成团队共识。
2. **定义最小执行本体接口**：完成 `EventExtractionResult`、`TargetStateSetSpec`、`PrimitiveRuleSpec`、`TriggerConditionSpec`、`EvolutionScheduleConfig`、`AssemblyRequest`、`AssemblyResult` 等接口草案（见 `docs/PRISM_execution_core_interfaces_v0_1.md`）。
3. **做最小原型**：选取一个典型场景（如质点在重力和电磁力共同作用下的运动），用新接口驱动完整演化流程，验证框架可行性。
4. **逐步让新核心接管主路径**：在原型验证通过后，将 `dispatcher.py` 的路由逻辑逐步迁移到新的 Evolution Scheduling 接口；旧 solver 路径可作为 fallback 保留直至完全替换。
