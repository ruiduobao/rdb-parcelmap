"""几何计算：面积（鞋带公式）/亩与公顷换算、周长、界址点表、重心、外包框。"""
import math

MU_PER_M2 = 1.0 / 666.6666667  # 1 亩 = 666.6667 ㎡


def signed_area(points):
    s = 0.0
    n = len(points)
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        s += a["x"] * b["y"] - b["x"] * a["y"]
    return s / 2.0


def area(points):
    return abs(signed_area(points))


def area_units(points):
    a = area(points)
    return {"m2": a, "mu": a * MU_PER_M2, "hectare": a / 10000.0}


def perimeter(points):
    n = len(points)
    return sum(math.hypot(points[(i + 1) % n]["x"] - points[i]["x"],
                          points[(i + 1) % n]["y"] - points[i]["y"]) for i in range(n))


def azimuth_of(p, q):
    """p->q 方位角（北起顺时针，度）。"""
    dx, dy = q["x"] - p["x"], q["y"] - p["y"]
    return math.degrees(math.atan2(dx, dy)) % 360


def boundary_table(points):
    """界址点表：逐边 点号/坐标/边长/方位角。"""
    rows = []
    n = len(points)
    for i in range(n):
        p, q = points[i], points[(i + 1) % n]
        rows.append({
            "from": p["name"], "to": q["name"],
            "x": p["x"], "y": p["y"],
            "length": math.hypot(q["x"] - p["x"], q["y"] - p["y"]),
            "azimuth_deg": azimuth_of(p, q),
        })
    return rows


def centroid(points):
    if not points:
        raise ValueError("没有界址点，无法计算重心。")
    a = signed_area(points)
    if abs(a) < 1e-12:
        return {"x": sum(p["x"] for p in points) / len(points),
                "y": sum(p["y"] for p in points) / len(points)}
    cx = cy = 0.0
    n = len(points)
    for i in range(n):
        p, q = points[i], points[(i + 1) % n]
        cr = p["x"] * q["y"] - q["x"] * p["y"]
        cx += (p["x"] + q["x"]) * cr
        cy += (p["y"] + q["y"]) * cr
    return {"x": cx / (6 * a), "y": cy / (6 * a)}


def bbox(points):
    if not points:
        raise ValueError("没有界址点，无法计算外包框。")
    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    return {"minx": min(xs), "miny": min(ys), "maxx": max(xs), "maxy": max(ys)}


def summary(points):
    au = area_units(points)
    return {"area_m2": au["m2"], "area_mu": au["mu"], "area_hectare": au["hectare"],
            "perimeter_m": perimeter(points), "centroid": centroid(points),
            "bbox": bbox(points), "boundary_table": boundary_table(points)}
