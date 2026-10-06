"""行程统计 API: 汇总/按月/常去地点/司机里程/维度聚合 (行程统计页五路
数据, 2026-09-27 新增, 参照充电统计; 时间筛选 3.3.0 下线, 全时段 + 车辆
过滤)。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .... import database
from ....schemas import OkResponse
from ... import repository, speed_hist_cache
from ...schemas import (
    PlaceAliasUpdate,
    PlaceHideUpdate,
    TripDims,
    TripDriverStat,
    TripLocStat,
    TripMonthlyStat,
    TripStatsSummary,
)

router = APIRouter()


@router.get("/stats/summary")
def get_trip_stats_summary(
        car_id: int | None = None,
        db: Session = Depends(database.get_db)) -> TripStatsSummary:
    """行程统计汇总 (顶部统计卡)。"""
    return repository.trip_summary(db, car_id)


@router.get("/stats/monthly")
def get_trip_stats_monthly(
        car_id: int | None = None,
        db: Session = Depends(database.get_db)) -> list[TripMonthlyStat]:
    """按月行程统计 (月度趋势图表用)。"""
    return repository.trip_monthly(db, car_id)


@router.get("/stats/locations")
def get_trip_stats_locations(
        car_id: int | None = None,
        db: Session = Depends(database.get_db),
        own: Session = Depends(database.get_own_db)) -> list[TripLocStat]:
    """常去地点 (起终点并计, 次数降序; 改过名的显示别名, 同别名并组,
    行带组坐标 raws/lat/lng + 组内真实地点 details —— 2026-09-30 用户点名
    点柱名弹改名框, 2026-10-03 管理页点组行展开)。隐藏名单 (左滑删除)
    在读侧过滤, 统计页/管理页同口径。"""
    return repository.trip_locations(db, own, car_id)


@router.post("/stats/place-alias")
def set_trip_place_alias(
        body: PlaceAliasUpdate,
        own: Session = Depends(database.get_own_db)) -> OkResponse:
    """常用地点改名 (places = 统计行的 raws 原样回传, 并组多名一起改;
    alias 空 = 还原原名)。设置页常用地点管理共用这一个口。"""
    repository.set_place_alias(own, body.places, body.alias)
    return OkResponse(ok=True)


@router.post("/stats/place-hide")
def set_trip_place_hide(
        body: PlaceHideUpdate,
        own: Session = Depends(database.get_own_db)) -> OkResponse:
    """常用地点删除/恢复 (2026-10-03 用户点名「左滑删除」): places = raw
    原名或组显示名; hidden=True 落隐藏行 (统计里消失), False 删行恢复。
    行程数据不动 —— 删除只是统计视图的开关。"""
    repository.set_place_hidden(own, body.places, body.hidden)
    return OkResponse(ok=True)


@router.get("/stats/place-hidden")
def get_trip_place_hidden(
        own: Session = Depends(database.get_own_db)) -> list[str]:
    """已删除地点名单 (管理页「已删除」分区, 每名一个恢复钮)。"""
    return sorted(repository.place_hidden_set(own))


@router.get("/stats/drivers")
def get_trip_stats_drivers(
        car_id: int | None = None,
        db: Session = Depends(database.get_db),
        own: Session = Depends(database.get_own_db)) -> list[TripDriverStat]:
    """司机里程分布 (按驾驶员归集的里程/次数, 归集口径与行程卡片同源:
    显式标注 > 默认驾驶员兜底, 都没有的归「未标注」)。"""
    return repository.trip_driver_stats(db, own, car_id)


@router.get("/stats/dimensions")
def get_trip_stats_dimensions(
        car_id: int | None = None,
        db: Session = Depends(database.get_db)) -> TripDims:
    """行程统计维度聚合: 出发时段/距离/时长计数; 车速两档例外 —— 是
    positions 积分的各速度段行驶里程与行车电量 (真速度分布 + 各速度段
    平均电耗, 2026-09-30 用户点名「横坐标是速度, 纵坐标是平均电耗」),
    从 speed_hist_cache 合入 (repository 侧占位 0)。"""
    dims = repository.trip_dimensions(db, car_id)
    dims.by_spd = speed_hist_cache.speed_bins(db, car_id)
    dims.by_spd_kwh = speed_hist_cache.speed_bins_kwh(db, car_id)
    return dims
