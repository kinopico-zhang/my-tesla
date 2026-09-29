"""全量轨迹缓存: 全库全精度扫描很慢 (上百万点要几分钟), 用 内存 + 磁盘
两级缓存, 按 drive id 增量追加 (已完成行程不会变更, 新行程 id 单调递增,
无需失效; 轨迹格式变更时版本号 +1, 旧缓存自动作废全量重建)。

缓存全车合存 (每条轨迹带 car_id), 全精度下发 pts 扁平数组, 时间/车辆/
驾驶员筛选不再在读取侧做 —— 客户端拿清单 (build_manifest) 在本地筛,
轨迹本体存浏览器 IndexedDB 按清单增量下载。

磁盘缓存是 JSONL (首行头 {v, max_id}, 之后一行一条轨迹): 全量几百万点
整册 json.load 会同时顶起原始 dict 树 + 模型拷贝两份大内存, 小内存 NAS
直接 swap 颠簸假死, 读取侧逐行解析、写入侧逐条落盘配对。
"""
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .. import config
from . import repository, roads_fit
from .models import TripDriver
from .schemas import MapManifest, MapManifestTrack, MapTrack

CACHE_VERSION = 5


@dataclass
class _CacheState:
    """内存缓存水位: 已覆盖到的最大 drive id 与全量轨迹。"""

    max_id: int
    tracks: list[MapTrack]


class _Cache:
    """模块级缓存持有者 (避免 global 语句; 测试用 reset 清空)。"""

    state: _CacheState | None = None


_cache = _Cache()
_lock = threading.Lock()


def reset() -> None:
    """清空内存缓存 (测试隔离用)。"""
    _cache.state = None


def cache_file() -> str:
    """磁盘缓存路径 (测试用 MAP_CACHE_FILE 重定向)。"""
    return os.environ.get("MAP_CACHE_FILE") or str(
        config.PROJECT_DIR / "data" / "tracks_cache.json")


def load_tracks(factory: sessionmaker[Session]) -> list[MapTrack]:
    """取全量轨迹: 内存新鲜直接返回; 落后则增量追加; 进程首访走磁盘缓存。"""
    with _lock:
        with factory() as session:
            max_id = repository.drive_max_id(session)
            state = _cache.state
            if state is not None and state.max_id >= max_id:
                return state.tracks
            if state is not None:
                after, merged = state.max_id, state.tracks
            else:
                after, merged = _read_disk_cache()
            new = (repository.query_tracks(session, after)
                   if after < max_id else [])
        merged = sorted(merged + new, key=lambda track: track.date)
        _cache.state = _CacheState(max_id=max_id, tracks=merged)
        if new:  # 有新数据才落盘
            _write_disk_cache(max_id, merged)
        return merged


def build_manifest(tracks: list[MapTrack], own: Session) -> MapManifest:
    """全量轨迹清单: 每条一行 {id, n, d, c, t, s, rn, m}。

    驾驶员标注在自有库且随标/清变动 —— 不进缓存, 清单每次现算; 道路
    拟合态 (s/rn) 同口径现算 (worker 随时在写新行), rd/rt 拼出进度。
    客户端拿清单对账本地 IndexedDB (缺的/n 不符的重下, 多余的删掉)
    并在本地按 t/c/d 做筛选, 轨迹本体不再按筛选请求。"""
    drivers: dict[int, int] = {}
    for drive_id, driver_id in own.execute(
            select(TripDriver.drive_id, TripDriver.driver_id)).all():
        drivers[drive_id] = driver_id
    roads = repository.roads_lite(own)
    rows: list[MapManifestTrack] = []
    done = 0
    for t in tracks:
        status, rn, ver = roads.get(t.id, ("", 0, 0))
        if ver != roads_fit.ROAD_FIT_V:      # 旧算法版本的行不算数
            status, rn = "", 0
        else:
            done += 1
        s = 1 if status == "ok" else (3 if status == "guess"
                                      else (2 if status else 0))
        rows.append(MapManifestTrack(id=t.id, n=len(t.pts) // 2,
                                     d=drivers.get(t.id), c=t.car_id, t=t.date,
                                     s=s, rn=rn if s in (1, 3) else 0, m=t.min))
    return MapManifest(v=CACHE_VERSION, tracks=rows, rv=roads_fit.ROAD_FIT_V,
                       rd=done, rt=len(tracks))


def warm(factory: sessionmaker[Session]) -> None:
    """启动时后台预热 (失败静默, 首次访问会重试)。"""
    try:
        load_tracks(factory)
    except (SQLAlchemyError, OSError):
        pass


def _read_disk_cache() -> tuple[int, list[MapTrack]]:
    """读磁盘缓存 (JSONL, 见模块头); 逐行解析校验, 原始 dict 用完即弃;
    版本不符 / 损坏一律当作没有 (全量重建)。"""
    try:
        with open(cache_file(), encoding="utf-8") as handle:
            head = json.loads(handle.readline())
            if int(head["v"]) != CACHE_VERSION:
                return -1, []
            tracks = [MapTrack.model_validate(json.loads(line))
                      for line in handle if line.strip()]
        return int(head["max_id"]), tracks
    except (OSError, ValueError, TypeError, KeyError, AttributeError,
            ValidationError):
        return -1, []


def _write_disk_cache(max_id: int, tracks: list[MapTrack]) -> None:
    """落盘 (临时文件 + 原子替换, JSONL 一行一条); 失败不影响本次响应。"""
    try:
        path = Path(cache_file())
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(path) + ".tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"v": CACHE_VERSION, "max_id": max_id},
                                    separators=(",", ":")) + "\n")
            for track in tracks:
                handle.write(json.dumps(track.model_dump(),
                                        separators=(",", ":")) + "\n")
        os.replace(tmp, path)
    except OSError:
        pass
