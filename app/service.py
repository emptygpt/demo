"""订单处理服务（依据 docs/SPEC.md 的 app/service.py 一节）。"""

from app.db import OrderStore
from app.feishu import FeishuClient, FeishuError
from app.models import Order, to_feishu_fields


def format_notification(order: Order) -> str:
    """飞书通知文本：订单号、客户、金额+币种。"""
    return (
        f"新订单 {order.order_number}\n"
        f"客户：{order.customer_name}\n"
        f"金额：{order.total:.2f} {order.currency}"
    )


def process_order(order: Order, store: OrderStore, feishu: FeishuClient) -> dict:
    """处理一笔订单。

    重复订单直接返回 duplicate，不调用飞书。
    新订单：入库 → 写飞书记录 → 发通知。飞书任一步失败时，
    从 store 删除该订单后重新抛出 FeishuError，保证重试可以再次处理。
    """
    if not store.insert_if_new(order):
        return {"status": "duplicate", "order_id": order.order_id}

    try:
        record_id = feishu.add_record(to_feishu_fields(order))
        feishu.send_message(format_notification(order))
    except FeishuError:
        store.delete(order.order_id)
        raise

    return {"status": "created", "order_id": order.order_id, "record_id": record_id}


def build_daily_text(summary: dict) -> str:
    """日汇总文本：日期、订单数、金额。"""
    return (
        f"{summary['date']} 订单日报\n"
        f"订单数：{summary['count']}\n"
        f"总金额：{summary['total']:.2f} {summary['currency']}".rstrip()
    )
