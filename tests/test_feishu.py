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


def test_real_add_record_not_implemented():
    feishu = RealFeishu()

    with pytest.raises(NotImplementedError, match="Feishu not connected yet"):
        feishu.add_record({"订单号": "#1001"})


def test_real_send_message_not_implemented():
    feishu = RealFeishu()

    with pytest.raises(NotImplementedError, match="Feishu not connected yet"):
        feishu.send_message("hello")
