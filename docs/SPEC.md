# 接口规范（TDD 依据，测试和实现都以此为准）

Python 3.12，包名 `app`，测试用 pytest（`tests/`），HTTP 测试用 fastapi.testclient。禁止真实网络请求。

## app/models.py
```python
@dataclass(frozen=True)
class Order:
    order_id: str        # Shopify 的 id 转成 str
    order_number: str    # name 字段，如 "#1001"
    customer_name: str   # "first last"，缺失时 "Guest"
    email: str           # 缺失时 ""
    total: float         # total_price 转 float
    currency: str
    created_at: str      # ISO 字符串原样保留
    items: list[dict]    # [{"title": str, "quantity": int}]

def parse_shopify_order(payload: dict) -> Order   # 缺 id 或 total_price 抛 ValueError
def to_feishu_fields(order: Order) -> dict
```
`to_feishu_fields` 返回键：订单号、客户、邮箱、金额(float)、币种、下单时间(int，毫秒时间戳，由 created_at 解析)、商品(字符串 "A x2, B x1")。

## app/security.py
`verify_shopify_hmac(body: bytes, header: str | None, secret: str) -> bool`
HMAC-SHA256(secret, body) 的 base64 与 header 用 hmac.compare_digest 比较；header 为空/None 返回 False。

## app/db.py
```python
class OrderStore:
    def __init__(self, path: str)           # ":memory:" 可用；自动建表；父目录不存在则创建
    def insert_if_new(self, order: Order) -> bool   # 新订单 True，order_id 已存在 False
    def delete(self, order_id: str) -> None
    def daily_summary(self, day: str) -> dict       # day="YYYY-MM-DD"，按 created_at 前 10 位匹配
        # {"date": day, "count": int, "total": float(保留 2 位), "currency": str}  无订单 count=0,total=0.0,currency=""
```

## app/feishu.py
```python
class FeishuError(Exception)
class FeishuClient(Protocol):
    def add_record(self, fields: dict) -> str     # 返回 record_id
    def send_message(self, text: str) -> None
class FakeFeishu:                                  # 内存模拟，测试和 demo 用
    records: list[dict]; messages: list[str]
    fail: bool = False                             # True 时两个方法都抛 FeishuError
    add_record 追加 fields 并返回 "rec_<序号>"；send_message 追加 text
class RealFeishu:                                  # 已实现：add_record 写多维表格，send_message 按 FEISHU_CHAT_ID 发群消息（无群 id 时退回机器人 Webhook）
    所有方法 raise NotImplementedError("Feishu not connected yet")
```

## app/service.py
```python
def format_notification(order: Order) -> str   # 含订单号、客户、金额+币种
def process_order(order: Order, store: OrderStore, feishu: FeishuClient) -> dict
    # 重复订单: {"status":"duplicate","order_id":...}，不调飞书
    # 新订单: insert_if_new → add_record → send_message → {"status":"created","order_id":...,"record_id":...}
    # 飞书任一步抛 FeishuError：store.delete(order_id) 后重新抛出（保证重试可再处理）
def build_daily_text(summary: dict) -> str     # 含日期、订单数、金额
```

## app/config.py
`Settings`（dataclass）：shopify_webhook_secret, sqlite_path, feishu_mode("fake"|"real", 默认 "fake")；`load_settings(env: Mapping|None=None)` 从环境变量读 SHOPIFY_WEBHOOK_SECRET / SQLITE_PATH(默认 ./data/orders.db) / FEISHU_MODE。

## app/main.py
`create_app(settings: Settings, store: OrderStore, feishu: FeishuClient) -> FastAPI`；模块级 `app` 用 load_settings 构建（fake 模式用 FakeFeishu，real 用 RealFeishu）。
- `GET /health` → {"status":"ok"}
- `POST /orders`：body 为 Shopify 订单 JSON（n8n 已校验时用），无签名要求 → process_order；非法 payload 422；FeishuError → 502
- `POST /webhooks/shopify`：必须 `X-Shopify-Hmac-Sha256` 校验原始 body，失败 401；通过后同 /orders
- `GET /summary/daily?date=YYYY-MM-DD`（缺省今天）→ daily_summary 加 "text": build_daily_text；`?notify=true` 时同时 feishu.send_message(text)
- 根据 `/orders` 与 webhook 的返回：duplicate 200，created 201
- `POST /alerts`：body `{"text": str}`（n8n Error Workflow 调用）→ feishu.send_message("[告警] " + text) → 200 {"status":"sent"}；缺 text 422；FeishuError 502

## app/simulator.py（假 Shopify，替代真实联调）
```python
def make_fake_order(n: int, *, now: datetime | None = None, rng: random.Random | None = None) -> dict
    # Shopify 订单 JSON：id=1000000+n（int），name="#<1000+n>"，email、customer(first/last)、
    # total_price(字符串，2位小数，>0)、currency="USD"、created_at(ISO，取 now，缺省当前时间)、
    # line_items(1~3 项，title/quantity)。必须能被 parse_shopify_order 解析；同 n 同 rng seed 结果一致
def sign_body(body: bytes, secret: str) -> str          # base64(HMAC-SHA256)，与 verify_shopify_hmac 配套
def send_orders(base_url: str, secret: str, count: int, *, post=None, start: int = 1, duplicate_every: int = 0) -> list[int]
    # 逐个 POST {base_url}/webhooks/shopify，body=json.dumps(order).encode()，header X-Shopify-Hmac-Sha256 + Content-Type
    # post 默认 httpx.post，签名 post(url, content=..., headers=...) -> 有 status_code 的对象
    # duplicate_every=k>0 时每第 k 单后再重发同一单一次（模拟 Shopify 重试）
    # 返回按发送顺序的 status_code 列表
```
CLI：`python -m app.simulator --url http://127.0.0.1:8000 --secret S --count 5 [--duplicate-every 3]`，打印每次状态码。

## 假飞书调试接口（仅 feishu 为 FakeFeishu 时注册，real 模式下不存在 → 404）
- `GET /fake/feishu` → {"records": [...], "messages": [...]}
- `POST /fake/feishu/fail?on=true|false` → 设置 fake.fail，返回 {"fail": bool}
