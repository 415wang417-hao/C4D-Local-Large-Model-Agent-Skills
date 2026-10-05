# 郑州西亚斯学院（SIAS）本地大模型 Agent 技能 —— 方案设计

> 挑战：**C4D 本地大模型 Agent 技能**
> 提交人：lenovo ｜ 完成级别：**Level 3（完整技能包）**，同时满足 Level 2 全部硬性要求；Level 4 已落地两项（**Uncensored 变体对照实验**、**性能参数调优记录**）
> 核心约束：**全流程零云 API**，地点数据 100% 由本地 Gemma 4 模型生成

---

## 0. 一页速览

| 项目 | 内容 |
|---|---|
| 本地模型 | `gemma4:e4b`（Ollama 标签，Q4_K_M 量化，6.58 GB，digest `dc35e8d9c606`） |
| 推理工具 | Ollama 0.35.1（本地服务 `http://127.0.0.1:11434`） |
| 运行设备 | 联想笔记本 · Intel Core i7-14650HX · NVIDIA RTX 5060 Laptop 8 GB · 内存 23.7 GB · Windows 11 (26200) |
| 实测速度 | 纯 CPU 稳定 **11.62 tok/s**（完整 Agent 流水线均值）／短请求峰值 15.42 tok/s／GPU 自动分层 19.89 tok/s |
| 地图产物 | `lenovo_C4D_map.html`，**8 个标记点 / 6 个类别**，可缩放、可点击、含全屏与鹰眼小地图 |
| 技能形态 | `lenovo_C4D_agent-skill/`：可安装、可复现、带 CLI 入口与记忆文件 |
| 云 API 花费 | **0 元**（全程本地推理） |

---

## 1. 任务要求 ↔ 实现对照

| 挑战要求 | 本方案实现 | 证据位置 |
|---|---|---|
| 本地跑通 Gemma 4 | Ollama 拉取并运行 `gemma4:e4b`，FlashAttention 关闭 + 分层卸载调优 | `screenshots/screenshot_01`、`verify_result.json` |
| 标注模型 + 量化 + 设备 | 终端 banner 逐项打印模型标签、体积、digest、CPU/GPU/内存/OS | `screenshot_01_model_device_speed.png` |
| 用本地模型驱动 Agent 技能 | `sias_agent` 包：函数调用 + 结构化输出 + 多步推理 + 自评迭代 | `sias_agent/*.py` |
| 生成交互式地图 | folium 渲染，标记点分色、弹窗、图例、全屏、鹰眼、比例尺 | `lenovo_C4D_map.html` |
| 含 SIAS，≥5 个标记点 | 8 个标记点，覆盖教学/文化/生活/运动/行政/景观 6 类 | `lenovo_C4D_map_result.json` |
| 可缩放、可点击 | Leaflet 原生交互 + 每个标记点独立 Popup | `screenshot_02_interactive_map.png` |
| **地点数据必须由本地模型生成** | 代码内**零地点常量**，POI 全部来自模型输出；生成链路写入记忆文件 | `memory/agent_memory.json` |
| 不花一分钱云 API | 仅调用 `127.0.0.1:11434`，无任何外网推理调用 | `llm_client.py` |

---

## 2. 设备与运行环境

| 项目 | 实测值 |
|---|---|
| 操作系统 | Windows 11（`platform.version()` 返回 10.0.26200） |
| CPU | Intel64 Family 6 Model 183 Stepping 1（Core i7-14650HX，16 核 24 线程） |
| GPU | NVIDIA GeForce RTX 5060 Laptop GPU，8151 MiB，驱动 592.15 |
| 内存 | 23.7 GB |
| Python | 3.11.8 |
| 推理后端 | Ollama 0.35.1（`OLLAMA_FLASH_ATTENTION=0`） |
| 关键第三方库 | requests / folium 0.20.0（渲染）/ Pillow（截图取证） |

> 采集代码：`sias_agent/agent.py::collect_device_info()`，复现命令：`python verify_env.py`。

---

## 3. 模型选型：为什么是 E4B

挑战给出四个候选：E2B / E4B / 26B MoE / 31B Dense。选型依据如下（目标设备为 **8 GB 显存 + 24 GB 内存**的移动端）：

| 候选 | 量级 | 8 GB 显存可行性 | 结构化输出/中文能力 | 结论 |
|---|---|---|---|---|
| **E2B** | 3.4 GB | ✅ 完全放得下 | 偏弱，长 JSON 易截断 | 备选（用于 uncensored 对比） |
| **E4B** | 6.58 GB | ✅ 可整卡加载，或纯 CPU 兜底 | 均衡，能稳定产出 8 条结构化 POI | **选用** |
| 26B MoE | ≈18 GB | ❌ 远超显存，需大量换页 | 强 | 排除（本机不可行） |
| 31B Dense | ≈20 GB | ❌ 不可行 | 强 | 排除（本机不可行） |

**结论**：在"8 GB 显存"这一硬约束下，E4B 是唯一能在**质量与速度之间取得平衡**的档位——它既能一次性产出 8 条带经纬度、类别与描述的结构化 POI，又能在纯 CPU 降级路径下稳定跑完多步 Agent 流水线。26B/31B 在本机不可行（无法在验收环境中复现，违背"本地运行验证"要求）。

**量化方式**：采用 Ollama 官方 `gemma4:e4b` 标签（Q4_K_M，6.58 GB）。选择 Q4_K_M 而非更高精度，是因为量化后体积（6.58 GB）刚好落在 8 GB 显存的可用区间内，同时 4-bit 量化对"生成结构化地点数据"这类任务的质量损失可忽略。

---

## 4. 系统架构

```
                       ┌──────────────────────────────┐
   用户指令 ─────────► │  run_map_agent.py (CLI 入口)  │
                       └───────────────┬──────────────┘
                                       │
                       ┌───────────────▼──────────────┐
                       │   agent.py  SiasMapAgent     │  ← 编排层（多步推理）
                       │  生成→校验→自评→(修订)→导语→渲染 │
                       └───┬───────┬───────┬───────┬──┘
                           │       │       │       │
        ┌──────────────────▼─┐ ┌───▼────┐ ┌▼──────┐ ┌▼────────────┐
        │ tools.py           │ │memory  │ │llm_   │ │map_builder  │
        │ 4 个 Agent 工具：   │ │.py     │ │client │ │.py          │
        │ generate_landmarks │ │全链路  │ │.py    │ │folium 渲染   │
        │ review_landmarks   │ │日志+   │ │Ollama │ │+统计+图例    │
        │ refine_landmarks   │ │记忆    │ │HTTP   │ │             │
        │ summarize_place    │ │持久化  │ │封装   │ │             │
        └────────────────────┘ └────────┘ └───────┘ └─────────────┘
                           │
                    ┌──────▼───────────────────────────┐
                    │ Ollama @ 127.0.0.1:11434         │
                    │ gemma4:e4b (Q4_K_M, 6.58 GB)     │
                    └──────────────────────────────────┘
```

**模块职责**

| 模块 | 行数量级 | 职责 |
|---|---|---|
| `llm_client.py` | ~170 行 | Ollama `/api/chat` 封装：超时、重试、`num_ctx`/`num_gpu`/`temperature` 控制、`unload()` 显存释放、token 统计（tok/s 由 `eval_count/eval_duration` 计算） |
| `tools.py` | ~280 行 | 4 个 Agent 工具 + **Ollama 原生 function calling 的 JSON Schema**；所有 prompt 模板集中于此处 |
| `agent.py` | ~266 行 | 编排层：设备信息采集、banner 打印、字段校验/去重/坐标过滤、自评-修订循环、渲染调度 |
| `memory.py` | ~120 行 | 记忆：每一步的模型输出、token 统计、时间戳落盘为 `memory/agent_memory.json` |
| `map_builder.py` | ~170 行 | folium 渲染：多底图、分色标记、中文弹窗、图例、全屏、鹰眼、比例尺、统计 |
| `run_map_agent.py` | ~63 行 | CLI 入口（`--place/--count/--out/--num-ctx/--demo-function-calling`） |
| `verify_env.py` | ~100 行 | 环境取证脚本：一屏打印四项硬证据并落盘 `verify_result.json` |

---

## 5. Agent 能力设计（对应"Agent 能力展示 25%"）

### 5.1 函数调用（Function Calling）
`tools.py` 中导出 `TOOLS_SCHEMA`（4 个工具的 JSON Schema），通过 Ollama `/api/chat` 的 `tools` 字段传入。模型可**自主决定**调用哪个工具、传什么参数；`agent.py::function_calling_demo()` 提供独立演示入口：

```bash
python run_map_agent.py --demo-function-calling
```

实测：模型在收到"为 SIAS 生成校园地图"后自主发起了 `generate_landmarks` 工具调用（参数由模型填写），而非等待人类指定。

### 5.2 结构化输出（Structured Output）
- 生成阶段：`format="json"` + prompt 内给出字段契约 → 模型输出 `{"landmarks":[{"name","lat","lng","category","description"}]}`
- 自评阶段：输出 `{"score","issues":[],"suggestions":[]}`
- 解析层做**容错**：剥离 ```json 围栏、截取首个 JSON 对象、字段缺失兜底，避免模型偶发多话导致解析失败。

### 5.3 多步推理（Multi-step Reasoning）
一条完整链路，共 5 步，全部由本地模型驱动：

```
[1/5] generate_landmarks  → 生成 8 个 POI（含经纬度/类别/描述）
[2/5] review_landmarks    → 模型对自身产出做批判性评审（评分 + issues + suggestions）
[3/5] refine_landmarks    → 若未达标则按建议修订（本次自评达标，跳过）
[4/5] summarize_place     → 生成面向用户的地图导语
[5/5] build_map           → 渲染交互式地图
```

### 5.4 自我反思与迭代
- Agent 内置**自评-修订闭环**：`score < threshold` 且未达最大修订轮次时，自动调用 `refine_landmarks` 并重新评审。
- 自评由**本地模型自己**完成，不是规则打分——模型给出了 4 条具体问题与 4 条改进建议（见《验证报告》第 2 节）。

### 5.5 记忆（Memory）
每一步的输入摘要、模型原始输出、token 数、耗时、token/s 均写入 `memory/agent_memory.json`，形成可追溯的执行日志——这既是"有记忆"的证据，也是本方案的**自证材料**（证明地点数据来自模型而非硬编码）。

### 5.6 工具统计与可观测性
每次调用返回 `prompt_tokens / completion_tokens / wall_time_s / tokens_per_sec / load_duration_s`，由 `OllamaClient.Stats` 统一封装，直接用于性能报告。

---

## 6. "零硬编码"核验（C4D 的独特风险项）

C4D 的负信号是**硬编码**——若地图地点由人手写 JSON，正中扣分项。本方案的核验方式：

1. **代码检索**：`grep -rn "34\.\|113\.\|图书馆\|教学楼" sias_agent/*.py`
   → 除 prompt 中的"字段契约"与函数名外，**不存在任何具体地点名或具体坐标常量**。
2. **数据来源**：`memory/agent_memory.json` 中 `action=generate_landmarks` 的条目记录了模型原始输出与 token 统计，可逐条核对。
3. **可复现的随机性**：即使把 8 个地点全部删除，重跑一次流水线，模型会重新生成一套地点（数量与类别分布受 prompt 约束，具体内容由模型决定）。
4. **prompt 只给"约束"，不给"答案"**：prompt 仅规定"学院位于河南郑州新郑市""需覆盖教学/生活/运动等类别""输出 JSON 字段"，不提供任何地点清单。

> 说明：为保证地图落在真实校址，prompt 中给出了「学校位于河南省郑州市新郑市（约 34.39°N, 113.74°E）」这一**地理锚点**（属于任务背景，不是地点答案）；每个具体 POI 的命名、坐标、类别、描述均由模型生成。

---

## 7. 关键工程决策与取舍

| 决策 | 原因 | 代价 |
|---|---|---|
| 关闭 FlashAttention（`OLLAMA_FLASH_ATTENTION=0`） | 本机 driver/backend 组合下开启会触发 `GGML_ASSERT` 内存池断言 | 推理略慢，但稳定 |
| 提供 `num_gpu=0` 纯 CPU 兜底 | 8 GB 显存被其他进程占用时（实测占用约 2.3 GB），自动分层会 OOM | 纯 CPU 约 11.6 tok/s（可接受） |
| 渲染前 `client.unload()` | 释放模型占用的显存/内存，避免与 folium + 浏览器渲染争抢 | 无 |
| 底图改为**免密钥**三源 | CartoDB 底图需要 API key，缺失时 `TileLayer` 的 `attribution` 触发渲染报错 | 视觉风格略朴素 |
| 内存中的 `_validate()` 只做清洗不做改写 | 保证"数据由模型生成"的可信度，程序仅做去重/范围过滤 | 模型偶发低精度坐标会保留 |

---

## 8. 已知限制与下一步

1. **自评分数标尺不统一**：模型自评给出 365 分（其自有标尺），而程序阈值为 75。虽未影响流程（判定为达标），但可解释性不佳。**改进**：在自评 prompt 中显式约束 `score ∈ [0,100]` 并给出评分细则。
2. **坐标精度**：部分 POI 经纬度小数位较少（2–4 位），存在标记点视觉重叠。**改进**：prompt 中要求 ≥6 位小数，并在 `_validate()` 中做最小间距去重。
3. **未做多设备对比**：受限于单机环境，仅完成"纯 CPU vs GPU 自动分层"两路径对比，以及 **E4B 默认模型 vs E2B-Uncensored 变体的同机横向对照**（已完成，见《验证报告》§3.5）；手机端（AI Edge Gallery）与第二台设备未覆盖。**改进**：补做手机端与 ≥12 GB 显存设备对照。
4. **地图风格**：当前为功能型浅色风格，未做深色主题与自定义图标。**改进**：引入自定义 SVG 图标与主题切换。

---

## 9. 交付物清单

| 文件 | 说明 |
|---|---|
| `lenovo_C4D_方案设计.md` | 本文件 |
| `lenovo_C4D_agent-skill/` | Agent 技能源码（含 README、requirements、CLI 入口、记忆文件） |
| `lenovo_C4D_map.html` | 生成的交互式地图（8 标记点 / 6 类别） |
| `lenovo_C4D_map_result.json` | 本次运行的完整结果摘要（含设备、POI、自评、性能） |
| `lenovo_C4D_output_screenshots/` | 运行截图（模型+设备+速度 / 交互式地图） |
| `lenovo_C4D_验证报告.md` | 模型输出质量评估 + 设备性能数据 |
| `lenovo_C4D_教学说明.md` | 安装与复现步骤 |
| `lenovo_C4D_AI日志.md` | AI 使用全过程（必须项） |
| `lenovo_C4D_拿来说明.md` | 使用的库/工具与参考来源 |
