#!/usr/bin/env python3
"""RDB ParcelMap 命令行入口：输入文件 -> GeoJSON + 报告 txt。

用法：
  python cli.py 输入.txt -o 输出前缀 [--kind coords|csv|dxf|edges] [--order xy|yx] [--strip-band]
         [--license 授权码] [--shp] [--pdf]
免费版：GeoJSON + 报告；Pro（凭授权码）：另可 Shapefile / 界址图 PDF 导出与批量处理。
辅助落图工具，成果须经人工核校，不作为测绘资质成果。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import exporters, geometry, parsers, traverse  # noqa: E402
from core import license as lic  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="RDB ParcelMap CLI（锐多宝 RDB）")
    ap.add_argument("input")
    ap.add_argument("-o", "--out", default="parcel_out")
    ap.add_argument("--kind", default="coords", choices=["coords", "csv", "dxf", "edges"])
    ap.add_argument("--order", default="xy", choices=["xy", "yx"])
    ap.add_argument("--strip-band", action="store_true")
    ap.add_argument("--license", dest="license_code", default="",
                    help="Pro 授权码（RDBPM- 开头）；无有效码时只出 GeoJSON + 报告")
    ap.add_argument("--crs", default="CGCS2000",
                    choices=["CGCS2000", "WGS84", "XIAN80", "BEIJING54",
                             "西安80", "北京54"],
                    help="导出坐标系标注与 .prj（四系，默认 CGCS2000）")
    ap.add_argument("--shp", action="store_true", help="Pro：同时导出 Shapefile zip")
    ap.add_argument("--pdf", action="store_true", help="Pro：同时导出界址图 PDF")
    args = ap.parse_args()
    lic_check = lic.verify_license(args.license_code)
    pro = lic_check["valid"]

    with open(args.input, encoding="utf-8", errors="replace") as f:
        text = f.read()
    extra = {}
    if args.kind == "coords":
        points = parsers.parse_coordinate_string(text, order=args.order, strip_band=args.strip_band)
    elif args.kind == "csv":
        points = parsers.parse_csv(text)
    elif args.kind == "dxf":
        d = parsers.parse_dxf(text)
        points = d["polylines"][0] if d["polylines"] else d["points"]
    else:
        edges = parsers.parse_edge_text(text)
        adj = traverse.bowditch_adjust(edges)
        points = adj["points"]
        extra = adj
    if len(points) < 3:
        print("错误：有效界址点不足 3 个", file=sys.stderr)
        return 1
    v = traverse.validate_polygon(points)
    points = v["points"]
    s = geometry.summary(points)
    exporters.export_geojson(points, args.out + ".geojson", crs_name=args.crs)
    written = [args.out + ".geojson"]
    pro_notes = []
    if args.shp or args.pdf:
        if not pro:
            pro_notes.append(f"注：未提供有效 Pro 授权码（{lic_check['reason']}），"
                             "Shapefile / 界址图 PDF 导出为 Pro 功能，本次仅输出 GeoJSON + 报告。")
        else:
            if args.shp:
                exporters.export_shapefile_zip(points, args.out + ".zip", crs_name=args.crs)
                written.append(args.out + ".zip")
            if args.pdf:
                exporters.export_pdf(points, args.out + ".pdf", crs_name=args.crs)
                written.append(args.out + ".pdf")
    elif not pro:
        pro_notes.append(f"注：当前为免费版（{lic_check['reason']}），仅输出 GeoJSON + 报告；"
                         "Shapefile 导出、界址图 PDF 导出与批量处理为 Pro 功能。")
    lines = [exporters.BRAND, "RDB ParcelMap 落图报告 · " + exporters.SLOGAN,
             exporters.DISCLAIMER, "",
             f"授权状态：{'Pro（' + lic_check['plan'] + ('，到期 ' + lic_check['expires'] if lic_check['expires'] else '，永久有效') + '）' if pro else '免费版'}",
             *pro_notes, "",
             f"界址点数：{len(points)}",
             f"面积：{s['area_m2']:.2f} ㎡ = {s['area_mu']:.4f} 亩 = {s['area_hectare']:.6f} 公顷",
             f"周长：{s['perimeter_m']:.2f} m",
             f"重心：({s['centroid']['x']:.3f}, {s['centroid']['y']:.3f})"]
    if extra:
        lines.append(f"闭合差 fx={extra['fx']:+.4f} m, fy={extra['fy']:+.4f} m, "
                     f"闭合差={extra['closure']:.4f} m, 相对闭合差=1/{extra['relative_closure']:.0f}")
    for w in v["warnings"]:
        lines.append("提示：" + w)
    lines.append("")
    lines.append("界址点表（点号 X Y 边长 方位角°）：")
    for r in s["boundary_table"]:
        lines.append(f"{r['from']} {r['x']:.3f} {r['y']:.3f} {r['length']:.2f} {r['azimuth_deg']:.4f}")
    lines.append("")
    lines.append(f"技术支持：{exporters.SUPPORT_EMAIL}")
    with open(args.out + "_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n已写出 {'、'.join(written)} 与 {args.out}_report.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
