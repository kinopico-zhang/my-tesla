"""全量轨迹缓存: 全库下采样扫描很慢 (~15s), 用 内存 + 磁盘 两级缓存,
按 drive id 增量追加 (已完成行程不会变更, 新行程 id 单调递增, 无需失效;
下采样算法变更时版本号 +1, 旧缓存自动作废全量重建)。

磁盘格式与旧版完全兼容: {"v": 2, "max_id": int, "tracks": [...]},
所以 data/tracks_cache.json 里已生成的缓存可继续使用, 不必重扫全库。
"""
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .. import config
from . import repository
from .schemas import MapTrack

CACHE_VERSION = 2


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


def filter_by_date(tracks: list[MapTrack], frm: str | None,
                   to: str | None) -> list[MapTrack]:
    """按本地日期过滤缓存轨迹 (YYYY-MM-DD 字符串比较, 与旧版一致)。"""
    if frm:
        tracks = [t for t in tracks if t.date >= frm]
    if to:
        tracks = [t for t in tracks if t.date <= to]
    return tracks


def warm(factory: sessionmaker[Session]) -> None:
    """启动时后台预热 (失败静默, 首次访问会重试)。"""
    try:
        load_tracks(factory)
    except (SQLAlchemyError, OSError):
        pass


def _read_disk_cache() -> tuple[int, list[MapTrack]]:
    """读磁盘缓存; 版本不符 / 损坏一律当作没有 (全量重建)。"""
    try:
        with open(cache_file(), encoding="utf-8") as handle:
            data = json.load(handle)
        if int(data["v"]) != CACHE_VERSION:
            return -1, []
        tracks = [MapTrack.model_validate(t) for t in data["tracks"]]
        return int(data["max_id"]), tracks
    except (OSError, ValueError, TypeError, KeyError, AttributeError,
            ValidationError):
        return -1, []


def _write_disk_cache(max_id: int, tracks: list[MapTrack]) -> None:
    """落盘 (临时文件 + 原子替换); 失败不影响本次响应。"""
    try:
        path = Path(cache_file())
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(path) + ".tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump({"v": CACHE_VERSION, "max_id": max_id,
                       "tracks": [t.model_dump() for t in tracks]},
                      handle, separators=(",", ":"))
        os.replace(tmp, path)
    except OSError:
        pass
