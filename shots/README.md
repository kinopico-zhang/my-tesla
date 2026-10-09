# shots/ — README 全页截图复刻管线

把 README 的 15 张 iPhone 17 Pro 设备截图 (docs/screenshot-*.png) 从零复刻出来:
种子服务器 → 无头射手 → 官方边框合成, 三步。全部中间产物落在 `$SHOTLAB`
(默认 `/tmp/shotlab`, 可再生, 不进仓); 本目录只进脚本与自制资产。

`pylint`/`mypy` 只扫 `app`/`tests`, 本目录不参与静态检查。

## 一次性准备

1. **边框** (Apple 官方资产, 不可再分发, 不进仓): 从
   [design resources](https://developer.apple.com/design/resources/) 下载
   `Bezel-iPhone-17.dmg`, 然后
   `python shots/undmg.py` 解出 PNG (纯 python 解 UDIF, carve 全部内嵌图),
   取 `010_1350x2760.png` 放到 `$SHOTLAB/bezel-png/`。
2. **字体** (截图里的中文要与 macOS 观感一致): 苹方三字重
   `PingFangSC-Regular/Medium/Semibold.otf` 装到 `~/.fonts/pingfang/` 后
   `fc-cache -f`。页面 CSS 字体栈点名 `"PingFang SC"`。
3. **无头浏览器环境** (本机 WSL 的 chromium 缺系统库):
   `LD_LIBRARY_PATH=/home/admin/pwlibs/extracted/usr/lib/x86_64-linux-gnu`,
   Python 环境带 `playwright` + `Pillow` (合成用)。

## 三步流程

```bash
# 1. 种子服务器: 假数据实例 (账号 admin/shot-pass-123), 打印 READY 后保持存活。
#    首次跑要对高德做 ~34 段驾车规划 (真实 Web 服务 Key, 几分钟 + 要网),
#    种子库一次成型: teslamate.db 已在即整库复用直接起服
#    (重建: 删 SHOTLAB 库或 SHOT_RESEED=1)。
.venv/bin/python shots/seed_server.py 8901

# 2. 射手: 15 个视图各一张 (开场动画一律等收完; 足迹地图手动定格回放终帧)。
#    原图 → $SHOTLAB/pages/tesla-<视图>.png。可带过滤词只拍一张, 如 `groups`。
LD_LIBRARY_PATH=... /tmp/pw-verify/bin/python shots/shoot.py

# 3. 合成: 官方 bezel + 状态栏/时间/电池/home bar → $SHOTLAB/final/。
LD_LIBRARY_PATH=... PYTHONPATH=<Pillow 所在> /tmp/pw-verify/bin/python shots/composite.py

# 4. 收尾: cp $SHOTLAB/final/tesla-*.png docs/screenshot-<视图>.png,
#    README 表格对齐, 提交 (纯图片提交不用等 CI)。
```

## 文件

| 文件 | 职责 |
|---|---|
| `seed_server.py` | 假数据实例: 充电 ~280 条跨 15 个月 (月度柱状图铺满 12 个月滑窗; 满充带额定续航采样, 331→322km 缓降喂电池健康曲线) + ~1000 程「一笔画」路网 (~两万公里, 近/中/远频次分层) + 双驾驶员 + 行程分组 + 地址坐标 (充电地图圆标) + 演示 app_settings (设置页回显) |
| `shoot.py` | 15 视图射手: 每视图独立 context (localStorage 预置视图), 等数据锚点 + 动画收尾; 地图是手动定格回放终帧的特例流程 |
| `composite.py` | 官方 bezel 合成: 预乘缩放 (透明留白 RGB 不渗边) + 洞形蒙版 (方角内容出不了圆角开窗) + 底部 34px 安全区拉伸补齐 |
| `undmg.py` | Apple dmg → PNG carver (解 UDIF blkx, carve 内嵌 PNG) |
| `assets/icons/` | 状态栏电池/信号与 home bar 图标 (自制, 随仓) |

## 种子数据口径

- 坐标是城市级演示点位 (非真实); 时间链 UTC 落库, 与生产口径一致。
- `MYHOME_PROD_DB` (默认根仓 `data/mytesla.db`, 只读) 只取 `amap_web_key`
  做道路拟合规划; 盘缓存 (`MAP_CACHE_FILE` 等) 一律重定向到 `$SHOTLAB/tesla/`,
  **绝不碰** 子仓 `data/` 下的生产缓存。
- 行程分组按地址走廊现查 drive id (种子重跑 id 会漂移, 不写死)。
