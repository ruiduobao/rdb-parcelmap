"""投影模块：国内四系椭球 + 高斯-克吕格（Gauss-Krüger）3 度带 / 6 度带正反算。

自写实现，采用标准椭球参数与通用高斯-克吕格级数公式，反算用牛顿迭代
精化，保证正反算往返精度在亚毫米量级。

支持坐标系（椭球）：
  - CGCS2000 ：a=6378137, 1/f=298.257222101
  - WGS84    ：a=6378137, 1/f=298.257223563
  - XIAN80   ：西安 80 / IAG75，a=6378140, 1/f=298.257
  - BEIJING54：北京 54 / 克拉索夫斯基，a=6378245, 1/f=298.3

带号口径与 parsers 一致：东坐标可带带号前缀（带号 * 1e6 + 500000 + 横坐标），
3 度带带号 25–45、6 度带带号 13–23（中国范围）；无前缀时横坐标含 500 km 假东。

跨椭球转换经经纬度中间量实现：同一大地经纬度在不同椭球上分别投影。
注意：北京 54 / 西安 80 与其他坐标系之间的大地坐标本身存在系统性差异，
严格转换需要地方七参数；本模块不做七参数改正，转换结果仅供概算，
界面与返回信息会带中文提示（见 conversion_note）。

产品定位：辅助落图工具，成果须经人工核校，不作为测绘资质成果。
"""
import math

# ---------------------------------------------------------------- 椭球定义

ELLIPSOIDS = {
    "CGCS2000": {"a": 6378137.0, "inv_f": 298.257222101, "label": "CGCS2000"},
    "WGS84": {"a": 6378137.0, "inv_f": 298.257223563, "label": "WGS84"},
    "XIAN80": {"a": 6378140.0, "inv_f": 298.257, "label": "西安80（IAG75）"},
    "BEIJING54": {"a": 6378245.0, "inv_f": 298.3, "label": "北京54（克拉索夫斯基）"},
}

_ALIASES = {
    "CGCS2000": "CGCS2000", "CGCS 2000": "CGCS2000", "2000国家大地坐标系": "CGCS2000",
    "国家2000": "CGCS2000",
    "WGS84": "WGS84", "WGS 84": "WGS84", "WGS-84": "WGS84",
    "XIAN80": "XIAN80", "XIAN 80": "XIAN80", "XIAN-80": "XIAN80",
    "西安80": "XIAN80", "西安1980": "XIAN80", "IAG75": "XIAN80", "IAG 1975": "XIAN80",
    "BEIJING54": "BEIJING54", "BEIJING 1954": "BEIJING54", "BEIJING-54": "BEIJING54",
    "北京54": "BEIJING54", "北京1954": "BEIJING54",
    "KRASSOVSKY": "BEIJING54", "KRASSOWSKY": "BEIJING54",
    "克拉索夫斯基": "BEIJING54", "克拉索夫斯基1940": "BEIJING54",
}

#: 涉及北京54 / 西安80 的跨系转换提示（未含地方七参数改正）
APPROX_NOTE = ("提示：北京54／西安80 与其他坐标系之间的转换未含地方七参数改正，"
               "仅供概算，成果须人工核校。")
#: 一般跨椭球转换提示（经经纬度中间量）
INTERMEDIATE_NOTE = "经经纬度中间量换算（未做七参数改正），成果须人工核校。"

FALSE_EASTING = 500000.0
# 带号合理范围（中国，与 parsers.strip_band_prefix / detect_band 口径一致）
ZONE_RANGES = {3: (25, 45), 6: (13, 23)}


def normalize_crs(name):
    """把坐标系名称/别名归一化为 CGCS2000 / WGS84 / XIAN80 / BEIJING54。

    无法识别时返回 None（调用方决定回退口径，保持既有 API 向后兼容）。"""
    if name is None:
        return None
    key = str(name).strip().upper().replace("（", "(").replace("）", ")")
    if key in _ALIASES:
        return _ALIASES[key]
    return _ALIASES.get(str(name).strip())


def ellipsoid(name):
    """返回椭球参数 dict {a, f, e2, ep2, label}；name 可为别名。"""
    crs = normalize_crs(name) or "CGCS2000"
    p = ELLIPSOIDS[crs]
    f = 1.0 / p["inv_f"]
    e2 = f * (2.0 - f)
    return {"name": crs, "a": p["a"], "f": f, "inv_f": p["inv_f"],
            "e2": e2, "ep2": e2 / (1.0 - e2), "label": p["label"]}


def conversion_note(src_crs, dst_crs):
    """跨椭球转换的中文提示。src/dst 相同时为空串；涉及北京54/西安80 时
    返回「未含地方七参数改正，仅供概算」提示；其余跨系返回中间量说明。"""
    s, d = normalize_crs(src_crs), normalize_crs(dst_crs)
    if s is None or d is None or s == d:
        return ""
    if s in ("XIAN80", "BEIJING54") or d in ("XIAN80", "BEIJING54"):
        return APPROX_NOTE
    return INTERMEDIATE_NOTE


# ---------------------------------------------------------------- 带号

def zone_from_lon(lon_deg, zone_width=3):
    """由经度求带号。3 度带：带号 = round(经度/3)，中央经线 = 带号*3；
    6 度带：带号 = floor(经度/6)+1，中央经线 = 带号*6-3。"""
    if zone_width == 3:
        return int(math.floor(lon_deg / 3.0 + 0.5))
    if zone_width == 6:
        return int(math.floor(lon_deg / 6.0)) + 1
    raise ValueError(f"不支持的带宽: {zone_width}（仅 3 或 6）")


def central_meridian(zone, zone_width=3):
    """带号 -> 中央经线（度）。"""
    if zone_width == 3:
        return zone * 3.0
    if zone_width == 6:
        return zone * 6.0 - 3.0
    raise ValueError(f"不支持的带宽: {zone_width}（仅 3 或 6）")


def detect_zone(easting, zone_width=3):
    """从东坐标识别带号前缀：数值 >= 1e6 且前段落在该带宽合理带号范围内时，
    认为带前缀，返回带号；否则返回 None（无前缀）。与 parsers 的剥离口径一致。"""
    e = abs(float(easting))
    if e < 1_000_000:
        return None
    zone = int(e // 1_000_000)
    lo, hi = ZONE_RANGES.get(zone_width, (0, 99))
    return zone if lo <= zone <= hi else None


def strip_zone(easting, zone_width=3):
    """剥离带号前缀，返回 (无前缀东坐标, 带号或 None)。"""
    zone = detect_zone(easting, zone_width)
    if zone is None:
        return float(easting), None
    sign = -1.0 if float(easting) < 0 else 1.0
    return sign * (abs(float(easting)) - zone * 1_000_000), zone


# ---------------------------------------------------------------- 正反算

def _forward_rad(phi, dlam, ell):
    """高斯-克吕格正算（弧度入参，dlam 为相对中央经线经差）。返回 (x_无假东, y)。"""
    a, e2, ep2 = ell["a"], ell["e2"], ell["ep2"]
    sinp, cosp, tanp = math.sin(phi), math.cos(phi), math.tan(phi)
    n = a / math.sqrt(1.0 - e2 * sinp * sinp)
    rho = a * (1.0 - e2) / (1.0 - e2 * sinp * sinp) ** 1.5
    eta2 = ep2 * cosp * cosp
    # 子午线弧长
    e4, e6 = e2 * e2, e2 * e2 * e2
    arc = a * ((1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi
               - (3 * e2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * math.sin(2 * phi)
               + (15 * e4 / 256 + 45 * e6 / 1024) * math.sin(4 * phi)
               - (35 * e6 / 3072) * math.sin(6 * phi))
    l2 = dlam * dlam
    x = (n * cosp * dlam
         + n / 6.0 * cosp ** 3 * dlam ** 3 * (1 - tanp * tanp + eta2)
         + n / 120.0 * cosp ** 5 * dlam ** 5
         * (5 - 18 * tanp * tanp + tanp ** 4 + 72 * eta2 - 58 * ep2))
    y = (arc + n * tanp * (cosp * cosp * l2 / 2.0
                           + cosp ** 4 * l2 * l2 / 24.0
                           * (5 - tanp * tanp + 9 * eta2 + 4 * eta2 * eta2)
                           + cosp ** 6 * l2 ** 3 / 720.0
                           * (61 - 58 * tanp * tanp + tanp ** 4 + 600 * eta2 - 330 * ep2)))
    return x, y


def gauss_forward(lat_deg, lon_deg, crs="CGCS2000", zone_width=3, zone=None,
                  with_prefix=True):
    """经纬度 -> 高斯-克吕格平面坐标。

    zone 为 None 时按经度自动定带；with_prefix=True 时东坐标加带号前缀
    （带号*1e6 + 500000 + x），与国内地籍成果的常见写法一致。
    返回 (东坐标 x, 北坐标 y)。"""
    ell = ellipsoid(crs)
    if zone is None:
        zone = zone_from_lon(lon_deg, zone_width)
    lam0 = math.radians(central_meridian(zone, zone_width))
    x, y = _forward_rad(math.radians(lat_deg), math.radians(lon_deg) - lam0, ell)
    x += FALSE_EASTING
    if with_prefix:
        x += zone * 1_000_000
    return x, y


def gauss_inverse(easting, northing, crs="CGCS2000", zone_width=3, zone=None):
    """高斯-克吕格平面坐标 -> 经纬度（度）。

    zone 为 None 时先从东坐标识别带号前缀（识别不到则按无前缀处理，
    此时需调用方保证坐标落在合理带内，中央经线按 x 所在位置无法唯一确定，
    故无前缀且未给 zone 时按「假东原点」反算相对经差并以 0 度为中央经线——
    实际业务请显式传 zone 或使用带前缀坐标）。先用级数反算求初值，
    再以正算做牛顿迭代精化，往返精度亚毫米。
    返回 (纬度 lat_deg, 经度 lon_deg)。"""
    ell = ellipsoid(crs)
    x = float(easting)
    if zone is None:
        x, zone = strip_zone(x, zone_width)
    else:
        z = detect_zone(x, zone_width)
        if z is not None and z == zone:
            x -= zone * 1_000_000
    lam0_deg = central_meridian(zone, zone_width) if zone is not None else 0.0
    lam0 = math.radians(lam0_deg)
    xp = x - FALSE_EASTING
    y = float(northing)
    a, e2, ep2 = ell["a"], ell["e2"], ell["ep2"]
    # 底点纬度（级数法）
    e4, e6 = e2 * e2, e2 * e2 * e2
    mu = y / (a * (1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    j1, j2, j3, j4 = 3 * e1 / 2 - 27 * e1 ** 3 / 32, 21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32, \
        151 * e1 ** 3 / 96, 1097 * e1 ** 4 / 512
    fp = (mu + j1 * math.sin(2 * mu) + j2 * math.sin(4 * mu)
          + j3 * math.sin(6 * mu) + j4 * math.sin(8 * mu))
    sinf, cosf, tanf = math.sin(fp), math.cos(fp), math.tan(fp)
    nf = a / math.sqrt(1 - e2 * sinf * sinf)
    rf = a * (1 - e2) / (1 - e2 * sinf * sinf) ** 1.5
    tf2 = tanf * tanf
    cf = ep2 * cosf * cosf
    d = xp / nf
    phi = fp - nf * tanf / rf * (d * d / 2
                                 - (5 + 3 * tf2 + 10 * cf - 4 * cf * cf - 9 * ep2) * d ** 4 / 24
                                 + (61 + 90 * tf2 + 298 * cf + 45 * tf2 * tf2 - 252 * ep2
                                    - 3 * cf * cf) * d ** 6 / 720)
    lam = lam0 + (d - (1 + 2 * tf2 + cf) * d ** 3 / 6
                  + (5 - 2 * cf + 28 * tf2 - 8 * ep2) * d ** 5 / 120) / cosf
    # 牛顿迭代精化（数值雅可比，3 次足够收敛到亚微米）
    for _ in range(3):
        fx, fy = _forward_rad(phi, lam - lam0, ell)
        dx, dy = fx - xp, fy - y
        if abs(dx) < 1e-7 and abs(dy) < 1e-7:
            break
        h = 1e-7
        fx1, fy1 = _forward_rad(phi + h, lam - lam0, ell)
        fx2, fy2 = _forward_rad(phi, lam - lam0 + h, ell)
        a11, a21 = (fx1 - fx) / h, (fy1 - fy) / h
        a12, a22 = (fx2 - fx) / h, (fy2 - fy) / h
        det = a11 * a22 - a12 * a21
        if det == 0:
            break
        phi -= (dx * a22 - dy * a12) / det
        lam -= (a11 * dy - a21 * dx) / det
    return math.degrees(phi), math.degrees(lam)


# ---------------------------------------------------------------- 转换

def latlon_to_plane(lat_deg, lon_deg, crs="CGCS2000", zone_width=3, zone=None,
                    with_prefix=True):
    """经纬度 -> 指定椭球平面坐标（gauss_forward 的语义别名）。"""
    return gauss_forward(lat_deg, lon_deg, crs, zone_width, zone, with_prefix)


def plane_to_latlon(x, y, crs="CGCS2000", zone_width=3, zone=None):
    """指定椭球平面坐标 -> 经纬度（gauss_inverse 的语义别名）。"""
    return gauss_inverse(x, y, crs, zone_width, zone)


def convert_plane(x, y, src_crs, dst_crs, zone_width=3, src_zone=None, dst_zone=None):
    """平面坐标跨系转换：源系反算经纬度（中间量）-> 目标系正算。

    返回 dict{x, y, lat, lon, src_crs, dst_crs, src_zone, dst_zone, note}；
    note 为中文提示（涉及北京54/西安80 时为七参数概算提示）。"""
    lat, lon = gauss_inverse(x, y, src_crs, zone_width, src_zone)
    if src_zone is None:
        src_zone = detect_zone(x, zone_width) or zone_from_lon(lon, zone_width)
    if dst_zone is None:
        dst_zone = zone_from_lon(lon, zone_width)
    nx, ny = gauss_forward(lat, lon, dst_crs, zone_width, dst_zone)
    return {"x": nx, "y": ny, "lat": lat, "lon": lon,
            "src_crs": normalize_crs(src_crs), "dst_crs": normalize_crs(dst_crs),
            "src_zone": src_zone, "dst_zone": dst_zone,
            "note": conversion_note(src_crs, dst_crs)}


def convert_latlon(lat_deg, lon_deg, dst_crs, zone_width=3, zone=None):
    """经纬度 -> 目标系平面坐标，返回 dict{x, y, lat, lon, dst_crs, dst_zone}。"""
    if zone is None:
        zone = zone_from_lon(lon_deg, zone_width)
    x, y = gauss_forward(lat_deg, lon_deg, dst_crs, zone_width, zone)
    return {"x": x, "y": y, "lat": lat_deg, "lon": lon_deg,
            "dst_crs": normalize_crs(dst_crs), "dst_zone": zone, "note": ""}


def convert_points(points, src_crs, dst_crs, input_kind="plane", zone_width=3,
                   src_zone=None, dst_zone=None):
    """批量转换点列 [{name, x, y}, ...]，保持点号与顺序。

    input_kind="plane"：输入为源系平面坐标，输出目标系平面坐标；
    input_kind="latlon"：输入 x=经度、y=纬度，输出目标系平面坐标。
    返回 (新点列, note)。"""
    out = []
    if input_kind == "latlon":
        for p in points:
            r = convert_latlon(p["y"], p["x"], dst_crs, zone_width, dst_zone)
            out.append({"name": p.get("name", ""), "x": r["x"], "y": r["y"]})
        return out, ""
    for p in points:
        r = convert_plane(p["x"], p["y"], src_crs, dst_crs, zone_width,
                          src_zone, dst_zone)
        out.append({"name": p.get("name", ""), "x": r["x"], "y": r["y"]})
    return out, conversion_note(src_crs, dst_crs)
