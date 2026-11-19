"""FastAPI 入口（依据 docs/SPEC.md 的 app/main.py 一节）。"""

import json
from datetime import date

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import Settings, load_settings
from app.db import OrderStore
from app.feishu import FakeFeishu, FeishuClient, FeishuError, RealFeishu
from app.models import parse_shopify_order
from app.security import verify_shopify_hmac
from app.service import build_daily_text, process_order

SIGNATURE_HEADER = "X-Shopify-Hmac-Sha256"


class AlertIn(BaseModel):
    text: str


def _parse_order_body(raw: bytes):
    """原始字节 → json → Order；非法 JSON、非对象或解析失败都转成 422。"""
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="invalid JSON body") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="order payload must be an object")
    try:
        return parse_shopify_order(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def create_app(settings: Settings, store: OrderStore, feishu: FeishuClient) -> FastAPI:
    app = FastAPI(title="Order Automation Demo")

    def _handle_order(order) -> JSONResponse:
        try:
            result = process_order(order, store, feishu)
        except FeishuError as exc:
            raise HTTPException(status_code=502, detail="feishu error") from exc
        status_code = 201 if result["status"] == "created" else 200
        return JSONResponse(content=result, status_code=status_code)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/orders")
    async def post_orders(request: Request) -> JSONResponse:
        order = _parse_order_body(await request.body())
        return _handle_order(order)

    @app.post("/webhooks/shopify")
    async def post_webhook_shopify(request: Request) -> JSONResponse:
        raw = await request.body()
        header = request.headers.get(SIGNATURE_HEADER)
        if not settings.shopify_webhook_secret or not verify_shopify_hmac(
            raw, header, settings.shopify_webhook_secret
        ):
            raise HTTPException(status_code=401, detail="invalid signature")
        order = _parse_order_body(raw)
        return _handle_order(order)

    @app.get("/summary/daily")
    def get_summary_daily(
        day: str | None = Query(default=None, alias="date"),
        notify: bool = False,
    ) -> dict:
        target = day or date.today().isoformat()
        summary = store.daily_summary(target)
        text = build_daily_text(summary)
        if notify:
            try:
                feishu.send_message(text)
            except FeishuError as exc:
                raise HTTPException(status_code=502, detail="feishu error") from exc
        return {**summary, "text": text}

    @app.post("/alerts")
    def post_alerts(body: AlertIn) -> dict:
        try:
            feishu.send_message("[告警] " + body.text)
        except FeishuError as exc:
            raise HTTPException(status_code=502, detail="feishu error") from exc
        return {"status": "sent"}

    if isinstance(feishu, FakeFeishu):

        @app.get("/fake/feishu")
        def get_fake_feishu() -> dict:
            return {"records": feishu.records, "messages": feishu.messages}

        @app.post("/fake/feishu/fail")
        def post_fake_feishu_fail(on: bool) -> dict:
            feishu.fail = on
            return {"fail": feishu.fail}

    return app


def _build_default_app() -> FastAPI:
    settings = load_settings()
    store = OrderStore(settings.sqlite_path)
    feishu: FeishuClient = RealFeishu() if settings.feishu_mode == "real" else FakeFeishu()
    return create_app(settings, store, feishu)


app = _build_default_app()
