"""RDB ParcelMap 轻量授权层（原创实现）。

授权码格式：RDBPM-XXXX-XXXX-...（Base32 分组码）
载荷：JSON {"e": 邮箱, "p": plan, "x": 到期日 YYYY-MM-DD 或 null}
签名：HMAC-SHA256(secret, 载荷字节) 取前 16 字节，与载荷拼接后 Base32 编码分组。

plan:
- monthly   ：月付版，载荷带到期日，过期失效；
- permanent ：永久版，载荷无到期日，永不过期。

密钥从环境变量 RDBPM_SECRET 读取；未设置时使用仓库内示例假密钥，
仅供本地开发与测试，上线前必须更换为真实密钥（见 get_secret 说明）。
"""
import base64
import hashlib
import hmac
import json
import os
from datetime import date, timedelta

PREFIX = "RDBPM-"
# 示例假密钥：仅供本地开发/测试，上线前必须通过环境变量 RDBPM_SECRET 更换为真实密钥。
EXAMPLE_SECRET = "RDBPM-EXAMPLE-SECRET-CHANGE-ME-BEFORE-PRODUCTION"
_SIG_LEN = 16
PLANS = ("monthly", "permanent")


def get_secret():
    """从环境变量 RDBPM_SECRET 读密钥；未设置时回退到示例假密钥（上线前必须更换）。"""
    return os.environ.get("RDBPM_SECRET") or EXAMPLE_SECRET


def _b32_encode(raw: bytes) -> str:
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _b32_decode(text: str) -> bytes:
    text = text.strip().upper()
    pad = (-len(text)) % 8
    return base64.b32decode(text + "=" * pad)


def _group(code_body: str) -> str:
    return "-".join(code_body[i:i + 4] for i in range(0, len(code_body), 4))


def issue_license(email, plan="monthly", days=30, secret=None, today=None):
    """签发授权码。monthly 须给出有效天数并写入到期日；permanent 无到期日。"""
    email = (email or "").strip()
    if not email or "@" not in email:
        raise ValueError("邮箱不合法")
    if plan not in PLANS:
        raise ValueError(f"未知 plan: {plan}（可选 monthly / permanent）")
    today = today or date.today()
    expires = None
    if plan == "monthly":
        if not days or int(days) <= 0:
            raise ValueError("monthly 授权须给出正整数有效天数")
        expires = (today + timedelta(days=int(days))).isoformat()
    payload = {"e": email, "p": plan, "x": expires}
    payload_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    key = (secret or get_secret()).encode("utf-8")
    sig = hmac.new(key, payload_bytes, hashlib.sha256).digest()[:_SIG_LEN]
    return PREFIX + _group(_b32_encode(payload_bytes + sig))


def verify_license(code, secret=None, today=None):
    """验签并判断过期。返回 dict: {valid, email, plan, expires, reason}。"""
    result = {"valid": False, "email": None, "plan": None, "expires": None, "reason": ""}
    if not code or not str(code).strip():
        result["reason"] = "未提供授权码"
        return result
    text = str(code).strip().upper()
    if not text.startswith(PREFIX):
        result["reason"] = "授权码前缀不正确"
        return result
    body = text[len(PREFIX):].replace("-", "").replace(" ", "")
    try:
        raw = _b32_decode(body)
    except Exception:
        result["reason"] = "授权码编码不合法"
        return result
    if len(raw) <= _SIG_LEN:
        result["reason"] = "授权码长度不正确"
        return result
    payload_bytes, sig = raw[:-_SIG_LEN], raw[-_SIG_LEN:]
    key = (secret or get_secret()).encode("utf-8")
    expected = hmac.new(key, payload_bytes, hashlib.sha256).digest()[:_SIG_LEN]
    if not hmac.compare_digest(sig, expected):
        result["reason"] = "授权码签名校验失败（可能已被篡改）"
        return result
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        result["reason"] = "授权码载荷不合法"
        return result
    plan = payload.get("p")
    expires = payload.get("x")
    if plan not in PLANS:
        result["reason"] = "授权码版本类型不合法"
        return result
    if plan == "monthly":
        if not expires:
            result["reason"] = "月付授权码缺少到期日"
            return result
        today = today or date.today()
        try:
            exp_date = date.fromisoformat(expires)
        except ValueError:
            result["reason"] = "授权码到期日不合法"
            return result
        if today > exp_date:
            result["reason"] = f"授权码已于 {expires} 过期"
            result.update({"email": payload.get("e"), "plan": plan, "expires": expires})
            return result
    result.update({"valid": True, "email": payload.get("e"), "plan": plan,
                   "expires": expires, "reason": "有效"})
    return result


def is_pro(code, secret=None, today=None):
    """是否为有效 Pro 授权（monthly 未过期或 permanent）。"""
    return verify_license(code, secret=secret, today=today)["valid"]
