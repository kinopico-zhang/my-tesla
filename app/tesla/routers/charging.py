"""充电 API: 列表/详情/费用回写/汇总/维度/地图点位/地区树 (统计与充电地图同源)。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ... import database
from .. import repository
from ._common import date_range_or_400
from ..schemas import (
    CarInfo,
    ChargingSessionDetail,
    ChargingSummary,
    ChargingSessionsPage,
    MonthlyStat,
    LocationStat,
    CostUpdateResult,
    ChargeDims,
    ChargeMapLocation,
    RegionNode,
    CostUpdateRequest,
)


charging = APIRouter(prefix="/tesla/charging/api")


# ---------------------------------------------------------------- 充电 API

@charging.get("/car")
def get_car(db: Session = Depends(database.get_db)) -> list[CarInfo]:
    """车辆信息。"""
    return repository.list_cars(db)


@charging.get("/summary")
def get_charging_summary(
        frm: str | None = Query(None, alias="from"), to: str | None = None,
        db: Session = Depends(database.get_db)) -> ChargingSummary:
    """充电汇总 (次数/电量/费用/SOC 与续航增益), 可按日期过滤。"""
    return repository.charging_summary(db, date_range_or_400(frm, to))


@charging.get("/dimensions")
def get_charging_dimensions(
        frm: str | None = Query(None, alias="from"), to: str | None = None,
        db: Session = Depends(database.get_db)) -> ChargeDims:
    """充电统计维度聚合: 快慢/开始时段/起充 SOC/峰值功率/城市 (统计页图表)。"""
    return repository.charging_dimensions(db, date_range_or_400(frm, to))


@charging.get("/map-locations")
def get_charging_map_locations(
        frm: str | None = Query(None, alias="from"), to: str | None = None,
        db: Session = Depends(database.get_db)) -> list[ChargeMapLocation]:
    """充电地图充电点聚合 (按地址, 次数降序; 无坐标的地址不上图)。"""
    return repository.charging_map_locations(db, date_range_or_400(frm, to))


@charging.get("/regions")
def get_charging_regions(
        db: Session = Depends(database.get_db)) -> list[RegionNode]:
    """充电地点省市区树 (级联下拉数据源, 按充电次数降序)。"""
    return repository.charging_region_tree(db)


@charging.get("/sessions")
def get_sessions(
        offset: int = 0, limit: int = 50, sort: str = "date_desc",
        type_: str = Query("all", alias="type"), q: str | None = None,
        region: str | None = None, cost: str | None = None,
        frm: str | None = Query(None, alias="from"), to: str | None = None,
        db: Session = Depends(database.get_db)) -> ChargingSessionsPage:
    """充电列表: 过滤 (日期/快慢/地点省市区/费用记录/地址搜索) → 排序 → 分页。

    region 是 "/" 连接的省市区路径 (1~3 段 = 精确到省/市/区县), 与行程页同款。
    """
    if sort not in repository.SORT_OPTIONS:
        raise HTTPException(400, f"不支持的排序: {sort}")
    if offset < 0 or limit < 0:
        raise HTTPException(400, "分页参数非法")
    if cost not in (None, "all", "recorded", "missing"):
        raise HTTPException(400, "不支持的费用筛选")
    if region and not 1 <= len([t for t in region.split("/") if t.strip()]) <= 3:
        raise HTTPException(400, "地区参数非法")
    flt = repository.SessionFilter(
        date_range=date_range_or_400(frm, to), charge_type=type_,
        region=region or None, query=q, sort=sort, offset=offset, limit=limit,
        cost=None if cost == "all" else cost)
    total, items = repository.list_charging_sessions(db, flt)
    return ChargingSessionsPage(total=total, items=items)


@charging.get("/sessions/{session_id}")
def get_session(session_id: int,
                db: Session = Depends(database.get_db)) -> ChargingSessionDetail:
    """充电详情: 卡片字段 + 采样曲线。"""
    detail = repository.charging_session_detail(db, session_id)
    if detail is None:
        raise HTTPException(404, "充电记录不存在")
    return detail


@charging.patch("/sessions/{session_id}/cost")
def update_cost(session_id: int, body: CostUpdateRequest,
                db: Session = Depends(database.get_db)) -> CostUpdateResult:
    """更新 / 添加 / 清除一条充电记录的费用 (写回 TeslaMate 库)。"""
    cost_in_range = body.cost is None or 0 <= body.cost <= 100000
    if not cost_in_range:
        raise HTTPException(400, "金额需在 0 ~ 100000 之间")
    result = repository.update_charging_cost(db, session_id, body.cost)
    if result is None:
        raise HTTPException(404, "充电记录不存在")
    return result


@charging.get("/monthly")
def get_monthly(
        frm: str | None = Query(None, alias="from"), to: str | None = None,
        db: Session = Depends(database.get_db)) -> list[MonthlyStat]:
    """按月充电统计 (图表用)。"""
    return repository.monthly_stats(db, date_range_or_400(frm, to))


@charging.get("/locations")
def get_locations(
        frm: str | None = Query(None, alias="from"), to: str | None = None,
        db: Session = Depends(database.get_db)) -> list[LocationStat]:
    """按充电地点分组统计 (图表用)。"""
    return repository.location_stats(db, date_range_or_400(frm, to))
