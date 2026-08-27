# sub2api-view

一个使用 `uv` 管理依赖的 Python + HTML 基础工程。

## 环境准备

```bash
uv sync
```

## 环境配置

复制 `.env.example` 为 `.env`，按需调整：

```env
APP_HOST=127.0.0.1
APP_PORT=8000
APP_RELOAD=true
SUB2API_BASE_URL=http://127.0.0.1:8080
SUB2API_ADMIN_KEY=your-admin-api-key
SUB2API_JWT_SECRET=your-sub2api-jwt-secret
```

`SUB2API_JWT_SECRET` 必须与 Sub2API 服务使用的 `JWT_SECRET` 完全一致。

## 启动服务

```bash
uv run python main.py
```

浏览器访问：

```text
http://127.0.0.1:8000/accounts?user_id=3&token=your-user-token
```

页面会校验 Sub2API 用户 Token。仅启用状态的用户可以访问，
验证通过后展示全部可调度账号。

## 自动重置订阅配额

调用下面的接口检测所有 OpenAI OAuth 账号。如果账号的 7 天额度窗口已经重置，
接口会自动重置该账号关联分组下所有活跃订阅的日、周、月配额：

```bash
curl -X POST \
  "http://127.0.0.1:8000/api/subscriptions/auto-reset?user_id=3" \
  -H "Authorization: Bearer your-admin-user-token"
```

该接口仅允许 Sub2API 管理员用户调用，并通过 `SUB2API_ADMIN_KEY` 调用
Sub2API 管理员 API。重复调用是安全的：已经在
当前 7 天窗口内重置过的订阅会被跳过。响应中会返回检查数量、重置数量以及失败明细，
单个账号或订阅失败不会中断其他数据的处理。

## Docker

构建镜像：

```bash
docker build -t sub2api-view .
```

启动容器：

```bash
docker run --rm -p 8000:8000 \
  -e SUB2API_BASE_URL=http://host.docker.internal:8080 \
  -e SUB2API_ADMIN_KEY=your-admin-api-key \
  -e SUB2API_JWT_SECRET=your-sub2api-jwt-secret \
  sub2api-view
```

使用 Docker Compose：

```bash
docker compose up -d
```

## 目录结构

```text
app/
  main.py          # FastAPI 应用入口
  routes/          # 路由模块
  templates/       # HTML 模板
  static/          # CSS / JS 静态资源
tests/             # 测试目录
```
