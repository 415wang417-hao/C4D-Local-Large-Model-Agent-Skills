# C4D 本地大模型 Agent 技能 —— 纯 CPU 本地大模型驱动的交互式地图 Agent

> 用**本机运行**的开源大模型（Ollama + gemma4:e4b）驱动一个具备 **函数调用 / 结构化输出 / 多步推理 / 自评迭代 / 持久记忆** 能力的 Agent，
> 从一句自然语言指令出发，自动完成「生成 POI → 评审 → 修订 → 生成导语 → 渲染地图」的 10 阶段流水线，
> 产出一个可缩放、可点击的交互式校园地图。**全流程零云 API、零费用、可离线复现。**

本仓库是 EduSeed 挑战 **C4D「本地大模型 Agent 技能」**（challenge_id `ch-20260717031455-uzqs9k`）的完整交付物。

---

## 1. 关键结果（实测数据）

| 指标 | 实测值 | 取证位置 |
|---|---|---|
| 运行模型 | `gemma4:e4b`（4.5B 有效参数，Q4_K_M，6.58 GB） | `lenovo_C4D_agent-skill/verify_result.json` |
| 模型 digest | `dc35e8d9c606` | 同上 |
| 推理设备 | `num_gpu=0` **纯 CPU 推理**（Windows 11） | `screenshot_01_model_device_speed.png` |
| 端到端一次跑通 | **365 s** | 运行截图 + `agent_memory.json` |
| 全流水线吞吐 | **11.62 tok/s** | 同上 |
| 短输出吞吐 | **18.43 tok/s** | 同上 |
| 地图产出 | **8 个标记点，覆盖 6 个类别** | `lenovo_C4D_map_result.json` |
| 工具技能 | 4 个 function-calling 工具 | `sias_agent/tools.py` |
| 失败台账 | 记录 8 类失败，6 次截图返工 | `lenovo_C4D_AAR.md` |

---

## 2. 快速开始

### 环境要求

- Windows 10/11（本项目在 Windows 11 + PowerShell 5.1 实测）
- [Ollama](https://ollama.com/) ≥ 0.3（本项目实测 0.35.1）
- Python ≥ 3.9

### 安装

```bash
# 1) 拉取本地模型
ollama pull gemma4:e4b

# 2) 安装 Python 依赖
pip install -r lenovo_C4D_agent-skill/requirements.txt
```

### 运行

```bash
cd lenovo_C4D_agent-skill

# 环境取证：打印模型 / 设备 / 推理速度，并落盘 verify_result.json
python verify_env.py

# 函数调用演示：观察模型如何自主选择工具并传参
python run_map_agent.py --demo-function-calling

# 完整流水线：生成 POI → 自评 → 导语 → 渲染交互式地图
python run_map_agent.py --place "郑州西亚斯学院(SIAS)" --count 8 --out ../lenovo_C4D_map.html

# 可选（加分项）：默认模型 vs uncensored 变体同任务对照
python uncensored_compare.py
```

`agent-skill/README.md` 内含完整的参数表、工具 Schema 与设计说明。

---

## 3. 仓库结构（交付物索引）

```
.
├── README.md                      # 本文件：安装 + 使用 + 交付物索引
├── lenovo_C4D_agent-skill/        # ① Agent 技能包（可运行代码）
│   ├── README.md                  #    技能包自身的使用说明（含参数表）
│   ├── run_map_agent.py           #    CLI 入口
│   ├── verify_env.py / .bat       #    环境取证（模型 / 设备 / tok·s⁻¹）
│   ├── demo_function_calling.bat  #    一键演示 + 环境证据（单窗口截图取证）
│   ├── uncensored_compare.py      #    加分项：模型变体对照实验
│   ├── requirements.txt
│   ├── sias_agent/                #    核心包
│   │   ├── llm_client.py          #      Ollama HTTP 封装 + tok/s 统计 + unload()
│   │   ├── tools.py               #      4 个工具实现 + JSON Schema + prompt 模板
│   │   ├── agent.py               #      编排：多步推理 / 校验 / 自评修订
│   │   ├── memory.py              #      持久记忆读写
│   │   └── map_builder.py         #      folium 渲染
│   └── memory/agent_memory.json   #    持久记忆：每步输入输出 + token + 耗时
├── lenovo_C4D_map.html            # ② 最终交互式地图产物（可直接双击打开）
├── lenovo_C4D_map_result.json     #    地图结构化结果（标记点 / 类别 / 统计）
├── lenovo_C4D_output_screenshots/ # ③ 运行截图 4 张 + 截图清单.md
│   ├── screenshot_01 / 01b / 02 / 03 ...png  #    模型设备与速度 / 交互式地图 / 函数调用
├── lenovo_C4D_Agent技能包_清单.md  # ④ Agent 技能包清单（能力 / 工具 / 文件对照）
├── lenovo_C4D_方案设计.md          #    方案设计（含本地 vs 云端取舍对比）
├── lenovo_C4D_验证报告.md          #    验证报告（环境取证 / 指标 / 复现步骤）
├── lenovo_C4D_教学说明.md          #    教学说明（含常见问题排查）
├── lenovo_C4D_拿来说明.md          #    拿来说明（怎么用 / 从哪看）
├── lenovo_C4D_AI日志.md            # ⑤ AI 使用日志（prompt 迭代 + 失败台账）
└── lenovo_C4D_AAR.md              # ⑥ 复盘 AAR（七维：学到什么 / 流程 / 卡点 / 改进）
```

---

## 4. 技术要点

1. **解耦：模型只负责理解与决策，工具层负责确定性执行。** 大模型不直接产出坐标文件，而是通过 4 个声明式工具（`generate_landmarks` / `review_landmarks` / `refine_landmarks` / `summarize_place`）驱动 Python 侧确定性代码。
2. **校验层只清洗不改写。** `agent.py::_validate()` 仅做去重、坐标范围过滤与字段兜底，**不补写内容**，保证「数据由模型生成」可被核验。
3. **零硬编码地点。** 代码中不含任何地点常量，所有 POI 均由本地模型生成（见 `memory/agent_memory.json`）。
4. **纯 CPU 可跑。** `OllamaClient(num_gpu=0)` 走 CPU 推理，渲染前 `unload()` 释放模型占用，无 GPU 环境亦可复现。
5. **免密钥底图。** 使用 OpenStreetMap / Esri World Imagery / OpenTopoMap，避免 API Key 缺失导致渲染失败。
6. **记忆可追溯。** 每一步的输入、输出、token 数与耗时写入 `agent_memory.json`，可独立核验推理过程。
7. **prompt 集中管理。** 全部模板位于 `tools.py`，便于版本对比与迭代（本项目经历 v1 → v2 两版）。

---

## 5. 验证与复现

```bash
# 1) 环境取证：模型标签 / digest / 设备 / 推理速度
python lenovo_C4D_agent-skill/verify_env.py

# 2) 跑完整流程，比对端到端耗时与 tok/s
python lenovo_C4D_agent-skill/run_map_agent.py --place "郑州西亚斯学院(SIAS)" --count 8

# 3) 核对记忆文件中的逐步 token 统计，与截图/报告数据交叉验证
```

详细过程、失败台账与逐项排查见 `lenovo_C4D_验证报告.md`、`lenovo_C4D_AI日志.md`、`lenovo_C4D_AAR.md`。

---

## 6. 已知不足（如实列出）

- 根 README 早期版本内容偏薄，本版已补齐安装、使用与交付物索引（即本次更新）。
- `agent-skill/` 在本地开发时产生过 `__pycache__` 编译缓存；仓库内从未包含此类文件，本版已补 `.gitignore` 防止后续误入。
- AAR 中的自评量纲（365 s）未与 rubric 百分制对齐，仅作过程度量。
- 端到端耗时与吞吐为单机单次实测值，不同 CPU 性能差异较大，非通用性能承诺。

---

## 7. 许可与致谢

- 代码：供学习与教学使用。
- 依赖：Ollama（MIT）、folium（MIT）、Leaflet（BSD-2）、requests（Apache-2.0）。
- 底图数据版权归 OpenStreetMap 贡献者 / Esri / OpenTopoMap 所有，请遵守各自使用条款。
