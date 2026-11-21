# 个人公司自动化运营 Demo（MVP）

Shopify 新订单 → n8n → Python（FastAPI）→ 飞书多维表格 + 飞书机器人通知，外加每日订单汇总。

## 架构

```
Shopify (orders/create webhook)
   │  HMAC 签名
   ▼
n8n  Webhook ──HTTP──▶  Python / FastAPI
                          ├─ 校验、清洗、字段映射
                          ├─ SQLite（order_id 去重 + 日报数据源）
                          ├─ 飞书 Bitable：新增记录
                          └─ 飞书群机器人：订单通知
n8n  Schedule ──HTTP──▶  GET /summary/daily ──▶ 飞书日报
n8n  Error Workflow ────▶ 飞书告警
```

## 当前状态

飞书部分用 `FakeFeishu` 内存模拟（`FEISHU_MODE=fake`，默认），其余已完成并有测试覆盖（TDD，83 个用例）。
`RealFeishu` 已实现（多维表格写记录 + 应用机器人按群 id 发消息），设 `FEISHU_MODE=real` 并填好飞书配置即可启用，见下文「接入真实飞书」。

## 目录

```
app/            FastAPI 服务（models / security / db / feishu / service / config / main）
tests/          pytest 用例与样例订单 fixtures
n8n/            可导入的工作流：订单入口、每日汇总、错误告警
docs/SPEC.md    接口规范（测试和实现的依据）
Dockerfile, docker-compose.yml
.env.example    配置样例（复制为 .env，不提交）
```

## 接口

| 接口 | 说明 |
|---|---|
| `GET /health` | 健康检查 |
| `POST /orders` | 接收订单 JSON（n8n 调用），新单 201，重复 200 |
| `POST /webhooks/shopify` | 直连 Shopify，校验 `X-Shopify-Hmac-Sha256`，失败 401 |
| `GET /summary/daily?date=&notify=` | 日报，`notify=true` 同时推送 |
| `POST /alerts` | n8n Error Workflow 告警入口 |

## 测试

```bash
pip install -r requirements-dev.txt
pytest -q
```

## 假 Shopify（不需要开发店和隧道）

`app/simulator.py` 生成 Shopify 格式的假订单，带 HMAC 签名推到 webhook，可模拟重复推送：

```bash
SHOPIFY_WEBHOOK_SECRET=demo-secret uvicorn app.main:app &
python -m app.simulator --url http://127.0.0.1:8000 --secret demo-secret --count 5 --duplicate-every 2
curl http://127.0.0.1:8000/summary/daily
```

输出每次请求的状态码：新订单 201、重复 200、签名错 401。

## 带 n8n 的完整演示（Shopify、飞书都是模拟）

无需 Docker：`npx n8n start` + `uvicorn`。n8n 工作流里 API 地址是容器内的 `http://api:8000`，本地跑要换成 `http://127.0.0.1:<端口>`（详见 `n8n/README.md`）。

```
假 Shopify 订单 ─POST─▶ n8n /webhook/shopify-order ─▶ API /orders ─▶ SQLite + FakeFeishu
查看模拟飞书：GET /fake/feishu            注入故障：POST /fake/feishu/fail?on=true
```

已实测（2026-11-19，n8n + API 本地运行）：
- 5 个新订单 + 1 次重复推送 → 模拟飞书表 5 行、通知 5 条，日报 5 单 821.09 USD
- 坏订单（缺 total_price）→ n8n 执行失败 → Error Workflow → `/alerts` → 飞书收到 `[告警] [n8n 错误] ...`
- 飞书故障时下单 → 订单回滚不入库；恢复后同一订单重推成功，不丢单不重复
- 每日汇总：接口 `GET /summary/daily?notify=true` 已验证；n8n 的 20:00 定时触发未实测

## 本地运行

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填入飞书配置
uvicorn app.main:app --reload
curl http://127.0.0.1:8000/health
```

## 排期

| 天 | 卡点 | 完成标准 |
|---|---|---|
| D1（模拟）| 飞书打通（目前为 FakeFeishu，待接真实 API）| 写入多维表格 1 行 + 机器人发 1 条消息 |
| D2 | Python 服务 | `POST /orders`：清洗 → SQLite 去重 → 写飞书 → 通知；配 n8n Error Workflow |
| D3 | n8n 串联 | n8n Webhook → HTTP Request → Python，curl 样例订单走通 |
| D4（模拟）| 接 Shopify | 目前用 simulator 假订单 + HMAC 校验；真实开发店 + 隧道后续再接 |
| D5 | 日报 + 交付 | `GET /summary/daily` 定时推送；docker-compose、架构图、演示视频 |

## 验收标准

1. 下单后 10 秒内多维表格出现记录，并收到机器人通知
2. 同一订单重复推送，表里只有一行
3. 签名不对的请求返回 401
4. 飞书凭证错误时收到告警
5. 日报数字与 SQLite 一致
6. 新机器 `docker compose up` + 填 `.env`，10 分钟内跑起来

## 暂不做

CRM、ERP、财务系统、微服务、K8s、AI Agent、权限系统、数据仓库、前端页面、多店铺。

## 路线

- V1（当前）：API 对接 Demo
- V2：PostgreSQL、CRM、库存、客户管理、财务统计
- V3：AI 客服、AI 报表、智能运营分析

## 接入真实飞书

1. 开发者后台建自建应用，开通 `bitable:app`（读写）和 `im:message:send_as_bot`，发布版本；记下 App ID / Secret。
2. 新建多维表格，字段（名称和类型要一致）：订单号、客户、邮箱、商品（文本）；金额（数字）；币种（文本）；下单时间（日期）。
3. 在表格上「添加文档应用」，把应用加为**可编辑**；表格地址里 `/base/<app_token>`、`?table=<table_id>` 分别填入配置。
4. 把应用机器人拉进要通知的群，填 `FEISHU_CHAT_ID`。
5. 复制 `.env.example` 为 `.env`，填值（不要提交），设 `FEISHU_MODE=real`，缺少必填项时服务启动即报错，不会静默回退成假模式。

已实测（真实飞书，Shopify 为模拟器）：新订单写入多维表格并在群里收到通知，重复推送不重复写入，日报可推送到群。
已知限制：日报「今天」按本机日期取、订单时间按 UTC 存，跨时区时可能算出 0 单；机器人暂不能接收群消息（只发不收）。
