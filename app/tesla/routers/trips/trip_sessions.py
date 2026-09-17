"""行程列表与标注 API: 列表/地区树/单条 + 过路费回传/驾驶员标注。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .... import database
from ... import repository
from ...schemas import TripItem, TripTollIn, DriverMark, TripsPage, TripRegions
from ....schemas import OkResponse
from .._common import date_range_or_400


router = APIRouter()

# 只列已完成的行程: TeslaMate 记录中断会留下 end_date 为空的"未关闭"行程
# (无里程/起终点, Grafana 行程面板同样不显示), 与地图页全量轨迹
# (distance IS NOT NULL) 的过滤口径一致。


@router.get("/sessions")
# 行程列表筛选项逐个加 (时间/起终地区/里程/驾驶员), 都是平铺查询参数
def get_trip_sessions(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    offset: int = 0, limit: int = 24,
                      frm: str | None = Query(None, alias="from"),
                      to: str | None = Query(None, alias="to"),
                      from_loc: str | None = None, to_loc: str | None = None,
                      km_min: float | None = None, km_max: float | None = None,
                      driver_id: int | None = None,
                      db: Session = Depends(database.get_db),
                      own: Session = Depends(database.get_own_db)) -> TripsPage:
    """行程列表 (最新在前, 只含已结束行程); from/to 按出发时间过滤 (本地日期),
    from_loc/to_loc 按起终省市区 ("/" 路径, 1~3 段 = 精确到省/市/区县),
    km_min/km_max 按里程 (km) 过滤, driver_id 按驾驶员 (含默认驾驶员兜底口径)。"""
    if offset < 0 or not 1 <= limit <= 100:
        raise HTTPException(400, "分页参数非法")
    for v in (km_min, km_max):
        if v is not None and not 0 <= v <= 1e6:
            raise HTTPException(400, "里程参数非法")
    if km_min is not None and km_max is not None and km_min > km_max:
        raise HTTPException(400, "里程参数非法")
    for loc in (from_loc, to_loc):
        if loc and not 1 <= len([s for s in loc.split("/") if s.strip()]) <= 3:
            raise HTTPException(400, "地区参数非法")
    total, items = repository.list_trips(db, own, offset, limit, repository.TripFilter(
        date_range=date_range_or_400(frm, to),
        from_loc=from_loc or None, to_loc=to_loc or None,
        km_min=km_min, km_max=km_max, driver_id=driver_id))
    return TripsPage(total=total, items=items)


@router.get("/regions")
def get_trip_regions(db: Session = Depends(database.get_db)) -> TripRegions:
    """行程起终点省市区树 (级联下拉数据源)。"""
    return repository.list_trip_regions(db)


@router.get("/sessions/{drive_id}")
def get_trip_session(drive_id: int,
                     db: Session = Depends(database.get_db),
                     own: Session = Depends(database.get_own_db)) -> TripItem:
    """单条行程信息: 分享链接 /tesla/trips?id=X 直开弹层时前端拉取。"""
    item = repository.get_trip(db, own, drive_id)
    if item is None:
        raise HTTPException(404, "行程不存在或未完成")
    return item


@router.post("/{drive_id}/toll")
def post_trip_toll(drive_id: int, body: TripTollIn,
                   db: Session = Depends(database.get_db),
                   own: Session = Depends(database.get_own_db)) -> OkResponse:
    """高速费估价回传: 前端用高德驾车规划 (沿轨迹途经点) 估出 tolls 后
    存进自有库。tolls=0 也是有效结果 (没走收费路); 重算 = 覆盖更新。"""
    if repository.get_trip(db, own, drive_id) is None:
        raise HTTPException(404, "行程不存在或未完成")
    repository.save_trip_toll(own, drive_id, body)
    return OkResponse(ok=True)


@router.post("/{drive_id}/driver")
def mark_trip_driver(drive_id: int, body: DriverMark,
                     db: Session = Depends(database.get_db),
                     own: Session = Depends(database.get_own_db)) -> TripItem:
    """标/清行程驾驶员 (driver_id 空 = 清除, 展示回默认驾驶员兜底)。
    返回更新后的行程条目 (前端直接刷新卡片与弹层)。"""
    if repository.get_trip(db, own, drive_id) is None:
        raise HTTPException(404, "行程不存在或未完成")
    try:
        repository.set_trip_driver(own, drive_id, body.driver_id)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    updated = repository.get_trip(db, own, drive_id)
    assert updated is not None   # 上面刚验证过存在
    return updated
