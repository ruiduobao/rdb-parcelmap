#!/usr/bin/env python3
"""RDB ParcelMap 授权码发码脚本（运营方使用）。

用法：
  python tools/issue_license.py --email user@example.com --plan monthly --days 30
  python tools/issue_license.py --email user@example.com --plan permanent

密钥从环境变量 RDBPM_SECRET 读取；未设置时使用 core/license.py 中的示例假密钥，
上线前必须更换。签发后会自验回读并打印验签结果。
技术支持：caaschengrui@163.com
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import license as lic  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="RDB ParcelMap 授权码签发（锐多宝出品）")
    ap.add_argument("--email", required=True, help="被授权邮箱")
    ap.add_argument("--plan", default="monthly", choices=["monthly", "permanent"])
    ap.add_argument("--days", type=int, default=30, help="monthly 有效天数（默认 30）")
    args = ap.parse_args()

    code = lic.issue_license(args.email, plan=args.plan, days=args.days)
    check = lic.verify_license(code)
    print(f"授权码：{code}")
    print(f"邮箱：{args.email}  版本：{args.plan}  到期日：{check['expires'] or '永久有效'}")
    print(f"自验回读：{'通过' if check['valid'] else '失败：' + check['reason']}")
    if lic.get_secret() == lic.EXAMPLE_SECRET:
        print("警告：当前使用的是仓库示例假密钥，上线前必须设置环境变量 RDBPM_SECRET 更换为真实密钥。")
    return 0 if check["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
