"""RDB ParcelMap 无头测试： .venv/bin/python -m pytest tests/ -q 或直接运行本文件。"""
import json
import math
import os
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import exporters, geometry, parsers, traverse  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
SQ = [{"name": f"J{i+1}", "x": x, "y": y}
      for i, (x, y) in enumerate([(500, 500), (600, 500), (600, 600), (500, 600)])]


def test_coords_variants():
    a = parsers.parse_coordinate_string("J1,500,500\nJ2,600,500\nJ3,600,600\nJ4,500,600")
    assert len(a) == 4 and a[1]["x"] == 600 and a[1]["name"] == "J2"
    b = parsers.parse_coordinate_string("500,500;600,500;600,600;500,600")
    assert len(b) == 4 and b[2]["y"] == 600
    c = parsers.parse_coordinate_string("500 500 600 500 600 600 500 600")
    assert len(c) == 4
    d = parsers.parse_coordinate_string("500,500\n500,600\n600,600\n600,500", order="yx")
    assert d[0]["x"] == 500 and d[0]["y"] == 500 and d[1]["x"] == 600 and d[1]["y"] == 500
    e = parsers.parse_coordinate_string("J1：500，500\nJ2：600，500", order="xy")
    assert len(e) == 2 and e[0]["name"] == "J1"


def test_band_prefix():
    assert parsers.detect_band("39500500.0,500.0") == 39
    pts = parsers.parse_coordinate_string("J1,39500500.00,500.00\nJ2,39500600.00,500.00", strip_band=True)
    assert pts[0]["x"] == 500500.00, pts


def test_csv_fixtures():
    with open(os.path.join(HERE, "fixtures", "points.csv"), encoding="utf-8") as f:
        pts = parsers.parse_csv(f.read())
    assert len(pts) == 4 and pts[2]["x"] == 600 and pts[2]["y"] == 600
    with open(os.path.join(HERE, "fixtures", "points_latlon.csv"), encoding="utf-8") as f:
        ll = parsers.parse_csv(f.read())
    assert ll[0]["x"] == 114.0 and ll[0]["y"] == 30.0  # x=经度, y=纬度


def test_dxf_fixture():
    with open(os.path.join(HERE, "fixtures", "parcel.dxf"), encoding="utf-8") as f:
        d = parsers.parse_dxf(f.read())
    assert len(d["polylines"]) == 1 and len(d["polylines"][0]) == 4
    assert d["polylines"][0][1] == {"name": "J2", "x": 600.0, "y": 500.0}
    assert len(d["points"]) == 1 and d["points"][0]["x"] == 550.0


def test_edge_text_and_traverse():
    text = open(os.path.join(ROOT, "examples", "example2_edges.txt"), encoding="utf-8").read()
    edges = parsers.parse_edge_text(text)
    assert len(edges) == 4
    raw = traverse.traverse(edges)
    assert abs(raw["fx"] - 0.05) < 1e-9, raw["fx"]
    assert abs(raw["fy"] - (-0.10)) < 1e-9, raw["fy"]
    assert abs(raw["closure"] - math.hypot(0.05, 0.10)) < 1e-9
    adj = traverse.bowditch_adjust(edges)
    # 平差后由平差点列+起点构成的闭合环应闭合：末边回到起点
    ring = adj["points"]
    last_edge_end = traverse.traverse(
        [{"from": ring[-1]["name"], "to": ring[0]["name"],
          "azimuth_deg": geometry.azimuth_of(ring[-1], ring[0]),
          "distance": math.hypot(ring[0]["x"] - ring[-1]["x"], ring[0]["y"] - ring[-1]["y"])}],
        start=(ring[-1]["x"], ring[-1]["y"]))
    assert abs(last_edge_end["points"][-1]["x"] - ring[0]["x"]) < 1e-9
    # 平差终点（原始导线终点经平差）与起点之差 ≈ 0：用 raw 平差定义验证
    assert abs(adj["points"][0]["x"]) < 1e-12 and abs(adj["points"][0]["y"]) < 1e-12
    assert 9000 < geometry.area(ring) < 11000


def test_edge_text_variants():
    e1 = parsers.parse_edge_text("J1-J2：北偏东30°，长25米")
    assert len(e1) == 1 and abs(e1[0]["azimuth_deg"] - 30) < 1e-9 and e1[0]["distance"] == 25
    e2 = parsers.parse_edge_text("J1→J2 方位角 45°30′20″ 距离 32.15 米")
    assert abs(e2[0]["azimuth_deg"] - (45 + 30 / 60 + 20 / 3600)) < 1e-9
    e3 = parsers.parse_edge_text("J2→J3 东北 方向 距离 10 米")
    assert abs(e3[0]["azimuth_deg"] - 45) < 1e-9
    e4 = parsers.parse_english_description("From J1 to J2 bearing N30°E distance 100 ft")
    assert abs(e4[0]["azimuth_deg"] - 30) < 1e-9 and abs(e4[0]["distance"] - 30.48) < 1e-9


def test_sizhi():
    text = open(os.path.join(ROOT, "examples", "example3_sizhi.txt"), encoding="utf-8").read()
    sz = parsers.parse_sizhi_text(text)
    assert sz["east"] == "张三承包地" and sz["south"] == "村道"
    assert sz["west"] == "排水沟" and sz["north"] == "李四宅基地"
    assert sz["lengths"] == {"east": 100.0, "south": 100.0, "west": 100.0, "north": 100.0}


def test_geometry_square():
    au = geometry.area_units(SQ)
    assert abs(au["m2"] - 10000) < 1e-9
    assert abs(au["mu"] - 15.0) < 1e-3
    assert abs(au["hectare"] - 1.0) < 1e-9
    assert abs(geometry.perimeter(SQ) - 400) < 1e-9
    t = geometry.boundary_table(SQ)
    assert len(t) == 4 and abs(t[0]["azimuth_deg"] - 90) < 1e-9 and abs(t[0]["length"] - 100) < 1e-9


def test_self_intersection():
    bow = [{"name": f"J{i+1}", "x": x, "y": y}
           for i, (x, y) in enumerate([(0, 0), (100, 100), (100, 0), (0, 100)])]
    v = traverse.validate_polygon(bow)
    assert v["self_intersecting"] is True and v["warnings"]
    assert traverse.validate_polygon(SQ)["self_intersecting"] is False


def test_exports_roundtrip(tmp_path=None):
    import tempfile
    td = tempfile.mkdtemp()
    gj = os.path.join(td, "p.geojson")
    exporters.export_geojson(SQ, gj)
    data = json.load(open(gj, encoding="utf-8"))
    ring = data["features"][0]["geometry"]["coordinates"][0]
    assert ring[0] == [500, 500] and ring[2] == [600, 600] and ring[0] == ring[-1]
    for crs in ("CGCS2000", "WGS84"):
        zp = os.path.join(td, f"p_{crs}.zip")
        exporters.export_shapefile_zip(SQ, zp, crs_name=crs)
        with zipfile.ZipFile(zp) as z:
            names = z.namelist()
            assert any(n.endswith(".shp") for n in names) and any(n.endswith(".prj") for n in names)
            import shapefile as shp_mod
            r = shp_mod.Reader(shp=io_bytes(z, ".shp"), shx=io_bytes(z, ".shx"), dbf=io_bytes(z, ".dbf"))
            pts = r.shapes()[0].points
            assert abs(pts[0][0] - 500) < 1e-9 and abs(pts[2][0] - 600) < 1e-9
    pdf = os.path.join(td, "p.pdf")
    _, note = exporters.export_pdf(SQ, pdf, sizhi=parsers.parse_sizhi_text(
        open(os.path.join(ROOT, "examples", "example3_sizhi.txt"), encoding="utf-8").read()))
    assert os.path.getsize(pdf) > 1000
    import re
    raw = open(pdf, "rb").read()
    assert len(re.findall(rb"/Type\s*/Page[^s]", raw)) >= 1
    print("PDF font:", note)


def io_bytes(zf, ext):
    import io as _io
    name = [n for n in zf.namelist() if n.endswith(ext)][0]
    return _io.BytesIO(zf.read(name))


def test_api_smoke():
    sys.path.insert(0, os.path.join(ROOT, "web"))
    import app as webapp
    client = webapp.app.test_client()
    assert client.get("/api/health").json["ok"] is True
    r = client.post("/api/parse", json={"kind": "coords",
                                        "text": "J1,500,500\nJ2,600,500\nJ3,600,600\nJ4,500,600"})
    assert r.status_code == 200
    assert abs(r.json["summary"]["area_m2"] - 10000) < 1e-6
    r2 = client.post("/api/export/geojson", json={"points": SQ})
    assert r2.json["features"][0]["geometry"]["type"] == "Polygon"
    from core import license as lic
    code = lic.issue_license("tester@example.com", plan="permanent")
    r3 = client.post("/api/export/pdf", json={"points": SQ}, headers={"X-License": code})
    assert r3.status_code == 200 and len(r3.data) > 1000


def test_license_issue_verify():
    from datetime import date
    from core import license as lic
    code = lic.issue_license("buyer@example.com", plan="monthly", days=30)
    assert code.startswith("RDBPM-")
    v = lic.verify_license(code)
    assert v["valid"] is True and v["plan"] == "monthly" and v["email"] == "buyer@example.com"
    assert v["expires"] and v["expires"] > date.today().isoformat()


def test_license_tamper():
    from core import license as lic
    code = lic.issue_license("buyer@example.com", plan="monthly", days=30)
    body = code[len("RDBPM-"):].replace("-", "")
    flipped = ("A" if body[5] != "A" else "B")
    bad = "RDBPM-" + body[:5] + flipped + body[6:]
    assert lic.verify_license(bad)["valid"] is False
    assert lic.verify_license("")["valid"] is False
    assert lic.verify_license("RDBPM-AAAA")["valid"] is False
    assert lic.verify_license(code, secret="another-secret")["valid"] is False


def test_license_expiry_and_permanent():
    from datetime import date, timedelta
    from core import license as lic
    code = lic.issue_license("old@example.com", plan="monthly", days=30,
                             today=date(2026, 1, 1))
    assert lic.verify_license(code, today=date(2026, 1, 31))["valid"] is True
    v = lic.verify_license(code, today=date(2026, 2, 1))
    assert v["valid"] is False and "过期" in v["reason"]
    perm = lic.issue_license("perm@example.com", plan="permanent")
    far = date.today() + timedelta(days=36500)
    v2 = lic.verify_license(perm, today=far)
    assert v2["valid"] is True and v2["plan"] == "permanent" and v2["expires"] is None


def test_export_gating():
    sys.path.insert(0, os.path.join(ROOT, "web"))
    import app as webapp
    from core import license as lic
    client = webapp.app.test_client()
    for fmt in ("shp", "pdf"):
        r = client.post(f"/api/export/{fmt}", json={"points": SQ})
        assert r.status_code == 403, (fmt, r.status_code)
        assert "Pro" in r.json["error"]
        r_bad = client.post(f"/api/export/{fmt}", json={"points": SQ, "license": "RDBPM-AAAA-BBBB"})
        assert r_bad.status_code == 403
    # GeoJSON 免费不限
    assert client.post("/api/export/geojson", json={"points": SQ}).status_code == 200
    perm = lic.issue_license("perm@example.com", plan="permanent")
    r = client.post("/api/export/shp", json={"points": SQ}, headers={"X-License": perm})
    assert r.status_code == 200 and len(r.data) > 100
    r = client.post("/api/export/pdf", json={"points": SQ, "license": perm})
    assert r.status_code == 200 and len(r.data) > 1000
    monthly = lic.issue_license("m@example.com", plan="monthly", days=30)
    assert client.post("/api/export/pdf", json={"points": SQ}, headers={"X-License": monthly}).status_code == 200
    v = client.post("/api/license/verify", json={"license": perm})
    assert v.json["valid"] is True and v.json["plan"] == "permanent"


# ---------------------------------------------------------------- 第 2 轮新增：四系投影 / PDF 分页

def _pdf_pages_text(path):
    """无第三方库提取 PDF 页数与文本：解 ASCII85+Flate 内容流，取 Tj 字符串
    按 UTF-16BE 解码（reportlab CID 字体口径）。返回 (页数, 文本)。"""
    import base64
    import re as _re
    import zlib as _zlib
    raw = open(path, "rb").read()
    pages = len(_re.findall(rb"/Type\s*/Page[^s]", raw))
    texts = []
    for m in _re.finditer(rb"stream\r?\n(.*?)endstream", raw, _re.S):
        data = m.group(1)
        try:
            data = _zlib.decompress(base64.a85decode(data, adobe=True))
        except Exception:
            try:
                data = _zlib.decompress(data)
            except Exception:
                continue
        for sm in _re.finditer(rb"\((?:\\.|[^\\()])*\)\s*Tj", data):
            inner = sm.group(0)[1:sm.group(0).rindex(b")")]
            out = bytearray()
            i = 0
            while i < len(inner):
                if inner[i:i + 1] == b"\\" and i + 1 < len(inner):
                    nxt = inner[i + 1:i + 2]
                    if nxt.isdigit():
                        j = i + 1
                        while j < len(inner) and inner[j:j + 1].isdigit() and j < i + 4:
                            j += 1
                        out.append(int(inner[i + 1:j], 8))
                        i = j
                        continue
                    out.extend(nxt)
                    i += 2
                    continue
                out.append(inner[i])
                i += 1
            texts.append(bytes(out).decode("utf-16-be", "ignore"))
    return pages, "\n".join(texts)


def _circle_points(n, cx=500.0, cy=500.0, r=300.0):
    return [{"name": f"J{i+1}",
             "x": cx + r * math.cos(2 * math.pi * i / n),
             "y": cy + r * math.sin(2 * math.pi * i / n)} for i in range(n)]


def test_projection_ellipsoid_params():
    from core import projection as P
    exp = {"CGCS2000": (6378137.0, 298.257222101), "WGS84": (6378137.0, 298.257223563),
           "XIAN80": (6378140.0, 298.257), "BEIJING54": (6378245.0, 298.3)}
    for name, (a, inv_f) in exp.items():
        e = P.ellipsoid(name)
        assert e["a"] == a and e["inv_f"] == inv_f, (name, e)


def test_projection_aliases():
    from core import projection as P
    assert P.normalize_crs("西安80") == "XIAN80"
    assert P.normalize_crs("IAG75") == "XIAN80"
    assert P.normalize_crs("北京54") == "BEIJING54"
    assert P.normalize_crs("克拉索夫斯基") == "BEIJING54"
    assert P.normalize_crs("WGS 84") == "WGS84"
    assert P.normalize_crs("不存在的系") is None


def test_gauss_roundtrip_cgcs2000():
    """正反算往返精度：平面往返误差容差 ≤1mm（0.001 m）。"""
    from core import projection as P
    for lat, lon in [(30.0, 114.0), (22.5, 108.7), (39.9, 116.4), (45.0, 125.0)]:
        zone = P.zone_from_lon(lon, 3)
        x, y = P.gauss_forward(lat, lon, "CGCS2000", 3, zone=zone)
        la, lo = P.gauss_inverse(x, y, "CGCS2000", 3, zone=zone)
        x2, y2 = P.gauss_forward(la, lo, "CGCS2000", 3, zone=zone)
        assert math.hypot(x2 - x, y2 - y) <= 0.001, (lat, lon, x2 - x, y2 - y)
        assert abs(la - lat) < 1e-9 and abs(lo - lon) < 1e-9


def test_gauss_roundtrip_four_systems():
    """四系 × 3/6 度带往返精度，容差 ≤1mm。"""
    from core import projection as P
    for crs in ("CGCS2000", "WGS84", "XIAN80", "BEIJING54"):
        for zw in (3, 6):
            for lat, lon in [(30.0, 114.0), (18.2, 109.8), (34.0, 113.9)]:
                zone = P.zone_from_lon(lon, zw)
                x, y = P.gauss_forward(lat, lon, crs, zw, zone=zone)
                la, lo = P.gauss_inverse(x, y, crs, zw, zone=zone)
                x2, y2 = P.gauss_forward(la, lo, crs, zw, zone=zone)
                assert math.hypot(x2 - x, y2 - y) <= 0.001, (crs, zw, lat, lon)


def test_gauss_central_meridian_and_equator():
    from core import projection as P
    # 中央经线（39 带 = 117°E）上东坐标 = 带号*1e6 + 500000；赤道北坐标 = 0
    x, y = P.gauss_forward(30.0, 117.0, "CGCS2000", 3)
    assert abs(x - 39500000.0) < 1e-6 and y > 0
    x0, y0 = P.gauss_forward(0.0, 117.0, "CGCS2000", 3)
    assert abs(y0) < 1e-9
    assert P.central_meridian(39, 3) == 117.0 and P.central_meridian(20, 6) == 117.0
    assert P.zone_from_lon(114.0, 3) == 38 and P.zone_from_lon(114.0, 6) == 20


def test_zone_detection_consistency_with_parsers():
    """带号识别/剥离口径与 parsers 既有逻辑一致。"""
    from core import projection as P
    assert P.detect_zone(39500500.0, 3) == 39 == parsers.detect_band("39500500.0,500.0")
    assert P.strip_zone(39500500.0, 3) == (500500.0, 39)
    v, band = parsers.strip_band_prefix(39500500.0, "x", True)
    assert v == 500500.0 and band == 39
    assert P.detect_zone(500500.0, 3) is None  # 无前缀不误判
    la, lo = P.plane_to_latlon(39500000.0, 3320113.398, "CGCS2000", 3)
    assert abs(lo - 117.0) < 1e-6 and abs(la - 30.0) < 1e-5
    # 39500500 剥带后横坐标 500500，即中央经线以东 500 m，经度应约为 117.0052°
    la2, lo2 = P.plane_to_latlon(39500500.0, 3320113.398, "CGCS2000", 3)
    assert abs(lo2 - 117.00518208) < 1e-6 and abs(la2 - 30.0) < 1e-5


def test_cross_ellipsoid_magnitudes():
    """同点跨椭球平面差量级：CGCS2000↔WGS84 不超厘米级（实测亚毫米），
    ↔西安80 米级、↔北京54 十米级。"""
    from core import projection as P
    lat, lon = 30.0, 114.0
    base = {c: P.gauss_forward(lat, lon, c, 3) for c in
            ("CGCS2000", "WGS84", "XIAN80", "BEIJING54")}
    d_wgs = math.hypot(base["WGS84"][0] - base["CGCS2000"][0],
                       base["WGS84"][1] - base["CGCS2000"][1])
    assert 0 < d_wgs < 0.01, d_wgs
    d_xa = math.hypot(base["XIAN80"][0] - base["CGCS2000"][0],
                      base["XIAN80"][1] - base["CGCS2000"][1])
    assert 0.5 < d_xa < 10, d_xa
    d_bj = math.hypot(base["BEIJING54"][0] - base["CGCS2000"][0],
                      base["BEIJING54"][1] - base["CGCS2000"][1])
    assert 10 < d_bj < 200, d_bj


def test_convert_plane_note_beijing54():
    from core import projection as P
    x, y = P.gauss_forward(30.0, 114.0, "CGCS2000", 3)
    r = P.convert_plane(x, y, "CGCS2000", "BEIJING54")
    assert "未含地方七参数改正" in r["note"] and "仅供概算" in r["note"]
    dx, dy = P.gauss_forward(30.0, 114.0, "BEIJING54", 3)
    assert math.hypot(r["x"] - dx, r["y"] - dy) < 1e-6  # 经纬度中间量与直算一致
    assert abs(r["lat"] - 30.0) < 1e-9 and abs(r["lon"] - 114.0) < 1e-9


def test_convert_note_xian80_and_same_crs():
    from core import projection as P
    assert "未含地方七参数改正" in P.conversion_note("XIAN80", "CGCS2000")
    assert "未含地方七参数改正" in P.conversion_note("CGCS2000", "北京54")
    assert P.conversion_note("CGCS2000", "CGCS2000") == ""
    n = P.conversion_note("CGCS2000", "WGS84")
    assert "七参数" not in n or "未做七参数" in n  # 一般跨系只有中间量说明


def test_convert_points_latlon_and_plane():
    from core import projection as P
    pts, note = P.convert_points(
        [{"name": "J1", "x": 114.0, "y": 30.0}], "WGS84", "CGCS2000",
        input_kind="latlon")
    dx, dy = P.gauss_forward(30.0, 114.0, "CGCS2000", 3)
    assert pts[0]["name"] == "J1" and math.hypot(pts[0]["x"] - dx, pts[0]["y"] - dy) < 1e-9
    src = [{"name": f"J{i+1}", "x": x, "y": y} for i, (x, y) in enumerate(
        P.gauss_forward(30.0 + k * 0.001, 114.0, "CGCS2000", 3) for k in range(3))]
    out, note2 = P.convert_points(src, "CGCS2000", "XIAN80")
    assert "未含地方七参数改正" in note2 and len(out) == 3 and out[2]["name"] == "J3"


def test_prj_four_systems():
    import tempfile
    from core import exporters as E
    td = tempfile.mkdtemp()
    expect = {"CGCS2000": ("CGCS2000", "6378137.0,298.257222101"),
              "WGS84": ("WGS 84", "6378137.0,298.257223563"),
              "XIAN80": ("IAG 1975", "6378140.0,298.257"),
              "BEIJING54": ("Krassowsky 1940", "6378245.0,298.3")}
    for crs, (sph, params) in expect.items():
        zp = os.path.join(td, f"p_{crs}.zip")
        E.export_shapefile_zip(SQ, zp, crs_name=crs)
        with zipfile.ZipFile(zp) as z:
            prj = z.read([n for n in z.namelist() if n.endswith(".prj")][0]).decode("utf-8")
        assert sph in prj and params in prj, (crs, prj)
    assert set(E.PRJ) == {"CGCS2000", "WGS84", "XIAN80", "BEIJING54"}


def test_prj_alias_chinese_names():
    import tempfile
    from core import exporters as E
    td = tempfile.mkdtemp()
    for alias, sph in (("西安80", "IAG 1975"), ("北京54", "Krassowsky 1940")):
        zp = os.path.join(td, "alias.zip")
        E.export_shapefile_zip(SQ, zp, crs_name=alias)
        with zipfile.ZipFile(zp) as z:
            prj = z.read([n for n in z.namelist() if n.endswith(".prj")][0]).decode("utf-8")
        assert sph in prj, (alias, prj)
    gj = E.to_geojson(SQ, crs_name="西安80")
    assert gj["crs"]["properties"]["name"] == "XIAN80"


def test_pdf_pagination_100_points():
    """100 个界址点：页数 >1 且坐标表点号齐全、不丢行。"""
    import re as _re
    import tempfile
    td = tempfile.mkdtemp()
    pdf = os.path.join(td, "p100.pdf")
    exporters.export_pdf(_circle_points(100), pdf)
    pages, text = _pdf_pages_text(pdf)
    assert pages > 1, pages
    for i in range(100):
        assert _re.search(rf"J{i+1}(?!\d)", text), f"缺 J{i+1}"
    assert "界址点坐标表" in text and "（续）" in text  # 续页表头重复
    assert "第 1 页" in text and f"共 {pages} 页" in text  # 页码
    assert "不作为测绘资质成果" in text  # 免责声明保留


def test_pdf_pagination_40_points_no_missing():
    import re as _re
    import tempfile
    td = tempfile.mkdtemp()
    pdf = os.path.join(td, "p40.pdf")
    exporters.export_pdf(_circle_points(40), pdf)
    pages, text = _pdf_pages_text(pdf)
    assert pages >= 2
    for i in range(40):
        assert _re.search(rf"J{i+1}(?!\d)", text), f"缺 J{i+1}"
    assert "四至" in text and "面积" in text  # 文末块未丢


def test_pdf_small_parcel_single_page():
    """原有样例回归：4 点小宗地仍为单页，内容齐全。"""
    import tempfile
    td = tempfile.mkdtemp()
    pdf = os.path.join(td, "small.pdf")
    exporters.export_pdf(SQ, pdf, sizhi=parsers.parse_sizhi_text(
        open(os.path.join(ROOT, "examples", "example3_sizhi.txt"), encoding="utf-8").read()))
    pages, text = _pdf_pages_text(pdf)
    assert pages == 1, pages
    for name in ("J1", "J2", "J3", "J4"):
        assert name in text
    assert "四至" in text and "张三承包地" in text and "第 1 页 / 共 1 页" in text


def test_api_convert_endpoint():
    sys.path.insert(0, os.path.join(ROOT, "web"))
    import app as webapp
    from core import projection as P
    client = webapp.app.test_client()
    x, y = P.gauss_forward(30.0, 114.0, "CGCS2000", 3)
    r = client.post("/api/convert", json={
        "points": [{"name": "J1", "x": x, "y": y}],
        "src_crs": "CGCS2000", "dst_crs": "BEIJING54"})
    assert r.status_code == 200, r.data
    assert "未含地方七参数改正" in r.json["note"] and "仅供概算" in r.json["note"]
    dx, dy = P.gauss_forward(30.0, 114.0, "BEIJING54", 3)
    assert math.hypot(r.json["points"][0]["x"] - dx, r.json["points"][0]["y"] - dy) < 1e-6
    r2 = client.post("/api/convert", json={
        "points": [{"name": "J1", "x": 114.0, "y": 30.0}],
        "src_crs": "WGS84", "dst_crs": "XIAN80", "input": "latlon"})
    assert r2.status_code == 200 and r2.json["dst_crs"] == "XIAN80"
    r3 = client.post("/api/convert", json={
        "points": [{"name": "J1", "x": 1, "y": 2}], "src_crs": "火星系", "dst_crs": "CGCS2000"})
    assert r3.status_code == 400


def test_api_export_shp_four_crs_prj():
    sys.path.insert(0, os.path.join(ROOT, "web"))
    import app as webapp
    from core import license as lic
    client = webapp.app.test_client()
    perm = lic.issue_license("perm@example.com", plan="permanent")
    for crs, sph in (("XIAN80", "IAG 1975"), ("BEIJING54", "Krassowsky 1940")):
        r = client.post("/api/export/shp", json={"points": SQ, "crs": crs},
                        headers={"X-License": perm})
        assert r.status_code == 200, (crs, r.status_code)
        import io as _io
        with zipfile.ZipFile(_io.BytesIO(r.data)) as z:
            prj = z.read([n for n in z.namelist() if n.endswith(".prj")][0]).decode("utf-8")
        assert sph in prj, (crs, prj)
    # 免费口径不变：无授权 SHP 仍 403、GeoJSON 仍免费
    assert client.post("/api/export/shp", json={"points": SQ, "crs": "XIAN80"}).status_code == 403
    assert client.post("/api/export/geojson", json={"points": SQ, "crs": "XIAN80"}).status_code == 200


def test_boundaries_scientific_notation_coords():
    # 第 3 轮：科学计数法坐标不得被静默误解析（旧实现 1e5 -> (1, 5)）
    pts = parsers.parse_coordinate_string("1e5,2e5\n3e5,4e5")
    assert pts[0]["x"] == 100000.0 and pts[0]["y"] == 200000.0, pts
    assert pts[1]["x"] == 300000.0 and pts[1]["y"] == 400000.0, pts


def test_boundaries_dxf_malformed_numbers_skipped():
    bad = ("0\nSECTION\n2\nENTITIES\n0\nLWPOLYLINE\n10\nabc\n20\n5.0\n"
           "10\n6.0\n20\n7.0\n0\nENDSEC\n0\nEOF\n")
    d = parsers.parse_dxf(bad)  # 不裸崩；坏值跳过、好值保留
    assert isinstance(d, dict) and "polylines" in d


def test_boundaries_edge_garbage_and_nonpositive():
    # 偏角写坏的一行不再穿透整表解析；负/零距离的边不收
    assert parsers.parse_edge_text("J1→J2 北偏东abc 长25米") == []
    assert parsers.parse_edge_text("J1→J2 方位角 45° 距离 -25 米") == []
    assert parsers.parse_edge_text("J1→J2 方位角 45° 距离 0 米") == []
    ok = parsers.parse_edge_text("J1→J2 北偏东30° 长25米\nJ2→J3 方位角 90° 距离 25 米")
    assert len(ok) == 2 and abs(ok[0]["azimuth_deg"] - 30) < 1e-9
    try:
        parsers.parse_angle("abc")
        raise AssertionError("应抛 ValueError")
    except ValueError as e:
        assert "无法解析角度" in str(e)


def test_boundaries_validate_duplicate_warnings():
    dup_name = [{"name": "J1", "x": 500, "y": 500}, {"name": "J1", "x": 600, "y": 500},
                {"name": "J3", "x": 600, "y": 600}, {"name": "J4", "x": 500, "y": 600}]
    w = traverse.validate_polygon(dup_name)["warnings"]
    assert any("点号重复" in x for x in w), w
    dup_pt = [{"name": f"J{i+1}", "x": x, "y": y} for i, (x, y) in
              enumerate([(500, 500), (500, 500), (600, 500), (600, 600)])]
    w = traverse.validate_polygon(dup_pt)["warnings"]
    assert any("零长边" in x for x in w), w


def test_boundaries_geometry_empty_points():
    for fn in (geometry.centroid, geometry.bbox):
        try:
            fn([])
            raise AssertionError("空点列应抛 ValueError")
        except ValueError as e:
            assert "没有界址点" in str(e)


def test_boundaries_closure_warning_threshold():
    assert traverse.closure_warning(float("inf")) is None
    assert traverse.closure_warning(5000, 0.01) is None
    w = traverse.closure_warning(1.41, 282.8)
    assert w and "闭合差超限" in w and "1/2000" in w


def test_sizhi_generation_square_with_neighbors():
    from core import boundary_desc
    gen = boundary_desc.generate_sizhi(SQ, neighbors={
        "东": "张三地", "南": "村道", "西": "水沟", "北": "李四地"})
    assert "东至张三地" in gen["text"] and "南至村道" in gen["text"], gen["text"]
    assert "西至水沟" in gen["text"] and "北至李四地" in gen["text"], gen["text"]
    assert gen["sizhi4"] == {"east": "张三地", "south": "村道",
                             "west": "水沟", "north": "李四地"}, gen["sizhi4"]
    assert len(gen["segments"]) == 4
    assert all(abs(s["length_m"] - 100.0) < 1e-6 for s in gen["segments"])
    assert "人工核校" in gen["note"]


def test_sizhi_generation_diamond_corners():
    from core import boundary_desc
    diamond = [{"name": f"J{i+1}", "x": x, "y": y} for i, (x, y) in
               enumerate([(550, 450), (650, 550), (550, 650), (450, 550)])]
    gen = boundary_desc.generate_sizhi(diamond, neighbors={"东南": "河道"})
    sectors = {s["sector"] for s in gen["segments"]}
    assert sectors == {"东南", "东北", "西北", "西南"}, sectors
    assert "东南至河道" in gen["text"], gen["text"]
    # 角扇区顶替口径：四方向都有名称（占位或顶替），不缺项
    assert all(gen["sizhi4"][k] for k in ("east", "south", "west", "north"))
    assert gen["sizhi4"]["east"] == "河道" or gen["sizhi4"]["south"] == "河道"


def test_sizhi_generation_placeholder_and_min_points():
    from core import boundary_desc
    gen = boundary_desc.generate_sizhi(SQ)
    assert "相邻地块（名称待填）" in gen["text"]
    try:
        boundary_desc.generate_sizhi(SQ[:2])
        raise AssertionError("应抛 ValueError")
    except ValueError as e:
        assert "3 个" in str(e)


def test_registration_table_square():
    from core import boundary_desc
    reg = boundary_desc.registration_table(SQ)
    assert len(reg["rows"]) == 4
    az = [r["azimuth_deg"] for r in reg["rows"]]
    assert az == [90.0, 0.0, 270.0, 180.0], az
    assert reg["rows"][0]["azimuth_dms"] == "90°00′00″"
    assert abs(reg["totals"]["area_m2"] - 10000.0) < 1e-6
    assert abs(reg["totals"]["area_mu"] - 15.0) < 0.01
    assert abs(reg["totals"]["perimeter_m"] - 400.0) < 1e-6
    assert boundary_desc.format_dms(45.5080556).startswith("45°30′")


def test_api_parse_sizhi_registration_and_closure_warning():
    sys.path.insert(0, os.path.join(ROOT, "web"))
    import app as webapp
    client = webapp.app.test_client()
    r = client.post("/api/parse", json={
        "kind": "coords", "text": "500,500\n600,500\n600,600\n500,600"})
    assert r.status_code == 200, r.status_code
    d = r.get_json()
    assert "sizhi_generated" in d and "四至" in d["sizhi_generated"]["note"]
    assert d["registration"]["totals"]["area_m2"] == 10000.0
    r2 = client.post("/api/parse", json={
        "kind": "edges",
        "text": "J1→J2 方位角 90° 距离 100 米\nJ2→J3 方位角 180° 距离 100 米"})
    assert r2.status_code == 200, r2.status_code
    w = r2.get_json()["validation"]["warnings"]
    assert any("闭合差超限" in x for x in w), w


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print(f"全部 {len(fns)} 项测试通过")
