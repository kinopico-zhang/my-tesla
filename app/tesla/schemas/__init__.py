"""My Tesla 的接口模型门面 (全部 pydantic, 不裸传 dict)。字段与既有前端逐字段对齐, JSON 形状不变。

按域分家: 充电 / 足迹地图 / 当前驾驶 / 行程 / 设置; 这里聚合对外名面
(调用方统一 from ..schemas import …, 不感知内部分层)。

`from` 是 Python 关键字, 行程条目的字段名用 from_ + alias="from"
(FastAPI 响应默认按别名序列化)。
"""
from .charging_schemas import (
    CarInfo,
    ChargeCurve,
    ChargeDims,
    ChargeMapLocation,
    ChargingSession,
    ChargingSessionDetail,
    ChargingSessionsPage,
    ChargingSummary,
    CityStat,
    CostUpdateRequest,
    CostUpdateResult,
    LocationStat,
    MonthlyStat,
)
from .live_schemas import LiveStatus
from .map_schemas import (
    AmapConfig,
    MapDetailTrack,
    MapSummary,
    MapTrack,
    TracksDetailResponse,
    TracksResponse,
)
from .settings_schemas import (
    AmapSettings,
    DriverIn,
    DriverInfo,
    DriverUpdate,
    SettingsState,
    SettingsUpdate,
    TeslaMateSettings,
)
from .trip_schemas import (
    DriverMark,
    GapFillRequest,
    GapFillResponse,
    MergedTrack,
    RegionNode,
    TollRoad,
    TripGroupIn,
    TripGroupInfo,
    TripGroupRename,
    TripItem,
    TripRegions,
    TripTollIn,
    TripTrack,
    TripsPage,
)

__all__ = [
    "AmapConfig", "AmapSettings", "CarInfo", "ChargeCurve", "ChargeDims",
    "ChargeMapLocation", "ChargingSession", "ChargingSessionDetail",
    "ChargingSessionsPage", "ChargingSummary", "CityStat", "CostUpdateRequest",
    "CostUpdateResult", "DriverIn", "DriverInfo", "DriverMark", "DriverUpdate",
    "GapFillRequest", "GapFillResponse", "LiveStatus", "LocationStat",
    "MapDetailTrack",
    "MapSummary", "MapTrack", "MergedTrack", "MonthlyStat", "RegionNode",
    "SettingsState", "SettingsUpdate", "TeslaMateSettings", "TollRoad",
    "TripGroupIn", "TripGroupInfo", "TripGroupRename", "TripItem",
    "TripRegions", "TripTollIn", "TripTrack", "TripsPage",
    "TracksDetailResponse", "TracksResponse",
]
