<div align="center">

# 🚗 My Tesla

**TeslaMate 行车数据的自托管展示应用** — 充电 · 足迹 · 行程 · 实时位置

[![CI](https://github.com/kinopico-zhang/my-tesla/actions/workflows/ci.yml/badge.svg)](https://github.com/kinopico-zhang/my-tesla/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/kinopico-zhang/my-tesla)](./LICENSE)
![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-3776AB?logo=python&logoColor=white)
![Node.js](https://img.shields.io/badge/Node.js-22-339933?logo=nodedotjs&logoColor=white)
![OS](https://img.shields.io/badge/OS-Linux%20%7C%20Windows%20%7C%20macOS-0078D6)

![pylint](https://img.shields.io/badge/pylint-10.00%2F10-brightgreen)
![mypy](https://img.shields.io/badge/mypy-strict-2A6DB2)
![pytest](https://img.shields.io/badge/pytest-431%20passed-0A9EDC?logo=pytest&logoColor=white)
![coverage](https://img.shields.io/badge/JS%20coverage-95%25%2B-brightgreen)

![ESLint](https://img.shields.io/badge/ESLint-passing-4B32C3?logo=eslint&logoColor=white)
![tsc](https://img.shields.io/badge/tsc-checkJS-3178C6?logo=typescript&logoColor=white)
![stylelint](https://img.shields.io/badge/stylelint-passing-263238?logo=stylelint&logoColor=white)
![html-validate](https://img.shields.io/badge/html--validate-passing-brightgreen)

</div>

> 从 [My Home](https://github.com/kinopico-zhang/my-home) 组合仓拆出来的独立仓:
> 账号体系 (登录/注册/账号管理) 内嵌在 `app/home/`, 单独 clone 本仓即可部署,
> 不需要组合仓。

<p align="center">
<img src="docs/screenshot-charging.png" width="300" alt="充电记录 · My Tesla (演示数据)">
<img src="docs/screenshot-map.png" width="300" alt="足迹地图 · My Tesla (演示数据)">
</p>

## ✨ 功能

- 🔋 **充电** — 充电记录 (费用 / 区域统计) · 充电统计 · 充电地图
- 🗺️ **足迹地图** — 行车轨迹 + 道路拟合 (WGS-84 → GCJ-02 纠偏), 轨迹断档自动补路
- 🎬 **行程** — 行程列表 · 行程统计 · 行程分组 · 轨迹回放动画
- 🚗 **实时位置** — 当前驾驶状态
- 🩺 **电池健康**
- 🚙 **多车切换** — 车辆选择住抽屉顶, 全视图跟着切
- 🧭 **单壳移动优先 UI** — 左缘右划呼出抽屉, 手势导航 (任意页通用)
- ⚙️ **应用内设置** — TeslaMate 连接 · 高德 Key · 驾驶员 · 常用地点, 改完即生效
- 🔄 **双部署模式** — 独立部署自带账号层; 或挂 My Home 组合仓共享账号单点登录

## 🚀 快速开始

需要 Python 3.13+ (venv) 与一个能连上的
[TeslaMate](https://docs.teslamate.org/) PostgreSQL 库:

```sh
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env      # 可全留空, 首启走 /setup 引导; TeslaMate 连接也可后填
./run.sh
```

`run.sh` 有证书时 HTTPS 与 HTTP 双开 (两个端口两个进程): HTTPS 走
`PORT` (默认 8500, 域名 + Let's Encrypt 证书), HTTP 走 `HTTP_PORT`
(默认 8501, 局域网 IP 直连); 没证书只开 `PORT` 的明文。会话 cookie 是
无状态 HMAC 签名, 两个口通用。

打开 `http://<host>:8500/` → 自动进 `/tesla/charging`。账号库为空时
登录页会带去 `/setup` 引导页: 注册第一个管理员, 顺路配 TeslaMate 连接
与地图 Key, 全部可跳过、之后在设置页随时补。`.env` 里设 `AUTH_PASS`
是旧口径种子 (只在空库时生效, 设了就不再进引导; 仓库是公开的, 不带
默认口令)。

## 🌐 页面与 URL

业务页面全部挂在 `/tesla` 前缀下 (与组合仓一致, 老书签不动):

| 路径 | 页面 |
|---|---|
| `/` | 302 → `/tesla` |
| `/tesla` | 单壳应用 (3.0): 抽屉切视图 —— 充电记录 (默认) / 充电统计 / 充电地图 / 足迹地图 / 行程列表 / 行程分组 / 当前驾驶 / 设置 / 更新日志 |

旧页地址 (`/tesla/charging`、`/tesla/trips` 等) 302 回壳并带 `?view=`
落到对应视图 (行程深链 `?id=` 照旧直开弹层), 老书签不断。

账号体系在根路径 (账号跟应用走, 不在业务前缀下): `/login` `/register`
登录与凭邀请注册, `/accounts` 账号管理 (仅管理员), `/api/*` 账号接口。
旧地址 (`/tesla/login`、`/tesla/api/*` 等) 302/307 兼容, 已发出去的邀请
链接不断。静态资源: `/tesla/static/*` (应用壳) 与 `/static/*` (账号页 +
全站小件 menu-user)。

## 📡 数据源

TeslaMate 连接三种给法 (优先级从高到低): 设置页里填 (存自有库, 改完热
重连实测) → `.env` 里的 `TMDB_*` → docker 容器定位 (与 TeslaMate 同机部署
时)。数据只读, 不会往 TeslaMate 库写任何东西。

高德 Key (`AMAP_KEY` + `AMAP_SECURITY_CODE`, 服务平台选「Web端 JS API」,
个人开发者免费) 未配置时地图页显示申请指引, 也可在设置页保存。

自有数据落在 `data/` (git 忽略): `mytesla.db` (轨迹断档补路等自产数据)
+ `users.db` 账号 + `certs/` 证书。

## ⚙️ 环境变量

完整清单见 [.env.example](.env.example), 常用项:

| 变量 | 默认 | 说明 |
|---|---|---|
| `AUTH_USER` / `AUTH_PASS` | `admin` / 空 | 旧口径首启种子 (不设则走 `/setup` 引导; 只在空账号库时种) |
| `PORT` / `HTTP_PORT` / `HTTP` | `8500` / `8501` | 双端口; `HTTP=1` 强制明文 (调试) |
| `TMDB_HOST` 等 | docker 定位 | TeslaMate PostgreSQL (设置页里填的优先) |
| `AMAP_KEY` / `AMAP_SECURITY_CODE` | 空 | 高德 Web端 JS API Key |
| `AMAP_STYLE` | `amap://styles/dark` | 地图样式 |
| `MYTESLA_DB` | `sqlite:///data/mytesla.db` | 自有库 (自产数据) |
| `MYHOME_USERS_DB` / `MYHOME_SECRET_FILE` | `data/users.db` / `.session_secret` | 账号库与会话密钥 (组合部署指到共享文件) |
| `TZ_NAME` / `CUR_SYMBOL` | `Asia/Shanghai` / `¥` | 显示口径 |

## 🧪 测试与质量门禁

```sh
npm install               # 前端工具链 (eslint/tsc/stylelint/html-validate/c8)
./run_tests.sh            # pylint + mypy + pytest + 前端全套 + 覆盖率门禁
```

门禁全绿才算过: pylint 10.00/10 (app 严检) · mypy 严格模式 · pytest 417 例
(真实 ORM + SQLite 临时库, 不碰真实数据; 含 e2e 冒烟: 起真 uvicorn
子进程打真 HTTP —— 登录 → 页面 → 静态资源, 与 ./run.sh 生产路径同构) · ESLint / tsc --checkJs /
stylelint / html-validate / node --test · c8 覆盖率 ≥95% (纯逻辑模块)。
CI 在 GitHub Actions 三平台跑同一套门禁。

从 My Home 组合仓的 `apps/my-tesla` 下跑时不用 npm install —— 脚本会
软链组合仓根的 node_modules。

## 📁 项目结构

```
app/
  tesla/         Tesla 应用本体 (repository 查询层 + routers 路由与页面)
  home/          账号层副本 (登录/注册/账号管理页面 + /api 会话接口 + 中间件)
  database/      三引擎: teslamate 库 / 自有库 / 账号库
  account_store/     账号库存取 (scrypt 密码 + 注册邀请)
  authentication.py  会话 cookie 签发与校验 (HMAC)
  main.py        独立装配: 账号层挂根, 应用挂 /tesla
tests/           pytest (真实 ORM + SQLite 临时库) + node --test (纯逻辑模块)
```

账号层的接口与 cookie 配方和 My Home 组合仓完全一致 (`/api/login`、
`/api/me`…): 组合部署时外层把 `MYHOME_USERS_DB` / `MYHOME_SECRET_FILE`
指到共享的账号库与密钥文件, 三个应用就共用同一批账号单点登录。

## 🔗 相关项目

| 仓 | 说明 |
|---|---|
| [My Home](https://github.com/kinopico-zhang/my-home) | 组合仓: 三应用 + 共享账号层, 单点登录 |
| [My Money](https://github.com/kinopico-zhang/my-money) | 家庭记账 (离线 LWW 同步) |
| [My Music](https://github.com/kinopico-zhang/my-music) | NAS 曲库听歌 (Service Worker 离线) |

## 📄 许可证

[MIT](./LICENSE) © 2026 kinopico
