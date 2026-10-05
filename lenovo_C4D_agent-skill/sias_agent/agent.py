"""
Agent 编排层。

实现一条"多步推理 + 工具调用 + 自我反思"的完整链路：

    生成 POI ──► 数量/字段校验 ──► 模型自评 ──► (不达标) 迭代修订 ──► 生成导语 ──► 渲染地图

同时提供 :meth:`SiasMapAgent.function_calling_demo`，用于演示 Ollama 原生
function calling：由模型自行决定调用哪个工具、传什么参数。
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional

from . import tools as T
from .llm_client import OllamaClient
from .map_builder import build_map, map_statistics
from .memory import Memory

NVIDIA_SMI = shutil.which("nvidia-smi") or r"C:\Windows\System32\nvidia-smi.exe"


# --------------------------------------------------------------------------- #
# 设备信息采集（供截图 / 报告取证）
# --------------------------------------------------------------------------- #
def collect_device_info() -> Dict[str, str]:
    info: Dict[str, str] = {}
    info["os"] = f"{platform.system()} {platform.release()} ({platform.version()})"
    info["python"] = platform.python_version()
    info["cpu"] = os.environ.get("PROCESSOR_IDENTIFIER", platform.processor() or "Unknown")

    # 内存
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"],
            text=True, timeout=20,
        ).strip()
        info["ram_gb"] = f"{int(out)/1024**3:.1f} GB"
    except Exception:
        info["ram_gb"] = "Unknown"

    # GPU
    try:
        out = subprocess.check_output(
            [NVIDIA_SMI, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            text=True, timeout=20,
        ).strip().splitlines()[0]
        info["gpu"] = out
    except Exception:
        info["gpu"] = "Unknown"

    # Ollama 版本
    try:
        info["ollama"] = subprocess.check_output(["ollama", "--version"], text=True, timeout=20).strip()
    except Exception:
        info["ollama"] = "Unknown"
    return info


def print_banner(client: OllamaClient, device: Dict[str, str]) -> None:
    models = {m.get("name"): m for m in client.list_models()}
    m = models.get(client.model, {})
    print("=" * 72)
    print(" SIAS 校园地图 Agent —— 本地大模型驱动")
    print("=" * 72)
    print(f" 模型        : {client.model}")
    print(f" 模型体积    : {round(m.get('size', 0)/1e9, 2)} GB   digest={str(m.get('digest',''))[:12]}")
    print(f" 运行工具    : {device.get('ollama')}")
    print(f" 操作系统    : {device.get('os')}")
    print(f" CPU         : {device.get('cpu')}")
    print(f" 内存        : {device.get('ram_gb')}")
    print(f" GPU         : {device.get('gpu')}")
    print(f" Python      : {device.get('python')}")
    print(f" 推理后端    : Ollama @ {client.host} (FlashAttention=OFF)")
    print("=" * 72)


# --------------------------------------------------------------------------- #
class SiasMapAgent:
    """地图生成 Agent。"""

    def __init__(
        self,
        client: OllamaClient,
        memory_path: str = "agent_memory.json",
        log: Callable[[str], None] = print,
    ) -> None:
        self.client = client
        self.log = log
        self.device = collect_device_info()
        self.memory = Memory(
            memory_path,
            model=client.model,
            device=f"{self.device.get('cpu')} | {self.device.get('gpu')} | RAM {self.device.get('ram_gb')}",
        )

    # ------------------------------------------------------------------ #
    def _record(self, role: str, action: str, content: str, stats: Any = None,
                payload: Optional[Dict[str, Any]] = None) -> None:
        d = stats.as_dict() if hasattr(stats, "as_dict") else (stats or {})
        self.memory.add(role, action, content, payload=payload, stats=d)

    # ------------------------------------------------------------------ #
    def generate(self, place: str, count: int = 6) -> Dict[str, Any]:
        self.log(f"[1/5] 调用本地模型生成 {count} 个校园 POI ...")
        out = T.generate_landmarks(self.client, place=place, count=count)
        self._record(
            "model", "generate_landmarks",
            f"生成 {len(out['landmarks'])} 个地点",
            out["stats"], payload={"landmarks": out["landmarks"]},
        )
        self.log(f"      -> {len(out['landmarks'])} 个地点 | {out['stats'].tokens_per_sec:.2f} tok/s")
        return out

    def review(self, place: str, landmarks: List[Dict[str, Any]]) -> Dict[str, Any]:
        self.log("[2/5] 模型自我评审 (self-critique) ...")
        out = T.review_landmarks(self.client, place, landmarks)
        self._record("model", "review_landmarks", f"自评得分 {out.get('score')}",
                     out.get("stats"), payload={"issues": out.get("issues")})
        self.log(f"      -> 自评得分 {out.get('score')} | 问题 {len(out.get('issues', []))} 条")
        return out

    def refine(self, place: str, landmarks: List[Dict[str, Any]], suggestions: List[str]) -> List[Dict[str, Any]]:
        self.log("[3/5] 依据评审意见迭代修订 ...")
        out = T.refine_landmarks(self.client, place, landmarks, suggestions)
        self._record("model", "refine_landmarks", f"修订为 {len(out['landmarks'])} 个地点", out["stats"])
        self.log(f"      -> 修订后 {len(out['landmarks'])} 个地点 | {out['stats'].tokens_per_sec:.2f} tok/s")
        return out["landmarks"]

    def summarize(self, place: str, landmarks: List[Dict[str, Any]]) -> str:
        self.log("[4/5] 生成地图导语 ...")
        out = T.summarize_place(self.client, place, landmarks)
        self._record("model", "summarize_place", out["summary"][:80], out["stats"])
        return out["summary"]

    def render(self, landmarks, title, subtitle, output_path) -> str:
        self.log("[5/5] 渲染交互式地图 ...")
        path = build_map(landmarks, title=title, subtitle=subtitle, output_path=output_path)
        self._record("tool", "build_map", f"地图已生成：{path}")
        self.log(f"      -> {path}")
        return path

    # ------------------------------------------------------------------ #
    def run(
        self,
        place: str = "郑州西亚斯学院(SIAS)",
        count: int = 6,
        output_path: str = "lenovo_C4D_map.html",
        title: str = "郑州西亚斯学院 (SIAS) 交互式校园地图",
        quality_threshold: float = 75.0,
        max_refine: int = 1,
    ) -> Dict[str, Any]:
        t_start = time.time()
        print_banner(self.client, self.device)
        self._record("user", "command", f"为 {place} 生成交互式校园地图（>= {count} 个标记点）")

        # 1) 生成
        gen = self.generate(place, count)
        landmarks = self._validate(gen["landmarks"], place, count)

        # 2) 自评 + 3) 迭代
        review = self.review(place, landmarks)
        score = review.get("score")
        refine_rounds = 0
        while (
            isinstance(score, (int, float))
            and score < quality_threshold
            and refine_rounds < max_refine
        ):
            landmarks = self._validate(
                self.refine(place, landmarks, review.get("suggestions", [])), place, count
            )
            refine_rounds += 1
            review = self.review(place, landmarks)
            score = review.get("score")
        if refine_rounds == 0:
            self.log("[3/5] 自评已达标，跳过修订")

        # 4) 导语
        summary = self.summarize(place, landmarks)

        # 渲染前释放模型内存（8GB 显存机型上避免与 folium 渲染争抢内存）
        self.client.unload()
        self.log("      -> 已释放模型内存，准备渲染")

        # 5) 渲染
        stats = map_statistics(landmarks)
        subtitle = f"共 {stats['total']} 个标记点 · {stats['category_count']} 个类别 · by {self.client.model}"
        path = self.render(landmarks, title, subtitle, output_path)

        elapsed = time.time() - t_start
        result = {
            "place": place,
            "model": self.client.model,
            "device": self.device,
            "landmarks": landmarks,
            "summary": summary,
            "review": {k: v for k, v in review.items() if k != "stats"},
            "refine_rounds": refine_rounds,
            "map_path": path,
            "statistics": stats,
            "elapsed_s": round(elapsed, 1),
            "avg_tokens_per_sec": self.memory.avg_tps(),
            "total_output_tokens": self.memory.total_tokens(),
        }
        self._record("agent", "done",
                     f"完成：{stats['total']} 个标记点，耗时 {elapsed:.1f}s",
                     payload={"map_path": path, "avg_tps": self.memory.avg_tps()})

        print("-" * 72)
        print(f" 完成！{stats['total']} 个标记点 / {stats['category_count']} 个类别")
        print(f" 地图文件  : {path}")
        print(f" 总耗时    : {elapsed:.1f} s")
        print(f" 平均速度  : {self.memory.avg_tps()} tok/s（累计 {self.memory.total_tokens()} output tokens）")
        print("-" * 72)
        return result

    # ------------------------------------------------------------------ #
    @staticmethod
    def _validate(landmarks: List[Dict[str, Any]], place: str, count: int) -> List[Dict[str, Any]]:
        """字段校验 + 去重 + 坐标范围过滤（不修改模型生成的内容，只做清洗）。"""
        seen, clean = set(), []
        for lm in landmarks or []:
            name = str(lm.get("name", "")).strip()
            if not name or name in seen:
                continue
            try:
                lat, lng = float(lm["lat"]), float(lm["lng"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                continue
            seen.add(name)
            lm["lat"], lm["lng"] = lat, lng
            lm.setdefault("category", "其他")
            lm.setdefault("description", "")
            clean.append(lm)
        if len(clean) < 5:
            raise ValueError(f"有效地点不足 5 个（{len(clean)}），无法满足挑战要求")
        return clean[: max(count, 5)]

    # ------------------------------------------------------------------ #
    def function_calling_demo(self, place: str = "郑州西亚斯学院(SIAS)") -> Dict[str, Any]:
        """演示 Ollama 原生 function calling：模型自主决定调用工具与参数。"""
        messages = [
            {"role": "system", "content": "你可以调用工具来帮助用户生成校园交互式地图。"},
            {"role": "user", "content": f"请为「{place}」生成一份交互式校园地图，至少 6 个标记点。"},
        ]
        res = self.client.chat(messages, tools=T.TOOLS_SCHEMA, temperature=0.2)
        calls = [
            {"name": c.get("function", {}).get("name"),
             "arguments": c.get("function", {}).get("arguments")}
            for c in res.tool_calls
        ]
        self._record("model", "function_calling",
                     f"模型自主发起 {len(calls)} 次工具调用",
                     res.stats, payload={"tool_calls": calls})
        return {"tool_calls": calls, "content": res.content, "stats": res.stats.as_dict()}
