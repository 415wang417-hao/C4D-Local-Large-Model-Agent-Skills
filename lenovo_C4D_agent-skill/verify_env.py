"""
C4D 本地运行验证脚本（截图取证用）。

一屏输出评分要求的全部硬证据：
  1) 运行的 Gemma 4 模型名称及量化标签，如 gemma4:e4b（+ digest）
  2) 运行工具（Ollama 版本）
  3) 设备信息（CPU / GPU / 内存 / 操作系统）
  4) 模型实际推理速度（tok/s，由 Ollama 返回的 eval_count / eval_duration 计算）

用法：
    python verify_env.py

可用环境变量覆盖：
    SIAS_MODEL   模型标签，默认 gemma4:e4b
    SIAS_NUM_GPU 卸载到 GPU 的层数，0 = 纯 CPU（默认），不设 = 自动分层
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:  # 保证控制台窗口内中文正常显示
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sias_agent.agent import collect_device_info, print_banner  # noqa: E402
from sias_agent.llm_client import OllamaClient  # noqa: E402

MODEL = os.environ.get("SIAS_MODEL", "gemma4:e4b")
NUM_GPU_ENV = os.environ.get("SIAS_NUM_GPU", "0")
NUM_GPU = int(NUM_GPU_ENV) if NUM_GPU_ENV not in ("", "auto") else None


def main() -> None:
    client = OllamaClient(model=MODEL, num_ctx=2048, num_gpu=NUM_GPU)
    if not client.is_alive():
        print("[错误] 未检测到本地 Ollama 服务（http://127.0.0.1:11434），请先运行 `ollama serve`。")
        sys.exit(1)

    device = collect_device_info()
    print_banner(client, device)

    print("[推理速度实测] 请求本地模型输出结构化 JSON，按 eval_count/eval_duration 计算 tok/s ...")
    t0 = time.perf_counter()
    res = client.chat(
        [
            {"role": "system", "content": "你是校园地图数据助手，只输出 JSON，不要任何解释。"},
            {"role": "user", "content": (
                '为"郑州西亚斯学院(SIAS)"生成 3 个校园地标，'
                '每个对象字段为 name / lat / lng / category / description，'
                '输出形如 {"landmarks":[...]} 的 JSON。'
            )},
        ],
        json_schema="json",
        temperature=0.3,
    )
    wall = time.perf_counter() - t0
    s = res.stats.as_dict()
    print(f"  实测：输出 {s['completion_tokens']} tokens / {s['wall_time_s']}s（含加载 {s['load_duration_s']}s）")
    print(f"  推理速度：{s['tokens_per_sec']} tok/s")
    print("  样例输出（本地模型生成，已截断）：")
    print("  " + " ".join(res.content.strip().split())[:180])
    print("-" * 72)
    print(f" 证据汇总 | 模型={MODEL} (digest={client.model_digest()[:12]})")
    print(f"          | 工具={device.get('ollama')}")
    print(f"          | 设备={device.get('cpu')} / {device.get('gpu')} / RAM {device.get('ram_gb')} / {device.get('os')}")
    print(f"          | 速度={s['tokens_per_sec']} tok/s（num_gpu={NUM_GPU_ENV}）")
    print("-" * 72)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify_result.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(
            {"model": MODEL, "num_gpu": NUM_GPU_ENV, "device": device,
             "stats": s, "sample_output": res.content,
             "measured_at": time.strftime("%Y-%m-%d %H:%M:%S")},
            f, ensure_ascii=False, indent=2,
        )
    print(f" 结果已写入：{out}")


if __name__ == "__main__":
    main()
