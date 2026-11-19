from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Order:
    order_id: str        # Shopify 的 id 转成 str
    order_number: str    # name 字段，如 "#1001"
    customer_name: str   # "first last"，缺失时 "Guest"
    email: str           # 缺失时 ""
    total: float         # total_price 转 float
    currency: str
    created_at: str      # ISO 字符串原样保留
    items: list[dict]    # [{"title": str, "quantity": int}]


def _customer_name(payload: dict) -> str:
    customer = payload.get("customer") or {}
    name = " ".join(
        part for part in (customer.get("first_name"), customer.get("last_name")) if part
    ).strip()
    return name or "Guest"


def parse_shopify_order(payload: dict) -> Order:
    """把 Shopify 订单 JSON 解析成 Order。不修改 payload。缺 id 或 total_price 抛 ValueError。"""
    if payload.get("id") is None:
        raise ValueError("Shopify order payload missing 'id'")
    if payload.get("total_price") is None:
        raise ValueError("Shopify order payload missing 'total_price'")

    try:
        total = float(payload["total_price"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid total_price: {payload['total_price']!r}") from exc

    items = [
        {"title": str(item.get("title", "")), "quantity": int(item.get("quantity", 0))}
        for item in (payload.get("line_items") or [])
    ]

    return Order(
        order_id=str(payload["id"]),
        order_number=str(payload.get("name", "")),
        customer_name=_customer_name(payload),
        email=payload.get("email") or "",
        total=total,
        currency=str(payload.get("currency", "")),
        created_at=str(payload.get("created_at", "")),
        items=items,
    )


def to_feishu_fields(order: Order) -> dict:
    """转成飞书多维表格记录字段。下单时间为毫秒时间戳（int）。"""
    created = datetime.fromisoformat(order.created_at)
    items_text = ", ".join(f"{item['title']} x{item['quantity']}" for item in order.items)

    return {
        "订单号": order.order_number,
        "客户": order.customer_name,
        "邮箱": order.email,
        "金额": float(order.total),
        "币种": order.currency,
        "下单时间": int(created.timestamp() * 1000),
        "商品": items_text,
    }
