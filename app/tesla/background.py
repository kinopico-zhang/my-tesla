"""TeslaMate 后台线程 (预热 ×2 + 高德 worker ×2) 的开动时机。

数据源没配 (真首启) 时这些线程没有可用的引擎 —— 起了也是对着占位主机
空转 (teslamate_engine.UNSET_HOST), 且设置保存热换引擎后线程手里的旧
工厂不跟手; 这里挂起等配置, 向导第二步存好真地址再现取工厂开动 (免
重启)。单仓与 My Home 组合部署共用同一份 (2026-10-09 起两仓 lifespan
都只调 launch_when_configured)。
"""
import threading
import time

from .. import database
from . import place_worker, roads_worker, settings_store
from . import speed_hist_cache, tracks_cache


def _start_all() -> None:
    """线程全量开动: 引擎工厂现取现用 (不吃热换前的旧引用)。"""
    # 后台预热轨迹缓存 (全量下采样 ~15s, 不阻塞启动)
    threading.Thread(target=tracks_cache.warm,
                     args=(database.session_factory(),), daemon=True).start()
    # 速度直方图预热 (行车采样积分, 冷启全量 ~60s; 有盘缓存时秒级)
    threading.Thread(target=speed_hist_cache.warm,
                     args=(database.session_factory(),), daemon=True).start()
    # 足迹「走过之路」拟合 worker (高德纠偏回填, 没配 Web 服务 key 就空转;
    # worker 自身先睡 90s 让两条预热先跑)
    threading.Thread(target=roads_worker.start,
                     args=(database.session_factory(),
                           database.own_session_factory()), daemon=True).start()
    # 常去地点命名 worker (高德逆地理回填, 同一把 Web 服务 key; 先睡 150s
    # 与 roads 错峰)
    threading.Thread(target=place_worker.start,
                     args=(database.session_factory(),
                           database.own_session_factory()), daemon=True).start()


def launch_when_configured() -> None:
    """数据源已配 (设置行/env/docker 任一) 立即开动; 真首启未配则 5s 一查
    自有库, 配好即开。"""
    def teslamate_ready() -> bool:
        with database.own_session_factory()() as own:  # pylint: disable=not-callable
            return "teslamate" not in settings_store.wizard_missing(own)

    if teslamate_ready():
        _start_all()
        return

    def wait_then_start() -> None:
        while not teslamate_ready():
            time.sleep(5)
        _start_all()

    threading.Thread(target=wait_then_start, daemon=True).start()
