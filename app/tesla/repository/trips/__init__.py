"""行程域门面: 列表/标注/断档补路/轨迹/分组, 统一名面重导出。

按职能分家: 条目组装与过滤在 trip_listing, 驾驶员/过路费标注在
trip_marks, 断档补路在 gap_fills, 单条与合并轨迹在 trip_tracks,
分组在 trip_groups; 调用方统一 repository.trips.xxx /
from ..trips import …, 不感知内部分层。
"""
from .gap_fills import (
    EARTH_RADIUS_KM,
    FILL_STEP_KM,
    GAP_ANCHOR_MAX_KM,
    save_fill,
)
from .trip_groups import (
    delete_trip_group,
    list_trip_groups,
    rename_trip_group,
    save_trip_group,
)
from .trip_listing import (
    TripFilter,
    get_trip,
    list_trip_regions,
    list_trips,
)
from .trip_marks import (
    _driver_condition,
    annotate_drivers,
    annotate_tolls,
    driver_scope,
    filter_map_tracks_by_driver,
    save_trip_toll,
    set_trip_driver,
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
    "TRIP_TRACK_PER", "TripFilter", "_driver_condition", "_utc_seconds",
    "annotate_drivers", "annotate_tolls", "closed_drive_ids_between",
    "delete_trip_group", "driver_scope", "filter_map_tracks_by_driver",
    "get_trip", "list_trip_groups", "list_trip_regions", "list_trips",
    "merged_track", "merged_track_plan", "merged_track_segments",
    "rename_trip_group", "save_fill", "save_trip_group", "save_trip_toll",
    "set_trip_driver", "trip_track",
]
