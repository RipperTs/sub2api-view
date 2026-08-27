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
AUTO_RESET_ENABLED=true
AUTO_RESET_INTERVAL_SECONDS=180
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
验证通过后查询用户的有效订阅，并展示订阅分组下的可调度账号。
管理员与普通用户使用相同的账号展示规则。

## 自动重置订阅配额

应用启动后会立即检测所有 OpenAI OAuth 账号，之后默认每隔 180 秒检测一次。
如果账号的 7 天额度窗口已经重置，任务会自动重置该账号关联分组下所有活跃订阅的
日、周、月配额。可以通过 `AUTO_RESET_ENABLED` 启停任务，并使用
`AUTO_RESET_INTERVAL_SECONDS` 调整执行间隔。

任务通过 `SUB2API_ADMIN_KEY` 直接调用 Sub2API 管理员 API，不对外提供手动重置接口。
重复执行是安全的：当前 7 天窗口内已经重置过的订阅会被跳过，单个账号或订阅失败
不会中断其他数据的处理。

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
