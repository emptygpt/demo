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

## 目录

```
app/            FastAPI 服务
  main.py       入口
.env.example    配置样例（复制为 .env，不提交）
requirements.txt
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
| D1 | 飞书打通 | 写入多维表格 1 行 + 机器人发 1 条消息 |
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
