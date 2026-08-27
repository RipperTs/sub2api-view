# sub2api-view

`sub2api-view` 是面向 [Sub2API](https://github.com/Wei-Shaw/sub2api) 的轻量级账号查看与订阅配额维护服务。

它根据当前用户的有效订阅分组展示可调度账号及额度信息，并在后台定时检测 OpenAI OAuth 账号的 7 天额度窗口，自动重置对应分组下的活跃订阅配额。

## 核心功能

- 使用 Sub2API 用户 JWT 校验访问身份和用户状态
- 仅展示用户有效订阅分组内的可调度账号
- 展示账号用量、额度窗口、重置卡和分组等信息
- 自动过滤账号凭据、令牌、代理等敏感字段，并对邮箱脱敏
- 应用启动后自动执行订阅配额重置任务，默认间隔 180 秒
- 支持本地运行、Docker 和 Docker Compose 部署
- 支持通过 GitHub Actions 将版本镜像发布到阿里云镜像仓库

## 工作原理

### 账号访问

页面和 API 均要求提供 Sub2API 用户 ID 与对应 JWT。验证通过后，服务会：

1. 查询用户的全部活跃订阅，收集订阅分组 ID。
2. 查询 Sub2API 中的全部账号。
3. 保留属于上述分组且 `schedulable` 不为 `false` 的账号。
4. 查询账号用量并清理敏感信息后返回给前端。

管理员和普通用户使用相同的账号筛选规则。没有活跃订阅的用户会得到空账号列表。

### 订阅配额自动重置

应用启动时会立即执行一次检查。每次执行完成后等待 `AUTO_RESET_INTERVAL_SECONDS`，然后开始下一次检查，默认等待 180 秒。

一次检查的处理流程如下：

1. 分页查询全部 `openai + oauth` 账号。
2. 强制刷新每个账号的用量，读取 7 天窗口重置时间；刷新失败时尝试使用账号快照中的 `extra.codex_7d_reset_at`。
3. 根据账号的 `group_ids` 建立分组与额度窗口的关系。
4. 同一分组包含多个账号时，使用其中最新的窗口起点作为该分组的重置边界。
5. 分页查询分组下的全部活跃订阅。
6. 当订阅的 `weekly_window_start`（缺失时使用 `starts_at`）早于分组重置边界时，调用 Sub2API 重置订阅配额。

订阅与账号之间没有直接绑定关系，二者通过分组关联。因此：

- A、B 账号属于同一分组时，任一账号进入新的 7 天窗口，该分组下所有活跃订阅都会参与重置。
- A、B 账号属于不同分组时，只会处理已进入新窗口账号所在分组的订阅。
- 一个账号属于多个分组时，它关联的所有分组都会参与处理。
- 相同订阅会按订阅 ID 去重，单个账号、分组或订阅失败不会阻止其他数据继续处理。

当前调用会同时重置订阅的日、周、月配额。项目不提供手动重置接口，所有重置均由后台定时任务完成。

## 环境要求

- Python 3.11 或更高版本
- [uv](https://docs.astral.sh/uv/)
- 可访问的 Sub2API 服务
- Sub2API 管理员 API Key
- 与 Sub2API 完全一致的 JWT Secret

Docker 部署不要求宿主机安装 Python 和 uv。

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

`uv` 会自动创建并使用项目根目录下的 `.venv` 虚拟环境。

### 2. 配置环境变量

复制配置模板：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`：

```env
APP_HOST=127.0.0.1
APP_PORT=8000
APP_RELOAD=false

SUB2API_BASE_URL=http://127.0.0.1:8080
SUB2API_ADMIN_KEY=your-admin-api-key
SUB2API_JWT_SECRET=your-sub2api-jwt-secret

AUTO_RESET_ENABLED=true
AUTO_RESET_INTERVAL_SECONDS=180
```

`SUB2API_JWT_SECRET` 必须与 Sub2API 服务使用的 `JWT_SECRET` 完全一致，否则用户 Token 无法通过校验。

### 3. 启动服务

```bash
uv run python main.py
```

默认监听 `http://127.0.0.1:8000`。

### 4. 访问账号页面

```text
http://127.0.0.1:8000/accounts?user_id=3&token=your-user-token
```

也可以访问根路径，参数保持一致：

```text
http://127.0.0.1:8000/?user_id=3&token=your-user-token
```

`user_id` 必须与 JWT 中的 `user_id` 一致，且用户在 Sub2API 中必须处于 `active` 状态。

## 配置说明

| 环境变量 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `APP_HOST` | 否 | `127.0.0.1` | Web 服务监听地址；容器内应使用 `0.0.0.0` |
| `APP_PORT` | 否 | `8000` | Web 服务监听端口 |
| `APP_RELOAD` | 否 | `true` | 是否启用 Uvicorn 自动重载；生产环境建议设为 `false` |
| `SUB2API_BASE_URL` | 是 | 无 | Sub2API 后端地址，末尾的 `/` 会被自动移除 |
| `SUB2API_ADMIN_KEY` | 是 | 无 | 调用 Sub2API 管理员 API 的密钥 |
| `SUB2API_JWT_SECRET` | 是 | 无 | 用于校验 Sub2API 用户 JWT 的密钥 |
| `AUTO_RESET_ENABLED` | 否 | `true` | 是否启用订阅配额自动重置任务 |
| `AUTO_RESET_INTERVAL_SECONDS` | 否 | `180` | 每次任务执行完成后的等待秒数，必须是正整数 |

布尔配置支持 `1`、`true`、`yes`、`on`，不区分大小写；其他值按关闭处理。

## API

### 查询账号

```http
GET /api/accounts?user_id={user_id}
Authorization: Bearer {user_token}
```

示例：

```bash
curl \
  -H "Authorization: Bearer your-user-token" \
  "http://127.0.0.1:8000/api/accounts?user_id=3&page=1&page_size=20"
```

支持的查询参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `user_id` | 是 | Sub2API 用户 ID，必须与 JWT 一致 |
| `page` | 否 | 页码，默认 `1` |
| `page_size` | 否 | 每页数量，默认 `20`，最大 `100` |
| `platform` | 否 | 按账号平台筛选 |
| `type` | 否 | 按账号类型筛选 |
| `status` | 否 | 按账号状态筛选 |
| `search` | 否 | 传递给 Sub2API 的搜索条件 |

响应中的账号凭据、访问令牌、刷新令牌、API Key、密码和代理信息会被移除，邮箱地址会被脱敏。

## Docker 部署

### 使用 Docker Compose

编辑 `docker-compose.yml` 中的 Sub2API 地址和密钥，然后启动：

```bash
docker compose up -d
```

查看日志：

```bash
docker compose logs -f sub2api-view
```

停止服务：

```bash
docker compose down
```

Compose 默认使用以下镜像：

```text
registry.cn-hangzhou.aliyuncs.com/ripper/sub2api-view:latest
```

### 本地构建镜像

```bash
docker build -t sub2api-view .
```

运行容器：

```bash
docker run --rm \
  --name sub2api-view \
  -p 8000:8000 \
  -e SUB2API_BASE_URL=http://host.docker.internal:8080 \
  -e SUB2API_ADMIN_KEY=your-admin-api-key \
  -e SUB2API_JWT_SECRET=your-sub2api-jwt-secret \
  -e AUTO_RESET_ENABLED=true \
  -e AUTO_RESET_INTERVAL_SECONDS=180 \
  sub2api-view
```

`host.docker.internal` 需要能够从容器访问。Linux 环境无法解析该地址时，请改为 Sub2API 的容器服务名、宿主机网关地址或实际网络地址。

## GitHub Actions 镜像发布

工作流文件位于 `.github/workflows/docker-publish.yml`。推送以 `v` 开头的 Git 标签时，GitHub Actions 会构建镜像并推送到阿里云镜像仓库。

在 GitHub 仓库的 `Settings > Secrets and variables > Actions` 中配置：

| Secret | 说明 |
| --- | --- |
| `ALIYUN_REGISTRY_USERNAME` | 阿里云镜像仓库登录用户名 |
| `ALIYUN_REGISTRY_PASSWORD` | 阿里云镜像仓库登录密码 |

发布版本：

```bash
git tag v1.0.0
git push origin v1.0.0
```

工作流会推送两个镜像标签：

```text
registry.cn-hangzhou.aliyuncs.com/ripper/sub2api-view:v1.0.0
registry.cn-hangzhou.aliyuncs.com/ripper/sub2api-view:latest
```

发布前需要在阿里云容器镜像服务中创建 `ripper/sub2api-view` 仓库，并确保配置的账号拥有推送权限。

## 测试

运行全部测试：

```bash
uv run python -m unittest discover -s tests -v
```

测试覆盖以下主要行为：

- Sub2API 客户端请求和订阅配额重置参数
- 分组与订阅匹配、分页、去重和失败隔离
- 自动重置任务配置、执行周期和应用生命周期
- 手动重置接口不可访问

## 项目结构

```text
.
|-- .github/workflows/
|   `-- docker-publish.yml                 # 阿里云镜像发布工作流
|-- app/
|   |-- core/
|   |   `-- security.py                    # JWT 与用户状态校验
|   |-- routes/
|   |   |-- api.py                         # 账号查询 API
|   |   `-- pages.py                       # 页面路由
|   |-- services/
|   |   |-- sub2api_client.py              # Sub2API 管理员 API 客户端
|   |   |-- subscription_quota_reset.py    # 分组订阅配额重置逻辑
|   |   `-- subscription_quota_reset_scheduler.py # 后台定时任务
|   |-- static/                              # CSS 与 JavaScript
|   |-- templates/                           # Jinja2 页面模板
|   `-- main.py                              # FastAPI 应用与生命周期
|-- tests/                                   # 单元测试
|-- .env.example                             # 环境变量模板
|-- docker-compose.yml                       # Compose 部署配置
|-- Dockerfile                               # Docker 镜像定义
|-- main.py                                  # 本地启动入口
|-- pyproject.toml                           # 项目与依赖配置
`-- uv.lock                                  # 依赖锁文件
```

## 生产环境注意事项

- `SUB2API_ADMIN_KEY` 权限较高，不要提交到 Git 仓库、前端代码或日志中。
- 页面 Token 位于 URL 查询参数中，生产环境应启用 HTTPS，并避免由代理或访问日志长期记录完整查询参数。
- 不要直接将服务暴露到不可信网络，建议放在反向代理、内网或其他访问控制之后。
- 每个应用进程都会启动一个定时任务。多副本部署时，只保留一个副本的 `AUTO_RESET_ENABLED=true`，其他副本应设为 `false`，避免并发重复重置。
- 定时任务采用“执行完成后再等待”的方式，实际两次启动时间的间隔等于任务耗时加配置间隔。
- 生产环境应将 `APP_RELOAD` 设置为 `false`，避免重载进程重复启动任务。

## 常见问题

### 页面返回 401 或 403

检查 `user_id` 是否与 JWT 中的用户 ID 一致、Token 是否过期、用户状态是否为 `active`，以及 `SUB2API_JWT_SECRET` 是否与 Sub2API 完全一致。

### 页面没有显示账号

确认用户拥有活跃订阅，订阅分组中存在账号，并且账号的 `schedulable` 没有被设置为 `false`。

### 自动重置没有执行

检查 `AUTO_RESET_ENABLED`、`AUTO_RESET_INTERVAL_SECONDS`、`SUB2API_BASE_URL` 和 `SUB2API_ADMIN_KEY`，然后查看应用日志中的“订阅配额自动重置”记录。

### 容器无法连接 Sub2API

确认 `SUB2API_BASE_URL` 是容器内部可访问的地址。两个服务位于同一个 Docker 网络时，优先使用 Sub2API 的 Compose 服务名。
