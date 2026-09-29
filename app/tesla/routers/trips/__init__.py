"""行程 API 装配: 列表/详情/合并轨迹(整包+流式)/直方图/分组/过路费/驾驶员归集。

按职能分家: 列表与标注在 trip_sessions, 轨迹三种取法 (单条/合并整包与
流式/断档补路回传) 在 trip_tracks (速度档直方图 2026-09-27 拆去
trip_hist —— trip_tracks 被缓存批次顶到行数上限), 分组 CRUD 在
trip_groups, 统计五路 (汇总/按月/常去地点/司机里程/维度) 在 trip_stats;
这里装配对外名面 trips (URL 前缀与旧版完全一致, 根 app 只认
trips_routes.trips)。
"""
from fastapi import APIRouter

from . import trip_groups, trip_hist, trip_sessions, trip_stats, trip_tracks

trips = APIRouter(prefix="/tesla/trips/api")
trips.include_router(trip_sessions.router)
trips.include_router(trip_tracks.router)
trips.include_router(trip_hist.router)
trips.include_router(trip_groups.router)
trips.include_router(trip_stats.router)
