import base64
import hashlib
import hmac
import json

import httpx
import pytest

from app.feishu import FakeFeishu, FeishuError, RealFeishu


def test_fake_add_record_records_fields_and_returns_incrementing_ids():
    feishu = FakeFeishu()

    first = feishu.add_record({"订单号": "#1001"})
    second = feishu.add_record({"订单号": "#1002"})

    assert first == "rec_1"
    assert second == "rec_2"
    assert feishu.records == [{"订单号": "#1001"}, {"订单号": "#1002"}]


def test_fake_send_message_appends_text():
    feishu = FakeFeishu()

    feishu.send_message("hello")
    feishu.send_message("world")

    assert feishu.messages == ["hello", "world"]


def test_fake_starts_empty():
    feishu = FakeFeishu()

    assert feishu.records == []
    assert feishu.messages == []
    assert feishu.fail is False


def test_fake_add_record_raises_when_fail_true():
    feishu = FakeFeishu()
    feishu.fail = True

    with pytest.raises(FeishuError):
        feishu.add_record({"订单号": "#1001"})

    assert feishu.records == []


def test_fake_send_message_raises_when_fail_true():
    feishu = FakeFeishu()
    feishu.fail = True

    with pytest.raises(FeishuError):
        feishu.send_message("hello")

    assert feishu.messages == []


# ---------- RealFeishu（用 httpx.MockTransport 模拟飞书） ----------

TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
RECORD_URL = "https://open.feishu.cn/open-apis/bitable/v1/apps/APPTOK/tables/TBL/records"
BOT_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/abc"


CHAT_URL = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"


def make_real(handler, secret="", bot_url=BOT_URL, chat_id=""):
    return RealFeishu(
        chat_id=chat_id,
        app_id="cli_x",
        app_secret="sec_x",
        app_token="APPTOK",
        table_id="TBL",
        bot_webhook=bot_url,
        bot_secret=secret,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def token_ok(request):
    return httpx.Response(200, json={"code": 0, "tenant_access_token": "t-1", "expire": 7200})


def test_real_add_record_gets_token_then_posts_fields():
    calls = []

    def handler(request):
        calls.append(request)
        if str(request.url) == TOKEN_URL:
            assert json.loads(request.content) == {"app_id": "cli_x", "app_secret": "sec_x"}
            return token_ok(request)
        assert str(request.url) == RECORD_URL
        assert request.headers["Authorization"] == "Bearer t-1"
        assert json.loads(request.content) == {"fields": {"订单号": "#1001"}}
        return httpx.Response(200, json={"code": 0, "data": {"record": {"record_id": "recABC"}}})

    assert make_real(handler).add_record({"订单号": "#1001"}) == "recABC"
    assert len(calls) == 2


def test_real_token_is_cached_between_calls():
    tokens = []

    def handler(request):
        if str(request.url) == TOKEN_URL:
            tokens.append(1)
            return token_ok(request)
        return httpx.Response(200, json={"code": 0, "data": {"record": {"record_id": "r"}}})

    feishu = make_real(handler)
    feishu.add_record({"a": 1})
    feishu.add_record({"a": 2})

    assert len(tokens) == 1


def test_real_expired_token_refreshes_and_retries_once():
    state = {"tokens": 0, "records": 0}

    def handler(request):
        if str(request.url) == TOKEN_URL:
            state["tokens"] += 1
            return httpx.Response(
                200, json={"code": 0, "tenant_access_token": f"t-{state['tokens']}", "expire": 7200}
            )
        state["records"] += 1
        if state["records"] == 1:
            return httpx.Response(200, json={"code": 99991663, "msg": "token invalid"})
        assert request.headers["Authorization"] == "Bearer t-2"
        return httpx.Response(200, json={"code": 0, "data": {"record": {"record_id": "recOK"}}})

    assert make_real(handler).add_record({"a": 1}) == "recOK"
    assert state == {"tokens": 2, "records": 2}


def test_real_add_record_api_error_raises_feishu_error_without_secrets():
    def handler(request):
        if str(request.url) == TOKEN_URL:
            return token_ok(request)
        return httpx.Response(200, json={"code": 1254045, "msg": "FieldNameNotFound"})

    with pytest.raises(FeishuError) as exc:
        make_real(handler).add_record({"x": 1})

    assert "1254045" in str(exc.value)
    assert "sec_x" not in str(exc.value)


def test_real_token_failure_raises_feishu_error():
    def handler(request):
        return httpx.Response(200, json={"code": 10003, "msg": "invalid param"})

    with pytest.raises(FeishuError):
        make_real(handler).add_record({"x": 1})


def test_real_network_error_raises_feishu_error():
    def handler(request):
        raise httpx.ConnectError("boom")

    with pytest.raises(FeishuError):
        make_real(handler).add_record({"x": 1})


def test_real_http_500_raises_feishu_error():
    def handler(request):
        if str(request.url) == TOKEN_URL:
            return token_ok(request)
        return httpx.Response(500, text="oops")

    with pytest.raises(FeishuError):
        make_real(handler).add_record({"x": 1})


def test_real_send_message_without_secret_posts_text():
    def handler(request):
        assert str(request.url) == BOT_URL
        body = json.loads(request.content)
        assert body == {"msg_type": "text", "content": {"text": "hello"}}
        return httpx.Response(200, json={"code": 0, "msg": "success"})

    make_real(handler).send_message("hello")


def test_real_send_message_with_secret_signs_request():
    def handler(request):
        body = json.loads(request.content)
        ts = body["timestamp"]
        expected = base64.b64encode(
            hmac.new(f"{ts}\nbotsec".encode(), b"", hashlib.sha256).digest()
        ).decode()
        assert body["sign"] == expected
        assert body["content"] == {"text": "hi"}
        return httpx.Response(200, json={"code": 0})

    make_real(handler, secret="botsec").send_message("hi")


def test_real_send_message_error_code_raises():
    def handler(request):
        return httpx.Response(200, json={"code": 19021, "msg": "sign match fail"})

    with pytest.raises(FeishuError):
        make_real(handler, secret="botsec").send_message("hi")


def test_real_send_message_without_webhook_raises():
    feishu = make_real(lambda r: httpx.Response(200, json={"code": 0}), bot_url="")

    with pytest.raises(FeishuError):
        feishu.send_message("hi")


def test_real_from_env_reads_all_values():
    env = {
        "FEISHU_APP_ID": "a",
        "FEISHU_APP_SECRET": "b",
        "FEISHU_BITABLE_APP_TOKEN": "c",
        "FEISHU_BITABLE_TABLE_ID": "d",
        "FEISHU_BOT_WEBHOOK": "https://x",
        "FEISHU_BOT_SECRET": "e",
    }
    feishu = RealFeishu.from_env(env)

    assert (feishu.app_id, feishu.app_token, feishu.table_id) == ("a", "c", "d")


@pytest.mark.parametrize(
    "missing", ["FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_BITABLE_APP_TOKEN", "FEISHU_BITABLE_TABLE_ID"]
)
def test_real_from_env_missing_required_raises(missing):
    env = {
        "FEISHU_APP_ID": "a",
        "FEISHU_APP_SECRET": "b",
        "FEISHU_BITABLE_APP_TOKEN": "c",
        "FEISHU_BITABLE_TABLE_ID": "d",
    }
    del env[missing]

    with pytest.raises(ValueError, match=missing):
        RealFeishu.from_env(env)


# ---------- 应用机器人按群 id 发消息 ----------


def test_real_send_message_via_chat_id_uses_app_bot_token():
    def handler(request):
        if str(request.url) == TOKEN_URL:
            return token_ok(request)
        assert str(request.url) == CHAT_URL
        assert request.headers["Authorization"] == "Bearer t-1"
        body = json.loads(request.content)
        assert body["receive_id"] == "oc_chat"
        assert body["msg_type"] == "text"
        assert json.loads(body["content"]) == {"text": "hello"}
        return httpx.Response(200, json={"code": 0, "data": {"message_id": "om_1"}})

    make_real(handler, chat_id="oc_chat").send_message("hello")


def test_real_chat_id_takes_priority_over_webhook():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if str(request.url) == TOKEN_URL:
            return token_ok(request)
        return httpx.Response(200, json={"code": 0})

    make_real(handler, chat_id="oc_chat", bot_url=BOT_URL).send_message("x")

    assert BOT_URL not in seen


def test_real_chat_message_expired_token_retries_once():
    state = {"tokens": 0, "sends": 0}

    def handler(request):
        if str(request.url) == TOKEN_URL:
            state["tokens"] += 1
            return httpx.Response(
                200, json={"code": 0, "tenant_access_token": f"t-{state['tokens']}", "expire": 7200}
            )
        state["sends"] += 1
        if state["sends"] == 1:
            return httpx.Response(200, json={"code": 99991663, "msg": "expired"})
        return httpx.Response(200, json={"code": 0})

    make_real(handler, chat_id="oc_chat").send_message("x")

    assert state == {"tokens": 2, "sends": 2}


def test_real_chat_message_error_code_raises():
    def handler(request):
        if str(request.url) == TOKEN_URL:
            return token_ok(request)
        return httpx.Response(200, json={"code": 230002, "msg": "bot not in chat"})

    with pytest.raises(FeishuError, match="230002"):
        make_real(handler, chat_id="oc_chat").send_message("x")


def test_real_chat_message_http_error_raises():
    def handler(request):
        if str(request.url) == TOKEN_URL:
            return token_ok(request)
        return httpx.Response(400, json={"code": 230002})

    with pytest.raises(FeishuError):
        make_real(handler, chat_id="oc_chat").send_message("x")


def test_real_from_env_reads_chat_id():
    env = {
        "FEISHU_APP_ID": "a",
        "FEISHU_APP_SECRET": "b",
        "FEISHU_BITABLE_APP_TOKEN": "c",
        "FEISHU_BITABLE_TABLE_ID": "d",
        "FEISHU_CHAT_ID": "oc_x",
    }

    assert RealFeishu.from_env(env).chat_id == "oc_x"


def test_real_http_error_includes_status_and_feishu_code():
    def handler(request):
        if str(request.url) == TOKEN_URL:
            return token_ok(request)
        return httpx.Response(403, json={"code": 91403, "msg": "Forbidden"})

    with pytest.raises(FeishuError) as exc:
        make_real(handler).add_record({"x": 1})

    assert "403" in str(exc.value)
    assert "91403" in str(exc.value)
