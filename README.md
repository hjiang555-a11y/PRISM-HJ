# PRISM-HJ：自然语言 → 物理模拟

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![PyBullet](https://img.shields.io/badge/Physics-PyBullet-orange)](https://pybullet.org)

**PRISM-HJ** 是一个轻量级命令行工具，将自然语言描述的物理问题自动转换为结构化物理场景（**PSDL**），
调用 **PyBullet** 进行确定性 3D 模拟，最后用自然语言返回结果。整个过程 **零训练**，完全依赖人类已知
的物理定律（由物理引擎提供）和 LLM 的理解能力。

> 核心理念：**用人类已有的物理知识增强 AI，而不是让 AI 从数据中重新学习物理。**

---

## 哲学与架构

### 为什么需要 PSDL？

- Token 空间太小，无法直接承载连续的物理状态向量。
- PSDL 作为 **物理场景描述语言**，显式包含所有必要参数（质量、位置、速度、边界条件等）。
- LLM 只负责 **翻译**（自然语言 → PSDL）和 **解释**（模拟结果 → 自然语言），不参与物理计算。

### 系统架构

```
用户输入（自然语言）
        │
        ▼
┌──────────────────┐
│  LLM (DeepSeek)  │  ← 翻译：自然语言 → PSDL (JSON)
└──────────────────┘
        │
        ▼
┌──────────────────┐
│   PSDL 验证器    │  ← Pydantic 模型，强制结构正确性
└──────────────────┘
        │
        ▼
┌──────────────────┐
│  PyBullet 模拟器  │  ← 确定性 3D 物理计算（重力、碰撞、边界）
└──────────────────┘
        │
        ▼
┌──────────────────┐
│  LLM (DeepSeek)  │  ← 解释：模拟结果 → 自然语言回答
└──────────────────┘
        │
        ▼
     最终回答
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

**预期输出片段：**

```
[INFO] Translating natural language to PSDL...
[INFO] PSDL (JSON):
{
  "world": {
    "gravity": [0, 0, -9.8],
    "dt": 0.01,
    "steps": 100,
    "space": {"min": [-10,-10,-10], "max": [10,10,10], "boundary_type": "elastic"},
    "theorems": ["newton_second", "energy_conservation"]
  },
  "objects": [
    {"type": "particle", "mass": 2.0, "radius": 0.1, "position": [0,0,5],
     "velocity": [0,0,0], "restitution": 0.9}
  ],
  "query": "1秒后球的位置和速度"
}
[INFO] Running physics simulation...
[INFO] Final states: [{"position": [0.0, 0.0, 4.51], "velocity": [0.0, 0.0, -9.8]}]

Answer:
根据模拟结果，该2千克的球在忽略空气阻力的情况下，从5米高度自由落体1秒后：
- 位置（高度）：约 4.51 米
- 速度：向下约 9.8 米/秒
```

#### 批量处理

```bash
# 从文件逐行读取问题
python main.py --file examples/questions.txt
```

---

## 项目结构

```
PRISM-HJ/
├── LICENSE                  (Apache 2.0)
├── README.md                (本文件)
├── requirements.txt         (Python 依赖)
├── main.py                  (主入口，argparse CLI)
├── src/
│   ├── __init__.py
│   ├── schema/
│   │   ├── __init__.py
│   │   └── psdl.py          # PSDL 数据模型（Pydantic）
│   ├── physics/
│   │   ├── __init__.py
│   │   └── engine.py        # PyBullet 封装
│   └── llm/
│       ├── __init__.py
│       └── translator.py    # Ollama 调用 + PSDL 生成
├── tests/
│   └── test_free_fall.py    # 单元测试（自由落体验证）
└── examples/
    └── questions.txt        # 示例问题文件
```

---

## 自定义与扩展

### 支持的物理机制（当前）

- 重力场
- 弹性碰撞（恢复系数）
- 3D 矩形边界（弹性 / 吸收）

### 预留的扩展接口

| 字段 | 说明 |
|------|------|
| `WorldSettings.theorems` | 激活不同物理定理（如动量守恒） |
| `WorldSettings.observer` | 切换参考系（惯性系/非惯性系） |
| `CircuitPort` | 电路元件（预留） |
| `FieldObject` | 电磁场（预留） |

### 添加新的物理模型（例如空气阻力）

1. 在 `psdl.py` 的 `WorldSettings` 中添加 `drag_coefficient: float = 0.0` 字段。
2. 在 `engine.py` 的 `step` 方法中，对每个粒子施加 `F_drag = -k * v²`。
3. 更新 `SYSTEM_PROMPT` 让 LLM 能从自然语言中提取阻力系数。

---

## 已知限制

- 当前仅支持 **球形粒子**（未来可扩展立方体、圆柱等）。
- 边界形状仅支持 **轴对齐长方体（AABB）**。
- 不处理流体、柔性体、热传导等复杂现象。
- LLM 对极其模糊或悖论性描述可能输出不符合物理的 PSDL（但会被 Pydantic 捕获并提示用户澄清）。
- 使用 `deepseek-r1:32b` 时，首次响应可能需要较长时间（取决于硬件）。

---

## 贡献指南

欢迎提交 Issue 和 Pull Request。请确保：

1. 代码符合 **PEP 8**。
2. 为新功能添加单元测试（`tests/` 目录）。
3. 更新 `README.md` 中相关部分。

---

## 许可证

本项目采用 **Apache 2.0** 许可证。详见 [LICENSE](LICENSE) 文件。

---

## 致谢

- [DeepSeek](https://deepseek.com/) 提供高性能开源模型
- [Ollama](https://ollama.com/) 简化本地 LLM 部署
- [PyBullet](https://pybullet.org/) 提供可靠的物理模拟
