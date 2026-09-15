"""行程 API: 列表/详情/合并轨迹(整包+流式)/分组/过路费/驾驶员归集。"""
import json
import math
import re
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ... import database
from .. import repository
from ..schemas import (
    TripItem,
    TripTollIn,
    DriverMark,
    TripsPage,
    TripRegions,
    TripTrack,
    MergedTrack,
    TripGroupIn,
    TripGroupRename,
    TripGroupInfo,
    GapFillRequest,
    GapFillResponse,
)
from ...schemas import OkResponse
from ._common import date_range_or_400


trips = APIRouter(prefix="/tesla/trips/api")


# ---------------------------------------------------------------- 行程 API
# 只列已完成的行程: TeslaMate 记录中断会留下 end_date 为空的"未关闭"行程
# (无里程/起终点, Grafana 行程面板同样不显示), 与地图页全量轨迹
# (distance IS NOT NULL) 的过滤口径一致。

@trips.get("/sessions")
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


@trips.get("/regions")
def get_trip_regions(db: Session = Depends(database.get_db)) -> TripRegions:
    """行程起终点省市区树 (级联下拉数据源)。"""
    return repository.list_trip_regions(db)


@trips.get("/sessions/{drive_id}")
def get_trip_session(drive_id: int,
                     db: Session = Depends(database.get_db),
                     own: Session = Depends(database.get_own_db)) -> TripItem:
    """单条行程信息: 分享链接 /tesla/trips?id=X 直开弹层时前端拉取。"""
    item = repository.get_trip(db, own, drive_id)
    if item is None:
        raise HTTPException(404, "行程不存在或未完成")
    return item


@trips.get("/merged")
def get_merged_track(ids: str,
                     db: Session = Depends(database.get_db),
                     own: Session = Depends(database.get_own_db)) -> MergedTrack:
    """多选连续行程 → 一条连续轨迹 (整包 JSON)。
    ts 为"累计行驶秒": 行程间的停驶时间剔除, 否则跨天合并后播放进度和
    实时时长全被停车时间淹没; pts/ts 结构与单条轨迹接口一致。
    边下边播走 /merged_stream, 这里是缓存命中等一次性消费的整包版本。"""
    id_list = _merged_id_list(ids, db)
    if not 2 <= len(id_list) <= 100:
        raise HTTPException(400, "ids 需为 2~100 个行程")
    try:
        return repository.merged_track(db, own, id_list)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc


def _merged_id_list(raw: str, db: Session) -> list[int]:
    """ids 参数两种写法: 逗号 id 列表, 或 "首-尾" 区间。

    连续行程本就要求头尾相接, 只记头尾 id 链接短得多; 区间在服务端
    展开成全部已结束行程 (未结束的自动跳过, 与行程列表同口径)。"""
    if "-" in raw and "," not in raw:
        m = re.fullmatch(r"(\d+)-(\d+)", raw)
        if m and int(m[1]) <= int(m[2]):
            return repository.closed_drive_ids_between(db, int(m[1]), int(m[2]))
        raise HTTPException(400, "ids 参数非法")
    try:
        return list(dict.fromkeys(int(x) for x in raw.split(",")))
    except ValueError:
        raise HTTPException(400, "ids 参数非法") from None


@trips.get("/merged_stream")
def get_merged_track_stream(ids: str,
                            db: Session = Depends(database.get_db),
                            own: Session = Depends(database.get_own_db)) -> StreamingResponse:
    """合并轨迹 NDJSON 流: 首行汇总头, 之后每行一段 (pts/ts)。

    38 段的轨迹整包要好几秒, 前端弹层先开、第一段到了就开播, 后续
    段到了追加 —— 不让用户对着死屏等全部数据下载完。"""
    id_list = _merged_id_list(ids, db)
    if not 2 <= len(id_list) <= 100:
        raise HTTPException(400, "ids 需为 2~100 个行程")
    try:
        plan = repository.merged_track_plan(db, id_list)   # 校验 + 头部 (404 在流开始前)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc

    def gen() -> Iterator[str]:
        yield json.dumps({"summary": plan.header.model_dump(by_alias=True),
                          "segs": len(plan.budgets)},   # 有轨迹数据的段数 (前端判下载中断用)
                         ensure_ascii=False, separators=(",", ":")) + "\n"
        for seg_pts, seg_ts in repository.merged_track_segments(db, own, plan):
            yield json.dumps({"pts": seg_pts, "ts": seg_ts},
                             separators=(",", ":")) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@trips.post("/gap_fill")
def post_gap_fill(body: GapFillRequest,
                  db: Session = Depends(database.get_db),
                  own: Session = Depends(database.get_own_db)) -> GapFillResponse:
    """断档补路回传: 前端高德规划成功后把 WGS 折线存进自有库, 之后
    单条/合并轨迹接口直接在服务端拼好, 不再每次重新规划。"""
    if (len(body.a) != 2 or len(body.b) != 2
            or not all(math.isfinite(v) for v in [*body.a, *body.b])
            or not 2 <= len(body.path) <= 500
            or any(len(p) != 2 or not all(math.isfinite(v) for v in p)
                   for p in body.path)):
        raise HTTPException(400, "补路参数非法")
    try:
        km = repository.save_fill(db, own, body)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return GapFillResponse(ok=True, km=km)


@trips.get("/groups")
def list_groups(db: Session = Depends(database.get_db),
                own: Session = Depends(database.get_own_db)) -> list[TripGroupInfo]:
    """全部轨迹分组 (逻辑分组, 存自有库, 行程原数据不动)。"""
    return repository.list_trip_groups(db, own)


@trips.post("/groups")
def save_group(body: TripGroupIn,
               db: Session = Depends(database.get_db),
               own: Session = Depends(database.get_own_db)) -> TripGroupInfo:
    """多选行程存成命名分组; 段数/里程/日期跨度展示时现算, 不落库。"""
    if len(set(body.ids)) < 2:
        raise HTTPException(400, "ids 去重后需为 2~100 个行程")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "名字不能为空")
    try:
        return repository.save_trip_group(db, own, name, body.ids)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@trips.patch("/groups/{group_id}")
def rename_group(group_id: int, body: TripGroupRename,
                 db: Session = Depends(database.get_db),
                 own: Session = Depends(database.get_own_db)) -> TripGroupInfo:
    """分组改名 (成员不动)。"""
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "名字不能为空")
    try:
        return repository.rename_trip_group(db, own, group_id, name)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@trips.delete("/groups/{group_id}")
def delete_group(group_id: int,
                 own: Session = Depends(database.get_own_db)) -> OkResponse:
    """删分组 (只删自有库记录)。"""
    try:
        repository.delete_trip_group(own, group_id)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    return OkResponse(ok=True)


@trips.post("/{drive_id}/toll")
def post_trip_toll(drive_id: int, body: TripTollIn,
                   db: Session = Depends(database.get_db),
                   own: Session = Depends(database.get_own_db)) -> OkResponse:
    """高速费估价回传: 前端用高德驾车规划 (沿轨迹途经点) 估出 tolls 后
    存进自有库。tolls=0 也是有效结果 (没走收费路); 重算 = 覆盖更新。"""
    if repository.get_trip(db, own, drive_id) is None:
        raise HTTPException(404, "行程不存在或未完成")
    repository.save_trip_toll(own, drive_id, body)
    return OkResponse(ok=True)


@trips.post("/{drive_id}/driver")
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


@trips.get("/{drive_id}/track")
def get_trip_track(drive_id: int,
                   db: Session = Depends(database.get_db),
                   own: Session = Depends(database.get_own_db)) -> TripTrack:
    """单条行程全精度轨迹: pts 为 [lng, lat, speed_km_h, power_W]
    (power 正=放电 负=动能回收, 可能为 null); ts 为相对起点的秒偏移
    (与 pts 下标对齐, 播放动画里用来算"已行驶时长"和平均功耗)。"""
    try:
        return repository.trip_track(db, own, drive_id)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
