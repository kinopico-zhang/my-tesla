<div align="center">

# <img src="https://cdn.simpleicons.org/tesla/E82127" height="26" alt="Tesla"> My Tesla

**TeslaMate 可视化工具**

[![CI](https://github.com/kinopico-zhang/my-tesla/actions/workflows/ci.yml/badge.svg)](https://github.com/kinopico-zhang/my-tesla/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/kinopico-zhang/my-tesla)](./LICENSE)
![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-3776AB?logo=python&logoColor=white)
![Node.js](https://img.shields.io/badge/Node.js-22-339933?logo=nodedotjs&logoColor=white)
![OS](https://img.shields.io/badge/OS-Linux%20%7C%20Windows%20%7C%20macOS-0078D6)

![pylint](https://img.shields.io/badge/pylint-10.00%2F10-brightgreen)
![mypy](https://img.shields.io/badge/mypy-strict-2A6DB2)
![pytest](https://img.shields.io/badge/pytest-442%20passed-0A9EDC?logo=pytest&logoColor=white)
![coverage](https://img.shields.io/badge/JS%20coverage-95%25%2B-brightgreen)

![ESLint](https://img.shields.io/badge/ESLint-passing-4B32C3?logo=eslint&logoColor=white)
![tsc](https://img.shields.io/badge/tsc-checkJS-3178C6?logo=typescript&logoColor=white)
![stylelint](https://img.shields.io/badge/stylelint-passing-263238?logo=stylelint&logoColor=white)
![html-validate](https://img.shields.io/badge/html--validate-passing-brightgreen)

</div>

## ✨ 功能

<p align="center">
<a name="shot-live"><img src="docs/screenshot-live.png" width="280" alt="状态 · My Tesla (演示数据)"></a>
<br><b>状态</b> — 车停在哪、还剩多少电、还能跑多远, 打开即见
</p>

<p align="center">
<a name="shot-trips"><img src="docs/screenshot-trips.png" width="280" alt="行程轨迹 · My Tesla (演示数据)"></a>
<br><b>行程轨迹</b> — 每一趟去了哪、开了多久、耗了多少电, 随时翻旧账
</p>

<p align="center">
<a name="shot-trip"><img src="docs/screenshot-trip.png" width="280" alt="单个行程 · My Tesla (演示数据)"></a>
<br><b>单个行程</b> — 回放这一趟怎么开的: 路线按车速着色, 横滑看速度与电耗曲线
</p>

<p align="center">
<a name="shot-tripstats"><img src="docs/screenshot-tripstats.png" width="280" alt="行程统计 · My Tesla (演示数据)"></a>
<br><b>行程统计</b> — 一段时间开了多少公里、平均电耗多少, 趋势与分布一眼看完
</p>

<p align="center">
<a name="shot-groups"><img src="docs/screenshot-groups.png" width="280" alt="行程分组 · My Tesla (演示数据)"></a>
<br><b>行程分组</b> — 出差、周末出行各归一册, 分开算用车账
</p>

<p align="center">
<a name="shot-map"><img src="docs/screenshot-map.png" width="280" alt="足迹地图 · My Tesla (演示数据)"></a>
<br><b>足迹地图</b> — 车轮碾过的每条路都亮在地图上, 拖时间轴回放这些年跑过的路
</p>

<p align="center">
<a name="shot-charging"><img src="docs/screenshot-charging.png" width="280" alt="充电记录 · My Tesla (演示数据)"></a>
<br><b>充电记录</b> — 每次在哪充、充了多少、花了几块钱, 按区域翻查
</p>

<p align="center">
<a name="shot-stats"><img src="docs/screenshot-stats.png" width="280" alt="充电统计 · My Tesla (演示数据)"></a>
<br><b>充电统计</b> — 每月充电量与花销的趋势, 用电的账一清二楚
</p>

<p align="center">
<a name="shot-battery"><img src="docs/screenshot-battery.png" width="280" alt="电池健康 · My Tesla (演示数据)"></a>
<br><b>电池健康</b> — 电池还剩几成、衰减快不快, 曲线直接说话
</p>

<p align="center">
<a name="shot-chargemap"><img src="docs/screenshot-chargemap.png" width="280" alt="充电地图 · My Tesla (演示数据)"></a>
<br><b>充电地图</b> — 常去充电点的地理分布, 陌生地方先看哪里充过电
</p>

## 🚀 部署

### 准备 · TeslaMate (数据源)

My Tesla 读 TeslaMate 的 PostgreSQL 库 (只读, 不往回写)。还没有的话,
官方推荐 docker compose 部署 (完整文档
[docs.teslamate.org](https://docs.teslamate.org/)):

```yaml
# docker-compose.yml —— 三处「改成」务必换成自己的随机值
services:
  teslamate:
    image: teslamate/teslamate:latest
    restart: always
    environment:
      - ENCRYPTION_KEY=改成随机串
      - DATABASE_USER=teslamate
      - DATABASE_PASS=改成密码
      - DATABASE_NAME=teslamate
      - DATABASE_HOST=database
      - TZ=Asia/Shanghai
    ports:
      - 4000:4000
    depends_on:
      - database
  database:
    image: postgres:17
    restart: always
    environment:
      - POSTGRES_USER=teslamate
      - POSTGRES_PASSWORD=改成密码
      - POSTGRES_DB=teslamate
    volumes:
      - teslamate-db:/var/lib/postgresql/data
volumes:
  teslamate-db:
```

`docker compose up -d` 后打开 `http://<host>:4000`, 登录 Tesla 账号并
添加车辆, 行驶/充电数据即开始落库。My Tesla 部署在别的机器时, 给
`database` 加 `ports: ["5432:5432"]` 把 PostgreSQL 发布出去。

### 准备 · Python 环境

需要 Python 3.13+:

```sh
python3.13 -m venv .venv          # Windows: py -3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 启动

```sh
.venv/bin/python -m app           # Windows: .venv\Scripts\python -m app
```

配置全走命令行参数 (`--help` 一屏看全), 端口只有一个 `8500`, 分两种情况:

- **有证书**: `fullchain.pem` + `privkey.pem` 放进 `data/certs/` 再启动,
  走 `https://<host>:8500/`;
- **没证书**: 直接启动, 走 `http://<host>:8500/` (`--http` 可强制明文,
  调试用)。

打开后自动进 `/tesla/charging`。首次打开先走设置向导, 三步: 注册管理员
账号 → 填 TeslaMate 的 PostgreSQL 连接 (主机/端口/账号/密码/库名, 保存即
实测连通) → 填高德 Key。三步配齐才能进应用, 一步不能跳; 中途关掉下次
从缺的那步接着配。之后想改, 设置页随时改。

## 📡 数据源

TeslaMate 连接只有一条路: 首启向导 (或之后的设置页) 里填, 保存即热重连
实测。数据只读, 不会往 TeslaMate 库写任何东西。

高德 Key (服务平台选「Web端 JS API」, 个人开发者免费) 未配置时地图页
显示申请指引。

自有数据落在 `data/` (git 忽略): `mytesla.db` (轨迹断档补路等自产数据)
+ `users.db` 账号 + `certs/` 证书。

## ⚙️ 启动参数

全量清单 `python -m app --help` (分组帮助即部署文档), 常用项:

| 参数 | 默认 | 说明 |
|---|---|---|
| `--port` | `8500` | 端口: 证书目录有证书走 HTTPS, 没证书走 HTTP |
| `--mytesla-db` | `sqlite:///data/mytesla.db` | 自有库 (自产数据) |
| `--users-db` / `--secret-file` | `data/users.db` / `.session_secret` | 账号库与会话密钥 |
| `--tz` / `--currency` | `Asia/Shanghai` / `¥` | 显示口径 |

参数没给的回落同名环境变量, 再回落内置默认 —— 显式参数 > 环境变量 >
默认, 自动化与容器注入仍可走环境变量。

## 📄 许可证

[MIT](./LICENSE) © 2026 kinopico
