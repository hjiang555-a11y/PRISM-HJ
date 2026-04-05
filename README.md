# PRISM-HJ：自然语言 → 物理模拟

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![PyBullet](https://img.shields.io/badge/Physics-PyBullet-orange)](https://pybullet.org)

**PRISM-HJ** 是一个轻量级命令行工具，将自然语言描述的物理问题自动转换为结构化物理场景契约（**PSDL v0.1**），
通过智能 dispatcher 选择最优求解器（解析精确解或 PyBullet 数值模拟），最后用自然语言返回结果。
整个过程 **零训练**，完全依赖人类已知的物理定律和 LLM 的理解能力。

> 核心理念：**PSDL 是系统的知识契约，执行层只是实现细节。**

---

## 四层架构（v0.1）

完整架构说明见 [`docs/architecture.md`](docs/architecture.md)。

```
用户输入（自然语言）
        │
        ▼
┌───────────────────────────────┐
│  第一层：NL 接口层             │  LLM 翻译：自然语言 → PSDL
│  src/llm/translator.py        │  classify_scenario() 预留接口
└───────────────────────────────┘
        │
        ▼
┌───────────────────────────────┐
│  第二层：PSDL 契约层           │  schema_version / scenario_type /
│  src/schema/psdl.py           │  assumptions / source_refs /
│  src/schema/units.py          │  validation_targets + 量纲校验
└───────────────────────────────┘
        │
        ▼
┌───────────────────────────────┐
│  第三层：知识编译层            │  场景分类 → 求解器路由
│  src/physics/dispatcher.py    │  src/templates/free_fall.py
└───────────────────────────────┘
        │
        ├─── free_fall ──▶ src/physics/analytic.py（精确解析解）
        └─── 其他       ──▶ src/physics/engine.py（PyBullet 数值积分）
        │
        ▼
┌───────────────────────────────┐
│  第四层：确定性执行层          │  可重现、可审计的物理求解
│  src/physics/analytic.py      │
│  src/physics/engine.py        │
└───────────────────────────────┘
        │
        ▼
     最终回答（NL）
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
├── docs/
│   └── architecture.md      # 四层架构详细说明
├── src/
│   ├── __init__.py
│   ├── schema/
│   │   ├── __init__.py
│   │   ├── psdl.py          # PSDL v0.1 知识契约（Pydantic）
│   │   └── units.py         # 量纲/单位框架（Dimension + UNITS + 校验）
│   ├── physics/
│   │   ├── __init__.py
│   │   ├── analytic.py      # 解析求解器（free_fall 精确解）
│   │   ├── dispatcher.py    # 求解器路由（scenario_type → solver）
│   │   └── engine.py        # PyBullet 封装（数值积分，无隐式地面）
│   ├── templates/
│   │   ├── __init__.py
│   │   └── free_fall.py     # free_fall 场景模板（含金标验证目标）
│   └── llm/
│       ├── __init__.py
│       └── translator.py    # Ollama 调用 + classify_scenario 预留
├── tests/
│   ├── test_free_fall.py    # 三层验证：解析/模板/PyBullet
│   ├── test_schema.py       # PSDL v0.1 字段与 ValidationTarget 测试
│   ├── test_units.py        # 量纲/单位框架测试
│   └── test_dispatcher.py   # 求解器路由与端到端 dispatch 测试
└── examples/
    └── questions.txt        # 示例问题文件
```

---

## PSDL v0.1 关键特性

### 新增字段

| 字段 | 说明 |
|------|------|
| `schema_version` | 契约版本（当前 `"0.1"`） |
| `scenario_type` | 场景分类（`"free_fall"`, `"projectile"`, …），驱动求解器路由 |
| `assumptions` | 显式建模假设（如 `"no air resistance"`, `"point mass"`） |
| `source_refs` | 教材/题目出处引用 |
| `validation_targets` | 预计算的金标期望值，供执行层自动验证 |
| `world.ground_plane` | 地面必须**显式**声明；执行层不再隐式添加 |

### 量纲/单位框架（units.py）

单位符号参与验证，不只是注释：

```python
from src.schema.units import Dimension, validate_unit_for_dimension

validate_unit_for_dimension("m/s^2", Dimension.acceleration)  # OK
validate_unit_for_dimension("kg",    Dimension.length)         # → DimensionError
validate_unit_for_dimension("mph",   Dimension.velocity)       # → UnknownUnitError
```

---

## 求解器策略

| `scenario_type` | 求解器 | 误差 |
|-----------------|--------|------|
| `"free_fall"` | `analytic.solve_free_fall()` | 浮点精度（< 1e-9） |
| 其他 / `None` | `engine.simulate_psdl()`（PyBullet） | ≤ 5%（半隐式 Euler） |

---

## 设计原则

1. **PSDL 优先于引擎** — 物理意图在契约层完整表达，执行层只是实现细节
2. **默认 SI** — 所有数值均为国际单位制
3. **units 参与验证** — 单位符号不只是文档，校验失败会抛出异常
4. **无隐式假设** — 地面、边界、阻尼等必须显式声明
5. **LLM 仅翻译** — 不承担任何物理计算
6. **可信闭环优先** — 每个新功能必须有对应测试和金标验证

---

## 已知限制

- units v0.1 仅支持 7 种基础量纲（无能量、压力、角动量等）
- dispatcher 当前仅路由 `free_fall` 到解析解；其余场景走 PyBullet
- 边界形状仅支持轴对齐长方体（AABB）
- LLM 对模糊描述可能输出不完整的 PSDL（但会被 Pydantic + units 校验捕获）

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
