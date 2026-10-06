"""高德 REST 的线上形状 (pydantic): 纠偏 v4 / 规划 v3 / 逆地理 v3 逐家建档。

厂商接口不是自家可控的 (人家改字段就改了), 不能拿裸 dict 探 ——
roads_amap 拿这里的 TypeAdapter 把应答文本验成模型才算数, 形状不对 /
坏 JSON 由调用方按 AmapError 归类。联网与错误类型在 roads_amap;
GraspPoint 是纠偏请求的点 (其余都是应答)。

高德 v3 的字符串字段偶发以数字进站 (status: 1), 空字段以 [] 进站
(addressComponent) —— _to_text 一律收编成 str; 距离字段缺/坏值收成
None (不冒充 0 米, _nearest 才挑得准)。"""
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, TypeAdapter


def _to_text(value: object) -> str:
    """高德的字符串字段 → 文本: str 原样, 数字转字, 其余 ([]/None) 为空。"""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def _num_or_none(value: object) -> float | None:
    """高德的距离字段 → 数值: 缺 / 坏值 / [] 一律 None。"""
    if isinstance(value, (int, float, str)):
        try:
            return float(value)
        except ValueError:
            return None
    return None


class GraspPoint(BaseModel):
    """纠偏请求的一个点: x/y = GCJ-02 坐标, sp = km/h, ag = 方位角,
    tm = 秒增量 (首点为绝对 Unix 秒)。"""

    x: float
    y: float
    sp: float
    ag: float
    tm: int


class _GraspOutPoint(BaseModel):
    """纠偏应答回的一个点 (GCJ-02)。"""

    x: float
    y: float


class _GraspData(BaseModel):
    """纠偏应答的 data 段。"""

    points: list[_GraspOutPoint] = Field(default_factory=list)


class GraspResponse(BaseModel):
    """纠偏应答 (errcode 0 = 成功, 30001 = 抓不到路, 配额码见调用方)。"""

    errcode: int = -1
    errmsg: str = ""
    data: _GraspData = Field(default_factory=_GraspData)


class _RouteStep(BaseModel):
    """规划应答的一步 (polyline = "lng,lat;lng,lat;..." GCJ-02)。"""

    polyline: str = ""


class _RoutePath(BaseModel):
    """规划应答的一条路径。"""

    steps: list[_RouteStep] = Field(default_factory=list)


class _RouteBody(BaseModel):
    """规划应答的 route 段。"""

    paths: list[_RoutePath] = Field(default_factory=list)


class RouteResponse(BaseModel):
    """规划应答 (status "1" = 成功, 字段偶发以数字进站, _to_text 收编)。"""

    status: Annotated[str, BeforeValidator(_to_text)] = ""
    infocode: Annotated[str, BeforeValidator(_to_text)] = ""
    info: Annotated[str, BeforeValidator(_to_text)] = ""
    route: _RouteBody = Field(default_factory=_RouteBody)


class AmapSpot(BaseModel):
    """regeo 应答 pois/roads 里的一条: 名字 + 距离 (米; 缺/坏 = None)。"""

    name: Annotated[str, BeforeValidator(_to_text)] = ""
    distance: Annotated[float | None, BeforeValidator(_num_or_none)] = None


class AddressComponent(BaseModel):
    """regeo 应答的区划段 (空字段高德发 [] 不是 "", _to_text 收编)。"""

    district: Annotated[str, BeforeValidator(_to_text)] = ""
    township: Annotated[str, BeforeValidator(_to_text)] = ""


class Regeocode(BaseModel):
    """regeo 应答的 regeocode 段 (地点命名的原料)。"""

    pois: list[AmapSpot] = Field(default_factory=list)
    roads: list[AmapSpot] = Field(default_factory=list)
    address: AddressComponent = Field(default_factory=AddressComponent,
                                      alias="addressComponent")


class RegeoResponse(BaseModel):
    """regeo 应答 (status "1" = 成功; regeocode 缺 = None)。"""

    status: Annotated[str, BeforeValidator(_to_text)] = ""
    infocode: Annotated[str, BeforeValidator(_to_text)] = ""
    info: Annotated[str, BeforeValidator(_to_text)] = ""
    regeocode: Regeocode | None = None


_GRASP_RESPONSE = TypeAdapter(GraspResponse)
_ROUTE_RESPONSE = TypeAdapter(RouteResponse)
_REGEO_RESPONSE = TypeAdapter(RegeoResponse)
