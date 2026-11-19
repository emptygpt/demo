import base64
import hashlib
import hmac


def verify_shopify_hmac(body: bytes, header: str | None, secret: str) -> bool:
    """校验 Shopify webhook 的 X-Shopify-Hmac-Sha256 头：HMAC-SHA256(secret, body) 的 base64 与 header 比较。"""
    if not header:
        return False

    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest)
    return hmac.compare_digest(expected, header.encode("utf-8"))
