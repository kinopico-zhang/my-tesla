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
![pytest](https://img.shields.io/badge/pytest-439%20passed-0A9EDC?logo=pytest&logoColor=white)
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

## 🚀 快速开始

需要 Python 3.13+ (venv) 与一个能连上的
[TeslaMate](https://docs.teslamate.org/) PostgreSQL 库:

```sh
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m app   # 配置全走命令行参数 (--help 看全量); 全默认首启走 /setup 引导
```

启动入口 `python -m app` (Windows 下 `.venv\Scripts\python -m app`), 部署
配置全走命令行参数 (`--help` 一屏看全)。端口只有一个: `data/certs/` 里
放了证书 (`fullchain.pem` + `privkey.pem`) 就走 HTTPS, 没放走 HTTP,
`--http` 可强制明文 (调试)。

打开 `http://<host>:8500/` → 自动进 `/tesla/charging`。账号库为空时
登录页会带去 `/setup` 引导页: 注册第一个管理员, 顺路配 TeslaMate 连接
与地图 Key, 全部可跳过、之后在设置页随时补。

## 📡 数据源

TeslaMate 连接三种给法 (优先级从高到低): 设置页里填 (存自有库, 改完热
重连实测) → 启动参数 `--teslamate-*` (回落环境变量 `TMDB_*`) → docker
容器定位 (与 TeslaMate 同机部署时)。数据只读, 不会往 TeslaMate 库写任何
东西。

高德 Key (服务平台选「Web端 JS API」, 个人开发者免费) 在设置页
「地图设置」里保存, 保存即生效; 未配置时地图页显示申请指引。

自有数据落在 `data/` (git 忽略): `mytesla.db` (轨迹断档补路等自产数据)
+ `users.db` 账号 + `certs/` 证书。

## ⚙️ 启动参数

全量清单 `python -m app --help` (分组帮助即部署文档), 常用项:

| 参数 | 默认 | 说明 |
|---|---|---|
| `--port` | `8500` | 端口: 证书目录有证书走 HTTPS, 没证书走 HTTP |
| `--teslamate-host` 等 | docker 定位 | TeslaMate PostgreSQL (设置页里填的优先) |
| `--mytesla-db` | `sqlite:///data/mytesla.db` | 自有库 (自产数据) |
| `--users-db` / `--secret-file` | `data/users.db` / `.session_secret` | 账号库与会话密钥 |
| `--tz` / `--currency` | `Asia/Shanghai` / `¥` | 显示口径 |

参数没给的回落同名环境变量 (如 `--teslamate-host` → `TMDB_HOST`), 再回落
内置默认 —— 显式参数 > 环境变量 > 默认, 自动化与容器注入仍可走环境变量。

## 📄 许可证

[MIT](./LICENSE) © 2026 kinopico
