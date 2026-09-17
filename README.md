# My Tesla

[![CI](https://github.com/kinopico-zhang/my-tesla/actions/workflows/ci.yml/badge.svg)](https://github.com/kinopico-zhang/my-tesla/actions/workflows/ci.yml)
![OS](https://img.shields.io/badge/OS-Linux%20%7C%20Windows%20%7C%20macOS-0078D6)
![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-3776AB?logo=python&logoColor=white)
![Node.js](https://img.shields.io/badge/Node.js-22-339933?logo=nodedotjs&logoColor=white)

TeslaMate 行车数据的展示应用: 充电记录 (费用/区域统计)、行车足迹
(轨迹地图 + 行程回放)、实时位置、行程列表与分组。FastAPI + SQLAlchemy +
Pydantic, 前端零依赖 (原生 JS + 高德地图 + echarts)。

从 [My Home](https://github.com/kinopico-zhang/my-home) 组合仓拆出来的
独立仓: 账号体系 (登录/注册/账号管理) 内嵌在 `app/home/`, 单独 clone
本仓即可部署, 不需要组合仓。

## 页面与 URL

业务页面全部挂在 `/tesla` 前缀下 (与组合仓一致, 老书签不动):

| 路径 | 页面 |
|---|---|
| `/` | 302 → `/tesla/charging` |
| `/tesla/charging` | 充电记录 (默认页) |
| `/tesla/stats` | 充电统计 |
| `/tesla/chargemap` | 充电地图 (热力图) |
| `/tesla/map` | 足迹地图 (轨迹) |
| `/tesla/trips` `/tesla/groups` | 行程列表 / 行程分组 |
| `/tesla/live` | 当前驾驶 (实时) |
| `/tesla/settings` | 软件设置 (TeslaMate 连接 / 高德 Key / 驾驶员) |
| `/tesla/changelog` | 更新日志 |

账号体系在根路径 (账号跟应用走, 不在业务前缀下): `/login` `/register`
登录与凭邀请注册, `/accounts` 账号管理 (仅管理员), `/api/*` 账号接口。
旧地址 (`/tesla/login`、`/tesla/api/*` 等) 302/307 兼容, 已发出去的邀请
链接不断。静态资源: `/tesla/static/*` (应用页) 与 `/static/*` (账号页 +
全站小件 menu-user / changelog-page)。

## 部署

需要 Python 3.13+ (venv) 与一个能连上的
[TeslaMate](https://docs.teslamate.io/) PostgreSQL 库:

```sh
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env      # 编辑: 至少设 AUTH_PASS; TeslaMate 连接可留到设置页填
./run.sh
```

`run.sh` 有证书时 HTTPS 与 HTTP 双开 (两个端口两个进程): HTTPS 走
`PORT` (默认 8500, 域名 + Let's Encrypt 证书), HTTP 走 `HTTP_PORT`
(默认 8501, 局域网 IP 直连); 没证书只开 `PORT` 的明文。会话 cookie 是
无状态 HMAC 签名, 两个口通用。

打开 `http://<host>:8500/` → 自动进 `/tesla/charging` (未登录先到登录页,
账密是 `.env` 里 `AUTH_USER`/`AUTH_PASS` 种下的管理员, 之后可在界面里改;
**`AUTH_PASS` 不设则不种管理员**, 仓库是公开的, 不带默认口令)。

TeslaMate 连接三种给法 (优先级从高到低): 设置页里填 (存自有库, 改完热
重连实测) → `.env` 里的 `TMDB_*` → docker 容器定位 (与 TeslaMate 同机部署
时)。数据只读, 不会往 TeslaMate 库写任何东西。高德 Key (`AMAP_KEY` +
`AMAP_SECURITY_CODE`, 服务平台选「Web端 JS API」, 个人开发者免费) 未配置
时地图页显示申请指引, 也可在设置页保存。

自有数据落在 `data/` (git 忽略): `mytesla.db` (轨迹断档补路等自产数据)
+ `users.db` 账号 + `certs/` 证书。

## 测试

```sh
npm install               # 前端工具链 (eslint/tsc/stylelint/html-validate/c8)
./run_tests.sh            # pylint + mypy + pytest + 前端全套 + 覆盖率门禁
```

从 My Home 组合仓的 `apps/my-tesla` 下跑时不用 npm install —— 脚本会
软链组合仓根的 node_modules。CI 在 GitHub Actions 三平台跑同一套门禁。

## 结构

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
