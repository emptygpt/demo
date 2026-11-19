import base64
import copy
import hashlib
import hmac
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import OrderStore
from app.feishu import FakeFeishu
from app.main import create_app

SECRET = "whsec_test_secret"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "shopify_order.json"
FIXTURE_ORDER = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
JSON_HEADERS = {"Content-Type": "application/json"}


def _sign(body: bytes, secret: str = SECRET) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def _order(**overrides) -> dict:
    order = copy.deepcopy(FIXTURE_ORDER)
    order.update(overrides)
    return order


def _body(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


@pytest.fixture
def fake() -> FakeFeishu:
    return FakeFeishu()


@pytest.fixture
def client(fake: FakeFeishu) -> TestClient:
    settings = Settings(
        shopify_webhook_secret=SECRET,
        sqlite_path=":memory:",
        feishu_mode="fake",
    )
    return TestClient(create_app(settings, OrderStore(":memory:"), fake))


def test_health(client: TestClient):
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_post_orders_new_order_returns_201(client: TestClient, fake: FakeFeishu):
    body = _body(FIXTURE_ORDER)

    resp = client.post("/orders", content=body, headers=JSON_HEADERS)

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "created"
    assert data["order_id"] == str(FIXTURE_ORDER["id"])
    assert data["record_id"]
    assert len(fake.records) == 1


def test_post_orders_duplicate_returns_200(client: TestClient, fake: FakeFeishu):
    body = _body(FIXTURE_ORDER)
    client.post("/orders", content=body, headers=JSON_HEADERS)

    resp = client.post("/orders", content=body, headers=JSON_HEADERS)

    assert resp.status_code == 200
    assert resp.json()["status"] == "duplicate"
    assert len(fake.records) == 1


def test_post_orders_invalid_payload_returns_422(client: TestClient):
    bad = {"name": "#1001"}  # 缺 id 与 total_price

    resp = client.post("/orders", content=_body(bad), headers=JSON_HEADERS)

    assert resp.status_code == 422


def test_post_orders_feishu_failure_returns_502(client: TestClient, fake: FakeFeishu):
    fake.fail = True

    resp = client.post("/orders", content=_body(FIXTURE_ORDER), headers=JSON_HEADERS)

    assert resp.status_code == 502
    assert fake.records == []


def test_webhook_valid_hmac_returns_201(client: TestClient, fake: FakeFeishu):
    body = _body(FIXTURE_ORDER)
    headers = {**JSON_HEADERS, "X-Shopify-Hmac-Sha256": _sign(body)}

    resp = client.post("/webhooks/shopify", content=body, headers=headers)

    assert resp.status_code == 201
    assert resp.json()["status"] == "created"
    assert len(fake.records) == 1


def test_webhook_missing_signature_returns_401(client: TestClient, fake: FakeFeishu):
    body = _body(FIXTURE_ORDER)

    resp = client.post("/webhooks/shopify", content=body, headers=JSON_HEADERS)

    assert resp.status_code == 401
    assert fake.records == []


def test_webhook_wrong_signature_returns_401(client: TestClient, fake: FakeFeishu):
    body = _body(FIXTURE_ORDER)
    headers = {**JSON_HEADERS, "X-Shopify-Hmac-Sha256": _sign(body, secret="wrong")}

    resp = client.post("/webhooks/shopify", content=body, headers=headers)

    assert resp.status_code == 401
    assert fake.records == []


def test_webhook_duplicate_push_returns_200_and_single_record(
    client: TestClient, fake: FakeFeishu
):
    body = _body(FIXTURE_ORDER)
    headers = {**JSON_HEADERS, "X-Shopify-Hmac-Sha256": _sign(body)}
    first = client.post("/webhooks/shopify", content=body, headers=headers)
    second = client.post("/webhooks/shopify", content=body, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert len(fake.records) == 1


def test_daily_summary_counts_and_totals(client: TestClient):
    client.post("/orders", content=_body(FIXTURE_ORDER), headers=JSON_HEADERS)
    second = _order(id=820982911946154509, name="#1002", total_price="50.00")
    client.post("/orders", content=_body(second), headers=JSON_HEADERS)

    resp = client.get("/summary/daily", params={"date": "2026-11-19"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["date"] == "2026-11-19"
    assert data["count"] == 2
    assert data["total"] == pytest.approx(249.50)
    assert data["currency"] == "USD"
    assert isinstance(data["text"], str)
    assert "2026-11-19" in data["text"]


def test_daily_summary_empty_day(client: TestClient):
    resp = client.get("/summary/daily", params={"date": "2000-01-01"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["total"] == 0.0
    assert data["currency"] == ""
    assert isinstance(data["text"], str)


def test_daily_summary_notify_true_sends_message(client: TestClient, fake: FakeFeishu):
    client.post("/orders", content=_body(FIXTURE_ORDER), headers=JSON_HEADERS)
    before = len(fake.messages)

    resp = client.get(
        "/summary/daily", params={"date": "2026-11-19", "notify": "true"}
    )

    assert resp.status_code == 200
    assert len(fake.messages) == before + 1
    assert fake.messages[-1] == resp.json()["text"]


def test_daily_summary_without_notify_sends_nothing(client: TestClient, fake: FakeFeishu):
    before = len(fake.messages)

    resp = client.get("/summary/daily", params={"date": "2026-11-19"})

    assert resp.status_code == 200
    assert len(fake.messages) == before


def test_post_alerts_sends_prefixed_message(client: TestClient, fake: FakeFeishu):
    before = len(fake.messages)

    resp = client.post(
        "/alerts", content=_body({"text": "订单同步失败"}), headers=JSON_HEADERS
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "sent"}
    assert len(fake.messages) == before + 1
    assert fake.messages[-1].startswith("[告警] ")
    assert "订单同步失败" in fake.messages[-1]


def test_post_alerts_missing_text_returns_422(client: TestClient):
    resp = client.post("/alerts", content=_body({}), headers=JSON_HEADERS)

    assert resp.status_code == 422


def test_post_alerts_feishu_failure_returns_502(client: TestClient, fake: FakeFeishu):
    fake.fail = True

    resp = client.post(
        "/alerts", content=_body({"text": "订单同步失败"}), headers=JSON_HEADERS
    )

    assert resp.status_code == 502
