import json
import random
from collections import Counter
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import OrderStore
from app.feishu import FakeFeishu
from app.main import create_app
from app.models import parse_shopify_order
from app.security import verify_shopify_hmac
from app.simulator import make_fake_order, send_orders, sign_body

SECRET = "whsec_test_secret"
BASE_URL = "http://testserver"
NOW = datetime(2026, 11, 19, 10, 0, 0, tzinfo=timezone.utc)


# ---------- make_fake_order ----------

def test_make_fake_order_is_parseable_with_positive_total():
    for n in range(1, 21):
        order = make_fake_order(n, now=NOW, rng=random.Random(n))
        parsed = parse_shopify_order(order)
        assert parsed.total > 0


def test_make_fake_order_id_and_number_follow_n():
    order = make_fake_order(1, now=NOW, rng=random.Random(0))
    parsed = parse_shopify_order(order)

    assert parsed.order_id == str(1000001)
    assert parsed.order_number == "#1001"


def test_same_n_same_seed_gives_same_order():
    first = make_fake_order(7, now=NOW, rng=random.Random(42))
    second = make_fake_order(7, now=NOW, rng=random.Random(42))

    assert first == second


def test_different_n_gives_different_order_id():
    a = parse_shopify_order(make_fake_order(1, now=NOW, rng=random.Random(0)))
    b = parse_shopify_order(make_fake_order(2, now=NOW, rng=random.Random(0)))

    assert a.order_id != b.order_id


def test_now_is_used_for_created_at():
    order = make_fake_order(3, now=NOW, rng=random.Random(0))

    assert datetime.fromisoformat(order["created_at"]) == NOW


def test_line_items_count_is_between_1_and_3():
    for n in range(1, 31):
        order = make_fake_order(n, now=NOW, rng=random.Random(n))
        items = order["line_items"]

        assert 1 <= len(items) <= 3
        for item in items:
            assert isinstance(item["title"], str)
            assert isinstance(item["quantity"], int)
            assert item["quantity"] >= 1


# ---------- sign_body / verify_shopify_hmac ----------

def test_sign_body_passes_verify_shopify_hmac():
    body = json.dumps({"id": 1}).encode("utf-8")
    signature = sign_body(body, SECRET)

    assert verify_shopify_hmac(body, signature, SECRET) is True


def test_modified_body_fails_verify_shopify_hmac():
    body = json.dumps({"id": 1}).encode("utf-8")
    signature = sign_body(body, SECRET)
    tampered = json.dumps({"id": 2}).encode("utf-8")

    assert verify_shopify_hmac(tampered, signature, SECRET) is False


# ---------- send_orders with a fake post ----------

class RecordingPost:
    """Records every call and returns status codes in the given order."""

    def __init__(self, codes=None):
        self.calls = []
        self._codes = list(codes) if codes is not None else None

    def __call__(self, url, content=None, headers=None):
        self.calls.append({"url": url, "content": content, "headers": headers})
        if self._codes is None:
            code = 201
        else:
            code = self._codes[len(self.calls) - 1]
        return SimpleNamespace(status_code=code)


def test_send_orders_posts_to_webhook_with_valid_signature():
    post = RecordingPost()

    send_orders(BASE_URL, SECRET, 2, post=post)

    assert len(post.calls) == 2
    for call in post.calls:
        assert call["url"] == f"{BASE_URL}/webhooks/shopify"
        assert call["headers"]["Content-Type"] == "application/json"
        signature = call["headers"]["X-Shopify-Hmac-Sha256"]
        assert verify_shopify_hmac(call["content"], signature, SECRET) is True
        assert json.loads(call["content"])["id"] >= 1000001


def test_send_orders_returns_status_codes_in_send_order():
    post = RecordingPost(codes=[201, 200, 201])

    result = send_orders(BASE_URL, SECRET, 3, post=post)

    assert result == [201, 200, 201]


def test_send_orders_duplicate_every_3_with_count_6_sends_8_and_repeats_same_orders():
    post = RecordingPost()

    send_orders(BASE_URL, SECRET, 6, post=post, duplicate_every=3)

    assert len(post.calls) == 8
    ids = [json.loads(call["content"])["id"] for call in post.calls]
    counts = Counter(ids)
    assert counts[1000003] == 2
    assert counts[1000006] == 2
    for order_id in (1000001, 1000002, 1000004, 1000005):
        assert counts[order_id] == 1
    # the duplicates are consecutive re-sends of the same body
    assert post.calls[3]["content"] == post.calls[2]["content"]
    assert post.calls[7]["content"] == post.calls[6]["content"]


# ---------- integration: send_orders -> real app via TestClient ----------

def test_send_orders_into_app_creates_orders_and_summarises_them():
    fake = FakeFeishu()
    store = OrderStore(":memory:")
    settings = Settings(
        shopify_webhook_secret=SECRET,
        sqlite_path=":memory:",
        feishu_mode="fake",
    )
    client = TestClient(create_app(settings, store, fake))
    sent_bodies = []

    def post(url, content=None, headers=None):
        assert url.startswith(BASE_URL)
        sent_bodies.append(content)
        return client.post(url[len(BASE_URL):], content=content, headers=headers)

    statuses = send_orders(BASE_URL, SECRET, 5, post=post, duplicate_every=2)

    # 5 new orders plus a re-send after order 2 and after order 4
    assert len(statuses) == 7
    assert statuses.count(201) == 5
    assert statuses.count(200) == 2
    assert statuses == [201, 201, 200, 201, 201, 200, 201]

    assert len(fake.records) == 5

    day = json.loads(sent_bodies[0])["created_at"][:10]
    summary = store.daily_summary(day)
    assert summary["count"] == 5
