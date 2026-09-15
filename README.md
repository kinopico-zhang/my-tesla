# My Tesla

读取 NAS 上 `teslamate_cn` (TeslaMate) 的 PostgreSQL 数据, 用手机友好的
iOS 风格页面展示充电与行驶数据: 充电记录瀑布流 + 充电曲线、充电统计、
充电地图热力图、足迹地图轨迹回放、行程列表与合并播放、当前驾驶实时页。
2026-09-15 起从「My Home」伞形应用 (myteslamate) 拆出, 独立成库 ——
账号体系随迁, 记账 (My Money) 与听歌 (My Music) 留在原仓库。

## 页面与 URL

业务页面全部挂在 `/tesla` 前缀下 (与拆库前一致, 老书签不动):

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

账号体系在根路径 (账号跟应用走, 不在业务前缀下):

| 路径 | 说明 |
|---|---|
| `/login` `/register` | 登录 / 凭邀请注册 |
| `/accounts` | 账号管理 (仅管理员: 用户列表 / 签发撤销邀请) |
| `/api/*` | 账号接口 (login / logout / register / me / 自助改名改密) |

旧地址 (`/tesla/login`、`/tesla/register`、`/tesla/accounts`、`/tesla/api/*`)
302/307 兼容, 已发出去的邀请链接不断。静态资源: `/tesla/static/*` (应用页)
与 `/static/*` (账号页 + 全站小件 menu-user / changelog-page)。

## 鉴权与账号

- 无状态 HMAC 签名 cookie (默认 90 天, 密钥在仓库根 `.session_secret`,
  首启自动生成, 不进 git)
- 首启种管理员: `AUTH_USER` / `AUTH_PASS` (不设则默认值), 之后走界面改
- 多账号: 管理员在 `/accounts` 生成一次性邀请链接 (1/7/30 天), 家人注册后
  各有各的账号; 除账号管理外的功能都能用
- 登录防爆破: 单 IP 连续失败 5 次锁定 60 秒
- 应用页会话过期跳 `/tesla/login` (不越出 PWA scope, 全屏 App 不弹回
  Safari); 账号层跳 `/login`

## 运行

```sh
./run.sh                 # 有 data/certs/ 时: HTTPS :8500 + HTTP :8501 双开
PORT=9000 ./run.sh       # 换 HTTPS 端口 (HTTP 侧用 HTTP_PORT, 默认 8501)
HTTP_PORT=8600 ./run.sh  # 换 HTTP 端口
HTTP=1 ./run.sh          # 临时只开明文调试 (无证书时也是单明文)
```

HTTPS 与 HTTP 同时服务 (两个进程): 域名 + 证书走 HTTPS, 局域网 IP 直连
走 HTTP; 会话 cookie 是无状态 HMAC 签名, 两个口通用。

`run.sh` 自动加载同目录 `.env` (模板见 `.env.example`): 足迹地图需要高德
开放平台的 Key (`AMAP_KEY` + `AMAP_SECURITY_CODE`, 服务平台选「Web端 JS API」,
个人开发者免费)。未配置时地图页显示申请指引。

依赖装在 `.venv` (Python 3.13, 由 `../python-env` 的 uv 创建 —— NAS 上的
布局, 别的环境用任意方式建 3.13 venv 即可):

```sh
export UV_CACHE_DIR=../python-env/uv-cache UV_PYTHON_INSTALL_DIR=../python-env/uv-python
../python-env/bin/uv venv .venv
../python-env/bin/uv pip install --python .venv/bin/python \
  -r requirements.txt -r requirements-dev.txt
```

## 结构

```
app/main.py               FastAPI 入口: 账号路由 + 中间件 (鉴权/搬家重定向/缓存)
app/config.py             环境变量集中读取
app/database.py           三组引擎: TeslaMate PostgreSQL / 自有 SQLite / 账号 SQLite
app/models.py             账号库表 (users + invitations, data/users.db)
app/account_store.py      账号逻辑 (scrypt 密码 / 邀请 / 管理员种子)
app/authentication.py     HMAC 会话 token + 登录限速
app/changelog.py          更新日志数据 (人工维护的版本批次)
app/tesla/                业务包: models / repository (全部 SQL) / 9 个页面
                          路由 + 页面静态文件 (含 echarts / 高德轨迹工具)
app/static/               账号层页面 (login / register / accounts) + 全站小件
tests/                    pytest 后端测试 + tests/js 前端纯逻辑测试 (node:test)
data/                     运行态: mytesla.db / users.db / tracks_cache.json /
                          certs/ (git 忽略)
```

## 数据源

- TeslaMate 的 PostgreSQL 容器 (`teslamate_cn_database_1`), 启动时 docker
  inspect 自动解析容器 IP; 也可 `TMDB_HOST` 直接指定, 或在设置页保存连接
  (存自有库, 优先级最高)
- 三组连接池互不相干: TeslaMate 原库 (只读, 迁移建表)、自有库
  (`data/mytesla.db`: 断档补路 / 行程分组 / 设置)、账号库 (`data/users.db`)
- 库内时间戳为 UTC, 对外输出本地时间 (`TZ_NAME`, 默认 Asia/Shanghai)
- 轨迹性能: positions 表千万行, 全量下采样 ~15s, 结果落盘 `data/` 增量追加,
  启动时后台线程预热

## 测试与 CI

```sh
./run_tests.sh                                  # 全部 (后端 + 前端)
.venv/bin/python -m pytest tests -q             # 后端 (pytest)
node --test tests/js/                           # 前端纯逻辑 (node:test)
```

后端测试不依赖真实数据库: conftest 给每个用例注入独立的 SQLite 文件库,
TestClient 不触发 lifespan —— 不碰 docker、不碰 PostgreSQL, 任何机器可跑。

GitHub Actions 是门禁 (`.github/workflows/ci.yml`):

- **python-tests**: ubuntu / windows / macos × 新旧 runner × Python 3.13
  (外加 ubuntu × 3.14), `fail-fast: false` 互不遮蔽
- **python-lint**: pylint (app 严检, tests 放宽仪式告警) + mypy 严格
- **frontend**: 三平台 × Node 22, ESLint / tsc --checkJs / node --test;
  c8 覆盖率门禁 95% (仅 Linux, 5 个纯逻辑 JS 模块)

## NAS 部署

服务以 admin 身份后台跑, 日志 `/tmp/my-tesla.log`:

```sh
deploy/restart_service.sh    # 停旧进程 + 起服务 (acme.sh 续期 reloadcmd 也是它)
```

### 从旧仓库 (myteslamate) 迁移数据

第一次切换服务前, 把运行态数据拷过来 (`.env`、`.session_secret` 同理,
都不在 git 里):

```sh
cd /share/CACHEDEV1_DATA/Public
cp -a myteslamate/data/users.db myteslamate/data/mytesla.db \
      myteslamate/data/tracks_cache.json my-tesla/data/
cp -a myteslamate/data/certs my-tesla/data/          # HTTPS 证书
cp -a myteslamate/.env myteslamate/.session_secret my-tesla/
```

然后停旧服务、起本仓库服务 (注意端口冲突: 先停旧再启新), 冒烟:

```sh
curl -sI https://…:8500/         # 302 → /tesla/charging
curl -sI http://…:8501/          # 同样 302 (局域网明文口)
curl -sk https…/login | grep '<title>'   # 登录 · My Tesla
curl -s -o /dev/null -w '%{http_code}' https…/api/me   # 401 (未登录)
```
