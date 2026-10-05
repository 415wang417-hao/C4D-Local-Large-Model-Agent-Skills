"""
本地 Gemma 4 推理客户端。

设计约束（C4D 挑战硬性要求）：
    * 只与 **本机 Ollama 服务** (http://127.0.0.1:11434) 通信；
    * 不依赖、不调用任何云端 API（无 API Key、无联网推理）；
    * 同时支持 Ollama 原生 `tools`（function calling）与 `format`（结构化 JSON 输出）。

依赖：requests
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

DEFAULT_HOST = "http://127.0.0.1:11434"


@dataclass
class LLMStats:
    """一次推理的性能画像，用于生成验证报告中的 tok/s 数据。"""

    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    wall_time_s: float = 0.0
    load_duration_s: float = 0.0
    tokens_per_sec: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "wall_time_s": round(self.wall_time_s, 3),
            "load_duration_s": round(self.load_duration_s, 3),
            "tokens_per_sec": round(self.tokens_per_sec, 2),
        }


@dataclass
class LLMResult:
    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    stats: LLMStats = field(default_factory=LLMStats)
    raw: Dict[str, Any] = field(default_factory=dict)


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    """极简 Ollama 客户端。

    Parameters
    ----------
    model : 模型标签，例如 ``gemma4:e4b``（必须已通过 ``ollama pull`` 下载到本机）。
    host  : Ollama 服务地址，默认本机回环地址。
    num_ctx : 上下文窗口。E4B 原生支持 128K，本地按需调小可省显存。
    """

    def __init__(
        self,
        model: str = "gemma4:e4b",
        host: str = DEFAULT_HOST,
        timeout: int = 600,
        num_ctx: int = 8192,
        temperature: float = 0.6,
        keep_alive: str = "30m",
        num_gpu: Optional[int] = None,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.num_ctx = num_ctx
        self.temperature = temperature
        self.keep_alive = keep_alive
        # num_gpu=0 表示纯 CPU 推理；None 表示交由 Ollama 自动分层卸载。
        # 在 8GB 显存机型上，显存被其它程序占用时纯 CPU 路径更稳定。
        self.num_gpu = num_gpu

    # ------------------------------------------------------------------ #
    # 基础能力
    # ------------------------------------------------------------------ #
    def is_alive(self) -> bool:
        try:
            return requests.get(f"{self.host}/api/tags", timeout=5).status_code == 200
        except requests.RequestException:
            return False

    def list_models(self) -> List[Dict[str, Any]]:
        r = requests.get(f"{self.host}/api/tags", timeout=10)
        r.raise_for_status()
        return r.json().get("models", [])

    def model_digest(self) -> str:
        for m in self.list_models():
            if m.get("name") == self.model or m.get("model") == self.model:
                return m.get("digest", "")
        return ""

    # ------------------------------------------------------------------ #
    # 推理
    # ------------------------------------------------------------------ #
    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        json_schema: Optional[Any] = None,
        temperature: Optional[float] = None,
        num_ctx: Optional[int] = None,
        keep_alive: Optional[str] = None,
    ) -> LLMResult:
        """调用 /api/chat。

        tools       : Ollama 原生 function calling 的 schema 列表。
        json_schema : 传入则启用结构化输出（Ollama `format` 字段，可传 JSON Schema 或 "json"）。
        """
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature if temperature is None else temperature,
                "num_ctx": self.num_ctx if num_ctx is None else num_ctx,
                **({"num_gpu": self.num_gpu} if self.num_gpu is not None else {}),
            },
            "keep_alive": keep_alive or self.keep_alive,
        }
        if tools:
            payload["tools"] = tools
        if json_schema is not None:
            payload["format"] = json_schema

        t0 = time.perf_counter()
        try:
            resp = requests.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout)
        except requests.RequestException as exc:  # pragma: no cover - 网络异常
            raise OllamaError(f"无法连接本地 Ollama 服务：{exc}") from exc
        wall = time.perf_counter() - t0
        if resp.status_code >= 400:
            raise OllamaError(f"Ollama 返回 {resp.status_code}: {resp.text[:400]}")
        data = resp.json()

        msg = data.get("message") or {}
        eval_count = data.get("eval_count") or 0
        eval_duration = data.get("eval_duration") or 0
        load_duration = data.get("load_duration") or 0
        tps = (eval_count / (eval_duration / 1e9)) if eval_duration else 0.0

        stats = LLMStats(
            model=data.get("model", self.model),
            prompt_tokens=data.get("prompt_eval_count") or 0,
            completion_tokens=eval_count,
            wall_time_s=wall,
            load_duration_s=load_duration / 1e9,
            tokens_per_sec=tps,
        )
        return LLMResult(
            content=msg.get("content", "") or "",
            tool_calls=msg.get("tool_calls", []) or [],
            stats=stats,
            raw=data,
        )

    # ------------------------------------------------------------------ #
    def unload(self) -> bool:
        """卸载当前模型（keep_alive=0），立即释放显存 / 内存。

        在 8 GB 显存的移动端 GPU 上，模型常驻会与后续渲染（folium / 浏览器）
        争抢内存，因此在渲染阶段前主动卸载。
        """
        try:
            r = requests.post(
                f"{self.host}/api/generate",
                json={"model": self.model, "keep_alive": 0},
                timeout=30,
            )
            return r.status_code < 400
        except requests.RequestException:
            return False
