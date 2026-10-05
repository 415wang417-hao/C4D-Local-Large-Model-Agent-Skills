"""
交互式地图渲染模块（基于 folium / Leaflet.js）。

产物为一页自包含 HTML：
* 支持平移、滚轮缩放、双击放大（Leaflet 原生交互）；
* 每个标记点可点击，弹出名称 / 类别 / 描述 / 坐标；
* 按类别着色并自动生成图例；
* 附带标题栏与地点统计面板。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

import folium
from folium import plugins

# 类别 -> 颜色 / 图标（仅样式映射，非地点数据）
CATEGORY_STYLE: Dict[str, Dict[str, str]] = {
    "教学": {"color": "blue", "icon": "graduation-cap"},
    "生活": {"color": "green", "icon": "cutlery"},
    "运动": {"color": "orange", "icon": "futbol"},
    "文化": {"color": "purple", "icon": "book"},
    "行政": {"color": "red", "icon": "building"},
    "景观": {"color": "cadetblue", "icon": "tree"},
}
DEFAULT_STYLE = {"color": "gray", "icon": "info-sign"}

LEGEND_COLORS = {
    "blue": "#2A81CB",
    "green": "#2AAD27",
    "orange": "#CB8427",
    "purple": "#9C2BCB",
    "red": "#CB2B3E",
    "cadetblue": "#4A9EA8",
    "gray": "#6C6C6C",
}


def build_map(
    landmarks: List[Dict[str, Any]],
    title: str = "SIAS 校园交互式地图",
    subtitle: str = "",
    output_path: str = "sias_map.html",
    center: Any = None,
    zoom: int = 16,
) -> str:
    """把地点数据渲染为交互式 HTML 地图。

    Parameters
    ----------
    landmarks : 由本地模型生成的 POI 列表。
    center    : (lat, lng)；为 None 时自动取所有点的几何中心。
    """
    if not landmarks:
        raise ValueError("landmarks 为空，无法生成地图")

    lats = [float(l["lat"]) for l in landmarks]
    lngs = [float(l["lng"]) for l in landmarks]
    ctr = center or (sum(lats) / len(lats), sum(lngs) / len(lngs))

    # 主底图：OpenStreetMap（免 API key）
    fmap = folium.Map(
        location=ctr,
        zoom_start=zoom,
        control_scale=True,
        tiles="OpenStreetMap",
        zoom_control=True,
        prefer_canvas=True,
    )
    # 可选叠加底图：卫星影像 / 地形图（可在右上角图层控件中自由切换）
    # 注：CartoDB 自 folium 0.20 起需 API key，此处改用免密钥源。
    folium.TileLayer(tiles="Esri.WorldImagery", name="卫星影像", control=True).add_to(fmap)
    folium.TileLayer(
        tiles="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        name="地形图 (OpenTopoMap)",
        control=True,
        attr="Map data &copy; OpenStreetMap contributors | Style &copy; OpenTopoMap (CC-BY-SA)",
    ).add_to(fmap)

    # 类别分组（可勾选图层）
    groups: Dict[str, folium.FeatureGroup] = {}

    for lm in landmarks:
        cat = lm.get("category", "其他")
        style = CATEGORY_STYLE.get(cat, DEFAULT_STYLE)
        if cat not in groups:
            groups[cat] = folium.FeatureGroup(name=f"{cat} ({style['icon']})")
        popup_html = (
            f"<div style='font-family:Microsoft YaHei,sans-serif;width:250px'>"
            f"<h4 style='margin:0 0 6px 0;color:{LEGEND_COLORS.get(style['color'], '#333')}'>"
            f"{lm.get('name','未命名')}</h4>"
            f"<div style='font-size:12px;color:#666;margin-bottom:6px'>类别：{cat}"
            f"　坐标：{float(lm['lat']):.5f}, {float(lm['lng']):.5f}</div>"
            f"<div style='font-size:13px;line-height:1.6'>{lm.get('description','')}</div>"
            f"</div>"
        )
        tooltip = f"{lm.get('name','')} · {cat}"
        folium.Marker(
            location=(float(lm["lat"]), float(lm["lng"])),
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=tooltip,
            icon=folium.Icon(color=style["color"], icon=style["icon"], prefix="fa"),
        ).add_to(groups[cat])

    for g in groups.values():
        g.add_to(fmap)

    if len(landmarks) >= 2:
        plugins.AntPath(
            locations=[(float(l["lat"]), float(l["lng"])) for l in landmarks],
            color="#8b5cf6",
            weight=2,
            opacity=0.55,
            dash_array="6 10",
        ).add_to(fmap)

    plugins.MiniMap(toggle_display=True).add_to(fmap)
    plugins.Fullscreen(position="topleft").add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)

    # 图例
    legend_items = "".join(
        f"<div style='display:flex;align-items:center;margin:3px 0'>"
        f"<span style='width:12px;height:12px;border-radius:50%;display:inline-block;"
        f"background:{LEGEND_COLORS.get(CATEGORY_STYLE.get(c, DEFAULT_STYLE)['color'], '#666')};"
        f"margin-right:6px'></span><span style='font-size:12px'>{c}</span></div>"
        for c in sorted({l.get("category", "其他") for l in landmarks})
    )
    legend_html = (
        "<div style='position:fixed;bottom:30px;left:30px;z-index:9999;background:rgba(255,255,255,.95);"
        "padding:10px 14px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,.2);"
        "font-family:Microsoft YaHei,sans-serif'>"
        "<div style='font-weight:700;font-size:13px;margin-bottom:6px'>地点类别</div>"
        f"{legend_items}</div>"
    )
    fmap.get_root().html.add_child(folium.Element(legend_html))

    # 标题栏
    header_html = (
        "<div style='position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:9999;"
        "background:linear-gradient(90deg,#1e3a8a,#7c3aed);color:#fff;padding:10px 26px;"
        "border-radius:10px;box-shadow:0 3px 14px rgba(0,0,0,.28);text-align:center;"
        "font-family:Microsoft YaHei,sans-serif'>"
        f"<div style='font-size:17px;font-weight:700;letter-spacing:1px'>{title}</div>"
        f"<div style='font-size:11px;opacity:.9;margin-top:3px'>{subtitle}</div></div>"
    )
    fmap.get_root().html.add_child(folium.Element(header_html))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    fmap.save(output_path)
    return os.path.abspath(output_path)


def map_statistics(landmarks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """统计信息，供报告使用。"""
    cats: Dict[str, int] = {}
    for l in landmarks:
        cats[l.get("category", "其他")] = cats.get(l.get("category", "其他"), 0) + 1
    return {
        "total": len(landmarks),
        "categories": cats,
        "category_count": len(cats),
    }
