"""导出：GeoJSON / Shapefile(zip) / 界址图 PDF（reportlab）。

产品定位：辅助落图工具，成果须经人工核校，不作为测绘资质成果。
"""
import glob
import io
import json
import os
import zipfile

from . import geometry

DISCLAIMER = "辅助落图工具，成果须经人工核校，不作为测绘资质成果"
BRAND = "RDB ParcelMap · 锐多宝出品"
SLOGAN = "把四至文字，一键落到图上。"
SUPPORT_EMAIL = "caaschengrui@163.com"

PRJ_CGCS2000 = (
    'GEOGCS["China Geodetic Coordinate System 2000",'
    'DATUM["China_2000",SPHEROID["CGCS2000",6378137.0,298.257222101]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)
PRJ_WGS84 = (
    'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)
PRJ_XIAN80 = (
    'GEOGCS["Xian 1980",'
    'DATUM["Xian_1980",SPHEROID["IAG 1975",6378140.0,298.257]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)
PRJ_BEIJING54 = (
    'GEOGCS["Beijing 1954",'
    'DATUM["Beijing_1954",SPHEROID["Krassowsky 1940",6378245.0,298.3]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)
PRJ = {"CGCS2000": PRJ_CGCS2000, "WGS84": PRJ_WGS84,
       "XIAN80": PRJ_XIAN80, "BEIJING54": PRJ_BEIJING54}


def _canonical_crs(crs_name):
    """坐标系名归一化（支持中文别名）；无法识别时原样返回，导出回退口径不变。"""
    from . import projection
    return projection.normalize_crs(crs_name) or crs_name


def to_geojson(points, properties=None, crs_name="CGCS2000"):
    crs_name = _canonical_crs(crs_name)
    ring = [[p["x"], p["y"]] for p in points]
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    props = {"name": "RDB ParcelMap 宗地", "disclaimer": DISCLAIMER,
             "brand": BRAND, "slogan": SLOGAN, "support": SUPPORT_EMAIL}
    if properties:
        props.update(properties)
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": crs_name}},
        "features": [{"type": "Feature", "properties": props,
                      "geometry": {"type": "Polygon", "coordinates": [ring]}}],
    }


def export_geojson(points, path, properties=None, crs_name="CGCS2000"):
    data = to_geojson(points, properties, crs_name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def export_shapefile_zip(points, zip_path, crs_name="CGCS2000", properties=None):
    """用 pyshp 写 .shp/.shx/.dbf，再加 .prj 后 zip 打包。"""
    import tempfile

    import shapefile  # pyshp
    base = os.path.splitext(os.path.basename(str(zip_path)))[0] or "parcel"
    with tempfile.TemporaryDirectory() as td:
        stem = os.path.join(td, base)
        w = shapefile.Writer(stem, shapeType=shapefile.POLYGON)
        w.field("NAME", "C", size=64)
        w.field("AREA_M2", "F", decimal=3)
        w.field("PERIM_M", "F", decimal=3)
        ring = [[p["x"], p["y"]] for p in points]
        w.poly([ring])
        au = geometry.area_units(points)
        w.record((properties or {}).get("name", "parcel")[:64], au["m2"], geometry.perimeter(points))
        w.close()
        with open(stem + ".prj", "w", encoding="utf-8") as f:
            f.write(PRJ.get(_canonical_crs(crs_name), PRJ_WGS84))
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for ext in (".shp", ".shx", ".dbf", ".prj"):
                z.write(stem + ext, base + ext)
    return zip_path


# ---------------------------------------------------------------- PDF

def _register_cjk_font():
    """在系统里找可用 CJK 字体注册到 reportlab；找不到退化 Helvetica。返回 (字体名, 说明)。"""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    candidates = []
    for pat in ("/usr/share/fonts/**/*NotoSansCJK*.ttc",
                "/usr/share/fonts/**/*NotoSansCJK*.ttf",
                "/usr/share/fonts/**/*NotoSerifCJK*.ttc",
                "/usr/share/fonts/**/*wqy*.ttf",
                "/usr/share/fonts/**/*DroidSansFallback*.ttf"):
        candidates.extend(sorted(glob.glob(pat, recursive=True)))
    assets = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")
    candidates = sorted(glob.glob(os.path.join(assets, "*.ttf"))) + candidates
    for path in candidates:
        try:
            pdfmetrics.registerFont(TTFont("CJK", path, subfontIndex=0))
            return "CJK", f"已注册 CJK 字体 {path}（TTC 子字体 0）"
        except Exception:
            try:
                pdfmetrics.registerFont(TTFont("CJK", path))
                return "CJK", f"已注册 CJK 字体 {path}"
            except Exception:
                continue
    # 退化方案：reportlab 内置 CID 中文字体 STSong-Light（无需字体文件，
    # 系统 Noto CJK 为 CFF 轮廓 TTC，reportlab 的 TTFont 不支持其轮廓格式时使用）
    try:
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        return "STSong-Light", ("系统 CJK 字体为 CFF 轮廓 TTC，TTFont 无法注册，"
                                 "已退化为 reportlab 内置 CID 字体 STSong-Light（中文可正常显示）")
    except Exception:
        return "Helvetica", "未找到可用 CJK 字体，退化为 Helvetica（中文可能显示为方框）"


def export_pdf(points, path, sizhi=None, title="界址图", crs_name="CGCS2000",
               note=None):
    """界址图 PDF（A4，坐标表自动分页）：第 1 页为宗地轮廓、界址点标注、
    指北针、比例尺文字与坐标表开头；坐标表超过单页容量时自动续页
    （表头重复、页脚带页码与免责声明），四至填写栏与面积/制图信息栏
    跟在表末，不足则另起一页。100 个界址点不溢出、不丢行。
    返回 (path, 字体说明)。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    font, font_note = _register_cjk_font()
    crs_name = _canonical_crs(crs_name)
    au = geometry.area_units(points)
    per = geometry.perimeter(points)
    table = geometry.boundary_table(points)
    bb = geometry.bbox(points)
    W, H = A4

    ROW_H = 4.2 * mm          # 坐标表行高（与原单页版一致）
    BOTTOM = 16 * mm          # 正文下限（页脚在其下方）
    headers = ["点号", "X（东）", "Y（北）", "至下点边长(m)", "方位角(°)"]
    colx = [15 * mm, 35 * mm, 75 * mm, 115 * mm, 150 * mm]

    def rows_fit(first_row_y):
        """从首行基线 first_row_y 起、本页可容纳的行数。"""
        if first_row_y < BOTTOM:
            return 0
        return int((first_row_y - BOTTOM) // ROW_H) + 1

    def header_block_height():
        # 表题（基线处）-> 表头 -5mm -> 分隔线 -2mm -> 首行 -4.2mm
        return 5 * mm + 2 * mm + ROW_H

    # ---- 分页规划（先算总页数，页脚才能写「第 X 页 / 共 Y 页」）
    map_bottom = H - 118 * mm                      # 第 1 页地图框下沿
    p1_title_y = map_bottom - 8 * mm               # 第 1 页表题基线
    p1_first_row = p1_title_y - header_block_height()
    cont_title_y = H - 18 * mm                     # 续页表题基线
    cont_first_row = cont_title_y - header_block_height()
    chunks = []
    rest = list(table)
    cap = rows_fit(p1_first_row)
    chunks.append(rest[:cap])
    rest = rest[cap:]
    while rest:
        cap = rows_fit(cont_first_row)
        chunks.append(rest[:cap])
        rest = rest[cap:]
    # 文末块（四至 + 面积/制图信息）高度：与绘制口径一致地估算
    tail_h = 9 * mm + 4 * 5.5 * mm + 9 * mm + 3 * 5.5 * mm
    if note:
        tail_h += 5.5 * mm
    last_first = p1_first_row if len(chunks) == 1 else cont_first_row
    last_row_y = last_first - ROW_H * (len(chunks[-1]) - 1) if chunks[-1] else last_first + ROW_H
    tail_extra_page = (last_row_y - tail_h) < BOTTOM
    total_pages = len(chunks) + (1 if tail_extra_page else 0)

    c = canvas.Canvas(str(path), pagesize=A4)

    def footer(page_no):
        c.setFont(font, 7.5)
        c.drawString(15 * mm, 10 * mm, DISCLAIMER)
        c.drawRightString(W - 15 * mm, 10 * mm, f"第 {page_no} 页 / 共 {total_pages} 页")

    def draw_table_header(title_y, continued):
        c.setFont(font, 11)
        c.drawString(15 * mm, title_y, "界址点坐标表" + ("（续）" if continued else ""))
        hy = title_y - 5 * mm
        c.setFont(font, 8)
        for x0, htxt in zip(colx, headers):
            c.drawString(x0, hy, htxt)
        ly = hy - 2 * mm
        c.line(15 * mm, ly, W - 15 * mm, ly)
        return title_y - header_block_height()

    def draw_rows(rows, first_row_y):
        """绘制 rows，返回最后一行基线 y（无行时返回首行基线 + ROW_H）。"""
        c.setFont(font, 8)
        ty = first_row_y
        for i, r in enumerate(rows):
            if i:
                ty -= ROW_H
            vals = [r["from"], f"{r['x']:.3f}", f"{r['y']:.3f}",
                    f"{r['length']:.2f}", f"{r['azimuth_deg']:.4f}"]
            for x0, v in zip(colx, vals):
                c.drawString(x0, ty, v)
        return ty if rows else first_row_y + ROW_H

    def draw_tail(ty):
        """四至填写栏 + 面积/制图信息栏，接在基线 ty 之下绘制。"""
        ty -= 9 * mm
        c.setFont(font, 11)
        c.drawString(15 * mm, ty, "四至")
        c.setFont(font, 9)
        sz = sizhi or {}
        labels = [("东至", sz.get("east")), ("南至", sz.get("south")),
                  ("西至", sz.get("west")), ("北至", sz.get("north"))]
        for lab, val in labels:
            ty -= 5.5 * mm
            c.drawString(15 * mm, ty, f"{lab}：{val if val else '＿＿＿＿＿＿＿＿'}")
        ty -= 9 * mm
        c.setFont(font, 9)
        c.drawString(15 * mm, ty, f"面积：{au['m2']:.2f} ㎡（{au['mu']:.4f} 亩 / {au['hectare']:.6f} 公顷）  周长：{per:.2f} m  坐标系：{crs_name}")
        ty -= 5.5 * mm
        c.drawString(15 * mm, ty, "制图：" + BRAND + " · " + DISCLAIMER)
        ty -= 5.5 * mm
        c.drawString(15 * mm, ty, f"图签：{BRAND}｜技术支持 {SUPPORT_EMAIL}")
        if note:
            ty -= 5.5 * mm
            c.drawString(15 * mm, ty, note)
        return ty

    def draw_map_page_head():
        c.setFont(font, 16)
        c.drawCentredString(W / 2, H - 18 * mm, f"{title} · RDB ParcelMap")
        c.setFont(font, 8)
        c.drawCentredString(W / 2, H - 23 * mm, BRAND + " · " + SLOGAN + " · " + DISCLAIMER)
        mx0, my0, mx1, my1 = 15 * mm, map_bottom, W - 15 * mm, H - 28 * mm
        c.rect(mx0, my0, mx1 - mx0, my1 - my0)
        spanx = max(bb["maxx"] - bb["minx"], 1e-9)
        spany = max(bb["maxy"] - bb["miny"], 1e-9)
        scale = min((mx1 - mx0) * 0.86 / spanx, (my1 - my0) * 0.86 / spany)
        ox = (mx0 + mx1) / 2 - (bb["minx"] + bb["maxx"]) / 2 * scale
        oy = (my0 + my1) / 2 - (bb["miny"] + bb["maxy"]) / 2 * scale

        def T(p):
            return (ox + p["x"] * scale, oy + p["y"] * scale)

        path_obj = c.beginPath()
        for i, p in enumerate(points):
            X, Y = T(p)
            path_obj.moveTo(X, Y) if i == 0 else path_obj.lineTo(X, Y)
        path_obj.close()
        c.setLineWidth(1.4)
        c.drawPath(path_obj, stroke=1, fill=0)
        c.setFont(font, 8)
        for p in points:
            X, Y = T(p)
            c.circle(X, Y, 2.2, stroke=1, fill=0)
            c.drawString(X + 3, Y + 3, p["name"])
        # 指北针
        nx, ny = mx1 - 14 * mm, my1 - 8 * mm
        c.line(nx, ny - 8 * mm, nx, ny + 4 * mm)
        c.line(nx - 2 * mm, ny + 1 * mm, nx, ny + 4 * mm)
        c.line(nx + 2 * mm, ny + 1 * mm, nx, ny + 4 * mm)
        c.setFont(font, 10)
        c.drawCentredString(nx, ny + 6 * mm, "N")
        # 比例尺文字（图上 40mm 对应实地距离）
        real40 = 40 * mm / scale
        c.setFont(font, 8)
        c.drawString(mx0 + 2 * mm, my0 + 3 * mm, f"比例尺参考：图上 40 mm ≈ 实地 {real40:.2f} m（以坐标为准）")

    # ---- 逐页绘制：表页（末页顺接文末块，除非规划为另起页）
    n_chunks = len(chunks)
    for pi, chunk in enumerate(chunks, start=1):
        if pi == 1:
            draw_map_page_head()
            first_y = draw_table_header(p1_title_y, continued=False)
        else:
            first_y = draw_table_header(cont_title_y, continued=True)
        ty = draw_rows(chunk, first_y)
        if pi == n_chunks and not tail_extra_page:
            draw_tail(ty)
        footer(pi)
        c.showPage()
    if tail_extra_page:
        draw_tail(H - 18 * mm + 9 * mm)  # 基线补偿：draw_tail 先 -9mm，落在 H-18mm
        footer(total_pages)
        c.showPage()
    c.save()
    return str(path), font_note
