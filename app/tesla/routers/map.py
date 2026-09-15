"""足迹地图 API: 汇总/轨迹/详情/诊断 (轨迹缓存与增量由 tracks_cache 提供)。"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ... import database
from .. import repository, tracks_cache, settings_store
from ..schemas import AmapConfig, MapSummary, TracksResponse, TracksDetailResponse
from ...schemas import OkResponse
from ._common import date_range_or_400


mapapi = APIRouter(prefix="/tesla/map/api")


# ---------------------------------------------------------------- 足迹地图 API

@mapapi.get("/config")
def map_config(own: Session = Depends(database.get_own_db)) -> AmapConfig:
    """高德 Key 与地图样式: 设置页可改 (存自有库), 未设回落 env;
    每次现读, 改完刷新页面即生效。"""
    key, code = settings_store.amap_values(own)
    return AmapConfig(amap_key=key, security_code=code,
                      style=settings_store.amap_style_value(own))


@mapapi.get("/summary")
def get_map_summary(
        frm: str | None = Query(None, alias="from"), to: str | None = None,
        driver_id: int | None = Query(None),
        db: Session = Depends(database.get_db),
        own: Session = Depends(database.get_own_db)) -> MapSummary:
    """地图页汇总: 行程数 / 总里程 / 总时长 / 起止日期, 可按驾驶员过滤。"""
    return repository.map_summary(db, own, date_range_or_400(frm, to), driver_id)


@mapapi.get("/tracks")
def get_tracks(frm: str | None = Query(None, alias="from"),
               to: str | None = None, driver_id: int | None = Query(None),
               own: Session = Depends(database.get_own_db)) -> TracksResponse:
    """全量粗轨迹 (每条 ~40 点, 两级缓存 + 增量), 可按日期/驾驶员过滤。"""
    date_range_or_400(frm, to)   # 先校验再过滤, 空列表也要拦住坏参数
    tracks = tracks_cache.load_tracks(database.session_factory())
    tracks = tracks_cache.filter_by_date(tracks, frm, to)
    if driver_id is not None:     # 驾驶员标注在自有库 → 缓存轨迹后置过滤
        tracks = repository.filter_map_tracks_by_driver(tracks, own, driver_id)
    return TracksResponse(count=len(tracks), tracks=tracks)


@mapapi.get("/tracks/detail")
def get_tracks_detail(
        ids: str, zoom: int = 15, w: float = -180.0, s: float = -90.0,  # pylint: disable=unused-argument
        e: float = 180.0, n: float = 90.0) -> TracksDetailResponse:
    """视野内高精度轨迹: bbox 过滤 + 按 ids 数量定下采样预算。"""
    # zoom 保留在签名里 (前端语义参数, 缩放档位语义), 服务端按 ids 数量算预算
    try:
        id_list = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(400, "ids 格式错误") from None
    id_list = id_list[:repository.DETAIL_MAX_IDS]
    if not id_list:
        return TracksDetailResponse(count=0, tracks=[])
    bbox_valid = -180 <= w < e <= 180 and -90 <= s < n <= 90
    if not bbox_valid:
        raise HTTPException(400, "bbox 参数非法")
    bbox = repository.BBox(west=w, south=s, east=e, north=n)
    per = repository.detail_per_for(len(id_list))
    tracks = repository.query_detail_parallel(
        database.session_factory(), id_list, per, bbox)
    return TracksDetailResponse(count=len(tracks), tracks=tracks)


@mapapi.post("/diag")
async def map_diag(request: Request) -> OkResponse:
    """浏览器端诊断上报 (排查地图加载问题), 只写日志不落库。"""
    try:
        body = await request.json()
    except ValueError:
        body = {}
    print(f"MAPDIAG {json.dumps(body, ensure_ascii=False)[:800]}", flush=True)
    return OkResponse(ok=True)
