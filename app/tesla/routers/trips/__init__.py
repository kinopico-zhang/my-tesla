"""行程 API 装配: 列表/详情/合并轨迹(整包+流式)/分组/过路费/驾驶员归集。

按职能分家: 列表与标注在 trip_sessions, 轨迹三种取法 (单条/合并整包与
流式/断档补路回传) 在 trip_tracks, 分组 CRUD 在 trip_groups; 这里装配
对外名面 trips (URL 前缀与旧版完全一致, 根 app 只认 trips_routes.trips)。
"""
from fastapi import APIRouter

from . import trip_groups, trip_sessions, trip_tracks

trips = APIRouter(prefix="/tesla/trips/api")
trips.include_router(trip_sessions.router)
trips.include_router(trip_tracks.router)
trips.include_router(trip_groups.router)
