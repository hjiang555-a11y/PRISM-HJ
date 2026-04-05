# PRISM-HJ 参考来源治理政策 (Source Governance Policy)

> 版本：v0.2 | 生效日期：2026-04 | 适用范围：所有 PSDL 模板、验证案例及单位定义

---

## 1. 为什么需要来源分层

PRISM-HJ 的物理推理过程依赖于权威教学与标准来源，以保证：

- **正确性**：模板逻辑和数值结果有可追溯的教材依据
- **可审查性**：当 ValidationTarget 失败时，能够回溯到具体来源章节
- **层级清晰**：不同质量的来源承担不同职责，不得混用
- **单位与计量规范分离**：计量标准机构（NIST、ITU）只负责单位定义和时频术语，不作为一般力学问题的模板来源

---

## 2. 来源层级定义

### tier_1_authoritative — 一级权威来源

适用于：**主模板依据（primary_template_source）**

这类来源是开放许可的大学物理教材，内容经同行评审，覆盖完整的经典力学体系。

| 来源 | 说明 |
|------|------|
| OpenStax University Physics | 完整大学物理（卷一~三），CC BY 4.0 |
| OpenStax College Physics 2e | 高中/大一物理，CC BY 4.0 |
| MIT OpenCourseWare Physics（8.01 / 8.02） | MIT 经典课程，CC BY-NC-SA |

### tier_2_high_quality_educational — 二级高质量教育来源

适用于：**辅助参考（secondary_reference）、概念佐证（conceptual_reference）**

| 来源 | 说明 |
|------|------|
| The Feynman Lectures on Physics | Caltech 出版，深度物理讲解 |
| Motion Mountain Physics Textbook | 开放教材，覆盖广泛的物理主题 |

### standards_only — 仅限标准与计量

适用于：**单位定义（units_reference）、时频计量术语（metrology_reference）**

| 来源 | 说明 |
|------|------|
| NIST Time and Frequency Division | 美国国家标准与技术研究院，SI 单位权威定义 |
| ITU Time/Frequency Handbook | 国际电信联盟，时间/频率国际计量标准 |

### pending — 待审查

未经评估或不满足上述条件的来源，**不得**用于模板或验证案例，需先走审核流程。

---

## 3. 各场景允许的来源类型

| 使用场景 | 允许层级 | 典型 role 值 |
|----------|----------|-------------|
| 力学模板主依据（free_fall、projectile、collision 等） | tier_1_authoritative | `primary_template_source` |
| 力学题目辅助参考 | tier_1_authoritative, tier_2_high_quality_educational | `secondary_reference`, `conceptual_reference` |
| 验证案例数值来源 | tier_1_authoritative | `primary_template_source` |
| SI 单位定义 | standards_only | `units_reference` |
| 时间/频率计量术语 | standards_only | `metrology_reference` |
| 标准参考元数据 | standards_only | `metrology_reference` |

---

## 4. NIST / ITU 使用限制（关键约束）

> **⚠️ 明确禁止：** 不得将 NIST 或 ITU 来源设为任何力学题目模板（free_fall、projectile、collision 等）的 `primary_template_source` 或 `secondary_reference`。

NIST 与 ITU 在 PRISM-HJ 中的角色**仅限于**：

1. **单位定义（units）**：SI 基本单位和导出单位的精确定义（如秒的铯原子跃迁定义）
2. **时间/频率计量术语（time_frequency_reference）**：如 UTC、TAI、频率标准等
3. **计量学语义边界（metrology_terms）**：不确定度、量值溯源等概念

这些来源**不适合**作为：
- 自由落体、抛体运动等经典力学题目的参考来源
- 物体碰撞、圆周运动等动力学问题的数值依据
- 任何需要"物理教学推导"的场景

---

## 5. source_refs 字段建模规范

在 PSDL 文档中，`source_refs` 字段支持两种格式：

### 推荐格式：结构化 `SourceRef` 对象

```json
{
  "source_id": "openstax_university_physics_v1",
  "role": "primary_template_source"
}
```

`role` 的合法值：

| role 值 | 含义 |
|---------|------|
| `primary_template_source` | 模板逻辑的主要教材依据 |
| `secondary_reference` | 辅助参考 |
| `units_reference` | 单位定义来源（仅 standards_only 使用）|
| `metrology_reference` | 计量术语来源（仅 standards_only 使用）|
| `conceptual_reference` | 概念性参考（物理含义解释）|

### 兼容格式：纯字符串（向后兼容）

```json
"OpenStax University Physics, Chapter 4.3"
```

新代码应优先使用结构化格式，以便与注册表 `data/sources/registry.yaml` 联动。

---

## 6. 来源注册表

所有可信来源均登记在 `data/sources/registry.yaml`。

新增来源需经过：
1. 确认开放许可状态
2. 确认所属 tier
3. 明确 `allowed_uses`（限制字段）
4. 将 `status` 设为 `active`

未在注册表中的来源不得在模板的 `source_refs` 中以 `source_id` 形式引用。

---

## 7. Wikipedia / Wikibooks 不纳入正式可信来源

Wikipedia 和 Wikibooks 内容可变、无同行评审责任，**不纳入正式可信来源白名单**，
不得出现在模板 `source_refs` 的 `source_id` 字段中。

可作为非正式草稿参考或开发期辅助，但须在 `pending` 层级下注明。
