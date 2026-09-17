"""足迹地图域接口模型: 地图配置/汇总/粗轨迹与视野内高精度轨迹。"""
from pydantic import BaseModel


class AmapConfig(BaseModel):
    """高德地图前端配置 (env / 设置页注入)。"""

    amap_key: str | None
    security_code: str | None
    style: str


class MapSummary(BaseModel):
    """地图页汇总。"""

    drives: int
    distance_km: float
    duration_min: int
    first_date: str | None
    last_date: str | None


class MapTrack(BaseModel):
    """全量粗轨迹 (每条下采样到 ~40 点)。"""

    id: int
    date: str
    km: float
    min: int | None
    pts: list[list[float]]


class TracksResponse(BaseModel):
    """全量粗轨迹响应。"""

    count: int
    tracks: list[MapTrack]


class MapDetailTrack(BaseModel):
    """视野内高精度轨迹。"""

    id: int
    pts: list[list[float]]


class TracksDetailResponse(BaseModel):
    """视野内高精度轨迹响应。"""

    count: int
    tracks: list[MapDetailTrack]
