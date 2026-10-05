# lenovo C4D · Agent 技能包清单（`lenovo_C4D_agent-skill/`）

> **本文件定位**：Agent 技能包的**索引与职责说明**。评审若想快速知道每个文件干什么、对应 CHALLENGE 的哪一级任务、怎么一键复现，看这一页即可。
> 详细安装步骤见《lenovo_C4D_教学说明.md》；架构设计见《lenovo_C4D_方案设计.md》；实测数据见《lenovo_C4D_验证报告.md》。

---

## 1. 技能包定位

- **名称**：`sias-agent`（SIAS 本地 Agent 技能）
- **驱动模型**：`gemma4:e4b`（Gemma 4 E4B，4.5B effective，Q4_K_M，6.58 GB，digest `dc35e8d9c606`），本地 Ollama `0.35.1`
- **能力声明**：**Level 3 — 完整 Agent 技能包**（并额外完成 Level 4 的 Uncensored 变体对照加分项）
- **设计原则**：**零硬编码地点数据**——地图上的 8 个标记点、名称、描述、坐标、类别，全部由本地模型通过 function calling 生成，代码中不含任何预设 POI。

---

## 2. 目录结构与文件职责

```
lenovo_C4D_agent-skill/
├── README.md                     技能包说明（安装 / 使用 / 目录结构）
├── requirements.txt              依赖清单（requests / folium 等）
├── run_map_agent.py              ★ 主入口：一条命令跑完整 Agent 流水线
├── verify_env.py                 环境取证：打印模型/工具/设备/速度四项硬证据
├── verify_env.bat                一键取证（自带窗口定位 + DPI 感知），对应 screenshot_01
├── demo_function_calling.bat     ★ 一键演示函数调用 + 环境证据同屏，对应 screenshot_03
├── uncensored_compare.py         Level 4 加分项：默认模型 vs Uncensored 变体同任务对照
├── uncensored_compare_result.json  上述对照实验的结构化结果
├── verify_result.json            环境取证结果（结构化）
├── agent_memory.json             技能包级运行记录
├── memory/
│   └── agent_memory.json         ★ 记忆文件：记录本轮生成的全部 POI 与模型自评
└── sias_agent/                   ★ 核心包
    ├── __init__.py
    ├── llm_client.py             Ollama 客户端（纯 CPU/GPU 分层、超时与重试、tok/s 采集）
    ├── tools.py                  ★ 工具定义：generate_landmarks 等的 JSON Schema（约束用协议不用形容词）
    ├── agent.py                  主编排：多步推理 → 工具调用 → 校验 → 自评 → 修订
    ├── memory.py                 记忆读写（跨轮保留地点与自评结论）
    └── map_builder.py            Folium 渲染：分色图例、自定义弹窗、统计卡片、免密钥底图降级链
```

> `sias_agent/__pycache__/` 为 Python 运行时字节码缓存，**可安全删除**，不参与交付内容。

---

## 3. 与 CHALLENGE 四级任务的对照

| 级别 | CHALLENGE 要求 | 本技能包的落地 | 证据位置 |
|---|---|---|---|
| **Level 1** 本地跑通 | 本地运行 Gemma 4 + 截图（含模型名、设备信息） | Ollama 0.35.1 + `gemma4:e4b`；`verify_env.bat` 一屏打印模型名/版本/digest、工具、CPU/GPU/RAM/OS、tok/s | `screenshot_01_model_device_speed.png` |
| **Level 2** 函数调用 + 地图 | 模型生成结构化地点数据；交互式地图；≥5 标记点；含名称/描述/坐标 | `generate_landmarks` 走 tools 协议生成 **8 个点 / 6 个类别**；Folium 交互地图（可缩放、可点标记、分色图例） | `lenovo_C4D_map.html`、`screenshot_02_interactive_map.png`、`memory/agent_memory.json` |
| **Level 3** 完整技能包 | 可复用技能包 + 更深的 Agent 能力 | 可独立运行的包结构；**多工具调用**（生成 / 校验 / 自评 / 修订）、**多轮自评闭环**、**记忆持久化**、**结构化 JSON 输出** | 本清单 + `sias_agent/` 源码 + 《教学说明》 |
| **Level 4** 极限优化（加分项） | 至少两项：模型对比 / 设备适配 / **Uncensored（加分）** / 量化对比 / 性能调优 | ① **Uncensored 变体同任务对照**（`uncensored_compare.py`）② **性能调优文档**（context、GPU offload 取舍，见《验证报告》§3） | `uncensored_compare_result.json`、《验证报告》§3 |

---

## 4. 一键复现入口

```powershell
cd lenovo_C4D_agent-skill

# ① 环境取证（截图 01）：一屏打印四项硬证据
verify_env.bat

# ② 函数调用演示（截图 03）：演示在前 + 环境证据在后，同一窗口可直接截屏
demo_function_calling.bat

# ③ 完整流水线：生成地图（需 Ollama 已启动、gemma4:e4b 已拉取）
python run_map_agent.py --place "郑州西亚斯学院(SIAS)" --count 8 --out ..\lenovo_C4D_map.html

# ④ Level 4 对照实验（可选）
python uncensored_compare.py
```

前置条件：Python 3.11+、`pip install -r requirements.txt`、Ollama 已运行且已 `ollama pull gemma4:e4b`。

---

## 5. "零硬编码"如何自证

### 5.1 数据链路（最直接）

```
llm_client.chat(tools=[generate_landmarks])   ← 本地 Ollama，JSON Schema 约束
      ↓  模型返回
parse_json_loose()                            ← 解析模型输出
      ↓
memory（持久化）→ map_builder（Folium 渲染）
```

整条链路上**不存在 `landmarks = [ {...} ]` 形式的常量列表**；`sias_agent/tools.py` 文件头即声明"本文件不包含任何地点名称 / 描述 / 坐标常量，所有标记点数据均由本地 Gemma 4 模型在运行时生成"。

### 5.2 精确核验命令（用真实产出反查源码）

用运行产物中真实产出的 8 个地标名，反查代码里有没有同名常量：

```powershell
cd lenovo_C4D_agent-skill
$names = @("中央图书馆","国际交流中心","主教学楼","体育综合馆","学生生活服务中心","行政管理大楼","中央广场","绿荫大道","国际化学院楼")
Get-ChildItem .\*.py,.\sias_agent\*.py | Select-String -Pattern $names -SimpleMatch -Encoding UTF8
```

**预期结果：仅 2 处命中，且都在注释里**（`sias_agent/tools.py` 第 174–175 行）：

```python
# 注：以下提示词经 v1 -> v2 两轮迭代优化（见 AI 日志"prompt 优化"一节）：
#     v1 仅给地理范围，产出偏通用（主教学楼/食堂…）；
#     v2 补充"学校客观特色"以提升地标辨识度，产出更贴合校情（国际交流中心/海外学生公寓区…）。
```

这两处是**事后补写的 prompt 迭代说明**（恰好引用了真实产出举例），不参与运行、不构成数据源。**可执行代码中不存在任何地标名**——把这两行注释删掉重跑，地图产出完全不受影响。

### 5.3 另一处需说明的文本（非地点数据）

`tools.py` 第 179 行的 prompt 背景段含"图书馆、体育馆、学生生活区"等**通名**：

```python
f"背景：该校位于河南省郑州市新郑市，是一所中西合璧、国际化特色鲜明的普通本科高校，"
"校园建筑融合欧式与现代风格，设有多个学院、图书馆、体育馆、学生生活区与国际交流设施。\n"
```

这是 v2 prompt 的**上下文描述**（提升模型对校情的理解），描述的是"学校有哪些**类型**的设施"，**不是具体地标名、也不是坐标数据**；它不含任何 `lat`/`lng`。

### 5.4 数据只在运行时产生（产物位置）

| 产物 | 内容 |
|---|---|
| `memory/agent_memory.json` | 模型输出原文 + 自评结论（可追溯生成过程） |
| `lenovo_C4D_map.html` | 8 个 `L.marker(`，与 `statistics.total = 8` 一致 |
| `lenovo_C4D_map_result.json` | 结构化结果，字段 `name / category / lat / lng / description`，含 `model`、`device`、`avg_tokens_per_sec`、`elapsed_s` |

