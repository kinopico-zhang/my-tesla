"""数据访问层门面: 按域拆成五个模块, 这里统一重导出 (调用方不必关心分布)。"""

from .common import (  # pylint: disable=unused-import
    BBox,
    DateRange,
    NotFound,
    fdate,
    ftime,
    parse_date_range,
    parse_region,
    region_address_ids,
    to_local,
)

from .charging import (  # pylint: disable=unused-import
    ChargeAgg,
    ChargeRow,
    SORT_OPTIONS,
    SessionFilter,
    charge_efficiency,
    charging_dimensions,
    charging_map_locations,
    charging_region_tree,
    charging_session_detail,
    charging_summary,
    list_cars,
    list_charging_sessions,
    location_stats,
    monthly_stats,
    update_charging_cost,
)

from .trips import (  # pylint: disable=unused-import
    EARTH_RADIUS_KM,
    FILL_STEP_KM,
    GAP_ANCHOR_MAX_KM,
    MERGED_TRACK_BUDGET,
    MERGED_TRACK_PER_MIN,
    MergedPlan,
    TRIP_TRACK_PER,
    TripFilter,
    annotate_drivers,
    annotate_tolls,
    closed_drive_ids_between,
    delete_trip_group,
    driver_scope,
    filter_map_tracks_by_driver,
    get_trip,
    list_trip_groups,
    list_trip_regions,
    list_trips,
    merged_track,
    merged_track_plan,
    merged_track_segments,
    rename_trip_group,
    save_fill,
    save_trip_group,
    save_trip_toll,
    set_trip_driver,
    trip_track,
)

from .live import (  # pylint: disable=unused-import
    live_status,
)

from .map import (  # pylint: disable=unused-import
    DETAIL_MAX_IDS,
    DETAIL_PER_FLOOR,
    DETAIL_PER_MAX,
    DETAIL_TOTAL_CAP,
    DETAIL_WORKERS,
    MAP_TRACKS_PER_DRIVE,
    detail_per_for,
    drive_max_id,
    map_summary,
    query_detail,
    query_detail_parallel,
    query_tracks,
)
