# n8n 工作流

三个工作流文件，都可以在 n8n 界面直接导入：

| 文件 | 作用 |
|---|---|
| `order-flow.json` | Webhook（POST，path `shopify-order`）→ `POST http://api:8000/orders` |
| `daily-summary.json` | 每天 20:00 → `GET http://api:8000/summary/daily?notify=true` |
| `error-workflow.json` | Error Trigger → `POST http://api:8000/alerts`（body `{"text": "..."}`） |

## 1. 启动

```bash
cp .env.example .env   # 填好配置
docker compose up -d
```

n8n 界面：http://127.0.0.1:5678（首次进入需要创建账号）。在 n8n 里访问 API 用 `http://api:8000`，不要用 `127.0.0.1`。

## 2. 导入工作流

1. 左上角菜单 → **Import from file**，选择 `n8n/error-workflow.json`
2. 再导入 `n8n/order-flow.json` 和 `n8n/daily-summary.json`
3. 导入后各工作流默认未激活，确认无误后打开右上角 **Active** 开关

## 3. 设置 Error Workflow

先导入并保存 `error-workflow`，然后对另外两个工作流分别操作：

1. 打开 `order-flow`（或 `daily-summary`）→ 右上角 **⋯** → **Settings**
2. **Error Workflow** 下拉框选择 `error-workflow`
3. 保存

这样订单流或日报出错时，错误信息会自动 POST 到 `/alerts`。

## 4. 用 cloudflared 暴露 5678 给 Shopify

Shopify 需要公网地址才能推送 webhook，本地开发可以用 cloudflared 做临时隧道：

```bash
cloudflared tunnel --url http://localhost:5678
```

终端会输出一个 `https://xxxx.trycloudflare.com` 地址。在 Shopify 后台（或开发店）添加 `orders/create` webhook，地址填：

```
https://xxxx.trycloudflare.com/webhook/shopify-order
```

注意：
- Webhook 路径前缀是 `/webhook/`（生产 URL）；`/webhook-test/` 只在界面点 Listen 时有效，用于调试。
- 隧道地址每次重启都会变，变了要回 Shopify 后台更新。
- 日报 20:00 按 n8n 容器的时区执行，如需改时区，在 compose 的 n8n 服务里加 `TZ=Asia/Shanghai` 或 `GENERIC_TIMEZONE=Asia/Shanghai`。
