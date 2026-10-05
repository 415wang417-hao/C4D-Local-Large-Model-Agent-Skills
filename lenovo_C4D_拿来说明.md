# 郑州西亚斯学院（SIAS）本地 Agent 地图 —— 拿来说明

> 说明本方案使用了哪些第三方库/工具、参考了哪些资料，以及哪些部分是自行设计实现的。

---

## 1. 运行环境与基础工具

| 名称 | 版本 | 用途 |
|---|---|---|
| Python | 3.11.8 | 主语言 |
| Ollama | 0.35.1 | 本地大模型运行时（**唯一推理后端，无任何云 API**） |
| Gemma 4 E4B | `gemma4:e4b`（Q4_K_M，6.58 GB，digest `dc35e8d9c606`） | 地点数据生成 / 自评 / 导语生成 |
| Windows 11 | 10.0.26200 | 宿主系统 |
| PowerShell | 5.1 | 环境取证与截图 |

---

## 2. Python 第三方库

| 库 | 版本 | 用途 | 引入位置 |
|---|---|---|---|
| `requests` | 2.34.2 | 调用 Ollama REST API（`/api/chat`、`/api/tags`、`/api/ps`） | `sias_agent/llm_client.py` |
| `folium` | 0.20.0 | 生成 Leaflet 交互式地图（标记点、弹窗、图层控制、图例、全屏、鹰眼） | `sias_agent/map_builder.py` |
| `psutil` | 内置 | 采集内存/CPU 信息，用于环境取证 | `verify_env.py` |
| `Pillow` | 内置 | 屏幕截图取证（Windows 侧配合 `System.Drawing`） | 取证脚本 |
| `json` / `math` / `pathlib` / `time` | 标准库 | JSON 解析与容错、距离计算、路径、计时 | 全项目 |

**folium 的间接依赖**：`branca`（图例/颜色映射）、`jinja2`（模板）、`Leaflet.js`（前端地图内核，随 HTML 内联 CDN 引用）。

> 未使用任何付费/受限库；未使用 LangChain、LlamaIndex 等重型编排框架——编排逻辑（多步推理、自评修订、记忆）为**本项目自行实现**，以保持可读性与可控性。

---

## 3. 地图底图（免密钥）

为满足"零成本、可复现"要求，刻意**避开需要 API Key 的底图**（如 CartoDB 的多数样式）：

| 底图 | 来源 | 类型 |
|---|---|---|
| OpenStreetMap 标准图 | `tile.openstreetmap.org` | 街道/通用 |
| Esri World Imagery | `server.arcgisonline.com` | 卫星影像 |
| OpenTopoMap | `tile.opentopomap.org` | 地形 |

三者在 `map_builder.py` 中以 `folium.LayerControl` 提供切换。

---

## 4. 参考的资料与来源

| 来源 | 参考内容 |
|---|---|
| Ollama 官方 API 文档（`/api/chat`、`/api/tags`） | `messages`/`tools` 字段格式、`format="json"`、`options`（`temperature`/`num_ctx`/`num_gpu`）、`keep_alive`、返回体中的 `eval_count`/`eval_duration`（用于计算 tok/s） |
| Ollama 原生 Function Calling 机制 | 工具声明用 OpenAI 兼容的 `{type:"function", function:{name, description, parameters}}` 结构；模型返回 `message.tool_calls` |
| folium 官方文档 | `Map` / `Marker` / `Icon` / `Popup` / `LayerControl` / `MiniMap` / `Fullscreen` / `Scale` 的用法 |
| Leaflet.js 文档 | 交互行为（缩放、拖拽、弹窗）与控件 |
| Gemma 模型卡（Google） | 模型族（E2B/E4B/26B MoE/31B Dense）的规模与定位，用于选型论证 |
| 挑战资料包 `CHALLENGE.md` 与评分表 | 交付物清单（8 件）、评分维度、Level 1–4 分级标准、C4D 的"硬编码"负信号 |
| 长期踩坑经验（本机历史任务沉淀） | ① Windows 下受限会话调用外部工具易被 UAC 提权拦截 → 采用"非提权 + 轮询产物"的稳妥做法；② 逐字符替换易造成二次转义 → 本项目的文本清洗统一采用单遍处理 |

---

## 5. 自行设计实现的部分（非拿来）

| 模块 | 自研内容 |
|---|---|
| `llm_client.py` | Ollama 封装层：超时/重试、`num_gpu` 可控、`unload()` 显存释放、**从 `eval_count/eval_duration` 反算 tok/s 的统计器** |
| `tools.py` | 4 个 Agent 工具的 JSON Schema、**v2 版生成 prompt（含地理锚点与类别约束）**、自评 prompt、修订 prompt、导语 prompt |
| `agent.py` | 多步编排、字段校验/去重/坐标过滤、**自评-修订闭环**、设备信息采集、banner 打印 |
| `memory.py` | 逐步记忆落盘（含每步 token 与耗时），使"数据由模型生成"可被第三方核验 |
| `map_builder.py` | 分色标记策略、中文弹窗模板、图例与统计卡片、多底图免密钥方案 |
| `verify_env.py` | **四项硬证据（模型/工具/设备/速度）的一屏取证脚本**，为"本地运行验证"提供可重复的证据生成方式 |

---

## 6. 明确未使用的（合规声明）

- ❌ 未调用任何云大模型 API（OpenAI / Anthropic / 国内厂商等）；
- ❌ 未使用任何需要 API Key 的地图服务；
- ❌ 地图地点数据**未**由人工编写或从外部数据集拷贝——全部由本地 `gemma4:e4b` 生成，逐条记录在 `memory/agent_memory.json`；
- ❌ 未使用爬虫抓取含个人信息的页面数据。
