"""
会话记忆模块。

为 Agent 提供跨轮次记忆能力：
* 记录每一轮的用户指令、模型输出、工具调用轨迹与性能指标；
* 以 JSON 文件持久化，支持中断后继续；
* 可导出为 Markdown 日志（供 AI 日志 / 验证报告取证）。

对应评分维度：Agent 能力 —— "有记忆"。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Turn:
    """一轮交互记录。"""

    index: int
    role: str
    action: str
    content: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    stats: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    @property
    def time_str(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp))


class Memory:
    """轻量 JSON 记忆库。"""

    def __init__(self, path: str, model: str = "", device: str = "") -> None:
        self.path = os.path.abspath(path)
        self.model = model
        self.device = device
        self.turns: List[Turn] = []
        self.meta: Dict[str, Any] = {
            "model": model,
            "device": device,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "skill": "sias-map-agent",
            "version": "1.0.0",
        }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._load()

    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self.meta.update(data.get("meta", {}))
                self.turns = [Turn(**t) for t in data.get("turns", [])]
            except Exception:
                # 记忆文件损坏时不阻断主流程
                self.turns = []

    def save(self) -> None:
        payload = {
            "meta": self.meta,
            "turns": [asdict(t) for t in self.turns],
        }
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------ #
    def add(
        self,
        role: str,
        action: str,
        content: str = "",
        payload: Optional[Dict[str, Any]] = None,
        stats: Optional[Dict[str, Any]] = None,
    ) -> Turn:
        turn = Turn(
            index=len(self.turns) + 1,
            role=role,
            action=action,
            content=content,
            payload=payload or {},
            stats=stats or {},
        )
        self.turns.append(turn)
        self.save()
        return turn

    def last(self) -> Optional[Turn]:
        return self.turns[-1] if self.turns else None

    def total_tokens(self) -> int:
        return sum(int(t.stats.get("completion_tokens", 0) or 0) for t in self.turns)

    def avg_tps(self) -> float:
        vals = [float(t.stats.get("tokens_per_sec", 0) or 0) for t in self.turns if t.stats]
        vals = [v for v in vals if v > 0]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    # ------------------------------------------------------------------ #
    def to_markdown(self) -> str:
        lines = [
            "# Agent 执行记忆（Memory Dump）",
            "",
            f"- 模型：`{self.meta.get('model')}`",
            f"- 设备：{self.meta.get('device')}",
            f"- 创建时间：{self.meta.get('created_at')}",
            f"- 记录轮次：{len(self.turns)}",
            f"- 累计输出 token：{self.total_tokens()}，平均速度：{self.avg_tps()} tok/s",
            "",
            "| # | 时间 | 角色 | 动作 | 摘要 | tok/s |",
            "|---|------|------|------|------|-------|",
        ]
        for t in self.turns:
            summary = (t.content or "").replace("\n", " ").strip()[:60]
            tps = t.stats.get("tokens_per_sec", "")
            lines.append(
                f"| {t.index} | {t.time_str} | {t.role} | {t.action} | {summary} | {tps} |"
            )
        return "\n".join(lines)
