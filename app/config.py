import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass
class Settings:
    shopify_webhook_secret: str = ""
    sqlite_path: str = "./data/orders.db"
    feishu_mode: str = "fake"  # "fake" | "real"


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """从环境变量读配置；env 为 None 时读 os.environ。"""
    source = os.environ if env is None else env
    return Settings(
        shopify_webhook_secret=source.get("SHOPIFY_WEBHOOK_SECRET", ""),
        sqlite_path=source.get("SQLITE_PATH", "./data/orders.db"),
        feishu_mode=source.get("FEISHU_MODE", "fake"),
    )
