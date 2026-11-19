"""SQLite 订单存储（依据 docs/SPEC.md 的 app/db.py 一节）。"""

import json
import os
import sqlite3

from app.models import Order


class OrderStore:
    def __init__(self, path: str):
        if path != ":memory:":
            parent = os.path.dirname(os.path.abspath(path))
            os.makedirs(parent, exist_ok=True)
        # FastAPI 在线程池里执行同步/异步处理函数，连接需允许跨线程使用
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id     TEXT PRIMARY KEY,
                order_number TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                email        TEXT NOT NULL,
                total        REAL NOT NULL,
                currency     TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                items        TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def insert_if_new(self, order: Order) -> bool:
        cur = self._conn.execute(
            """
            INSERT OR IGNORE INTO orders
                (order_id, order_number, customer_name, email, total, currency, created_at, items)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order.order_id,
                order.order_number,
                order.customer_name,
                order.email,
                order.total,
                order.currency,
                order.created_at,
                json.dumps(order.items, ensure_ascii=False),
            ),
        )
        self._conn.commit()
        return cur.rowcount == 1

    def delete(self, order_id: str) -> None:
        self._conn.execute("DELETE FROM orders WHERE order_id = ?", (order_id,))
        self._conn.commit()

    def daily_summary(self, day: str) -> dict:
        count, total = self._conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(total), 0) FROM orders "
            "WHERE substr(created_at, 1, 10) = ?",
            (day,),
        ).fetchone()
        currency_row = self._conn.execute(
            "SELECT currency FROM orders WHERE substr(created_at, 1, 10) = ? "
            "ORDER BY created_at LIMIT 1",
            (day,),
        ).fetchone()
        return {
            "date": day,
            "count": int(count),
            "total": round(float(total), 2),
            "currency": currency_row[0] if currency_row else "",
        }
