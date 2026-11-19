"""OrderStore 测试（依据 docs/SPEC.md 的 app/db.py 一节）。"""

import os

from app.db import OrderStore
from app.models import Order


def make_order(
    order_id: str = "1001",
    created_at: str = "2026-11-18T10:00:00+08:00",
    total: float = 10.0,
    currency: str = "CNY",
) -> Order:
    return Order(
        order_id=order_id,
        order_number=f"#{order_id}",
        customer_name="Test Buyer",
        email="buyer@example.com",
        total=total,
        currency=currency,
        created_at=created_at,
        items=[{"title": "Sample", "quantity": 1}],
    )


# ---------- 初始化 ----------

def test_memory_db_initializes():
    store = OrderStore(":memory:")
    # 自动建表后应能直接写入和查询
    assert store.insert_if_new(make_order("A1")) is True


def test_file_db_under_tmp_path(tmp_path):
    db_file = tmp_path / "orders.db"
    store = OrderStore(str(db_file))
    assert store.insert_if_new(make_order("F1")) is True
    assert db_file.exists()


def test_file_db_creates_missing_parent_dirs(tmp_path):
    db_file = tmp_path / "nested" / "deeper" / "orders.db"
    assert not db_file.parent.exists()

    store = OrderStore(str(db_file))

    assert db_file.parent.is_dir()
    assert os.path.exists(db_file)
    assert store.insert_if_new(make_order("P1")) is True


def test_file_db_persists_across_instances(tmp_path):
    db_file = str(tmp_path / "persist.db")
    OrderStore(db_file).insert_if_new(make_order("R1"))

    reopened = OrderStore(db_file)
    assert reopened.insert_if_new(make_order("R1")) is False


# ---------- insert_if_new ----------

def test_insert_new_order_returns_true():
    store = OrderStore(":memory:")
    assert store.insert_if_new(make_order("N1")) is True


def test_insert_duplicate_order_returns_false():
    store = OrderStore(":memory:")
    store.insert_if_new(make_order("D1"))
    assert store.insert_if_new(make_order("D1")) is False


def test_insert_different_orders_both_true():
    store = OrderStore(":memory:")
    assert store.insert_if_new(make_order("X1")) is True
    assert store.insert_if_new(make_order("X2")) is True


# ---------- delete ----------

def test_delete_allows_reinsert():
    store = OrderStore(":memory:")
    store.insert_if_new(make_order("T1"))
    store.delete("T1")
    assert store.insert_if_new(make_order("T1")) is True


def test_delete_unknown_order_does_not_raise():
    store = OrderStore(":memory:")
    store.delete("never-existed")  # 不应抛异常


def test_delete_only_removes_target_order():
    store = OrderStore(":memory:")
    store.insert_if_new(make_order("K1"))
    store.insert_if_new(make_order("K2"))
    store.delete("K1")
    assert store.insert_if_new(make_order("K2")) is False
    assert store.insert_if_new(make_order("K1")) is True


# ---------- daily_summary ----------

def test_daily_summary_count_total_currency():
    store = OrderStore(":memory:")
    store.insert_if_new(make_order("S1", "2026-11-18T09:00:00+08:00", 10.10, "CNY"))
    store.insert_if_new(make_order("S2", "2026-11-18T18:30:00+08:00", 20.20, "CNY"))

    summary = store.daily_summary("2026-11-18")

    assert summary["date"] == "2026-11-18"
    assert summary["count"] == 2
    assert summary["total"] == 30.30
    assert summary["currency"] == "CNY"


def test_daily_summary_total_rounded_to_two_decimals():
    store = OrderStore(":memory:")
    # 0.1 + 0.2 在浮点下是 0.30000000000000004，应保留 2 位
    store.insert_if_new(make_order("R1", "2026-11-18T09:00:00+08:00", 0.1, "USD"))
    store.insert_if_new(make_order("R2", "2026-11-18T10:00:00+08:00", 0.2, "USD"))

    summary = store.daily_summary("2026-11-18")

    assert summary["total"] == 0.3
    assert round(summary["total"], 2) == summary["total"]


def test_daily_summary_only_counts_matching_day():
    store = OrderStore(":memory:")
    store.insert_if_new(make_order("Y1", "2026-11-17T23:59:59+08:00", 100.0, "CNY"))
    store.insert_if_new(make_order("T1", "2026-11-18T00:00:00+08:00", 5.5, "CNY"))
    store.insert_if_new(make_order("T2", "2026-11-18T12:00:00+08:00", 4.5, "CNY"))
    store.insert_if_new(make_order("N1", "2026-11-19T08:00:00+08:00", 50.0, "CNY"))

    summary = store.daily_summary("2026-11-18")

    assert summary["count"] == 2
    assert summary["total"] == 10.0
    assert summary["currency"] == "CNY"


def test_daily_summary_empty_day_returns_zero_values():
    store = OrderStore(":memory:")
    store.insert_if_new(make_order("E1", "2026-11-18T09:00:00+08:00", 99.0, "CNY"))

    summary = store.daily_summary("2026-11-20")

    assert summary == {
        "date": "2026-11-20",
        "count": 0,
        "total": 0.0,
        "currency": "",
    }


def test_daily_summary_empty_store_returns_zero_values():
    store = OrderStore(":memory:")

    summary = store.daily_summary("2026-11-18")

    assert summary["count"] == 0
    assert summary["total"] == 0.0
    assert summary["currency"] == ""


def test_daily_summary_after_delete_excludes_order():
    store = OrderStore(":memory:")
    store.insert_if_new(make_order("G1", "2026-11-18T09:00:00+08:00", 10.0, "CNY"))
    store.insert_if_new(make_order("G2", "2026-11-18T10:00:00+08:00", 5.0, "CNY"))
    store.delete("G1")

    summary = store.daily_summary("2026-11-18")

    assert summary["count"] == 1
    assert summary["total"] == 5.0
