import base64
import hashlib
import hmac
import json
from pathlib import Path

from app.security import verify_shopify_hmac

FIXTURE = Path(__file__).parent / "fixtures" / "shopify_order.json"
SECRET = "test-webhook-secret"


def load_body() -> bytes:
    with FIXTURE.open(encoding="utf-8") as f:
        payload = json.load(f)
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def test_valid_signature_passes():
    body = load_body()
    header = sign(body, SECRET)

    assert verify_shopify_hmac(body, header, SECRET) is True


def test_tampered_body_fails():
    body = load_body()
    header = sign(body, SECRET)
    tampered = body.replace(b"199.50", b"1.00")

    assert tampered != body
    assert verify_shopify_hmac(tampered, header, SECRET) is False


def test_none_header_fails():
    body = load_body()

    assert verify_shopify_hmac(body, None, SECRET) is False


def test_empty_header_fails():
    body = load_body()

    assert verify_shopify_hmac(body, "", SECRET) is False


def test_wrong_secret_fails():
    body = load_body()
    header = sign(body, SECRET)

    assert verify_shopify_hmac(body, header, "another-secret") is False
