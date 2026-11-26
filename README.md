# RDB ParcelMap · 锐多宝出品 — 宗地界址智能落图

**定位语：把四至文字，一键落到图上。**

锐多宝 RDB 自有品牌工具（品牌标：`web/static/brand.svg`，深黛蓝底、白色轨道弧线环绕朱砂定位点、青绿点缀）。把宗地界址信息（坐标串 / 表格 / 界址文字描述）自动变成地图上的宗地多边形，核对后导出成果。面向国内场景：宅基地与承包地确权的「四至」描述、征地红线附件、历史地籍档案数字化。

> **定位声明：本产品为辅助落图工具，成果须经人工核校，不作为测绘资质成果。**

## 功能

- **坐标串解析（自写）**：`x,y` / `y,x` 顺序开关；分号、换行、空格分隔；`J1、J2…` 点号标注；CGCS2000 三度带带号前缀识别与可选剥离。
- **CSV 导入**：`点号,X,Y` 或 `点号,纬度,经度` 两种表头，中英文列名都认。
- **DXF 导入（自写 ASCII DXF 解析器）**：只取 LWPOLYLINE / POLYLINE 顶点与 POINT 实体。
- **中文界址文本解析（自写）**：边表式（`J1→J2 方位角 45°30′20″ 距离 32.15 米`、`J1-J2：北偏东30°，长25米`；方位角数值 / 度分秒 / 八方位与十六方位词 / 偏角写法）与四至式描述的四至名称、边长提取；英文象限角 `N30°E` + 米/英尺距离的基础解析。
- **导线计算与平差（自写）**：边序列 → 坐标，输出闭合差 fx、fy 与相对闭合差；Bowditch（罗盘）法则按边长比例平差；坐标点列成图时校验闭合与自交并报警。
- **几何成果**：面积（鞋带公式，含亩 / 公顷换算）、周长、界址点表（点号 / 坐标 / 边长 / 方位角逐边）、重心、外包框。
- **四系坐标**：CGCS2000 / WGS84 / 西安80 / 北京54 四系齐备（自写高斯-克吕格 3/6 度带正反算，`core/projection.py`，往返精度亚毫米）；跨系经经纬度中间量换算，涉及北京54/西安80 时提示「未含地方七参数改正，仅供概算」；网页端 `/api/convert` 与导出坐标系选择均已贯通。
- **导出**：GeoJSON；Shapefile（zip 打包 .shp/.shx/.dbf/.prj，四系 .prj）；界址图 PDF（宗地轮廓、界址点标注、指北针、比例尺文字、界址点坐标表、四至填写栏、面积与制图信息栏；坐标表超单页自动分页，表头重复、带页码，100 个界址点不溢出不丢行）。
- **网页应用**：左侧输入（粘贴 / 文件上传 / 解析参数），中间 Leaflet 地图（卫星 + 街道底图切换、多边形叠加、顶点拖动微调、逐边核对高亮），右侧成果（面积 / 周长 / 闭合差报告、界址点表、导出按钮）。Leaflet 已 vendor 到本地 `web/static/vendor/`，部署到国内服务器不依赖境外 CDN。卫星底图使用 Esri World Imagery 公开瓦片（© Esri, Maxar, Earthstar Geographics 等），使用须遵守其许可条款，正式商用前请核对授权；街道底图为 OpenStreetMap（© OSM 贡献者）。
- **命令行**：`cli.py` 输入文件 → GeoJSON + 报告 txt，适合批处理。

## 运行方式

```bash
cd ~/workspace/products-rdb/parcelmap
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 网页应用（默认 http://127.0.0.1:8642 ）
.venv/bin/python web/app.py

# 命令行
.venv/bin/python cli.py examples/example1_coords.txt --kind coords -o out1
.venv/bin/python cli.py examples/example2_edges.txt --kind edges -o out2

# 测试（一条命令）
.venv/bin/python tests/test_parcelmap.py
```

目录：`core/`（纯 Python 核心库，与界面解耦：parsers / traverse / geometry / exporters）、`web/`（Flask 后端 + 单页前端）、`examples/`（3 个样例 + 期望结果说明）、`tests/`（无头测试与 fixtures）、`cli.py`。

## 价格与版本（三档定版）

| 版本 | 价格 | 功能 |
|---|---|---|
| 免费版 | 0 元 | 解析（坐标串 / CSV / DXF / 边表 / 四至文本）、地图核对、GeoJSON 导出，不限次 |
| Pro 月付 | 10 元 / 月 | 免费版全部功能 + Shapefile 导出、界址图 PDF 导出、批量 CLI 处理 |
| 永久版 | 100 元（一次性） | Pro 全部功能，永久有效，无到期日 |

授权方式：Pro 使用轻量授权码（`core/license.py`，HMAC-SHA256 签名、Base32 分组码、前缀 `RDBPM-`；载荷含邮箱、版本与到期日，月付带到期日、永久版无到期日，验签防篡改并判断过期）。密钥从环境变量 `RDBPM_SECRET` 读取，仓库内仅为示例假密钥，**上线前必须更换**。发码：`tools/issue_license.py --email <邮箱> --plan monthly --days 30` 或 `--plan permanent`（签发后自验回读）。网页端在成果区粘贴授权码激活（存浏览器 localStorage，导出时经请求头/参数携带，后端校验，无有效码返回 403）；CLI 用 `--license <授权码>`，无码时只出 GeoJSON + 报告并在报告中注明。收款通道上线前另行确认。

## 联系方式

- 技术支持：caaschengrui@163.com

## 免责声明

本工具为**辅助落图工具，成果须经人工核校，不作为测绘资质成果**，不得直接作为确权、征地、登记等法定用途的成果文件；因未经核校直接使用所生后果由使用者承担。平面坐标在网页地图上的显示为以首点为锚的近似平移（仅供核对形状），不构成定位成果；经纬度模式按输入坐标真实位置显示。

署名：RDB ParcelMap · 锐多宝出品。技术支持：caaschengrui@163.com
