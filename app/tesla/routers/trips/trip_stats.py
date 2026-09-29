"""行程统计 API: 汇总/按月/常去地点/司机里程/维度聚合 (行程统计页五路
数据, 2026-09-27 新增, 参照充电统计; 时间筛选 3.3.0 下线, 全时段 + 车辆
过滤)。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .... import database
from ... import repository, speed_hist_cache
from ...schemas import (
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
        db: Session = Depends(database.get_db)) -> list[TripLocStat]:
    """常去地点 (起终点并计, 次数降序)。"""
    return repository.trip_locations(db, car_id)


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
    """行程统计维度聚合: 出发时段/距离/时长/电耗计数; 车速档例外 —— 是
    positions 积分的各速度段行驶里程 (真速度分布, 2026-09-27 用户点名),
    从 speed_hist_cache 合入 (repository 侧占位 0)。"""
    dims = repository.trip_dimensions(db, car_id)
    dims.by_spd = speed_hist_cache.speed_bins(db, car_id)
    return dims
