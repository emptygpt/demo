import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models import Order, parse_shopify_order, to_feishu_fields

FIXTURE = Path(__file__).parent / "fixtures" / "shopify_order.json"


def load_payload() -> dict:
    with FIXTURE.open(encoding="utf-8") as f:
        return json.load(f)


def test_parse_normal_order_from_fixture():
    order = parse_shopify_order(load_payload())

    assert isinstance(order, Order)
    assert order.order_id == "820982911946154508"
    assert order.order_number == "#1001"
    assert order.customer_name == "Jon Smith"
    assert order.email == "jon@example.com"
    assert order.total == 199.5
    assert isinstance(order.total, float)
    assert order.currency == "USD"
    assert order.created_at == "2026-11-19T10:30:00+08:00"
    assert order.items == [
        {"title": "Widget", "quantity": 2},
        {"title": "Gadget", "quantity": 1},
    ]


def test_parse_missing_id_raises_value_error():
    payload = load_payload()
    del payload["id"]

    with pytest.raises(ValueError):
        parse_shopify_order(payload)


def test_parse_missing_total_price_raises_value_error():
    payload = load_payload()
    del payload["total_price"]

    with pytest.raises(ValueError):
        parse_shopify_order(payload)


def test_parse_without_customer_uses_guest():
    payload = load_payload()
    del payload["customer"]

    order = parse_shopify_order(payload)

    assert order.customer_name == "Guest"


def test_parse_without_email_uses_empty_string():
    payload = load_payload()
    del payload["email"]

    order = parse_shopify_order(payload)

    assert order.email == ""


def test_to_feishu_fields_has_exact_keys():
    order = parse_shopify_order(load_payload())

    fields = to_feishu_fields(order)

    assert set(fields.keys()) == {
        "订单号",
        "客户",
        "邮箱",
        "金额",
        "币种",
        "下单时间",
        "商品",
    }


def test_to_feishu_fields_values_from_fixture():
    order = parse_shopify_order(load_payload())

    fields = to_feishu_fields(order)

    assert fields["订单号"] == "#1001"
    assert fields["客户"] == "Jon Smith"
    assert fields["邮箱"] == "jon@example.com"
    assert fields["币种"] == "USD"


def test_to_feishu_fields_amount_is_float():
    order = parse_shopify_order(load_payload())

    fields = to_feishu_fields(order)

    assert isinstance(fields["金额"], float)
    assert fields["金额"] == 199.5


def test_to_feishu_fields_timestamp_is_millisecond_int():
    order = parse_shopify_order(load_payload())

    fields = to_feishu_fields(order)

    # 2026-11-19T10:30:00+08:00 == 2026-11-19T02:30:00Z
    expected_ms = int(datetime(2026, 11, 19, 2, 30, tzinfo=timezone.utc).timestamp() * 1000)

    ts = fields["下单时间"]
    assert isinstance(ts, int)
    assert not isinstance(ts, bool)
    assert ts == expected_ms


def test_to_feishu_fields_items_is_string():
    order = parse_shopify_order(load_payload())

    fields = to_feishu_fields(order)

    assert isinstance(fields["商品"], str)
    assert fields["商品"] == "Widget x2, Gadget x1"


def test_parse_does_not_mutate_payload():
    payload = load_payload()
    snapshot = copy.deepcopy(payload)

    parse_shopify_order(payload)

    assert payload == snapshot
