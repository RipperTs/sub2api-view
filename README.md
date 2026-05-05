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
```

## 启动服务

```bash
uv run python main.py
```

浏览器访问：

```text
http://127.0.0.1:8000
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
