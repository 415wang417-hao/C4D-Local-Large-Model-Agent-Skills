# -*- coding: utf-8 -*-
"""C4D Level 4 加分项：默认模型 vs Uncensored 变体 同任务对照实验
用法: python uncensored_compare.py
输出: uncensored_compare.json （同目录）
"""
import json
import os
import time
import urllib.request

OLLAMA = "http://127.0.0.1:11434"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uncensored_compare.json")

PROMPT = """你是郑州西亚斯学院(SIAS)的校园地理信息助手。
学校位于河南省郑州市新郑市（约 34.39°N, 113.74°E），以国际化办学和欧式建筑风格著称。

请生成 5 个校园地点，要求：
1. 覆盖 教学、文化、生活、运动、行政、景观 中的至少 4 类；
2. 每个地点给出：name（中文名）、category（类别）、lat/lng（经纬度，保留 2-4 位小数）、description（30-60 字中文描述）；
3. 只输出 JSON：{"landmarks":[{...}]}"""

MODELS = [
    {"tag": "gemma4:e4b", "label": "默认模型", "params": "E4B"},
    {"tag": "Librellama/gemma4:e2b-Uncensored", "label": "Uncensored 变体", "params": "E2B"},
]

CATS = ["教学", "文化", "生活", "运动", "行政", "景观"]
REFUSAL_HINTS = ["抱歉", "无法", "不能提供", "I cannot", "sorry", "作为AI"]


def call(model, num_ctx=2048, num_gpu=0):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": False,
        "format": "json",
        "options": {"num_ctx": num_ctx, "num_gpu": num_gpu, "temperature": 0.7, "seed": 42},
    }
    req = urllib.request.Request(
        OLLAMA + "/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=1800) as r:
        d = json.loads(r.read().decode("utf-8"))
    wall = time.time() - t0

    content = d.get("message", {}).get("content", "") or ""
    ec = d.get("eval_count", 0) or 0
    ed = (d.get("eval_duration", 0) or 0) / 1e9
    ld = (d.get("load_duration", 0) or 0) / 1e9
    return {
        "wall_s": round(wall, 2),
        "eval_count": ec,
        "eval_duration_s": round(ed, 3),
        "load_duration_s": round(ld, 2),
        "tok_per_s": round(ec / ed, 2) if ed > 0 else None,
        "raw": content,
    }


def analyze(raw):
    info = {"json_ok": False, "count": 0, "categories": [], "category_count": 0,
            "refused": any(h in raw for h in REFUSAL_HINTS),
            "avg_desc_len": 0, "coord_precision_ok": 0}
    try:
        obj = json.loads(raw)
    except Exception:
        return info
    info["json_ok"] = True
    items = obj.get("landmarks", []) if isinstance(obj, dict) else (obj if isinstance(obj, list) else [])
    info["count"] = len(items)
    cats, descs, prec = set(), [], 0
    for it in items:
        if not isinstance(it, dict):
            continue
        cats.add(it.get("category", "?"))
        d = it.get("description", "") or ""
        descs.append(len(d))
        for k in ("lat", "lng"):
            v = str(it.get(k, ""))
            if "." in v and 2 <= len(v.split(".")[1]) <= 6:
                prec += 1
    info["categories"] = sorted(cats)
    info["category_count"] = len(cats)
    info["avg_desc_len"] = round(sum(descs) / len(descs), 1) if descs else 0
    info["coord_precision_ok"] = prec
    return info


def unload(model):
    try:
        req = urllib.request.Request(
            OLLAMA + "/api/generate",
            data=json.dumps({"model": model, "keep_alive": 0}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=60).read()
    except Exception as e:
        print("  unload 警告:", e)


def main():
    results = []
    for m in MODELS:
        print("=" * 60)
        print("模型:", m["tag"], "|", m["label"])
        try:
            r = call(m["tag"])
        except Exception as e:
            print("  失败:", e)
            results.append({**m, "error": str(e)})
            continue
        a = analyze(r["raw"])
        print("  tok/s = %s | 输出 tokens = %s | 耗时 %.2fs (加载 %.2fs)"
              % (r["tok_per_s"], r["eval_count"], r["wall_s"], r["load_duration_s"]))
        print("  JSON 合规 = %s | 地点数 = %s | 类别 = %s (%s 类) | 拒答 = %s"
              % (a["json_ok"], a["count"], a["categories"], a["category_count"], a["refused"]))
        row = {**m, **r, **{"analysis": a}}
        row.pop("raw", None)
        row["raw_excerpt"] = r["raw"][:1200]
        results.append(row)
        unload(m["tag"])
        time.sleep(2)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"prompt": PROMPT, "results": results}, f, ensure_ascii=False, indent=2)
    print("=" * 60)
    print("结果已写入:", OUT)


if __name__ == "__main__":
    main()
