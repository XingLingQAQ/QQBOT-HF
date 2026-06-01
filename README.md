---
title: QQBOT HF
emoji: 🤖
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

<!--
上方 YAML 是 Hugging Face Space 的配置块（必须位于 README 顶部）。
`sdk: docker` 告诉 HF 用本仓库 Dockerfile 构建；`app_port: 7860` 指定对外端口。
在 HF 之外的环境（本地 / 其他平台）该块会被当作注释忽略，不影响使用。
-->

# QQBOT-HF — QQ 机器人管理面板

在 **Hugging Face 免费 Docker Space** 上一键运行的 QQ 机器人管理面板。单容器、单端口，集成
**Lagrange.OneBot / NapCatQQ + NoneBot2**，提供 Web 管理界面：协议切换、扫码登录、插件管理、文件管理与网页终端。

技术栈：**FastAPI + React(Vite) + supervisord + Lagrange.OneBot / NapCatQQ + NoneBot2**。

**双协议后端，任选其一运行：**
- **Lagrange.OneBot**（默认）：搭配**内置自建签名服务**（[VincentZyu233/SignServer](https://github.com/VincentZyu233/SignServer)），
  容器内一键自动配置，无需依赖已停服的官方中央签名服务。
- **NapCatQQ**（默认不启用）：基于官方 Linux QQ 注入，无需签名服务；在前端一键切换即可启用。

> 同一时刻仅运行一个后端：选择 NapCatQQ 时，Lagrange 及其签名服务会自动停止；反之亦然。

---

## 功能特性

- **协议切换**：在网页一键切换 **Lagrange.OneBot** 与 **NapCatQQ**；切换时自动停止旧后端、启动新后端并重启 NoneBot，选择持久化于 `/data/manager/protocol.json`，重启后保留。
- **自建签名服务**：内置 VincentZyu233/SignServer，容器构建时自动编译，启动时自动配置（监听 `127.0.0.1:8087`），替代已停服的官方中央签名服务。
- **扫码登录管理**：按当前协议自动展示对应二维码（Lagrange / NapCat）与登录状态，支持刷新与退出登录。
- **插件管理**：在线安装 / 卸载 NoneBot 插件，启用/禁用切换，JSON 配置编辑，自动重启生效。
- **文件管理**：浏览 / 编辑 / 上传 / 下载 / 重命名 / 删除（严格限制在 `/data` 内）。
- **网页终端**：基于 xterm.js 的浏览器终端，以非 root 的 `appuser` 运行 `/bin/bash`。
- **进程控制**：实时显示各后端进程状态，并可手动启动 / 停止 / 重启（`lagrange`、`signserver`、`napcat`、`nonebot`）。
- **日志查看**：在网页查看 `backend` / `lagrange` / `signserver` / `napcat` / `nonebot` / `supervisord` 日志，支持自动刷新与下载。
- **NapCat 快速登录**：可配置 QQ 号启用快速登录，复用已保存会话自动登录，无需重复扫码（仅 NapCat 协议）。
- **持久化**：登录凭据、插件包、配置、协议选择与日志均位于 `/data`，容器重建后保留。

---

## 架构与端口约定

| 项目 | 取值 | 说明 |
|---|---|---|
| 对外端口 | `$PORT`（默认 `7860`） | uvicorn 监听；FastAPI 同时托管前端、API、WebSocket |
| NoneBot 内部端口 | `8080` | 仅容器内监听，反向 WS 服务端 |
| 签名服务（SignServer） | `127.0.0.1:8087` | 仅容器内监听，供 Lagrange 调用 |
| Lagrange / NapCat → NoneBot | `ws://127.0.0.1:8080/onebot/v11/ws` | 反向 WebSocket |
| Access Token | 留空（仅本机） | 两端需一致 |
| supervisord 控制端口 | `127.0.0.1:9001` | 仅容器内监听，供后端调用 `supervisorctl` |

NoneBot（OneBot v11 适配器）作为反向 WS **服务端**监听 8080，当前协议的适配器（Lagrange.OneBot 或 NapCatQQ）作为客户端连接进来。三者均不对外暴露。

容器内由 **supervisord 作为 PID 1** 监管以下进程：`backend` / `nonebot` 常驻，`lagrange` + `signserver`（Lagrange 协议）与 `napcat`（NapCat 协议）按所选协议互斥启停，崩溃自动重启。

---

## `/data` 持久化目录

```
/data/
├── python-packages/      # 动态安装的 NoneBot 插件包
├── lagrange/             # Lagrange 工作目录
│   ├── appsettings.json  # 反向 WS 指向 NoneBot
│   ├── keystore.json     # 登录凭据（Lagrange 自动生成）
│   ├── device.json
│   └── qr-0.png          # 待扫码登录二维码
├── napcat/               # NapCatQQ 工作目录（NAPCAT_WORKDIR）
│   ├── config/
│   │   └── onebot11.json # 反向 WS 指向 NoneBot（首启从模板生成）
│   ├── cache/
│   │   └── qrcode.png    # NapCat 待扫码登录二维码
│   ├── logs/
│   └── home/             # QQ 登录会话（$HOME/.config/QQ）
├── nonebot/
│   ├── .env              # NoneBot 配置
│   ├── bot.py            # 入口（首次运行从模板复制）
│   └── data/             # 插件数据
├── plugins.json          # 已安装插件清单 + 配置
└── manager/              # 后端日志、会话密钥、协议选择等
    ├── secret_key
    ├── protocol.json     # 当前协议后端选择（lagrange / napcat）
    ├── backend.log
    ├── lagrange.log
    ├── signserver.log
    ├── napcat.log
    └── nonebot.log
```

---

## 部署到 Hugging Face Docker Space

1. 在 Hugging Face 新建一个 **Docker** 类型的 Space。
2. 将本仓库内容推送到该 Space（或在 Space 中引用本仓库的 `Dockerfile`）。
3. 在 Space 的 **Settings → Variables and secrets** 中设置环境变量（见下表）。
4. 启动后访问 Space URL，使用设置的账号密码登录（默认 `admin` / `admin123`）。

> **HF Space 配置块**：本仓库 `README.md` 顶部已内置 HF 所需的 YAML 元数据
> （`sdk: docker`、`app_port: 7860`）。新建 Docker Space 并推送本仓库后即可自动构建，无需额外配置端口。

> **首次启动说明**：基础 Python/NoneBot 依赖已内置在镜像中；动态安装的插件会持久化到 `/data/python-packages`。

### 环境变量一览

| 变量 | 默认值 | 必填 | 说明 |
|---|---|---|---|
| `ADMIN_USER` | `admin` | 否 | 管理面板登录用户名 |
| `ADMIN_PASS` | `admin123` | 否 | 管理面板登录密码，**强烈建议修改** |
| `PORT` | `7860` | 否 | 对外端口；HF Space 固定 7860，一般无需改 |
| `DATA_DIR` | `/data` | 否 | 持久化数据根目录，一般无需改 |

> 凭据仅通过环境变量注入，绝不写死在代码中；后端使用 `hmac.compare_digest` 比较，避免时序侧信道。

---

## 防休眠（保活）说明

HF 免费 Space 在连续 **48 小时无外部请求**后会休眠。请使用**外部分钟级别的可用性监控服务**
（例如 [UptimeRobot](https://uptimerobot.com/)）定时访问本面板 URL 来保持唤醒。

> 请遵守平台规则，**不要**在容器内实现违规的自我保活机制。

---

## GitHub Actions（构建镜像）

工作流 `.github/workflows/docker-build.yml` 会在 PR 中构建镜像以验证可构建性；向 `main` 推送或手动触发时会发布
`ghcr.io/xinglingqaq/qqbot-hf:latest` 与对应提交 SHA 标签到 GitHub Packages。
如需额外推送到 Docker Hub，请在仓库 **Settings → Secrets and variables → Actions** 配置：

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

未配置 Docker Hub secrets 时，只发布 GitHub Packages。

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

## 各功能使用说明

登录后左侧导航分为七页：

1. **总览**：顶部账号卡显示登录状态、QQ 号、昵称与头像；**协议选择器**可在 Lagrange.OneBot 与 NapCatQQ 间一键切换（带确认弹窗）；**NapCat 快速登录**卡片可填写 QQ 号并启用快速登录（见下）；下方按当前协议展示相关进程的实时状态（每 3 秒轮询）。
2. **扫码登录**：按当前协议显示对应登录二维码与状态提示，可「刷新二维码」；已登录可「退出登录」。页面每 2.5 秒自动检测状态。
3. **插件管理**：顶部输入插件名（须匹配 `nonebot[-_]plugin[-_]*`）在线安装；列表支持启用/禁用切换、编辑 JSON 配置、卸载；任意变更后自动重启 NoneBot 生效。
4. **进程控制**：手动启动 / 停止 / 重启各后端进程（`lagrange`、`signserver`、`napcat`、`nonebot`），实时显示状态（每 3 秒轮询）。后端面板进程（`backend`）不在此处控制，以免停止后无法访问面板。
5. **日志**：查看各进程运行日志（`backend`、`lagrange`、`signserver`、`napcat`、`nonebot`、`supervisord`），切换标签即时加载、可开关「自动刷新」（每 3 秒）、按钮「下载」完整日志。出于性能仅显示文件尾部（约 256KB）。
6. **文件管理**：限制在 `/data` 内浏览/编辑/上传（支持拖拽）/下载/新建/重命名/删除；文本文件可在线编辑保存（≤2MB）。
7. **网页终端**：基于 xterm.js 的浏览器终端，以非 root 的 `appuser` 运行 `/bin/bash`，工作目录 `/data`，自适应窗口大小，断开后可「重新连接」。

### NapCat 快速登录

在「总览 → NapCat 快速登录」填入 QQ 号并勾选启用后，NapCat 启动时会以 `-q <QQ号>` 方式复用上次扫码保存的会话**自动登录，无需重复扫码**。前提是该 QQ 号此前已在本容器成功扫码登录过一次（会话保存在 `/data/napcat/home/.config/QQ`）。配置持久化于 `/data/napcat/config/quick_login.json`；当前协议为 NapCat 时保存会自动重启 NapCat 生效，否则在切换到 NapCat 后生效。仅对 NapCatQQ 协议有效。

---

## 安全要点

- 管理员密码经环境变量注入，使用 `hmac.compare_digest` 比较。
- 除登录与静态资源外，所有 API 与 WS 终端均需有效会话。
- 插件名经白名单正则校验；pip / 子进程使用参数数组，绝不 `shell=True`。
- 文件管理所有路径经 `safe_join` 限制在 `/data`，拒绝 `..` 与符号链接逃逸。
- 网页终端以非 root 的 `appuser` 运行。

---

## 常见问题（FAQ）

- **关于签名服务**：本项目内置**自建签名服务**（VincentZyu233/SignServer），随容器自动编译与配置，
  Lagrange 的 `appsettings.json` 默认指向 `http://127.0.0.1:8087`，**无需依赖已停服的官方中央签名服务**。
  排查签名相关问题可查看 `/data/manager/signserver.log` 与 `/data/manager/lagrange.log`。
- **关于 QQ 版本锁定（3.2.19-39038）**：自建签名服务的内存偏移是针对官方 Linux QQ **3.2.19-39038**
  逆向得到的，NapCat 4.18.x 也将该版本列为受支持版本，因此镜像锁定安装此版本 QQ。**请勿随意升级 QQ 版本**，
  否则签名会失效。如需更换版本，需同时更新 `Dockerfile` 的 `QQ_DEB_URL`/`QQ_DEB_SHA512` 与
  `sign.config.toml` 的 `offset`/`version`。
- **关于 NapCatQQ**：NapCat 注入官方 QQ（Electron），需要 Xvfb 等 GUI 依赖，已内置于镜像。切换到 NapCat 后，
  在「扫码登录」页扫描二维码即可；登录会话保存在 `/data/napcat/home/.config/QQ`。排查请查看 `/data/manager/napcat.log`。
- **关于镜像体积**：因内置 QQ + Xvfb/ffmpeg + GUI 库 + 自建签名服务，镜像体积约 **2.2GB**（远大于纯 Lagrange 方案），
  CI 构建与 HF 首次拉取会相应变慢，属正常现象。
- **登录失败 / 二维码不显示**：先确认当前协议（总览页），再查看对应日志（Lagrange：`lagrange.log`+`signserver.log`；
  NapCat：`napcat.log`）。面板本身（鉴权、插件、文件、终端、进程托管、持久化）不依赖任何协议后端。
- **HF 免费 Space 重启后数据丢失**：HF 免费层的容器存储是**临时的**（付费的持久化存储已下线）。
  本项目把所有状态放在 `/data`，在支持持久卷的环境（自建 Docker、挂载 volume）中重建后会保留；
  但在 HF 免费 Space 上，Space 重建/重启后 `/data` 可能被清空，需要重新扫码登录并重装插件。
  如需长期稳定，建议挂载持久卷或自建部署。
- **插件加载失败**：查看 `/data/manager/nonebot.log`，确认插件包名与模块名正确。
- **修改配置后未生效**：插件相关操作会自动重启 NoneBot；也可在「插件管理」页点击「重启 NoneBot」。
- **外部组件版本与容器内更新**：Lagrange.OneBot（linux-x64 self-contained nightly）、VincentZyu233/SignServer、
  NapCatQQ（Shell `v4.18.4`）、官方 Linux QQ（`3.2.19-39038`）均在实现时通过来源核实并在 `Dockerfile`
  中以 `ARG` 固定；如需变更，请相应更新 `Dockerfile` 对应的 `*_URL` / `*_REF` / `*_SHA512` 参数。
  签名服务默认指向容器内自建的 `http://127.0.0.1:8087`，旧的官方地址会在首次启动时自动迁移到本地。
  如上游变更，可在「总览」页执行「修复 Lagrange 配置」「更新 Lagrange」或「更新 NoneBot/依赖」。
