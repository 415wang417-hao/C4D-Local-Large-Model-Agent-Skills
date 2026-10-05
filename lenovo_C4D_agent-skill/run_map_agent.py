#!/usr/bin/env python
"""
SIAS 校园地图 Agent —— 命令行入口。

用法示例
--------
    python run_map_agent.py --place "郑州西亚斯学院(SIAS)" --count 8 \
        --out ../lenovo_C4D_map.html --memory ./agent_memory.json

    # 仅演示 function calling
    python run_map_agent.py --demo-function-calling
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sias_agent.agent import SiasMapAgent
from sias_agent.llm_client import OllamaClient


def main() -> int:
    ap = argparse.ArgumentParser(description="本地 Gemma 4 驱动的 SIAS 校园交互式地图 Agent")
    ap.add_argument("--model", default="gemma4:e4b", help="Ollama 模型标签")
    ap.add_argument("--host", default="http://127.0.0.1:11434", help="本地 Ollama 服务地址")
    ap.add_argument("--place", default="郑州西亚斯学院(SIAS)", help="目标校园")
    ap.add_argument("--count", type=int, default=8, help="标记点数量（>=5）")
    ap.add_argument("--out", default="lenovo_C4D_map.html", help="地图输出路径")
    ap.add_argument("--memory", default="agent_memory.json", help="记忆文件路径")
    ap.add_argument("--num-ctx", type=int, default=8192, help="上下文长度")
    ap.add_argument("--demo-function-calling", action="store_true", help="仅运行 function calling 演示")
    args = ap.parse_args()

    client = OllamaClient(model=args.model, host=args.host, num_ctx=args.num_ctx)
    if not client.is_alive():
        print(f"[错误] 无法连接本地 Ollama 服务：{args.host}")
        print("       请先启动 Ollama，并确认已 `ollama pull " + args.model + "`")
        return 2

    agent = SiasMapAgent(client, memory_path=args.memory)

    if args.demo_function_calling:
        out = agent.function_calling_demo(args.place)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    result = agent.run(place=args.place, count=args.count, output_path=args.out)

    # 汇总文件（供报告引用）
    summary_path = os.path.splitext(args.out)[0] + "_result.json"
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(f" 结果摘要已写入: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
