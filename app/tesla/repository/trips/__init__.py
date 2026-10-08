"""行程域门面: 列表/标注/断档补路/轨迹/分组/统计, 统一名面重导出。

按职能分家: 条目组装与过滤在 trip_listing, 驾驶员/过路费标注在
trip_marks, 断档补路在 gap_fills, 单条与合并轨迹在 trip_tracks,
分组在 trip_groups, 统计聚合在 trip_stats (2026-09-27 新增, 参照
充电统计; 常去地点链 2026-09-30 再拆 trip_places —— 停车事件口径,
其隐藏/改名写侧 2026-10-08 又拆 place_admin), 调用方统一
repository.trips.xxx / from ..trips import …, 不感知内部分层。
"""
from .gap_fills import (
    EARTH_RADIUS_KM,
    FILL_STEP_KM,
    GAP_ANCHOR_MAX_KM,
    fills_version,
    save_fill,
)
from .place_admin import (
    place_hidden_set,
    set_place_alias,
    set_place_hidden,
)
from .trip_groups import (
    delete_trip_group,
    list_trip_groups,
    rename_trip_group,
    save_trip_group,
)
from .trip_hist import track_hist
from .trip_listing import (
    TripFilter,
    _trip_item,
    drive_open,
    get_trip,
    list_trip_regions,
    list_trips,
)
from .trip_marks import (
    _driver_condition,
    annotate_drivers,
    annotate_tolls,
    driver_scope,
    save_trip_toll,
    set_trip_driver,
)
from .trip_places import trip_locations
from .trip_stats import (
    trip_dimensions,
    trip_driver_stats,
    trip_monthly,
    trip_summary,
)
from .trip_tracks import (
    MERGED_TRACK_BUDGET,
    MERGED_TRACK_PER_MIN,
    TRIP_TRACK_PER,
    MergedPlan,
    _utc_seconds,
    closed_drive_ids_between,
    merged_track,
    merged_track_plan,
    merged_track_segments,
    trip_track,
)

__all__ = [
    "EARTH_RADIUS_KM", "FILL_STEP_KM", "GAP_ANCHOR_MAX_KM",
    "MERGED_TRACK_BUDGET", "MERGED_TRACK_PER_MIN", "MergedPlan",
    "TRIP_TRACK_PER", "TripFilter", "_driver_condition", "_trip_item",
    "_utc_seconds",
    "annotate_drivers", "annotate_tolls", "closed_drive_ids_between", "drive_open",
    "delete_trip_group", "driver_scope",
    "get_trip", "fills_version", "list_trip_groups", "list_trip_regions", "list_trips",
    "merged_track", "merged_track_plan", "merged_track_segments",
    "place_hidden_set",
    "rename_trip_group", "save_fill", "save_trip_group", "save_trip_toll",
    "set_place_hidden", "set_trip_driver", "track_hist", "trip_dimensions",
    "trip_driver_stats",
    "set_place_alias", "trip_locations",
    "trip_monthly", "trip_summary", "trip_track",
]
