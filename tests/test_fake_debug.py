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


def _body(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


class NonFakeFeishu:
    """最小的非 Fake 客户端：只有 add_record / send_message，不是 FakeFeishu 子类。"""

    def __init__(self) -> None:
        self.records: list[dict] = []
        self.messages: list[str] = []

    def add_record(self, fields: dict) -> str:
        self.records.append(fields)
        return f"rec_{len(self.records)}"

    def send_message(self, text: str) -> None:
        self.messages.append(text)


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


def test_fake_debug_initially_empty(client: TestClient):
    resp = client.get("/fake/feishu")

    assert resp.status_code == 200
    assert resp.json() == {"records": [], "messages": []}


def test_fake_debug_reflects_created_order(client: TestClient):
    client.post("/orders", content=_body(FIXTURE_ORDER), headers=JSON_HEADERS)

    resp = client.get("/fake/feishu")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["records"]) == 1
    assert len(data["messages"]) == 1


def test_fake_debug_fail_toggle_causes_502_then_recovers(client: TestClient):
    resp = client.post("/fake/feishu/fail", params={"on": "true"})
    assert resp.status_code == 200
    assert resp.json() == {"fail": True}

    failed = client.post("/orders", content=_body(FIXTURE_ORDER), headers=JSON_HEADERS)
    assert failed.status_code == 502

    resp = client.post("/fake/feishu/fail", params={"on": "false"})
    assert resp.status_code == 200
    assert resp.json() == {"fail": False}

    retried = client.post("/orders", content=_body(FIXTURE_ORDER), headers=JSON_HEADERS)
    assert retried.status_code == 201


def test_fake_debug_absent_for_non_fake_client():
    settings = Settings(
        shopify_webhook_secret=SECRET,
        sqlite_path=":memory:",
        feishu_mode="fake",
    )
    app = create_app(settings, OrderStore(":memory:"), NonFakeFeishu())
    client = TestClient(app)

    resp = client.get("/fake/feishu")

    assert resp.status_code == 404
