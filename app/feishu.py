"""飞书客户端（依据 docs/SPEC.md 的 app/feishu.py 一节）。"""

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

import httpx


class FeishuError(Exception):
    """飞书调用失败。"""


class FeishuClient(Protocol):
    def add_record(self, fields: dict) -> str: ...

    def send_message(self, text: str) -> None: ...


@dataclass
class FakeFeishu:
    """内存模拟，测试和 demo 用。"""

    records: list[dict] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    fail: bool = False

    def add_record(self, fields: dict) -> str:
        if self.fail:
            raise FeishuError("fake feishu failure")
        self.records.append(fields)
        return f"rec_{len(self.records)}"

    def send_message(self, text: str) -> None:
        if self.fail:
            raise FeishuError("fake feishu failure")
        self.messages.append(text)


_BASE = "https://open.feishu.cn/open-apis"
_TOKEN_EXPIRED_CODES = {99991663, 99991668, 99991661}


class RealFeishu:
    """真实飞书：多维表格新增记录 + 群自定义机器人通知。

    错误信息只含接口 code/msg，不含 secret、token。
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        app_token: str,
        table_id: str,
        bot_webhook: str = "",
        bot_secret: str = "",
        client: httpx.Client | None = None,
        chat_id: str = "",
    ) -> None:
        self.chat_id = chat_id
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token
        self.table_id = table_id
        self.bot_webhook = bot_webhook
        self.bot_secret = bot_secret
        self._client = client or httpx.Client(timeout=10)
        self._token = ""
        self._token_expires_at = 0.0

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "RealFeishu":
        for key in (
            "FEISHU_APP_ID",
            "FEISHU_APP_SECRET",
            "FEISHU_BITABLE_APP_TOKEN",
            "FEISHU_BITABLE_TABLE_ID",
        ):
            if not env.get(key):
                raise ValueError(f"missing env {key}")
        return cls(
            app_id=env["FEISHU_APP_ID"],
            app_secret=env["FEISHU_APP_SECRET"],
            app_token=env["FEISHU_BITABLE_APP_TOKEN"],
            table_id=env["FEISHU_BITABLE_TABLE_ID"],
            bot_webhook=env.get("FEISHU_BOT_WEBHOOK", ""),
            bot_secret=env.get("FEISHU_BOT_SECRET", ""),
            chat_id=env.get("FEISHU_CHAT_ID", ""),
        )

    def _post(self, url: str, **kwargs) -> dict:
        try:
            resp = self._client.post(url, **kwargs)
            if resp.status_code >= 400:
                detail = ""
                try:
                    body = resp.json()
                    detail = f" code={body.get('code')} msg={body.get('msg')}"
                except ValueError:
                    pass
                raise FeishuError(f"feishu http {resp.status_code}{detail}")
            return resp.json()
        except FeishuError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise FeishuError(f"feishu request failed: {type(exc).__name__}") from exc

    def _get_token(self, force: bool = False) -> str:
        if not force and self._token and time.time() < self._token_expires_at:
            return self._token
        data = self._post(
            f"{_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        if data.get("code") != 0 or not data.get("tenant_access_token"):
            raise FeishuError(f"feishu token error code={data.get('code')} msg={data.get('msg')}")
        self._token = data["tenant_access_token"]
        self._token_expires_at = time.time() + max(int(data.get("expire", 7200)) - 300, 0)
        return self._token

    def _authed_post(self, url: str, **kwargs) -> dict:
        """带 tenant token 的 POST；token 过期（99991663 等）时刷新并重试一次。"""
        data: dict = {}
        for attempt in range(2):
            token = self._get_token(force=attempt == 1)
            data = self._post(url, headers={"Authorization": f"Bearer {token}"}, **kwargs)
            if data.get("code") in _TOKEN_EXPIRED_CODES and attempt == 0:
                continue
            break
        return data

    def add_record(self, fields: dict) -> str:
        url = f"{_BASE}/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"
        data = self._authed_post(url, json={"fields": fields})
        if data.get("code") != 0:
            raise FeishuError(f"feishu bitable error code={data.get('code')} msg={data.get('msg')}")
        return data["data"]["record"]["record_id"]

    def send_message(self, text: str) -> None:
        if self.chat_id:
            data = self._authed_post(
                f"{_BASE}/im/v1/messages?receive_id_type=chat_id",
                json={
                    "receive_id": self.chat_id,
                    "msg_type": "text",
                    "content": json.dumps({"text": text}, ensure_ascii=False),
                },
            )
            if data.get("code") != 0:
                raise FeishuError(f"feishu im error code={data.get('code')} msg={data.get('msg')}")
            return
        if not self.bot_webhook:
            raise FeishuError("feishu bot webhook not configured")
        body: dict = {"msg_type": "text", "content": {"text": text}}
        if self.bot_secret:
            ts = str(int(time.time()))
            sign = base64.b64encode(
                hmac.new(f"{ts}\n{self.bot_secret}".encode(), b"", hashlib.sha256).digest()
            ).decode()
            body["timestamp"] = ts
            body["sign"] = sign
        data = self._post(self.bot_webhook, json=body)
        if data.get("code", data.get("StatusCode", 0)) != 0:
            raise FeishuError(f"feishu bot error code={data.get('code')} msg={data.get('msg')}")
