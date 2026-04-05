# PRISM-HJ：自然语言 → 物理模拟

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![PyBullet](https://img.shields.io/badge/Physics-PyBullet-orange)](https://pybullet.org)

**PRISM-HJ** 是一个轻量级命令行工具，将自然语言描述的物理问题自动转换为结构化物理场景契约（**PSDL v0.1**），
通过智能 dispatcher 选择最优求解器（解析精确解或 PyBullet 数值模拟），最后用自然语言返回结果。
整个过程 **零训练**，完全依赖人类已知的物理定律和 LLM 的理解能力。

> 核心理念：**PSDL 是系统的知识契约，执行层只是实现细节。**

---

## 四层架构（v0.2）

完整架构说明见 [`docs/architecture.md`](docs/architecture.md)。

```
用户输入（自然语言）
        │
        ▼
┌──────────────────────────────────────┐
│  第一层：NL 接口层                    │  模板优先路径：classify_scenario()
│  src/llm/translator.py               │  → free_fall / projectile / collision
│  src/templates/extractor.py          │  → 参数提取 → 模板 PSDL（无 LLM）
└──────────────────────────────────────┘  ↓ 若无法提取则 fallback → LLM
        │
        ▼
┌──────────────────────────────────────┐
│  第二层：PSDL 契约层                  │  schema_version / scenario_type /
│  src/schema/psdl.py                  │  assumptions / source_refs /
│  src/schema/units.py                 │  validation_targets + 量纲校验
│  src/sources/validation.py           │  ← source registry 运行时校验
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│  第三层：知识编译层                   │  场景分类 → 求解器路由
│  src/physics/dispatcher.py           │  src/templates/{free_fall, projectile,
│  src/validation/runner.py            │               collision}.py
└──────────────────────────────────────┘
        │
        ├─── free_fall  ──▶ analytic.solve_free_fall()（精确解）
        ├─── projectile ──▶ analytic.solve_projectile()（精确解）
        ├─── collision  ──▶ analytic.solve_collision_1d_elastic()（精确解）
        └─── 其他       ──▶ engine.simulate_psdl()（PyBullet 数值积分）
        │
        ▼
┌──────────────────────────────────────┐
│  第四层：确定性执行层 + 验证          │  可重现、可审计的物理求解
│  src/physics/analytic.py             │  + 自动验证 validation_targets
│  src/physics/engine.py               │
└──────────────────────────────────────┘
        │
        ▼
     最终回答（NL）+ Validation Summary
```

---

## 快速开始

### 1. 环境准备

```bash
# 克隆仓库
git clone https://github.com/yourusername/PRISM-HJ.git
cd PRISM-HJ

# 创建 conda 环境（推荐）
conda create -n prism python=3.10 -y
conda activate prism

# 安装 Python 依赖
pip install -r requirements.txt
```

### 2. 安装 Ollama 并拉取模型

```bash
# 安装 Ollama（Linux / macOS / WSL2）
curl -fsSL https://ollama.com/install.sh | sh

# 拉取 DeepSeek-R1:32B（约 20GB，需耐心等待）
ollama pull deepseek-r1:32b

# 在另一个终端保持 Ollama 服务运行
ollama serve
```

### 3. 运行第一个测试

```bash
python main.py --question "一个2kg的球从高度5米自由落体，忽略空气阻力，1秒后球的位置和速度？"
```

示例输出（模板优先路径，无 LLM 调用）：

```
[Solver: analytic_free_fall]
[Validation: 2/2 passed]
  final_z: PASS — observed=0.1 m, expected=0.1 m, tol=1.0%
  final_vz: PASS — observed=-9.8 m/s, expected=-9.8 m/s, tol=1.0%
```

#### 批量处理

```bash
python main.py --file examples/questions.txt
```

### 4. 运行单元测试

```bash
python -m pytest tests/ -v
```

---

## 项目结构

```
PRISM-HJ/
├── LICENSE                  (Apache 2.0)
├── README.md                (本文件)
├── requirements.txt         (Python 依赖)
├── main.py                  (主入口，argparse CLI)
├── data/
│   └── sources/
│       └── registry.yaml    # 来源注册表（tier 治理）
├── docs/
│   ├── architecture.md      # 四层架构详细说明
│   └── source_policy.md     # 来源治理政策（v0.2）
├── src/
│   ├── schema/
│   │   ├── psdl.py          # PSDL v0.1 知识契约（Pydantic）
│   │   └── units.py         # 量纲/单位框架
│   ├── sources/
│   │   ├── registry.py      # 来源注册表加载器（运行时）
│   │   └── validation.py    # source_refs 运行时校验（4条规则）
│   ├── physics/
│   │   ├── analytic.py      # 解析求解器（free_fall / projectile / collision）
│   │   ├── dispatcher.py    # 求解器路由 + dispatch_with_validation()
│   │   └── engine.py        # PyBullet 封装（数值积分，无隐式地面）
│   ├── templates/
│   │   ├── extractor.py     # 自然语言参数提取（正则，模板优先路径）
│   │   ├── free_fall.py     # free_fall 场景模板
│   │   ├── projectile.py    # projectile 场景模板（v0.2 新增）
│   │   └── collision.py     # collision 场景模板（v0.2 新增）
│   ├── validation/
│   │   └── runner.py        # ValidationTarget 自动执行
│   └── llm/
│       └── translator.py    # 模板优先路径 + Ollama LLM fallback
├── tests/
│   ├── test_free_fall.py             # 三层验证：解析/模板/PyBullet
│   ├── test_schema.py                # PSDL v0.1 字段与 ValidationTarget
│   ├── test_units.py                 # 量纲/单位框架
│   ├── test_dispatcher.py            # 求解器路由
│   ├── test_classifier.py            # 场景分类器
│   ├── test_sources.py               # 来源注册表结构
│   ├── test_validation_runner.py     # ValidationTarget 执行
│   ├── test_pipeline_integration.py  # 模板优先编译路径集成测试（v0.2）
│   ├── test_source_registry_validation.py  # 来源运行时校验测试（v0.2）
│   ├── test_projectile_template.py   # projectile 模板与解析器（v0.2）
│   └── test_collision_template.py    # collision 模板与解析器（v0.2）
└── examples/
    └── questions.txt        # 示例问题文件
```

---

## PSDL v0.1 关键特性

### 新增字段

| 字段 | 说明 |
|------|------|
| `schema_version` | 契约版本（当前 `"0.1"`） |
| `scenario_type` | 场景分类（`"free_fall"`, `"projectile"`, `"collision"`），驱动求解器路由 |
| `assumptions` | 显式建模假设（如 `"no air resistance"`, `"point mass"`） |
| `source_refs` | 教材/题目出处引用（受 source registry 治理） |
| `validation_targets` | 预计算的金标期望值，供执行层自动验证 |
| `world.ground_plane` | 地面必须**显式**声明；执行层不再隐式添加 |

### 量纲/单位框架（units.py）

```python
from src.schema.units import Dimension, validate_unit_for_dimension

validate_unit_for_dimension("m/s^2", Dimension.acceleration)  # OK
validate_unit_for_dimension("kg",    Dimension.length)         # → DimensionError
validate_unit_for_dimension("mph",   Dimension.velocity)       # → UnknownUnitError
```

---

## 模板优先编译路径（v0.2）

当前支持的 `scenario_type` 及对应模板优先路径：

| `scenario_type` | 模板文件 | 参数提取器 | 解析求解器 |
|-----------------|----------|-----------|-----------|
| `"free_fall"` | `templates/free_fall.py` | `extractor.extract_free_fall_params()` | `analytic.solve_free_fall()` |
| `"projectile"` | `templates/projectile.py` | `extractor.extract_projectile_params()` | `analytic.solve_projectile()` |
| `"collision"` | `templates/collision.py` | `extractor.extract_collision_params()` | `analytic.solve_collision_1d_elastic()` |

**工作流程**：
1. `classify_scenario()` 用正则规则识别场景类型（中文 + 英文）
2. 对应 extractor 尝试从自然语言中提取数值参数
3. 若提取成功 → 直接构建 PSDL 模板（**不调用 LLM**）
4. 若提取失败 → fallback 到 Ollama LLM 路径

**Fallback 场景**：
- 问题中无法提取关键参数（如高度、速度等）
- 识别结果为 `None`（未知题型）
- 所有其他非支持场景（optics、EM 等）

---

## 求解器策略（v0.2）

| `scenario_type` | 求解器 | 误差 |
|-----------------|--------|------|
| `"free_fall"` | `analytic.solve_free_fall()` | 浮点精度（< 1e-9） |
| `"projectile"` | `analytic.solve_projectile()` | 浮点精度（< 1e-9） |
| `"collision"` | `analytic.solve_collision_1d_elastic()` | 浮点精度（< 1e-9） |
| 其他 / `None` | `engine.simulate_psdl()`（PyBullet） | ≤ 5%（半隐式 Euler） |

---

## Source Registry 治理（v0.2）

来源注册表 `data/sources/registry.yaml` 现已参与**运行时校验**（非仅文档约束）。

`src/sources/validation.py` 的 `validate_source_refs()` 强制执行四条规则：

1. `source_id` 必须存在于注册表
2. 分配的 `role` 必须在该来源的 `allowed_uses` 列表中
3. `tier: standards_only` 的来源（NIST、ITU）不得在力学场景中担任 `secondary_reference` 或内容来源角色
4. 力学场景（`free_fall` / `projectile` / `collision`）的 `primary_template_source` 必须来自 `tier_1_authoritative`

> **NIST / ITU 仍仅限 units/metrology 用途**：它们的 `allowed_uses` 只有 `units_reference` 和 `metrology_reference`，不得作为任何力学题型的模板来源。

---

## Validation Summary（v0.2）

CLI 现在始终打印 solver 路径和验证摘要：

```
[Solver: analytic_projectile]
[Validation: 4/4 passed]
  final_x:  PASS — observed=10.0 m, expected=10.0 m, tol=1.0%
  final_z:  PASS — observed=0.1 m, expected=0.1 m, tol=1.0%
  final_vx: PASS — observed=10.0 m/s, expected=10.0 m/s, tol=1.0%
  final_vz: PASS — observed=-9.8 m/s, expected=-9.8 m/s, tol=1.0%
```

若 `validation_targets` 为空，主流程仍正常执行：

```
[Solver: pybullet]
[Validation: no targets defined]
```

---

## 设计原则

1. **PSDL 优先于引擎** — 物理意图在契约层完整表达，执行层只是实现细节
2. **默认 SI** — 所有数值均为国际单位制
3. **units 参与验证** — 单位符号不只是文档，校验失败会抛出异常
4. **无隐式假设** — 地面、边界、阻尼等必须显式声明
5. **LLM 仅翻译** — 不承担任何物理计算；模板优先路径减少 LLM 依赖
6. **可信闭环优先** — 每个新功能必须有对应测试和金标验证
7. **来源治理** — source registry 运行时强制执行，而非文档约束

---

## 已知限制

- units v0.1 仅支持 7 种基础量纲（无能量、压力、角动量等）
- 边界形状仅支持轴对齐长方体（AABB）
- collision 模板仅支持 1-D 弹性碰撞（两质点，沿 x 轴）
- LLM 对模糊描述可能输出不完整的 PSDL（但会被 Pydantic + units 校验捕获）
- 模板参数提取器（extractor.py）仅覆盖常见表述；罕见表述会 fallback 到 LLM

---

## 贡献指南

欢迎提交 Issue 和 Pull Request。请确保：

1. 代码符合 **PEP 8**。
2. 为新功能添加单元测试（`tests/` 目录）。
3. 更新 `README.md` 与 `docs/architecture.md` 中相关部分。

---

## 许可证

本项目采用 **Apache 2.0** 许可证。详见 [LICENSE](LICENSE) 文件。

---

## 致谢

- [DeepSeek](https://deepseek.com/) 提供高性能开源模型
- [Ollama](https://ollama.com/) 简化本地 LLM 部署
- [PyBullet](https://pybullet.org/) 提供可靠的物理模拟

