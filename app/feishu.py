"""飞书客户端（依据 docs/SPEC.md 的 app/feishu.py 一节）。"""

from dataclasses import dataclass, field
from typing import Protocol


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


class RealFeishu:
    """暂不实现。"""

    def add_record(self, fields: dict) -> str:
        raise NotImplementedError("Feishu not connected yet")

    def send_message(self, text: str) -> None:
        raise NotImplementedError("Feishu not connected yet")
