"""导线计算与平差（自写）：边序列 -> 坐标、闭合差、Bowditch（罗盘）法则平差；
坐标点列成多边形的闭合与自交校验。"""
import math

try:
    from shapely.geometry import Polygon as _ShpPolygon
    _HAS_SHAPELY = True
except Exception:  # pragma: no cover
    _HAS_SHAPELY = False


def _seg_intersect(p1, p2, p3, p4):
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    d1, d2 = cross(p3, p4, p1), cross(p3, p4, p2)
    d3, d4 = cross(p1, p2, p3), cross(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def has_self_intersection(points):
    """自交检测（自写线段相交判定，shapely 可用时交叉验证）。points 不含重复闭合点。

    候选对生成用 x 方向扫描线剪枝：x 投影不重叠的线段对不可能相交，
    其 _seg_intersect 结果恒为 False，故剪枝不改变判定结果，仅把
    典型场景的复杂度从 O(n^2) 降到近 O(n log n)（全长跨越型线段为最坏情形）。
    """
    pts = [(p["x"], p["y"]) for p in points]
    n = len(pts)
    if n < 4:
        return False
    segs = [(pts[i], pts[(i + 1) % n]) for i in range(n)]

    def _adjacent(i, j):
        return j == i or (j + 1) % n == i or (i + 1) % n == j

    found = None  # None=未判定（走完候选生成再下结论）
    if _HAS_SHAPELY and n >= 64 and all(a != b for a, b in segs):
        # 空间索引生成候选对：STRtree 的 intersects 是真交集的超集，
        # 最终仍由 _seg_intersect 判定，故结果与全对枚举一致，仅候选集大幅缩小。
        try:
            from shapely.geometry import LineString as _LS
            from shapely.strtree import STRtree as _STRtree
            lines = [_LS([a, b]) for a, b in segs]
            pairs = _STRtree(lines).query(lines, predicate="intersects")
            found = False
            for i, j in zip(pairs[0].tolist(), pairs[1].tolist()):
                if i == j or _adjacent(i, j):
                    continue
                if _seg_intersect(*segs[i], *segs[j]):
                    found = True
                    break
        except Exception:  # noqa: BLE001 索引异常时回退扫描线
            found = None
    if found is None:
        # 扫描线回退：x 投影不重叠（或 y 投影不重叠）的线段对不可能相交，
        # 其 _seg_intersect 恒为 False，剪枝不改变判定结果。
        boxes = [(min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1]))
                 for a, b in segs]
        order = sorted(range(n), key=lambda i: boxes[i][0])
        active = []  # (maxx, miny, maxy, seg_idx)
        found = False
        for i in order:
            minx_i, _maxx_i, miny_i, maxy_i = boxes[i]
            active = [t for t in active if t[0] >= minx_i]
            for _mx, mny, mxy, j in active:
                if _adjacent(i, j) or max(miny_i, mny) > min(maxy_i, mxy):
                    continue
                if _seg_intersect(*segs[i], *segs[j]):
                    found = True
                    break
            if found:
                break
            active.append((boxes[i][1], miny_i, maxy_i, i))
    if found:
        return True
    if _HAS_SHAPELY:
        poly = _ShpPolygon(pts)
        return not poly.is_valid and not poly.is_simple if hasattr(poly, "is_simple") else not poly.is_valid
    return False


def closure_warning(relative_closure, closure=None):
    """闭合差超限口径：相对闭合差低于界址点测量常用要求 1/2000 时给出
    中文警告文案，合格返回 None。供 Web/API 展示层统一调用。"""
    if relative_closure is None:
        return None
    try:
        rel = float(relative_closure)
    except (TypeError, ValueError):
        return None
    if rel == float("inf") or rel >= 2000:
        return None
    detail = f"，闭合差 {closure:.3f} 米" if closure is not None else ""
    return (f"警告：闭合差超限（相对闭合差约 1/{rel:.0f}{detail}），低于常用要求 "
            "1/2000：方位角或边长很可能录入有误，平差结果仅供参考，请逐边核对原始记录。")


def validate_polygon(points):
    """校验：点数、闭合（首尾若重复给出提示）、点号/点位重复、自交。返回 dict。"""
    pts = list(points)
    warnings = []
    closed_duplicate = False
    if len(pts) >= 2 and abs(pts[0]["x"] - pts[-1]["x"]) < 1e-9 and abs(pts[0]["y"] - pts[-1]["y"]) < 1e-9:
        closed_duplicate = True
        pts = pts[:-1]
        warnings.append("首尾点重复，已按闭合处理（内部去除重复尾点）")
    names = [p.get("name") for p in pts]
    dup_names = sorted({n for n in names if n and names.count(n) > 1})
    if dup_names:
        warnings.append("警告：点号重复（{}），界址点表与四至引用会含糊，请改名后重录。".format(
            "、".join(dup_names)))
    seen_at = {}
    for i, p in enumerate(pts):
        key = (round(float(p["x"]), 9), round(float(p["y"]), 9))
        if key in seen_at:
            j = seen_at[key]
            if j == i - 1:
                warnings.append(f"警告：第 {j + 1} 与第 {i + 1} 点坐标完全重合（零长边），"
                                "请核对是否多录了一行。")
            else:
                warnings.append(f"警告：第 {j + 1} 与第 {i + 1} 点坐标重合（非相邻点重位），"
                                "多边形可能退化，请核对原始记录。")
        else:
            seen_at[key] = i
    selfx = has_self_intersection(pts) if len(pts) >= 4 else False
    if selfx:
        warnings.append("警告：多边形自交（蝴蝶结形），面积与成果不可直接使用，须人工核校")
    return {"point_count": len(pts), "closed_duplicate": closed_duplicate,
            "self_intersecting": selfx, "warnings": warnings, "points": pts}


def traverse(edges, start=(0.0, 0.0), start_name=None):
    """由边序列做导线计算。
    edges: [{from,to,azimuth_deg,distance}]
    返回 {points（未平差，含终点）, fx, fy, closure（闭合差长度）,
          relative_closure（相对闭合差 1/N 的 N，完美闭合为 inf）,
          total_distance, end_name}"""
    x, y = float(start[0]), float(start[1])
    name = start_name or (edges[0]["from"] if edges else "J1")
    points = [{"name": name, "x": x, "y": y}]
    total = 0.0
    for e in edges:
        az = math.radians(e["azimuth_deg"])
        dx = e["distance"] * math.sin(az)
        dy = e["distance"] * math.cos(az)
        x, y = x + dx, y + dy
        total += e["distance"]
        points.append({"name": e["to"], "x": x, "y": y})
    # 闭合差：终点应回到起点（闭合导线）
    fx = points[-1]["x"] - points[0]["x"]
    fy = points[-1]["y"] - points[0]["y"]
    closure = math.hypot(fx, fy)
    rel = (total / closure) if closure > 1e-12 else float("inf")
    return {"points": points, "fx": fx, "fy": fy, "closure": closure,
            "relative_closure": rel, "total_distance": total,
            "end_name": points[-1]["name"]}


def bowditch_adjust(edges, start=(0.0, 0.0), start_name=None):
    """Bowditch（罗盘）法则平差：闭合差按边长比例反号分配。
    返回 {points（平差后，不含重复终点）, raw: traverse 结果, fx, fy, ...}"""
    raw = traverse(edges, start, start_name)
    fx, fy, total = raw["fx"], raw["fy"], raw["total_distance"]
    x, y = float(start[0]), float(start[1])
    name = start_name or (edges[0]["from"] if edges else "J1")
    points = [{"name": name, "x": x, "y": y}]
    cum = 0.0
    run_x = run_y = 0.0  # 前缀和增量累加（加法顺序与逐边重算 sum() 一致，结果逐位相同）
    for i, e in enumerate(edges):
        az = math.radians(e["azimuth_deg"])
        cum += e["distance"]
        run_x += e["distance"] * math.sin(az)
        run_y += e["distance"] * math.cos(az)
        nx = points[0]["x"] + run_x
        ny = points[0]["y"] + run_y
        if total > 0:
            nx -= fx * (cum / total)
            ny -= fy * (cum / total)
        if i < len(edges) - 1:
            points.append({"name": e["to"], "x": nx, "y": ny})
        else:
            # 末点应与起点重合，平差后强制闭合
            points[-1]  # noqa
    return {"points": points, "raw_points": raw["points"], "fx": fx, "fy": fy,
            "closure": raw["closure"], "relative_closure": raw["relative_closure"],
            "total_distance": total}
