"""RDB ParcelMap 网页后端（Flask）：解析 / 导出 API。

辅助落图工具，成果须经人工核校，不作为测绘资质成果。
运行： .venv/bin/python web/app.py  （默认 http://127.0.0.1:8642）
"""
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask, jsonify, request, send_file, send_from_directory

from core import boundary_desc, exporters, geometry, parsers, projection, traverse
from core import license as lic

app = Flask(__name__, static_folder="static", static_url_path="/static")
HERE = os.path.dirname(os.path.abspath(__file__))


def build_result(points, extra=None):
    v = traverse.validate_polygon(points)
    pts = v["points"]
    if 0 < len(pts) < 3:
        v["warnings"].append(
            f"仅解析到 {len(pts)} 个界址点，不足 3 个，无法构成宗地，请检查输入是否完整。")
    out = {"points": pts, "validation": v, "summary": geometry.summary(pts) if len(pts) >= 3 else None}
    if len(pts) >= 3:
        # P-U2：四至自动生成草稿 + 界址点成果表，随解析结果一并给出（须人工核校）
        out["sizhi_generated"] = boundary_desc.generate_sizhi(pts)
        out["registration"] = boundary_desc.registration_table(pts)
    if extra:
        out.update(extra)
    return out


def _empty_points_error(kind_label):
    return jsonify({"error": f"没有解析到任何界址点：请检查输入内容是否与所选输入类型"
                             f"（{kind_label}）匹配、坐标格式是否正确。"}), 400


@app.get("/")
def index():
    return send_from_directory(os.path.join(HERE, "static"), "index.html")


@app.post("/api/parse")
def api_parse():
    body = request.get_json(force=True, silent=True) or {}
    kind = body.get("kind", "coords")
    text = body.get("text", "")
    order = body.get("order", "xy")
    strip_band = bool(body.get("strip_band", False))
    try:
        if kind == "coords":
            pts = parsers.parse_coordinate_string(text, order=order, strip_band=strip_band)
            if not pts:
                return _empty_points_error("坐标串")
            return jsonify(build_result(pts, {"band": parsers.detect_band(text)}))
        if kind == "csv":
            pts = parsers.parse_csv(text)
            if not pts:
                return _empty_points_error("CSV 文本")
            return jsonify(build_result(pts))
        if kind == "dxf":
            d = parsers.parse_dxf(text)
            pts = d["polylines"][0] if d["polylines"] else d["points"]
            if not pts:
                return _empty_points_error("DXF 文本")
            return jsonify(build_result(pts, {"dxf_points": d["points"], "polyline_count": len(d["polylines"])}))
        if kind == "edges":
            edges = parsers.parse_edge_text(text)
            if not edges:
                return jsonify({"error": "未解析出边（方位+距离）"}), 400
            adj = traverse.bowditch_adjust(edges)
            result = build_result(adj["points"], {
                "edges": edges, "traverse": {"fx": adj["fx"], "fy": adj["fy"],
                "closure": adj["closure"], "relative_closure": adj["relative_closure"],
                "total_distance": adj["total_distance"]}})
            warn = traverse.closure_warning(adj["relative_closure"], adj["closure"])
            if warn:
                result["validation"]["warnings"].append(warn)
            return jsonify(result)
        if kind == "sizhi":
            sz = parsers.parse_sizhi_text(text)
            if not any([sz.get("east"), sz.get("south"), sz.get("west"), sz.get("north")]) \
                    and not any(v is not None for v in (sz.get("lengths") or {}).values()):
                return jsonify({"error": "没有提取到四至信息：请确认文本包含"
                                         "「东至…、南至…、西至…、北至…」式的四至描述。"}), 400
            return jsonify({"sizhi": sz})
        return jsonify({"error": f"未知 kind: {kind}"}), 400
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 400


def _license_code(body):
    return (request.headers.get("X-License") or request.args.get("license")
            or body.get("license") or "")


@app.post("/api/license/verify")
def api_license_verify():
    body = request.get_json(force=True, silent=True) or {}
    return jsonify(lic.verify_license(_license_code(body)))


@app.post("/api/export/<fmt>")
def api_export(fmt):
    body = request.get_json(force=True, silent=True) or {}
    points = body.get("points") or []
    crs = body.get("crs", "CGCS2000")
    if fmt in ("shp", "pdf"):
        check = lic.verify_license(_license_code(body))
        if not check["valid"]:
            return jsonify({"error": "该导出为 Pro 功能，需要有效授权码（Pro 月付 10 元/月或永久版 100 元）。"
                                     f"当前状态：{check['reason']}。免费版可使用解析、地图核对与 GeoJSON 导出。"
                                     "技术支持：caaschengrui@163.com"}), 403
    if len(points) < 3:
        return jsonify({"error": "至少需要 3 个界址点"}), 400
    if fmt == "geojson":
        data = exporters.to_geojson(points, crs_name=crs)
        return jsonify(data)
    if fmt == "shp":
        buf_path = os.path.join(HERE, "..", "parcel.zip")
        exporters.export_shapefile_zip(points, buf_path, crs_name=crs)
        with open(buf_path, "rb") as f:
            data = f.read()
        os.remove(buf_path)
        return send_file(io.BytesIO(data), mimetype="application/zip",
                         as_attachment=True, download_name="parcel.zip")
    if fmt == "pdf":
        buf_path = os.path.join(HERE, "..", "parcel.pdf")
        sizhi = body.get("sizhi")
        if sizhi is None and body.get("auto_sizhi"):
            # P-U2：显式 opt-in 时用自动生成四至草稿填 PDF 四至栏（neighbors 可传）
            sizhi = boundary_desc.generate_sizhi(
                points, neighbors=body.get("neighbors"))["sizhi4"]
        exporters.export_pdf(points, buf_path, sizhi=sizhi, crs_name=crs,
                             note=body.get("note"))
        with open(buf_path, "rb") as f:
            data = f.read()
        os.remove(buf_path)
        return send_file(io.BytesIO(data), mimetype="application/pdf",
                         as_attachment=True, download_name="parcel.pdf")
    return jsonify({"error": f"未知格式: {fmt}"}), 400


@app.post("/api/convert")
def api_convert():
    """坐标系转换（免费，属解析/核对类）：四系（CGCS2000/WGS84/西安80/北京54）
    之间经经纬度中间量换算，3/6 度带可选。涉及北京54/西安80 的转换在
    返回 note 中带「未含地方七参数改正，仅供概算」中文提示。"""
    body = request.get_json(force=True, silent=True) or {}
    points = body.get("points") or []
    src = projection.normalize_crs(body.get("src_crs", "CGCS2000"))
    dst = projection.normalize_crs(body.get("dst_crs", "CGCS2000"))
    if src is None or dst is None:
        return jsonify({"error": "未知坐标系：支持 CGCS2000 / WGS84 / 西安80 / 北京54。"}), 400
    if not points:
        return jsonify({"error": "没有待转换的界址点。"}), 400
    kind = body.get("input", "plane")
    if kind not in ("plane", "latlon"):
        return jsonify({"error": f"未知 input: {kind}（plane=平面坐标，latlon=x 为经度、y 为纬度）"}), 400
    try:
        zw = int(body.get("zone_width", 3))
        out, note = projection.convert_points(
            points, src, dst, input_kind=kind, zone_width=zw,
            src_zone=body.get("src_zone"), dst_zone=body.get("dst_zone"))
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 400
    return jsonify({"points": out, "src_crs": src, "dst_crs": dst,
                    "zone_width": zw, "note": note,
                    "disclaimer": exporters.DISCLAIMER})


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "product": "RDB ParcelMap",
                    "disclaimer": exporters.DISCLAIMER})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PARCELMAP_PORT", "8642")))
