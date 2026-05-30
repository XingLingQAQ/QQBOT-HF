# QQBOT-HF — QQ 机器人管理面板

在 **Hugging Face 免费 Docker Space** 上一键运行的 QQ 机器人管理面板。单容器、单端口，集成
**Lagrange.OneBot + NoneBot2**，提供 Web 管理界面：扫码登录、插件管理、文件管理与网页终端。

技术栈：**FastAPI + React(Vite) + supervisord + Lagrange.OneBot + NoneBot2**。

---

## 功能特性

- **扫码登录管理**：在网页查看登录二维码、登录状态，支持刷新二维码与退出登录。
- **插件管理**：在线安装 / 卸载 NoneBot 插件，启用/禁用切换，JSON 配置编辑，自动重启生效。
- **文件管理**：浏览 / 编辑 / 上传 / 下载 / 重命名 / 删除（严格限制在 `/data` 内）。
- **网页终端**：基于 xterm.js 的浏览器终端，以非 root 的 `appuser` 运行 `/bin/bash`。
- **进程总览**：实时显示 Lagrange / NoneBot / 后端进程状态。
- **持久化**：所有状态（venv、登录凭据、插件、配置、日志）均位于 `/data`，容器重建后保留。

---

## 架构与端口约定

| 项目 | 取值 | 说明 |
|---|---|---|
| 对外端口 | `$PORT`（默认 `7860`） | uvicorn 监听；FastAPI 同时托管前端、API、WebSocket |
| NoneBot 内部端口 | `8080` | 仅容器内监听，反向 WS 服务端 |
| Lagrange → NoneBot | `ws://127.0.0.1:8080/onebot/v11/ws` | 反向 WebSocket |
| Access Token | 留空（仅本机） | 两端需一致 |

NoneBot（OneBot v11 适配器）作为反向 WS **服务端**监听 8080，Lagrange.OneBot 连接进来。两者均不对外暴露。

容器内由 **supervisord 作为 PID 1** 监管三个进程：`backend` / `lagrange` / `nonebot`，崩溃自动重启。

---

## `/data` 持久化目录

```
/data/
├── venv/                 # Python 虚拟环境（依赖 + 插件）
├── lagrange/             # Lagrange 工作目录
│   ├── appsettings.json  # 反向 WS 指向 NoneBot
│   ├── keystore.json     # 登录凭据（Lagrange 自动生成）
│   ├── device.json
│   └── qr-0.png          # 待扫码登录二维码
├── nonebot/
│   ├── .env              # NoneBot 配置
│   ├── bot.py            # 入口（首次运行从模板复制）
│   └── data/             # 插件数据
├── plugins.json          # 已安装插件清单 + 配置
└── manager/              # 后端日志、会话密钥等
    ├── secret_key
    ├── backend.log
    ├── lagrange.log
    └── nonebot.log
```

---

## 部署到 Hugging Face Docker Space

1. 在 Hugging Face 新建一个 **Docker** 类型的 Space。
2. 将本仓库内容推送到该 Space（或在 Space 中引用本仓库的 `Dockerfile`）。
3. 在 Space 的 **Settings → Variables and secrets** 中设置环境变量：
   - `ADMIN_USER`（默认 `admin`）
   - `ADMIN_PASS`（默认 `admin123`，**强烈建议修改**）
   - 可选：`PORT`（默认 `7860`，HF 一般固定为 7860）
4. 启动后访问 Space URL，使用上面的账号密码登录。

> **首次启动较慢**：首启会创建 venv、安装 NoneBot 等依赖、下载签名服务相关资源，请耐心等待。

---

## 防休眠（保活）说明

HF 免费 Space 在连续 **48 小时无外部请求**后会休眠。请使用**外部分钟级别的可用性监控服务**
（例如 [UptimeRobot](https://uptimerobot.com/)）定时访问本面板 URL 来保持唤醒。

> 请遵守平台规则，**不要**在容器内实现违规的自我保活机制。

---

## GitHub Actions（构建镜像）

工作流 `.github/workflows/docker-build.yml` 会在向 `main` 推送或提交 PR 时构建镜像以验证可构建性。
如需推送到 Docker Hub，请在仓库 **Settings → Secrets and variables → Actions** 配置：

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

未配置时工作流仅构建、不推送。

---

## 本地开发

后端（需要本机有 Python）：

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
DATA_DIR=./_data uvicorn app.main:app --reload --port 7860
```

前端：

```bash
cd frontend
npm install
npm run dev      # 通过 vite 代理 /api 与 /ws 到 localhost:7860
```

构建前端产物：

```bash
cd frontend && npm install && npm run build   # 输出 dist/
```

---

## 安全要点

- 管理员密码经环境变量注入，使用 `hmac.compare_digest` 比较。
- 除登录与静态资源外，所有 API 与 WS 终端均需有效会话。
- 插件名经白名单正则校验；pip / 子进程使用参数数组，绝不 `shell=True`。
- 文件管理所有路径经 `safe_join` 限制在 `/data`，拒绝 `..` 与符号链接逃逸。
- 网页终端以非 root 的 `appuser` 运行。

---

## 常见问题（FAQ）

- **二维码不显示 / 登录失败（`Signer server returned a NotFound` / `All login failed`）**：
  这是 **Lagrange 签名服务（SignServer）** 问题，属于上游外部依赖。截至本项目编写时，Lagrange.Core
  官方仓库挂有 “Termination Notice：中央 SignServer 已临时停服”，因此官方签名服务可能对当前 nightly
  协议版本不可用。处理方式：在「文件管理」中编辑 `/data/lagrange/appsettings.json` 的 `SignServerUrl`
  填入一个与所用 Lagrange 版本匹配、当前可用的签名服务地址，然后在「扫码登录」页点击「刷新二维码」。
  排查请查看 `/data/manager/lagrange.log`。面板本身（鉴权、插件、文件、终端、进程托管、持久化）不依赖签名服务。
- **插件加载失败**：查看 `/data/manager/nonebot.log`，确认插件包名与模块名正确。
- **修改配置后未生效**：插件相关操作会自动重启 NoneBot；也可在「插件管理」页点击「重启 NoneBot」。
- **外部组件版本**：Lagrange.OneBot（linux-x64 self-contained nightly）与签名服务地址
  `https://sign.lagrangecore.org/api/sign` 在实现时通过 MCP 核实；如上游变更，请相应更新
  `Dockerfile` 的 `LAGRANGE_URL` 与 `appsettings.json` 的 `SignServerUrl`。
