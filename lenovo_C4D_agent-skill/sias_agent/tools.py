"""
Agent 工具集（Function Calling Tools）。

设计原则
--------
1. **零硬编码地点数据**：本文件不包含任何地点名称 / 描述 / 坐标常量。
   所有标记点数据均由本地 Gemma 4 模型在运行时生成，正负样本均由模型产出。
2. 每个工具同时具备两种身份：
   * LLM 可调用的 function（附带 JSON Schema 声明，供 Ollama `tools` 使用）；
   * 普通 Python 函数（可直接被代码调用，便于测试与评测复现）。

工具清单
--------
- ``generate_landmarks`` : 让本地模型生成 N 个校园标记点（结构化 JSON 输出）
- ``review_landmarks``   : 让本地模型对自己生成的数据做质量自评（多步推理 / 自我反思）
- ``refine_landmarks``   : 依据自评意见对数据进行修订（迭代优化）
- ``summarize_place``    : 让本地模型输出一段校园简介
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------- #
# 结构化输出 Schema（Ollama `format` 字段）—— 仅描述"形状"，不含任何地点数据
# --------------------------------------------------------------------------- #
LANDMARKS_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "landmarks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": ["教学", "生活", "运动", "文化", "行政", "景观"],
                    },
                    "lat": {"type": "number"},
                    "lng": {"type": "number"},
                    "description": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "category", "lat", "lng", "description"],
            },
        }
    },
    "required": ["landmarks"],
}

REVIEW_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "score": {"type": "number"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "suggestions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["score", "issues", "suggestions"],
}


# --------------------------------------------------------------------------- #
# 供 Ollama `tools` 使用的 function 声明
# --------------------------------------------------------------------------- #
TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "generate_landmarks",
            "description": "调用本地大模型，生成指定校园的若干兴趣点(POI)数据，包含名称、类别、经纬度与简介。",
            "parameters": {
                "type": "object",
                "properties": {
                    "place": {"type": "string", "description": "校园/地点全称"},
                    "count": {"type": "integer", "description": "需要生成的标记点数量，至少 5 个"},
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "期望覆盖的类别列表",
                    },
                },
                "required": ["place", "count"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "review_landmarks",
            "description": "让本地大模型对自己生成的地点数据做质量自评，返回评分与改进建议。",
            "parameters": {
                "type": "object",
                "properties": {
                    "place": {"type": "string"},
                    "landmarks_json": {"type": "string", "description": "待评估的地点数据(JSON 字符串)"},
                },
                "required": ["place", "landmarks_json"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_map",
            "description": "把地点数据渲染为可缩放、可点击的交互式 HTML 地图并保存到磁盘。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "output_path": {"type": "string", "description": "输出 HTML 的绝对路径"},
                },
                "required": ["title", "output_path"],
            },
        },
    },
]


# --------------------------------------------------------------------------- #
# JSON 容错解析：小模型偶尔会包裹 ```json 代码块或加前后缀说明
# --------------------------------------------------------------------------- #
def parse_json_loose(text: str) -> Any:
    """从模型输出中稳健地抽取 JSON。

    1) 直接 json.loads；
    2) 去掉 ```json ... ``` 围栏后重试；
    3) 截取首个 '{' 到末个 '}' 的子串重试。
    """
    if text is None:
        raise ValueError("空输出")
    t = text.strip()
    for candidate in (t,):
        try:
            return json.loads(candidate)
        except Exception:
            pass
    fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.MULTILINE).strip()
    try:
        return json.loads(fenced)
    except Exception:
        pass
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end > start:
        return json.loads(t[start : end + 1])
    raise ValueError(f"无法解析为 JSON：{t[:200]}")


# --------------------------------------------------------------------------- #
# 工具实现
# --------------------------------------------------------------------------- #
def generate_landmarks(
    client,
    place: str = "郑州西亚斯学院(SIAS)",
    count: int = 6,
    categories: Optional[List[str]] = None,
    region_hint: str = "校区位于河南省郑州市新郑市，中心经纬度约 34.395, 113.745",
) -> Dict[str, Any]:
    """调用本地模型生成地点数据（结构化 JSON 输出）。

    Returns
    -------
    dict: ``{"landmarks": [...], "stats": {...}, "raw": "..."}``
    """
    cats = categories or ["教学", "生活", "运动", "文化", "行政", "景观"]
    system = (
        "你是一名熟悉中国高校校园地理的助手。"
        "请严格依据现实世界中该高校的真实院系、建筑与生活设施来输出地点，"
        "不要编造不存在的建筑；名称使用中文。"
    )
    # 注：以下提示词经 v1 -> v2 两轮迭代优化（见 AI 日志"prompt 优化"一节）：
    #     v1 仅给地理范围，产出偏通用（主教学楼/食堂…）；
    #     v2 补充"学校客观特色"以提升地标辨识度，产出更贴合校情（国际交流中心/海外学生公寓区…）。
    user = (
        f"请为「{place}」生成 {count} 个最具辨识度的校园地标/设施(POI)。\n"
        f"背景：该校位于河南省郑州市新郑市，是一所中西合璧、国际化特色鲜明的普通本科高校，"
        "校园建筑融合欧式与现代风格，设有多个学院、图书馆、体育馆、学生生活区与国际交流设施。\n"
        f"地理参考：{region_hint}，请在各点 ±0.02 经纬度范围内合理分布，不要超出校园范围。\n"
        f"类别请从 {cats} 中选择，且尽量覆盖多个类别。\n"
        f"description 用 20-40 字说明该地点的功能或特色。\n"
        "只输出 JSON，不要任何额外解释。"
    )
    res = client.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        json_schema=LANDMARKS_JSON_SCHEMA,
        temperature=0.7,
    )
    data = parse_json_loose(res.content)
    landmarks = data.get("landmarks", []) if isinstance(data, dict) else []
    return {"landmarks": landmarks, "stats": res.stats, "raw": res.content}


def review_landmarks(client, place: str, landmarks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """让本地模型对自己的输出做质量自评（自我反思环节）。"""
    system = "你是一名严格的地图数据审校员，擅长发现 POI 数据中的问题。"
    user = (
        f"以下是关于「{place}」的校园 POI 数据(JSON)：\n"
        f"{json.dumps({'landmarks': landmarks}, ensure_ascii=False)}\n\n"
        "请从「真实性、坐标合理性、描述信息量、类别多样性」四个角度打分(0-100)，"
        "列出发现的问题与改进建议。只输出 JSON。"
    )
    res = client.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        json_schema=REVIEW_JSON_SCHEMA,
        temperature=0.3,
    )
    try:
        data = parse_json_loose(res.content)
    except Exception:
        data = {"score": None, "issues": [], "suggestions": []}
    data["stats"] = res.stats
    return data


def refine_landmarks(
    client,
    place: str,
    landmarks: List[Dict[str, Any]],
    suggestions: List[str],
) -> Dict[str, Any]:
    """依据自评建议，让模型对数据做一轮修订（迭代优化）。"""
    system = "你是一名校园地理数据编辑，能够按审校意见精确修订数据。"
    user = (
        f"原始数据(JSON)：{json.dumps({'landmarks': landmarks}, ensure_ascii=False)}\n\n"
        f"审校意见：{json.dumps(suggestions, ensure_ascii=False)}\n\n"
        f"请据此修订「{place}」的 POI 数据，保持字段结构不变，输出完整 JSON。"
    )
    res = client.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        json_schema=LANDMARKS_JSON_SCHEMA,
        temperature=0.4,
    )
    data = parse_json_loose(res.content)
    return {
        "landmarks": data.get("landmarks", []) if isinstance(data, dict) else [],
        "stats": res.stats,
    }


def summarize_place(client, place: str, landmarks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """让本地模型为地图生成一段导语。"""
    names = "、".join(l.get("name", "") for l in landmarks)
    res = client.chat(
        [
            {"role": "system", "content": "你是一名校园导游文案撰稿人。"},
            {
                "role": "user",
                "content": (
                    f"请为「{place}」的交互式校园地图写一段 80-120 字的导语，"
                    f"需自然提到这些地点：{names}。直接输出正文，不要标题。"
                ),
            },
        ],
        temperature=0.7,
    )
    return {"summary": res.content.strip(), "stats": res.stats}
