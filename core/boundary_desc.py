"""四至描述自动生成 + 界址点成果表（登记表格式输出）——独有功能 P-U2。

四至生成口径（草稿生成，须人工核校，符合本产品「辅助落图工具」定位）：
- 每条边按「重心 → 边中点」的方向方位角归入八方位扇区
  （北/东北/东/东南/南/西南/西/西北，扇区宽 45°、以正方位为中心）；
- 沿多边形边序把同扇区的连续边合并为一段，段长为各边边长之和；
- 相邻名称由调用方给（neighbors）：可按扇区给（{"东": "张三地"}）、
  按边序号给（list，与界址点表边序一致），或按 from 点号给
  （{"J1": "张三地"}）；都没有时用占位「相邻地块（名称待填）」；
- sizhi4 为四至四方向口径（供界址图 PDF 四至栏）：有纯 cardinal 段时
  直接取用；没有时取与该方向相邻的角扇区中最长一段的名称顶替
  （菱形状宗地只有角边时的起草启发式，生成稿仍须人工核校）。
"""
import math

from . import geometry

SECTORS = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
_CARDINAL_OF_CORNER = {"东北": ("东", "北"), "东南": ("东", "南"),
                       "西南": ("西", "南"), "西北": ("西", "北")}
PLACEHOLDER = "相邻地块（名称待填）"
NOTE = ("四至为自动生成的草稿：方位按重心至各边中点的方向归并、相邻名称为"
        "调用方提供或占位，须经人工核校后方可用于成果。")


def sector_of_azimuth(azimuth_deg):
    """方位角（北起顺时针）-> 八方位扇区名。"""
    az = float(azimuth_deg) % 360.0
    idx = int((az + 22.5) // 45) % 8
    return ["北", "东北", "东", "东南", "南", "西南", "西", "西北"][idx]


def format_dms(azimuth_deg):
    """方位角 -> 度分秒文本，如 45°30′20″（秒四舍五入，进位归整）。"""
    total_seconds = int(round((float(azimuth_deg) % 360.0) * 3600))
    total_seconds %= 360 * 3600
    d, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{d}°{m:02d}′{s:02d}″"


def _neighbor_for(neighbors, sector, edge_index, from_name):
    if not neighbors:
        return None
    if isinstance(neighbors, dict):
        if from_name in neighbors:
            return neighbors[from_name]
        if sector in neighbors:
            return neighbors[sector]
        return None
    if isinstance(neighbors, (list, tuple)):
        if 0 <= edge_index < len(neighbors):
            return neighbors[edge_index]
    return None


def generate_sizhi(points, neighbors=None):
    """由多边形生成四至草稿。points 至少 3 个。

    返回 {"text", "segments", "sizhi4", "note"}：
    - segments: [{sector, name, length_m, from, to}]，按「东起顺时针」
      的阅读习惯排序（找不到东段时按多边形边序）；
    - sizhi4: {"east","south","west","north"} 名称（PDF 四至栏口径）；
    - text: 「东至…（长 … 米），北至…」规范句式全文。
    """
    pts = list(points or [])
    if len(pts) < 3:
        raise ValueError("至少需要 3 个界址点才能生成四至。")
    center = geometry.centroid(pts)
    table = geometry.boundary_table(pts)
    raw_segments = []
    for i, row in enumerate(table):
        p, q = pts[i], pts[(i + 1) % len(pts)]
        mid = {"x": (p["x"] + q["x"]) / 2.0, "y": (p["y"] + q["y"]) / 2.0}
        sector = sector_of_azimuth(geometry.azimuth_of(center, mid))
        name = _neighbor_for(neighbors, sector, i, row["from"]) or PLACEHOLDER
        if raw_segments and raw_segments[-1]["sector"] == sector \
                and raw_segments[-1]["name"] == name:
            raw_segments[-1]["length_m"] += row["length"]
            raw_segments[-1]["to"] = row["to"]
        else:
            raw_segments.append({"sector": sector, "name": name,
                                 "length_m": row["length"],
                                 "from": row["from"], "to": row["to"]})
    # 首尾同扇区同名时环形合并（边序绕回起点）
    if len(raw_segments) > 1 and raw_segments[0]["sector"] == raw_segments[-1]["sector"] \
            and raw_segments[0]["name"] == raw_segments[-1]["name"]:
        raw_segments[0]["length_m"] += raw_segments[-1]["length_m"]
        raw_segments[0]["from"] = raw_segments[-1]["from"]
        raw_segments.pop()
    # 阅读顺序：东 -> 东南 -> 南 -> 西南 -> 西 -> 西北 -> 北 -> 东北（顺时针）
    order = ["东", "东南", "南", "西南", "西", "西北", "北", "东北"]
    segments = sorted(raw_segments,
                      key=lambda s: order.index(s["sector"]))
    for s in segments:
        s["length_m"] = round(s["length_m"], 2)
    text = "，".join(f"{s['sector']}至{s['name']}（长 {s['length_m']:.2f} 米）"
                     for s in segments) + "。"
    by_sector = {}
    for s in segments:
        if s["sector"] not in by_sector or s["length_m"] > by_sector[s["sector"]]["length_m"]:
            by_sector[s["sector"]] = s
    sizhi4 = {}
    for cardinal, key in (("东", "east"), ("南", "south"), ("西", "west"), ("北", "north")):
        seg = by_sector.get(cardinal)
        if seg is None:
            corners = [by_sector[c] for c, pair in _CARDINAL_OF_CORNER.items()
                       if cardinal in pair and c in by_sector]
            seg = max(corners, key=lambda s: s["length_m"]) if corners else None
        sizhi4[key] = seg["name"] if seg else PLACEHOLDER
    return {"text": text, "segments": segments, "sizhi4": sizhi4, "note": NOTE}


def registration_table(points):
    """界址点成果表（不动产登记常用表式）：逐点坐标 + 逐边边长/方位角
    （数值 + 度分秒），附面积与周长汇总。points 至少 3 个。"""
    pts = list(points or [])
    if len(pts) < 3:
        raise ValueError("至少需要 3 个界址点才能生成界址点成果表。")
    table = geometry.boundary_table(pts)
    rows = []
    for i, row in enumerate(table):
        rows.append({
            "seq": i + 1,
            "from": row["from"], "to": row["to"],
            "x": round(row["x"], 3), "y": round(row["y"], 3),
            "length_m": round(row["length"], 2),
            "azimuth_deg": round(row["azimuth_deg"], 4),
            "azimuth_dms": format_dms(row["azimuth_deg"]),
        })
    au = geometry.area_units(pts)
    return {"rows": rows,
            "totals": {"perimeter_m": round(geometry.perimeter(pts), 2),
                       "area_m2": round(au["m2"], 2),
                       "area_mu": round(au["mu"], 4),
                       "area_hectare": round(au["hectare"], 6)},
            "note": "界址点成果表（自动生成草稿）：坐标、边长与方位角由落图点列"
                    "计算，面积为图上量算值，须经人工核校后方可用于成果。"}
