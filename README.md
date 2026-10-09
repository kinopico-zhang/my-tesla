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
![pytest](https://img.shields.io/badge/pytest-446%20passed-0A9EDC?logo=pytest&logoColor=white)
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

### 准备 · TeslaMate 连接参数

会来用 My Tesla 的人必然已经装好了 TeslaMate (还没装的看官方文档
[docs.teslamate.org](https://docs.teslamate.org/))。My Tesla 只读它的
PostgreSQL, 不往回写任何东西。数据链路:

```mermaid
%%{init: {"theme":"base","flowchart":{"curve":"basis","nodeSpacing":44,"rankSpacing":64},"themeVariables":{"fontSize":"14px","primaryColor":"#1b1b1e","primaryTextColor":"#f5f5f7","primaryBorderColor":"#4a4a4e","lineColor":"#8e8e93","edgeLabelBackground":"#1b1b1e","clusterBkg":"#111113","clusterBorder":"#3a3a3e"}}}%%
flowchart LR
    subgraph tmhost["🖥️ TeslaMate 所在机器 · docker compose"]
        tm["TeslaMate"] -- "行车数据落库" --> pg[("PostgreSQL<br/>.env 的 POSTGRES_*")]
    end
    car["🚗 特斯拉车辆"] -- "Tesla 账号" --> tm
    web["📱 浏览器 / 手机"] --> app["My Tesla"]
    app -. "只读查询 · 向导第二步填五项" .-> pg
    app -- "地图瓦片 · 道路拟合" --> amap["🗺️ 高德开放平台"]
    app -- "账号 · 设置 · Key" --> own[("自有 SQLite<br/>data/mytesla.db")]
    style app fill:#e82127,stroke:#5a1a1c,stroke-width:1.5px,color:#ffffff
```

首启向导第二步 (或之后的 设置 → 数据库) 要填的五项, 全部在 TeslaMate
那台机器的 `docker-compose.yml` / `.env` 里:

| 表单字段 | TeslaMate 那边 | 默认 |
|---|---|---|
| 地址 | 跑 TeslaMate 的那台机器 (见下) | — |
| 端口 | `database` 服务映射到宿主的端口 | `5432` |
| 用户 | `POSTGRES_USER` | `teslamate` |
| 密码 | `POSTGRES_PASSWORD` | — |
| 库名 | `POSTGRES_DB` | `teslamate` |

想不起来值, 在 TeslaMate 的 compose 目录里一条命令全打出来 (密码也在
里面):

```sh
docker compose exec database env | grep -E '^POSTGRES_'
```

地址只有一件事要注意: 官方 compose 默认**不**把 5432 发布到宿主 (只在
compose 内部网络互通), 跨机器访问要先给 `database` 服务加端口映射再重建
(加完 `docker compose up -d`):

```yaml
  database:
    ports:
      - "5432:5432"
```

- **My Tesla 装在别的机器** (常见): 地址填 TeslaMate 那台机器的 IP,
  端口 `5432`, 防火墙放行;
- **同一台机器**: 同样加端口映射, 地址填 `localhost`。

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

<p align="center">
<a name="shot-setup-1"><img src="docs/screenshot-setup-1.png" width="240" alt="向导第一步 · 建立管理员"></a>
<a name="shot-setup-2"><img src="docs/screenshot-setup-2.png" width="240" alt="向导第二步 · 填 TeslaMate 连接"></a>
<a name="shot-setup-3"><img src="docs/screenshot-setup-3.png" width="240" alt="向导第三步 · 填高德 Key"></a>
<br><b>① 建立管理员</b> — 注册即登录 · <b>② 数据源</b> — 五项按上表抄
TeslaMate 那台机器 · <b>③ 地图</b> — 高德 Key, 保存并进入应用
</p>

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
