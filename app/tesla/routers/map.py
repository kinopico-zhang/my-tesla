"""足迹地图 API: 汇总/清单/走过之路流/诊断 (全量轨迹缓存与清单由
tracks_cache 提供; 2026-09-29 起前端只画走过的路, 原始轨迹流端点退役)。"""
import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ... import database
from .. import repository, roads_worker, settings_store, tracks_cache
from ..schemas import (AmapConfig, MapManifest, MapSummary, RoadStreamRow)
from ...schemas import OkResponse
from ._common import date_range_or_400


mapapi = APIRouter(prefix="/tesla/map/api")

STREAM_MAX_IDS = 200   # stream 单次最多条数 (客户端 ~50 一批)


# ---------------------------------------------------------------- 足迹地图 API

@mapapi.get("/config")
def map_config(own: Session = Depends(database.get_own_db)) -> AmapConfig:
    """地图前端配置: 高德 Key 与样式; 设置页可改 (存自有库),
    未设回落 env; 每次现读, 改完刷新页面即生效。"""
    key, code = settings_store.amap_values(own)
    return AmapConfig(amap_key=key, security_code=code,
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


@mapapi.get("/roads/stream")
def get_roads_stream(
        ids: str,
        own: Session = Depends(database.get_own_db)) -> StreamingResponse:
    """按 ids 批回「走过之路」: NDJSON 一行一条, 只回有几何的行 (ok=证实
    / guess=推断; failed/skip 没有路可画)。故意不挂 ETag: drive_roads 是
    upsert 语义 (worker 随时补新行), ETag 的内容不变前提不成立 ——
    IndexedDB 对账 (清单 rn) 本身就是缓存层。"""
    try:
        wanted = {int(x) for x in ids.split(",") if x.strip()}
    except ValueError:
        raise HTTPException(400, "ids 格式错误") from None
    if len(wanted) > STREAM_MAX_IDS:
        raise HTTPException(400, f"一次最多 {STREAM_MAX_IDS} 条")
    rows = repository.roads_rows(own, sorted(wanted))

    def lines() -> Iterator[str]:
        for row in rows:
            yield json.dumps(RoadStreamRow(
                id=row.drive_id, n=row.n, km=row.km,
                pts=json.loads(row.pts or "[]"),
                g=json.loads(row.gaps or "[]")).model_dump(),
                separators=(",", ":")) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson")


@mapapi.get("/roads/tick")
def roads_tick() -> OkResponse:
    """踢一脚拟合 worker (设置页存 Web 服务 key 后调): worker 没起也不算错。"""
    roads_worker.nudge()
    return OkResponse(ok=True)


@mapapi.post("/diag")
async def map_diag(request: Request) -> OkResponse:
    """浏览器端诊断上报 (排查地图加载问题), 只写日志不落库。"""
    try:
        body = await request.json()
    except ValueError:
        body = {}
    print(f"MAPDIAG {json.dumps(body, ensure_ascii=False)[:800]}", flush=True)
    return OkResponse(ok=True)
