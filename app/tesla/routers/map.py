"""足迹地图 API: 汇总/清单/轨迹流/诊断 (全量轨迹缓存与增量由 tracks_cache 提供)。"""
import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ... import database
from .. import repository, tracks_cache, settings_store
from ..schemas import AmapConfig, MapManifest, MapSummary
from ...schemas import OkResponse
from ._common import date_range_or_400


mapapi = APIRouter(prefix="/tesla/map/api")

STREAM_MAX_IDS = 200   # /tracks/stream 单次最多轨迹条数 (客户端 ~50 一批)


# ---------------------------------------------------------------- 足迹地图 API

@mapapi.get("/config")
def map_config(own: Session = Depends(database.get_own_db)) -> AmapConfig:
    """地图前端配置: 服务商 + 高德 Key 与样式; 设置页可改 (存自有库),
    未设回落 env; 每次现读, 改完刷新页面即生效。"""
    key, code = settings_store.amap_values(own)
    return AmapConfig(provider=settings_store.map_provider_value(own),
                      amap_key=key, security_code=code,
                      style=settings_store.amap_style_value(own))


@mapapi.get("/summary")
def get_map_summary(
        frm: str | None = Query(None, alias="from"), to: str | None = None,
        driver_id: int | None = Query(None), car_id: int | None = Query(None),
        db: Session = Depends(database.get_db),
        own: Session = Depends(database.get_own_db)) -> MapSummary:
    """地图页汇总: 行程数 / 总里程 / 总时长 / 起止日期, 可按驾驶员/车辆过滤。"""
    return repository.map_summary(db, own, date_range_or_400(frm, to),
                                  driver_id, car_id)


@mapapi.get("/tracks/manifest")
def get_tracks_manifest(
        own: Session = Depends(database.get_own_db)) -> MapManifest:
    """全量轨迹清单 (每次打开足迹地图现拉): 每条 {id, 点数 n, 驾驶员 d,
    车 c, 日期 t}。客户端拿它对账浏览器本地库 —— 缺的/n 不符的重下,
    多余的删掉; 时间/车辆/驾驶员筛选也按清单在本地做, 不再按筛选请求。"""
    return tracks_cache.build_manifest(
        tracks_cache.load_tracks(database.session_factory()), own)


@mapapi.get("/tracks/stream")
def get_tracks_stream(ids: str) -> StreamingResponse:
    """按 ids 批量回全精度轨迹: NDJSON 一行一条, 客户端边下载边渲染。
    上限 STREAM_MAX_IDS 条 (防误把全量塞进一个请求)。"""
    try:
        wanted = {int(x) for x in ids.split(",") if x.strip()}
    except ValueError:
        raise HTTPException(400, "ids 格式错误") from None
    if len(wanted) > STREAM_MAX_IDS:
        raise HTTPException(400, f"一次最多 {STREAM_MAX_IDS} 条轨迹")
    tracks = tracks_cache.load_tracks(database.session_factory())

    def lines() -> Iterator[str]:
        for track in tracks:   # 缓存序 (日期升序) 逐条吐, 与清单序一致
            if track.id in wanted:
                yield json.dumps(track.model_dump(),
                                 separators=(",", ":")) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson")


@mapapi.post("/diag")
async def map_diag(request: Request) -> OkResponse:
    """浏览器端诊断上报 (排查地图加载问题), 只写日志不落库。"""
    try:
        body = await request.json()
    except ValueError:
        body = {}
    print(f"MAPDIAG {json.dumps(body, ensure_ascii=False)[:800]}", flush=True)
    return OkResponse(ok=True)
