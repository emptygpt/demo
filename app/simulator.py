"""假 Shopify：生成订单、签名并推送到 /webhooks/shopify，替代真实联调。

依据 docs/SPEC.md 的 app/simulator.py 一节。
CLI: python -m app.simulator --url http://127.0.0.1:8000 --secret S --count 5 [--duplicate-every 3]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import random
from datetime import datetime, timezone
from typing import Callable

import httpx

FIRST_NAMES = ["Alice", "Bob", "Chen", "Dana", "Erik", "Fatima", "Gus", "Hana"]
LAST_NAMES = ["Smith", "Lee", "Garcia", "Kim", "Novak", "Patel", "Brown", "Wong"]
PRODUCTS = [
    "Classic Tee",
    "Canvas Tote",
    "Ceramic Mug",
    "Desk Mat",
    "Hoodie",
    "Sticker Pack",
    "Notebook",
    "Cap",
]


def make_fake_order(
    n: int,
    *,
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> dict:
    """生成第 n 单的 Shopify 订单 JSON。同 n、同 rng seed、同 now 结果一致。"""
    rng = rng if rng is not None else random.Random(n)
    now = now if now is not None else datetime.now(timezone.utc)

    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    total = max(5.0, round(rng.uniform(5, 500), 2))
    line_items = [
        {"title": rng.choice(PRODUCTS), "quantity": rng.randint(1, 3)}
        for _ in range(rng.randint(1, 3))
    ]

    return {
        "id": 1000000 + n,
        "name": f"#{1000 + n}",
        "email": f"{first.lower()}.{last.lower()}{n}@example.com",
        "customer": {"first_name": first, "last_name": last},
        "total_price": f"{total:.2f}",
        "currency": "USD",
        "created_at": now.isoformat(),
        "line_items": line_items,
    }


def sign_body(body: bytes, secret: str) -> str:
    """Shopify 风格签名：base64(HMAC-SHA256(secret, body))。"""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def send_orders(
    base_url: str,
    secret: str,
    count: int,
    *,
    post: Callable | None = None,
    start: int = 1,
    duplicate_every: int = 0,
) -> list[int]:
    """逐单 POST 到 {base_url}/webhooks/shopify，返回按发送顺序的状态码。

    duplicate_every=k>0 时，每第 k 单发完后再重发同一单一次（模拟 Shopify 重试）。
    """
    post = post if post is not None else httpx.post
    url = f"{base_url}/webhooks/shopify"
    statuses: list[int] = []

    for i in range(count):
        order = make_fake_order(start + i)
        body = json.dumps(order).encode("utf-8")
        headers = {
            "X-Shopify-Hmac-Sha256": sign_body(body, secret),
            "Content-Type": "application/json",
        }
        statuses.append(post(url, content=body, headers=headers).status_code)

        if duplicate_every > 0 and (i + 1) % duplicate_every == 0:
            statuses.append(post(url, content=body, headers=headers).status_code)

    return statuses


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="假 Shopify：向 webhook 推送模拟订单")
    parser.add_argument("--url", required=True, help="服务地址，如 http://127.0.0.1:8000")
    parser.add_argument("--secret", required=True, help="Shopify webhook 密钥")
    parser.add_argument("--count", type=int, default=5, help="订单数量，默认 5")
    parser.add_argument(
        "--duplicate-every",
        type=int,
        default=0,
        help="每第 k 单后重发一次同一单，0 表示不重发",
    )
    args = parser.parse_args(argv)

    statuses = send_orders(
        args.url,
        args.secret,
        args.count,
        duplicate_every=args.duplicate_every,
    )
    for index, status in enumerate(statuses, start=1):
        print(f"{index}\t{status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
