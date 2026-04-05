# PRISM-HJ 架构文档

## 概述

PRISM-HJ（Physical Reasoning & Inference System for Mechanics — HJ）采用**四层架构**，
将"自然语言"与"确定性物理执行"完全解耦，使每一层都可独立测试、替换和审计。

---

## 四层架构

```
┌─────────────────────────────────────────────────────┐
│          第一层：自然语言接口层 (NL Interface)         │
│  src/llm/translator.py                              │
│  职责：NL → PSDL 翻译；仅做语义映射，不做计算         │
├─────────────────────────────────────────────────────┤
│          第二层：PSDL 契约层 (Contract Layer)         │
│  src/schema/psdl.py  ·  src/schema/units.py         │
│  职责：结构化知识契约；量纲/单位强制验证              │
├─────────────────────────────────────────────────────┤
│          第三层：知识编译层 (Knowledge Compiler)      │
│  src/physics/dispatcher.py  ·  src/templates/       │
│  职责：场景分类 → 选择求解器；模板填充                │
├─────────────────────────────────────────────────────┤
│          第四层：确定性执行层 (Deterministic Engine)  │
│  src/physics/analytic.py  ·  src/physics/engine.py  │
│  职责：可重现、可校验的数值/解析求解                  │
└─────────────────────────────────────────────────────┘
```

---

## 第一层：自然语言接口层

**模块**：`src/llm/translator.py`

**职责**：
- 接收任意自然语言物理问题
- 调用 LLM（Ollama）将其翻译为合法的 PSDL v0.1 JSON
- 可选地调用 `classify_scenario()` 帮助 LLM 填写 `scenario_type` 字段

**约束**：
- LLM **只翻译，不计算**；所有数值计算在第三/四层完成
- 输出必须通过 PSDL Pydantic 校验才能进入下一层

**接口预留**：
- `classify_scenario(text) -> str`：返回场景类型字符串（future: 用于模板路由）
- `fill_template(scenario_type, params) -> PSDL`：模板填充（future）

---

## 第二层：PSDL 契约层

**模块**：`src/schema/psdl.py`，`src/schema/units.py`

### PSDL v0.1 关键字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `schema_version` | `str` | 始终 `"0.1"` |
| `scenario_type` | `str \| None` | 场景分类（`free_fall`, `projectile`, …） |
| `assumptions` | `List[str]` | 显式假设（无空气阻力、质点模型等） |
| `source_refs` | `List[str]` | 教材/题目来源引用 |
| `validation_targets` | `List[ValidationTarget]` | 期望结果（供执行层校验） |
| `world.ground_plane` | `bool` | 地面必须**显式**开启，默认 `False` |

### 量纲/单位体系（units.py）

基础量纲：`length`, `mass`, `time`, `velocity`, `acceleration`, `force`, `dimensionless`

| 单位符号 | 名称 | 量纲 |
|----------|------|------|
| `m` | metre | length |
| `kg` | kilogram | mass |
| `s` | second | time |
| `m/s` | metre per second | velocity |
| `m/s^2` | metre per second squared | acceleration |
| `N` | newton | force |
| `1` | dimensionless | dimensionless |

`validate_unit_for_dimension(unit_symbol, expected_dimension)` 在不兼容时抛出 `DimensionError`。

---

## 第三层：知识编译层

**模块**：`src/physics/dispatcher.py`，`src/templates/`

**职责**：
- `dispatch(psdl) -> List[Dict]`：根据 `scenario_type` 路由到对应求解器
- 当前支持：
  - `free_fall` → `analytic.solve_free_fall()`
  - 其他/未知 → `engine.simulate_psdl()`（PyBullet 数值求解）

**模板基础设施**（`src/templates/`）：
- `free_fall.build_psdl(...)` — 从物理参数直接生成符合 PSDL v0.1 的文档，
  包含正确的 `assumptions`、`validation_targets` 和 `source_refs`

---

## 第四层：确定性执行层

**模块**：`src/physics/analytic.py`，`src/physics/engine.py`

### 解析求解器（analytic.py）

- `solve_free_fall(psdl) -> List[Dict]`：精确运动学方程，误差为浮点精度
- 公式：`z(t) = z₀ + v₀ₜ·t − ½·g·t²`，`vz(t) = v₀ₜ − g·t`
- 返回格式与 PyBullet 求解器相同：`[{"position": [x,y,z], "velocity": [vx,vy,vz]}]`

### PyBullet 数值求解器（engine.py）

- 半隐式 Euler 积分，默认 `dt=0.01s`
- **地面平面必须显式建模**：`WorldSettings.ground_plane=True` 或直接调用 `sim.add_plane()`
- `simulate_psdl()` 不再隐式添加地面

---

## 设计原则

1. **PSDL 优先于引擎**：物理意图在契约层完整表达，执行层只是实现细节
2. **默认 SI**：所有数值均为国际单位制；单位符号参与校验
3. **无隐式假设**：地面、边界、阻尼等必须显式声明
4. **可信闭环优先**：新功能必须有对应测试和金标验证才能合并
5. **LLM 仅翻译**：第一层不承担任何物理计算或验证

---

## 数据流

```
用户输入 (自然语言)
    ↓  text_to_psdl() / classify_scenario()
PSDL v0.1 文档 (JSON + Pydantic 校验)
    ↓  dispatcher.dispatch()
    ├─ [free_fall]  → analytic.solve_free_fall()
    └─ [other]      → engine.simulate_psdl()
    ↓
List[{"position": [...], "velocity": [...]}]
    ↓  generate_answer()
自然语言回答
```
