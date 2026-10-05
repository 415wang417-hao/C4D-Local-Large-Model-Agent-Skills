# 郑州西亚斯学院（SIAS）本地 Agent 地图 —— 教学说明

> 目标：让任何一位同学在自己的电脑上，从零复现"本地 Gemma 4 驱动 Agent 生成交互式地图"的全过程。
> 全程不需要任何云 API、不需要 API Key、不花一分钱。

---

## 1. 前置条件

| 项目 | 要求 | 检查命令 |
|---|---|---|
| 操作系统 | Windows 10/11（macOS / Linux 同样支持，路径改写即可） | `winver` |
| Python | ≥ 3.9（本项目在 3.11.8 上验证） | `python --version` |
| Ollama | ≥ 0.3（本项目在 0.35.1 上验证） | `ollama --version` |
| 磁盘空间 | ≥ 10 GB（模型 6.58 GB + 依赖） | — |
| 内存 | ≥ 16 GB（纯 CPU 路径建议 ≥ 16 GB） | — |
| 显卡 | 非必需（有 8 GB 显存更好，无独显也能跑） | — |

---

## 2. 安装步骤

### 第 1 步：安装 Ollama
1. 访问 `https://ollama.com/download` 下载 Windows 安装包并安装；
2. 安装后确认服务在运行：
   ```powershell
   ollama --version
   # 期望输出：ollama version is 0.35.1
   ```

### 第 2 步：拉取 Gemma 4 模型
```powershell
ollama pull gemma4:e4b
ollama list
# 期望看到：gemma4:e4b   ...   6.6 GB
```
> 若磁盘/内存紧张，可改用更小的 `gemma4:e2b`；本项目的 CLI 支持 `--model` 参数切换。

### 第 3 步：安装 Python 依赖
```powershell
cd lenovo_C4D_agent-skill
python -m pip install -r requirements.txt
```
`requirements.txt` 内容：
```
requests>=2.31
folium>=0.17
Pillow>=10.0
psutil>=5.9
```

### 第 4 步（可选，推荐）：关闭 FlashAttention
Windows + NVIDIA 驱动组合下开启 FlashAttention 可能触发 `GGML_ASSERT` 断言，建议为当前用户设置：
```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_FLASH_ATTENTION","0","User")
```
设置后重启 Ollama 服务（托盘图标 → Quit，再重新启动）。

---

## 3. 目录结构

```
lenovo_C4D_agent-skill/
├── run_map_agent.py          # 命令行入口
├── verify_env.py             # 环境取证脚本（截图/报告用）
├── verify_env.bat            # 上述脚本的可视化窗口包装
├── demo_function_calling.bat # 函数调用演示 + 环境证据（一键截图取证）
├── uncensored_compare.py     # 可选实验：默认模型 vs uncensored 变体对照
├── verify_result.json        # 环境取证结果（运行后生成）
├── requirements.txt          # Python 依赖
├── README.md                 # 技能说明
├── memory/
│   └── agent_memory.json     # 记忆文件（每次运行后更新）
└── sias_agent/
    ├── __init__.py
    ├── llm_client.py         # Ollama HTTP 封装（含 tok/s 统计、unload）
    ├── tools.py              # 4 个 Agent 工具 + JSON Schema + prompt 模板
    ├── agent.py              # 编排层（多步推理 + 自评修订 + 渲染调度）
    ├── memory.py             # 记忆持久化
    └── map_builder.py        # folium 地图渲染
```

---

## 4. 快速开始（3 条必做命令 + 1 条可选）

```powershell
cd lenovo_C4D_agent-skill

# ① 环境取证：打印并保存 模型/工具/设备/速度 四项证据
python verify_env.py

# ② 看 Agent 的"函数调用"能力：模型自主选择并调用工具
python run_map_agent.py --demo-function-calling

# ②'（Windows 一键截图取证）双击运行 demo_function_calling.bat：
#     同一窗口内先跑函数调用演示（含 tok/s），再打印环境证据
#     （Ollama 版本 / 模型与 digest / CPU·GPU·RAM·OS / 卸载策略），
#     一张截图即可覆盖"模型名+版本、工具、设备、tok/s"四项要求
demo_function_calling.bat

# ③ 跑完整流水线：生成 POI → 自评 → 导语 → 渲染地图
python run_map_agent.py --place "郑州西亚斯学院(SIAS)" --count 8 `
    --out ..\lenovo_C4D_map.html --memory .\memory\agent_memory.json

# ④（可选，Level 4 加分项）默认模型 vs uncensored 变体同任务对照
python uncensored_compare.py
```

④ 为可选实验，详见第 8 节；不跑它不影响 ①–③ 的任何结果。

③ 完成后：
- 地图：`..\lenovo_C4D_map.html`（双击用浏览器打开）
- 结果摘要：`..\lenovo_C4D_map_result.json`
- 执行日志：`.\memory\agent_memory.json`

> 首次运行需要加载 6.58 GB 模型，约 17 s；整条流水线在 8 核以上 CPU 上约 **4–7 分钟**（本项目实测 365 s）。

---

## 5. 参数说明

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--model` | `gemma4:e4b` | Ollama 模型标签，可换 `gemma4:e2b` 等 |
| `--host` | `http://127.0.0.1:11434` | 本地 Ollama 地址 |
| `--place` | `郑州西亚斯学院(SIAS)` | 目标地点 |
| `--count` | `8` | 标记点数量（自动保证 ≥5） |
| `--out` | `lenovo_C4D_map.html` | 地图输出路径 |
| `--memory` | `agent_memory.json` | 记忆文件路径 |
| `--num-ctx` | `8192` | 上下文长度（**显存小建议 2048**） |
| `--demo-function-calling` | 关闭 | 仅演示函数调用 |

---

## 6. 常见问题（FAQ）

**Q1：报错 `无法连接本地 Ollama 服务`**
Ollama 服务未启动。打开开始菜单运行 `Ollama`，或执行 `ollama serve` 后重试。

**Q2：报错 `GGML_ASSERT ... failed to allocate` / 进程崩溃**
显存不足。解决方法二选一：
- 在 `sias_agent/llm_client.py` 调用处传 `num_gpu=0` 强制纯 CPU；
- 或把 `--num-ctx` 降到 `2048`，关闭浏览器等占显存程序。

**Q3：地图打开是空白 / 底图不显示**
本项目默认使用**免密钥**底图（OpenStreetMap / Esri 卫星 / OpenTopoMap）。若三个底图全部空白，通常是网络问题——请在能联网的环境打开，或把 `map_builder.py` 中的底图换成组织内网瓦片地址。

**Q4：终端中文乱码**
Windows 控制台执行 `chcp 65001` 切到 UTF-8；`verify_env.bat` 已内置该命令。

**Q5：速度很慢（< 5 tok/s）**
- 确认模型已预热（`keep_alive=30m`）；
- 关闭其他占用 CPU/显存的程序；
- 减少 `--count`（输出 token 数与 POI 数量近似线性）；
- 有独显时确认 Ollama 已启用 GPU（`ollama ps` 查看）。

**Q6：想换一所学校**
直接改 `--place`，例如 `--place "郑州大学"`。注意：prompt 中的**地理锚点**（经纬度）写在 `sias_agent/tools.py`，换校时需一并修改该锚点，否则坐标仍会落在西亚斯附近。

---

## 7. 复现自检清单

运行完第 4 节的三条命令后，逐项打勾：

- [ ] `python verify_env.py` 输出了模型名、Ollama 版本、CPU/GPU、内存、OS、tok/s
- [ ] `verify_result.json` 已生成且内容非空
- [ ] `--demo-function-calling` 输出了模型自主调用的工具名与参数
- [ ] `lenovo_C4D_map.html` 存在、体积约 25 KB
- [ ] 浏览器打开地图：可见 ≥5 个标记点、可缩放、点击弹窗、有图例
- [ ] `memory/agent_memory.json` 中有 `turns` 记录（含每步 token 与 tok/s）
- [ ] `lenovo_C4D_map_result.json` 中 `landmarks` 数量与 `--count` 一致

全部勾选即复现成功。

---

## 8. 可选实验（Level 4 加分项）：默认模型 vs Uncensored 变体

### 8.1 目的

在**同一台设备、同一条纯 CPU 推理路径**上，把默认模型与一个 uncensored 社区变体放在**同一任务**下横向对比，回答两个问题：小模型的审查倾向会不会影响任务完成？更小的模型是不是一定更快？

### 8.2 准备工作

```powershell
ollama pull gemma4:e4b                          # 默认模型（6.58 GB）
ollama pull Librellama/gemma4:e2b-Uncensored    # 变体（3.4 GB）
python uncensored_compare.py                    # 运行对照
```

脚本对两个模型各发**同一个 prompt**（生成 5 个校园 POI）、固定 `seed=42`，跑完一个立刻 `unload()` 再跑下一个，避免显存/内存相互干扰；结果写入 `uncensored_compare_result.json`。

### 8.3 本次实测结果（可直接对照）

| 项 | `gemma4:e4b`（默认） | `e2b-Uncensored` |
|---|---|---|
| 体积 | 6.58 GB | 3.4 GB |
| 解码速度 | 17.37 tok/s | 15.59 tok/s |
| 输出 tokens / 耗时 | 1429 / 84.3 s | 868 / 62.5 s |
| JSON 合规 / 地点数 | ✅ / 5 | ✅ / 5 |
| 类别语言 | 英文（Teaching/Sports…） | 中文（教学/运动…） |
| 拒答 | 否 | 否 |

### 8.4 教学要点

1. **本任务属中性内容，两个模型都没有拒答**——"uncensored"的差别体现在**语言遵守度**上：默认模型把 `category` 写成英文，变体严格跟随中文 prompt。
2. **"参数小⇒速度快"不成立**：E2B 体积小约 48%，解码速度反而略低（15.59 vs 17.37 tok/s），本机 CPU 路径受内存带宽与算子实现影响更大。
3. **最值得讲的一条**：两个模型在**只要求 `format=json`、不给字段 Schema** 时，都把 `lat`/`lng` 合并成了一个字符串 `"lat/lng": "34.3920, 113.7415"`；而主流程走 **function calling（tools + JSON Schema）** 时，同一个模型输出的是两个独立数值字段。→ **教学生写 Agent 时，别指望用自然语言把字段"叮嘱"出来，直接给 Schema。**
4. **诚实标注局限**：两个模型参数量本就不同，因此这不是严格的"审查维度"对照，速度差异也不能归因于审查开关。做对照实验时，**说明不了的事就不要写进结论**。

### 8.5 扩展建议

- 扩到手机端（Gemma 4 的 AI Edge Gallery）与 ≥12 GB 显存设备，形成多设备矩阵；
- 增加 `temperature=0` / 多轮取均值的统计口径（当前为单次采样）；
- 把对照脚本改造成通用 `--models a,b,c --task xxx` 形式，便于换任务复用。
