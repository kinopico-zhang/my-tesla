<div align="center">

# <img src="https://cdn.simpleicons.org/tesla/E82127" height="26" alt="Tesla"> My Tesla

**TeslaMate 可视化工具**

[![CI](https://github.com/kinopico-zhang/my-tesla/actions/workflows/ci.yml/badge.svg)](https://github.com/kinopico-zhang/my-tesla/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/kinopico-zhang/my-tesla)](./LICENSE)
![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-3776AB?logo=python&logoColor=white)
![Node.js](https://img.shields.io/badge/Node.js-22-339933?logo=nodedotjs&logoColor=white)
![OS](https://img.shields.io/badge/OS-Linux%20%7C%20Windows%20%7C%20macOS-0078D6)
![Docker](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)
<br>
![pylint](https://img.shields.io/badge/pylint-10.00%2F10-brightgreen)
![mypy](https://img.shields.io/badge/mypy-strict-2A6DB2)
![pytest](https://img.shields.io/badge/pytest-471%20passed-0A9EDC?logo=pytest&logoColor=white)
![coverage](https://img.shields.io/badge/JS%20coverage-95%25%2B-brightgreen)
<br>
![ESLint](https://img.shields.io/badge/ESLint-passing-4B32C3?logo=eslint&logoColor=white)
![tsc](https://img.shields.io/badge/tsc-checkJS-3178C6?logo=typescript&logoColor=white)
![stylelint](https://img.shields.io/badge/stylelint-passing-263238?logo=stylelint&logoColor=white)
![html-validate](https://img.shields.io/badge/html--validate-passing-brightgreen)

</div>

## 1. 功能

<p align="center">
<a name="shot-live"><img src="docs/screenshot-live.png?v=4" width="280" alt="状态 · My Tesla (演示数据)"></a>
<br><b>状态</b> — 车开到哪、还剩多少电、还能跑多远, 打开即见; 行驶中蓝点实时跟车
</p>

<p align="center">
<a name="shot-trips"><img src="docs/screenshot-trips.png?v=2" width="280" alt="行程轨迹 · My Tesla (演示数据)"></a>
<br><b>行程轨迹</b> — 每一趟去了哪、开了多久、耗了多少电, 随时翻旧账
</p>

<p align="center">
<a name="shot-trip"><img src="docs/screenshot-trip.png?v=2" width="280" alt="单个行程 · My Tesla (演示数据)"></a>
<br><b>单个行程</b> — 回放这一趟怎么开的: 路线按车速着色, 横滑看速度与电耗曲线
</p>

<p align="center">
<a name="shot-tripstats"><img src="docs/screenshot-tripstats.png?v=2" width="280" alt="行程统计 · My Tesla (演示数据)"></a>
<br><b>行程统计</b> — 一段时间开了多少公里、平均电耗多少, 趋势与分布一眼看完
</p>

<p align="center">
<a name="shot-groups"><img src="docs/screenshot-groups.png?v=2" width="280" alt="行程分组 · My Tesla (演示数据)"></a>
<br><b>行程分组</b> — 出差、周末出行各归一册, 分开算用车账; 组里组外的行程在「详细行程」页随手点选增减
</p>

<p align="center">
<a name="shot-map"><img src="docs/screenshot-map.png?v=2" width="280" alt="足迹地图 · My Tesla (演示数据)"></a>
<br><b>足迹地图</b> — 车轮碾过的每条路都亮在地图上, 拖时间轴回放这些年跑过的路
</p>

<p align="center">
<a name="shot-charging"><img src="docs/screenshot-charging.png?v=2" width="280" alt="充电记录 · My Tesla (演示数据)"></a>
<br><b>充电记录</b> — 每次在哪充、充了多少、花了几块钱, 按区域翻查
</p>

<p align="center">
<a name="shot-stats"><img src="docs/screenshot-stats.png?v=2" width="280" alt="充电统计 · My Tesla (演示数据)"></a>
<br><b>充电统计</b> — 每月充电量与花销的趋势, 用电的账一清二楚
</p>

<p align="center">
<a name="shot-battery"><img src="docs/screenshot-battery.png?v=2" width="280" alt="电池健康 · My Tesla (演示数据)"></a>
<br><b>电池健康</b> — 电池还剩几成、衰减快不快, 曲线直接说话
</p>

<p align="center">
<a name="shot-chargemap"><img src="docs/screenshot-chargemap.png?v=2" width="280" alt="充电地图 · My Tesla (演示数据)"></a>
<br><b>充电地图</b> — 常去充电点的地理分布, 陌生地方先看哪里充过电
</p>

## 2. 系统架构

<p align="center">
<a name="arch"><img src="docs/architecture.svg?v=7" width="800" alt="My Tesla 数据链路"></a>
</p>

## 3. 部署

两条路任选一条: 容器一条命令起 (推荐, 不用装 Python), 或者手动跑 (改代码时更方便)。

### 3.1 Docker

```sh
git clone https://github.com/kinopico-zhang/my-tesla.git
cd my-tesla
mkdir -p data                     # 持久化目录, 见下
docker compose up -d --build
```

镜像基于 `python:3.13-slim`, 装好依赖、以非 root (uid 1000) 运行,
`HEALTHCHECK` 探活打在公开的 `/login` 上。浏览器打开
`http://<host>:8500/`, 见到登录页 (未初始化则是四页向导) 就是服务正常。

运行期只有 `./data` 一处需要持久化: 两个 SQLite 库 (`mytesla.db`、
`users.db`)、轨迹与车速缓存, 以及首次启动自动生成的会话密钥
`.session_secret`。删掉这个目录等于重置整个应用 (含管理员账号)。
容器内是 uid 1000, 若宿主上 `data/` 的属主不是 1000 且不可写,
`chown -R 1000:1000 data` 即可 (或以 `user: "<uid>:<gid>"` 覆盖)。

连 TeslaMate 有两种接法:

- **首启在向导里填** —— 最简单。连接值存进 `data/` 里的自有库, 之后
  改设置页即可, 不用重启容器;
- **启动前用环境变量预置** —— 照 `.env.example` 复制成 `.env` 填写
  `TMDB_HOST` / `TMDB_PORT` / `TMDB_USER` / `TMDB_PASS` / `TMDB_NAME`。
  TeslaMate 官方 compose 的服务名是 `database`, 把 `docker-compose.yml`
  末尾那段 `networks` 注释打开 (改成自己的项目名, 默认
  `teslamate_default`), 两者就能直连; 更省事的做法是把 `my-tesla`
  这一段直接贴进 TeslaMate 的 compose file, 同网络自动连通。

`MYTESLA_PORT` 改宿主端口, `TZ` / `TZ_NAME` 改时区 (默认 `Asia/Shanghai`)。
容器只跑明文 HTTP; 要上 HTTPS 就在前面放反向代理, 或挂进证书目录并
覆盖 `command` 加 `--cert-file` / `--key-file`。

### 3.2 手动运行

需要 Python 3.13+:

```sh
git clone https://github.com/kinopico-zhang/my-tesla.git
cd my-tesla
python3.13 -m venv .venv          # Windows: py -3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m app           # Windows: .venv\Scripts\python -m app
```

终端打出 `Uvicorn running on http://0.0.0.0:8500` 即已启动; 浏览器打开
`http://<host>:8500/`, 见到登录页 (未初始化则是四页向导) 就是服务正常。

监听 `--host` (默认 `0.0.0.0`)、端口 `--port` (默认 `8500`)。端口分两种情况:

- **有证书**: `--cert-file` 与 `--key-file` 指到 `fullchain.pem` 与
  `privkey.pem`, 走 `https://<host>:8500/`;
- **没证书**: 直接启动, 走 `http://<host>:8500/` (`--http` 可强制明文,
  调试用)。

## 4. 初始化

四页向导一路走: 管理员 → 数据源 → 地图 → 完成。数据源与地图两页各带
「测试」钮 —— 数据库真连一次、地图 Key 真验一遍, 测试通过「下一步」才
解锁, 改过输入就作废重测; 最后一页把三页所填汇总过目, 点「进入应用」
进入应用。导航按钮常驻屏幕底部, 与表单内容分离。

### 4.1 建立管理员

注册管理员账号, 注册即登录。

<p align="center">
<a name="shot-setup-1"><img src="docs/screenshot-setup-1.png?v=2" width="240" alt="向导第一页 · 建立管理员"></a>
</p>

### 4.2 数据源

填 TeslaMate 的 PostgreSQL 连接, 保存即实测连通。五项全部在 TeslaMate
那台机器的 `docker-compose.yml` / `.env` 里:

<table align="center">
<thead><tr><th>表单字段</th><th>TeslaMate 那边</th><th>默认</th></tr></thead>
<tbody>
<tr><td>地址</td><td>跑 TeslaMate 的那台机器 (见下)</td><td>—</td></tr>
<tr><td>端口</td><td><code>database</code> 服务映射到宿主的端口</td><td><code>5432</code></td></tr>
<tr><td>用户</td><td><code>POSTGRES_USER</code></td><td><code>teslamate</code></td></tr>
<tr><td>密码</td><td><code>POSTGRES_PASSWORD</code></td><td>—</td></tr>
<tr><td>库名</td><td><code>POSTGRES_DB</code></td><td><code>teslamate</code></td></tr>
</tbody>
</table>

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

<p align="center">
<a name="shot-setup-2"><img src="docs/screenshot-setup-2.png?v=3" width="240" alt="向导第二页 · 填 TeslaMate 连接"></a>
</p>

### 4.3 地图

填地图 Key、安全码和 Web Key, 先点「测试」验证, 通过了「下一步」才解锁。

**地图 Key 与安全码** (服务平台选「Web端 (JS API)」):

- 打开 <a href="https://console.amap.com" target="_blank">高德开放平台控制台</a>, 注册并登录
- 左侧「应用管理」→「创建新应用」
- 在应用里「添加 Key」, 服务平台选「Web端 (JS API)」
- Key 生成后点开详情, 「安全密钥」就是这里的安全码 —— Key 和安全码配套,
  换新 Key 要配新安全码

**Web Key** (足迹道路拟合要用):

- 在同一个应用的「添加 Key」再来一把, 服务平台选「Web服务」
- 和上面的地图 Key 是两种类型, 不能混用
- 只在服务端用: 把足迹轨迹拟合到实际道路

<p align="center">
<a name="shot-setup-3"><img src="docs/screenshot-setup-3.png?v=4" width="240" alt="向导第三页 · 填高德 Key"></a>
</p>

### 4.4 完成

最后一页把三页所填汇总过目 —— 密码与 Key 只显示打码后的样子。点
「进入应用」进入应用, 直接落到状态页。

<p align="center">
<a name="shot-setup-4"><img src="docs/screenshot-setup-4.png?v=2" width="240" alt="向导第四页 · 所填汇总与进入应用"></a>
</p>

## 5. 许可证

[MIT](./LICENSE) © 2026 kinopico
