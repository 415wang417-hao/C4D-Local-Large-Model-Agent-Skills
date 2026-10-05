# sias-map-agent ｜ 本地 Gemma 4 驱动的校园交互式地图 Agent 技能

> 用**本机运行**的 Gemma 4 模型（Ollama）驱动一个具备**函数调用、结构化输出、多步推理、自评迭代、记忆**能力的 Agent，
> 自动为指定校园生成可缩放、可点击的交互式地图。**全流程零云 API、零费用。**

- 模型：`gemma4:e4b`（Q4_K_M，6.58 GB）
- 运行时：Ollama ≥ 0.3
- 产物：`{place}_map.html`（folium / Leaflet 交互式地图）

---

## 1. 特性

| 能力 | 说明 |
|---|---|
| 🔧 函数调用 | 4 个工具以 OpenAI 兼容 JSON Schema 声明，模型**自主**选择与传参（Ollama 原生 tool calling） |
| 📐 结构化输出 | 生成/自评/导语三处均为严格 JSON，解析层含围栏剥离与字段兜底 |
| 🧠 多步推理 | 生成 POI → 评审 →（未达标则修订）→ 生成导语 → 渲染地图 |
| 🔁 自评闭环 | 模型对自身产出打分并给建议，低于阈值自动触发修订 |
| 💾 记忆 | 每一步的输入/输出/token/耗时写入 `memory/agent_memory.json`，可追溯、可核验 |
| 🗺️ 交互地图 | 分色标记、中文弹窗、图层切换、图例、统计卡片、全屏、鹰眼、比例尺 |
| 🧯 稳定兜底 | 支持 `num_gpu=0` 纯 CPU 推理；渲染前自动 `unload()` 释放显存 |

**零硬编码**：代码中不含任何地点常量，所有 POI 均由本地模型生成（见 `memory/agent_memory.json`）。

---

## 2. 安装

```bash
# 1) 安装 Ollama 并拉取模型
ollama pull gemma4:e4b

# 2) 安装 Python 依赖
pip install -r requirements.txt
```

`requirements.txt`：`requests>=2.31`、`folium>=0.17`、`Pillow>=10.0`、`psutil>=5.9`

---

## 3. 使用

```bash
# 环境取证（输出模型/设备/推理速度，并落盘 verify_result.json）
python verify_env.py

# 函数调用演示（看模型如何自主调用工具）
python run_map_agent.py --demo-function-calling

# 一键截图取证（Windows 双击运行）：同一窗口内先跑函数调用演示，
# 再打印环境证据（Ollama 版本 / 模型与 digest / CPU·GPU·RAM·OS / 卸载策略），
# 便于一张截图同时覆盖"模型名+版本、工具、设备、tok/s"四项要素
demo_function_calling.bat

# 完整流程：生成 POI → 自评 → 导语 → 渲染地图
python run_map_agent.py --place "郑州西亚斯学院(SIAS)" --count 8 --out ./sias_map.html

# 可选（Level 4）：默认模型 vs uncensored 变体同任务对照，结果写 uncensored_compare_result.json
python uncensored_compare.py
```

### 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--model` | `gemma4:e4b` | Ollama 模型标签 |
| `--host` | `http://127.0.0.1:11434` | Ollama 服务地址 |
| `--place` | `郑州西亚斯学院(SIAS)` | 目标地点 |
| `--count` | `8` | 标记点数量（≥5 生效） |
| `--out` | `lenovo_C4D_map.html` | 地图输出路径 |
| `--memory` | `agent_memory.json` | 记忆文件路径 |
| `--num-ctx` | `8192` | 上下文长度（小显存建议 2048） |
| `--demo-function-calling` | off | 仅演示函数调用 |

---

## 4. 目录结构

```
.
├── run_map_agent.py        # CLI 入口
├── verify_env.py           # 环境取证（模型/设备/速度）
├── verify_env.bat          # 取证脚本的可视化窗口包装
├── demo_function_calling.bat  # 函数调用演示 + 环境证据（一键截图取证）
├── uncensored_compare.py   # Level 4 加分项：默认模型 vs uncensored 变体对照实验
├── uncensored_compare_result.json  # 上述实验的原始结果
├── verify_result.json      # 环境取证落盘结果
├── requirements.txt
├── memory/
│   └── agent_memory.json   # 记忆：每步模型输出 + token 统计
└── sias_agent/
    ├── __init__.py
    ├── llm_client.py       # Ollama HTTP 封装 + tok/s 统计 + unload()
    ├── tools.py            # 工具实现 + JSON Schema + prompt 模板
    ├── agent.py            # 编排：多步推理 / 校验 / 自评修订
    ├── memory.py           # 记忆持久化
    └── map_builder.py      # folium 渲染
```

---

## 5. 提供给模型的工具（Function Calling）

| 工具 | 作用 | 关键参数 |
|---|---|---|
| `generate_landmarks` | 生成校园 POI（名称/类别/经纬度/描述） | `count`（≥5） |
| `review_landmarks` | 对已有 POI 做批判性评审，返回评分 + 问题 + 建议 | `landmarks` |
| `refine_landmarks` | 按评审建议修订 POI | `landmarks`, `suggestions` |
| `summarize_place` | 为地图生成一段导语 | `place`, `landmarks` |

Schema 见 `sias_agent/tools.py::TOOLS_SCHEMA`。

---

## 6. 设计要点

1. **校验层只清洗不改写**：`agent.py::_validate()` 仅做去重、坐标范围过滤与字段兜底，**不补写内容**，以保证"数据由模型生成"可被核验。
2. **免密钥底图**：OpenStreetMap / Esri World Imagery / OpenTopoMap，避免因缺失 API Key 导致渲染失败。
3. **显存兜底**：`OllamaClient(num_gpu=0)` 走纯 CPU；`unload()` 在渲染前释放模型占用。
4. **prompt 集中管理**：全部模板位于 `tools.py`，便于版本对比与迭代（本项目经历 v1→v2 两版）。

---

## 7. 常见问题

见《教学说明》第 6 节（连接失败 / 显存不足 / 底图空白 / 中文乱码 / 速度慢 / 换校）。

---

## 8. 许可与致谢

- 代码：供学习与教学使用。
- 依赖：Ollama（MIT）、folium（MIT）、Leaflet（BSD-2）、requests（Apache-2.0）。
- 底图数据版权归 OpenStreetMap 贡献者 / Esri / OpenTopoMap 所有，请遵守各自的使用条款。
