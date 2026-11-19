import pytest

from app.db import OrderStore
from app.feishu import FakeFeishu, FeishuError
from app.models import Order
from app.service import build_daily_text, format_notification, process_order


def make_order(**overrides) -> Order:
    data = {
        "order_id": "5001",
        "order_number": "#1001",
        "customer_name": "Alice Smith",
        "email": "alice@example.com",
        "total": 99.5,
        "currency": "CNY",
        "created_at": "2026-11-18T10:00:00+08:00",
        "items": [{"title": "Book", "quantity": 2}],
    }
    data.update(overrides)
    return Order(**data)


# ---------- format_notification ----------

def test_format_notification_contains_order_number_customer_and_amount():
    order = make_order()

    text = format_notification(order)

    assert "#1001" in text
    assert "Alice Smith" in text
    assert "99.5" in text
    assert "CNY" in text


def test_format_notification_uses_amount_from_order():
    order = make_order(order_number="#2002", customer_name="Bob", total=12.0, currency="USD")

    text = format_notification(order)

    assert "#2002" in text
    assert "Bob" in text
    assert "12" in text
    assert "USD" in text


# ---------- build_daily_text ----------

def test_build_daily_text_contains_date_count_and_total():
    summary = {
        "date": "2026-11-18",
        "count": 3,
        "total": 256.8,
        "currency": "CNY",
    }

    text = build_daily_text(summary)

    assert "2026-11-18" in text
    assert "3" in text
    assert "256.8" in text
    assert "CNY" in text


def test_build_daily_text_zero_orders():
    summary = {"date": "2026-11-18", "count": 0, "total": 0.0, "currency": ""}

    text = build_daily_text(summary)

    assert "2026-11-18" in text
    assert "0" in text


# ---------- process_order ----------

@pytest.fixture
def store():
    s = OrderStore(":memory:")
    yield s


@pytest.fixture
def feishu():
    return FakeFeishu()


def test_process_order_new_order_is_created_and_feishu_called_once_each(store, feishu):
    order = make_order()

    result = process_order(order, store, feishu)

    assert result["status"] == "created"
    assert result["order_id"] == order.order_id
    assert result["record_id"] == "rec_1"
    assert len(feishu.records) == 1
    assert len(feishu.messages) == 1


def test_process_order_duplicate_returns_duplicate_and_skips_feishu(store, feishu):
    order = make_order()
    process_order(order, store, feishu)

    result = process_order(order, store, feishu)

    assert result == {"status": "duplicate", "order_id": order.order_id}
    assert len(feishu.records) == 1
    assert len(feishu.messages) == 1


def test_process_order_feishu_failure_raises_and_removes_order_from_store(store, feishu):
    order = make_order()
    feishu.fail = True

    with pytest.raises(FeishuError):
        process_order(order, store, feishu)

    # 订单已从 store 删除：同一订单可以再次插入
    assert store.insert_if_new(order) is True


def test_process_order_retry_succeeds_after_feishu_recovers(store, feishu):
    order = make_order()
    feishu.fail = True

    with pytest.raises(FeishuError):
        process_order(order, store, feishu)

    feishu.fail = False
    result = process_order(order, store, feishu)

    assert result["status"] == "created"
    assert result["order_id"] == order.order_id
    assert result["record_id"] == "rec_1"
    assert len(feishu.records) == 1
    assert len(feishu.messages) == 1
