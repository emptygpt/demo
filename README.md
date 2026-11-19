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

飞书部分用 `FakeFeishu` 内存模拟（`FEISHU_MODE=fake`，默认），其余已完成并有测试覆盖（TDD，67 个用例）。
`RealFeishu` 是占位，接入真实飞书时只需实现 `app/feishu.py` 里的两个方法。

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
| D4 | 接 Shopify | Partners 开发店 + 隧道，真实下单自动进表；HMAC 校验 |
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
