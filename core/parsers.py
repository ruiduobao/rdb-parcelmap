"""解析器集合（全部自写）：坐标串 / CSV / DXF / 中文界址文本 / 英文地块描述。

坐标约定：内部统一使用 (x, y) = (东, 北)；经纬度时 x=经度, y=纬度。
边（Edge）约定：dict {from, to, azimuth_deg（方位角，北起顺时针）, distance（米）}
"""
import csv
import io
import math
import re

# ---------------------------------------------------------------- 工具

_NUM = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"

def dms_to_deg(d, m=0.0, s=0.0):
    sign = -1 if d < 0 else 1
    return sign * (abs(d) + m / 60.0 + s / 3600.0)

def parse_angle(text):
    """把角度文本解析为十进制度。支持：123.45 / 45°30′20″ / 45°30'20" / 45度30分20秒"""
    t = str(text).strip()
    t = t.replace("度", "°").replace("分", "′").replace("秒", "″")
    t = t.replace("'", "′").replace('"', "″")
    m = re.match(rf"^({_NUM})\s*°\s*(?:({_NUM})\s*′)?\s*(?:({_NUM})\s*″)?$", t)
    if m:
        return dms_to_deg(float(m.group(1)), float(m.group(2) or 0), float(m.group(3) or 0))
    try:
        return float(t)
    except ValueError:
        raise ValueError(f"无法解析角度：{text!r}，请写成 123.45 或 45°30′20″ 的形式。")

# 十六方位词 -> 方位角（北起顺时针）
COMPASS16 = {
    "北": 0, "北北东": 22.5, "东北": 45, "东北东": 67.5, "东": 90, "东南东": 112.5,
    "东南": 135, "南南东": 157.5, "南": 180, "南南西": 202.5, "西南": 225,
    "西南西": 247.5, "西": 270, "西北西": 292.5, "西北": 315, "北北西": 337.5,
    "正北": 0, "正东": 90, "正南": 180, "正西": 270,
}
# 长词优先
_COMPASS_KEYS = sorted(COMPASS16, key=len, reverse=True)

def compass_to_azimuth(word):
    return COMPASS16[word.strip()]

def parse_deflection(text):
    """解析「北偏东30°」「南偏西45°30′」等偏角写法 -> 方位角。无匹配返回 None。"""
    t = str(text).strip().replace(" ", "")
    m = re.match(r"^([南北])偏([东西])(.+)$", t)
    if not m:
        return None
    base, toward = m.group(1), m.group(2)
    # 角度只截取其后的前导角度 token：整行文本里偏角后面常跟「长25米」
    # 等内容（且本函数已删除全部空格），整段喂 parse_angle 会误判。
    tm = re.match(rf"({_NUM}\s*(?:°|º)?(?:{_NUM}\s*′)?(?:{_NUM}\s*″)?)", m.group(3))
    if not tm:
        return None
    try:
        ang = parse_angle(tm.group(1))
    except ValueError:
        return None
    if base == "北" and toward == "东":
        return ang % 360
    if base == "北" and toward == "西":
        return (360 - ang) % 360
    if base == "南" and toward == "东":
        return (180 - ang) % 360
    return (180 + ang) % 360  # 南偏西

# ---------------------------------------------------------------- 1. 坐标串

def strip_band_prefix(value, axis, strip=True):
    """CGCS2000 三度带：带号前缀识别。x（东坐标）常见 6~8 位整数部分，
    如带号 39 时东坐标写作 39xxxxxx.xx（8 位整数）。strip=True 且整数部分
    >=8 位时剥离前两位带号，返回 (数值, 带号或None)。"""
    v = float(value)
    if not strip:
        return v, None
    s = f"{abs(v):.10f}"
    intpart = s.split(".")[0]
    if axis == "x" and len(intpart) >= 8:
        band = int(intpart[:2])
        if 25 <= band <= 45:  # 三度带带号合理范围
            return float(("-" if v < 0 else "") + intpart[2:] + "." + s.split(".")[1]), band
    return v, None

def parse_coordinate_string(text, order="xy", strip_band=False):
    """坐标串解析。
    - order: "xy" 表示每行 x,y；"yx" 表示 y,x
    - 分隔：分号 / 换行 / 空格（空格分隔时按数值两两成对）
    - 点号标注：行首可带 J1、J2、点1 等标注（逗号/冒号/空格分隔）
    返回 list[dict{name, x, y}]，并在首个带带号点上记录 band（键 '_band' 不出现，
    带号汇总由 detect_band 单独提供）。"""
    raw = str(text).strip()
    if not raw:
        return []
    # 先按分号/换行切行；若整体只有一行且空格分隔数值>=4，则两两成对
    lines = [ln.strip() for ln in re.split(r"[;\n]+", raw) if ln.strip()]
    tokens_mode = False
    if len(lines) == 1 and "," not in lines[0] and "，" not in lines[0]:
        nums = re.findall(_NUM, lines[0])
        labels = re.findall(r"[A-Za-z]{1,3}\d+\s*[:：]?", lines[0])
        if len(nums) >= 4 and len(nums) % 2 == 0 and len(labels) <= 1:
            tokens_mode = True
    points = []
    if tokens_mode:
        nums = [float(v) for v in re.findall(_NUM, lines[0])]
        for i in range(0, len(nums), 2):
            a, b = nums[i], nums[i + 1]
            x, y = (a, b) if order == "xy" else (b, a)
            points.append({"name": f"J{len(points)+1}", "x": x, "y": y})
        return points
    for ln in lines:
        name = None
        m = re.match(r"^\s*([A-Za-z]{1,3}\d+|点\s*\d+)\s*[,，:：\s]\s*(.*)$", ln)
        rest = ln
        if m and re.search(_NUM, m.group(2)):
            name = m.group(1).replace(" ", "")
            if name.startswith("点"):
                name = "J" + name[1:]
            rest = m.group(2)
        nums = [float(v) for v in re.findall(_NUM, rest.replace("，", ","))]
        if len(nums) < 2:
            continue
        a, b = nums[0], nums[1]
        x, y = (a, b) if order == "xy" else (b, a)
        if strip_band:
            x, _band = strip_band_prefix(x, "x", True)
        points.append({"name": name or f"J{len(points)+1}", "x": x, "y": y})
    return points

def detect_band(text):
    """从坐标串中探测 CGCS2000 三度带带号（东坐标 8 位整数前两位）。"""
    for v in re.findall(_NUM, str(text)):
        ip = f"{abs(float(v)):.2f}".split(".")[0]
        if len(ip) >= 8 and 25 <= int(ip[:2]) <= 45:
            return int(ip[:2])
    return None

# ---------------------------------------------------------------- 2. CSV

_HEADER_MAP = {
    "点号": "name", "点名": "name", "编号": "name", "name": "name", "id": "name", "point": "name",
    "x": "x", "东坐标": "x", "东": "x", "横坐标": "x",
    "y": "y", "北坐标": "y", "北": "y", "纵坐标": "y",
    "经度": "lon", "lon": "lon", "lng": "lon", "longitude": "lon",
    "纬度": "lat", "lat": "lat", "latitude": "lat",
}

def parse_csv(text):
    """CSV 导入：表头支持 点号,X,Y 或 点号,纬度,经度（中英文列名）。
    经纬度模式下返回 x=经度, y=纬度。"""
    text = str(text).lstrip("\ufeff")
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return []
    header = [c.strip().lower() for c in rows[0]]
    mapped = [_HEADER_MAP.get(h) for h in header]
    has_header = any(mapped) and sum(1 for m in mapped if m) >= 2
    points = []
    if has_header:
        idx = {m: i for i, m in enumerate(mapped) if m}
        for r in rows[1:]:
            try:
                if "lon" in idx and "lat" in idx:
                    x, y = float(r[idx["lon"]]), float(r[idx["lat"]])
                else:
                    x, y = float(r[idx["x"]]), float(r[idx["y"]])
            except (ValueError, IndexError, KeyError):
                continue
            name = r[idx["name"]].strip() if "name" in idx and r[idx["name"]].strip() else f"J{len(points)+1}"
            points.append({"name": name, "x": x, "y": y})
    else:  # 无表头：默认三列 点号,x,y 或两列 x,y
        for r in rows:
            nums = []
            name = None
            for c in r:
                try:
                    nums.append(float(c))
                except ValueError:
                    if name is None and c.strip():
                        name = c.strip()
            if len(nums) >= 2:
                points.append({"name": name or f"J{len(points)+1}", "x": nums[0], "y": nums[1]})
    return points

# ---------------------------------------------------------------- 3. DXF（自写 ASCII 解析）

def _dxf_float(val):
    """DXF 数值字段容错：非数值（文件损坏/手工改坏）返回 None 跳过，不裸崩。"""
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def parse_dxf(text):
    """自写 ASCII DXF 解析：只取 LWPOLYLINE / POLYLINE 顶点与 POINT 实体。
    返回 {"polylines": [[{name,x,y},...], ...], "points": [{name,x,y}, ...]}"""
    raw_lines = str(text).splitlines()
    pairs = []
    for i in range(0, len(raw_lines) - 1, 2):
        pairs.append((raw_lines[i].strip(), raw_lines[i + 1].strip()))
    polylines, points = [], []
    entity = None        # 当前实体类型
    verts = []           # 当前多段线顶点 [(x,y), ...]
    pending_x = None     # 待配对的 x
    point_xy = {}        # 当前 POINT 坐标

    def close_entity():
        nonlocal entity, verts, pending_x, point_xy
        if entity in ("LWPOLYLINE", "POLYLINE") and verts:
            polylines.append([{"name": f"J{k+1}", "x": vx, "y": vy}
                              for k, (vx, vy) in enumerate(verts)])
        if entity == "POINT" and "x" in point_xy and "y" in point_xy:
            points.append({"name": f"P{len(points)+1}",
                           "x": point_xy["x"], "y": point_xy["y"]})
        entity, verts, pending_x, point_xy = None, [], None, {}

    for code, val in pairs:
        if code == "0":
            if val in ("LWPOLYLINE", "POLYLINE", "POINT", "VERTEX"):
                if val == "VERTEX" and entity == "POLYLINE":
                    pending_x = None
                    continue
                close_entity()
                entity = val if val != "VERTEX" else "POLYLINE"
            else:
                close_entity()
            continue
        if entity in ("LWPOLYLINE", "POLYLINE"):
            if code == "10":
                pending_x = _dxf_float(val)
            elif code == "20" and pending_x is not None:
                yv = _dxf_float(val)
                if yv is not None:
                    verts.append((pending_x, yv))
                pending_x = None
        elif entity == "POINT":
            if code == "10":
                fv = _dxf_float(val)
                if fv is not None:
                    point_xy["x"] = fv
            elif code == "20":
                fv = _dxf_float(val)
                if fv is not None:
                    point_xy["y"] = fv
    close_entity()
    return {"polylines": polylines, "points": points}

# ---------------------------------------------------------------- 4/5. 边表式文本

_EDGE_HEAD = re.compile(
    r"([A-Za-z]{0,3}\d+)\s*(?:→|->|—|–|-{1,2}|至|到)\s*([A-Za-z]{0,3}\d+)")

def _parse_distance(t):
    """提取距离（米）。支持 米/m/公尺；英尺 ft/feet/′（数值后）。返回米或 None。"""
    m = re.search(rf"({_NUM})\s*(?:英尺|feet|ft)\b", t, re.I)
    if m:
        return float(m.group(1)) * 0.3048
    m = re.search(rf"({_NUM})\s*(?:米|公尺|m(?![a-z]))", t, re.I)
    if m:
        return float(m.group(1))
    m = re.search(rf"(?:距离|长|边长|distance|dist\.?|length)\s*[:：=]?\s*({_NUM})", t, re.I)
    if m:
        return float(m.group(1))
    return None

def _parse_azimuth(t):
    """从一段文本提取方位角：方位角数值/DMS、偏角写法、十六方位词、象限角 N30°E。"""
    # 象限角 N30°E / S45W 等
    m = re.search(r"([NS])\s*(\d+(?:\.\d+)?)\s*°?\s*([EW])", t)
    if m:
        ang = float(m.group(2))
        ns, ew = m.group(1), m.group(3)
        if ns == "N" and ew == "E":
            return ang
        if ns == "N" and ew == "W":
            return 360 - ang
        if ns == "S" and ew == "E":
            return 180 - ang
        return 180 + ang
    # 偏角：出现「北偏东/南偏西」句式时以偏角解析为唯一口径——解析失败
    # 直接返回 None，不得穿透到下方方位词兜底（句中「北」「南」字会被
    # 误抓成正北/正南方位角，把写坏的偏角静默变成错边）。
    if re.search(r"[南北]偏[东西]", t):
        m = re.search(r"[南北]偏[东西][^，,；;米m]+", t)
        return parse_deflection(m.group(0)) if m else None
    # 方位角 + DMS/数值
    m = re.search(r"(?:方位角|方位|azimuth|bearing)\s*[:：=]?\s*([0-9°′″'\"度分秒.]+)", t, re.I)
    if m:
        try:
            return parse_angle(m.group(1)) % 360
        except ValueError:
            pass
    # 十六方位词
    for w in _COMPASS_KEYS:
        if w in t:
            return float(COMPASS16[w])
    return None

def parse_edge_text(text):
    """边表式文本解析（中英文）。逐行如：
      J1→J2 方位角 45°30′20″ 距离 32.15 米
      J1-J2：北偏东30°，长25米
      J1 to J2 bearing N30°E distance 100 ft
    返回 list[Edge]。"""
    edges = []
    for line in str(text).splitlines():
        line = line.strip()
        if not line:
            continue
        m = _EDGE_HEAD.search(line)
        if not m:
            m2 = re.search(r"([A-Za-z]{0,3}\d+)\s+(?:to|TO)\s+([A-Za-z]{0,3}\d+)", line)
            if not m2:
                continue
            m = m2
        az = _parse_azimuth(line)
        dist = _parse_distance(line)
        if az is None or dist is None or dist <= 0:
            continue  # 距离缺失或非正数（写错符号等）的行不收，避免反向走线静默出错
        edges.append({"from": m.group(1), "to": m.group(2),
                      "azimuth_deg": az % 360, "distance": dist})
    return edges

_SIZHI_DIRS = {"东": "east", "西": "west", "南": "south", "北": "north"}

def parse_sizhi_text(text):
    """四至式描述解析：提取四至名称与（若写明）各边边长。
    例：东至张三地，南至村道，西至水沟，北至李四地；东边长25.5米，南边长30米…
    返回 {"east":..., "south":..., "west":..., "north":...,
          "lengths": {"east": 米或None, ...}, "raw": 原文}"""
    t = str(text)
    out = {"east": None, "south": None, "west": None, "north": None,
           "lengths": {"east": None, "south": None, "west": None, "north": None},
           "raw": t}
    for cn, key in _SIZHI_DIRS.items():
        m = re.search(rf"{cn}至\s*([^，,；;。\n]+)", t)
        if m:
            val = m.group(1).strip()
            lm = re.search(rf"(.+?)(?:[，,；;]?\s*(?:长|边长)\s*)?({_NUM})\s*米", val)
            if re.search(rf"(?:长|边长)\s*{_NUM}\s*米", val) or re.search(rf"{_NUM}\s*米", val):
                mm = re.search(rf"({_NUM})\s*米", val)
                out["lengths"][key] = float(mm.group(1))
                val = re.sub(rf"[，,；;]?\s*(?:长|边长)?\s*{_NUM}\s*米.*$", "", val).strip("，,；; ")
            out[key] = val or None
        m2 = re.search(rf"{cn}边\s*(?:长)?\s*({_NUM})\s*米", t)
        if m2:
            out["lengths"][key] = float(m2.group(1))
    return out

def parse_english_description(text):
    """英文地块描述基础解析：象限角 bearing（N30°E 等）+ 距离（米/英尺）。
    与中文边表共用逐行解析，英文行如
      From P1 to P2 bearing N30°E distance 100 ft
    返回 list[Edge]（距离统一换算为米）。"""
    return parse_edge_text(text)
