"""行程轨迹 API: 单条全精度轨迹 + 合并轨迹 (整包/NDJSON 流式) + 断档补路回传。"""
import json
import math
import re
import zlib
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .... import database
from ... import repository
from ...schemas import (
    MergedTrack,
    GapFillRequest,
    GapFillResponse,
    TripTrack,
)


router = APIRouter()


# 轨迹类接口的浏览器缓存 (2026-09-25 用户点名「每次打开轨迹都要加载轨迹加载
# 地图, 很慢, 要充分利用浏览器的缓存」): 已结束行程的 positions 不可变, 响应
# 只会因补路 (fills_version) 或载荷算法 (盐值) 而变 —— ETag 命中 304, 不重下。
_ETAG_SALT = "t1"   # 载荷算法变了要换 (换 = 客户端全量重拉一次)


def _track_etag(fills: int, kind: str, raw_ids: str) -> str:
    """fills = 补路版本; raw_ids 用 URL 原串 (同 URL 同串, 校验前就能算)。"""
    key = f"{zlib.crc32(raw_ids.encode()) & 0xffffffff:08x}"
    return f'"{_ETAG_SALT}-{kind}-{key}-{fills}"'


def _cacheable(request: Request, response: Response, etag: str) -> Response | None:
    """命中 If-None-Match → 304 (不重算轨迹); 两路都挂 ETag + no-cache
    (校验只是一次 SELECT max(id); 自带 Cache-Control 豁免 API 默认 no-store)。"""
    nm = (Response(status_code=304)
          if request.headers.get("if-none-match") == etag else None)
    target = nm if nm is not None else response
    target.headers["ETag"] = etag
    target.headers["Cache-Control"] = "private, no-cache"
    return nm


@router.get("/merged", response_model=MergedTrack)
def get_merged_track(ids: str, request: Request, response: Response,
                     db: Session = Depends(database.get_db),
                     own: Session = Depends(database.get_own_db)) -> MergedTrack | Response:
    """多选连续行程 → 一条连续轨迹 (整包 JSON)。
    ts 为"累计行驶秒": 行程间的停驶时间剔除, 否则跨天合并后播放进度和
    实时时长全被停车时间淹没; pts/ts 结构与单条轨迹接口一致。
    边下边播走 /merged_stream, 这里是缓存命中等一次性消费的整包版本。"""
    etag = _track_etag(repository.fills_version(own), "m", ids)
    if (nm := _cacheable(request, response, etag)) is not None:
        return nm
    id_list = _merged_id_list(ids, db)
    if len(id_list) < 2:                    # 上限 2026-09-25 用户点名撤掉
        raise HTTPException(400, "ids 需至少 2 个行程")
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


@router.get("/merged_summary", response_model=MergedTrack)
def get_merged_summary(ids: str, request: Request, response: Response,
                       db: Session = Depends(database.get_db),
                       own: Session = Depends(database.get_own_db)) -> MergedTrack | Response:
    """合并轻量汇总 (深链用): 只查 drives/地址/换算系数, 不碰 positions。

    弹层头部一开就有数 —— 流式汇总头要等地图引擎装载后才随流发出,
    深链重开 (刷新/分享/PWA 重开) 手里没卡片数据, 2026-09-24 用户再报
    「加载地图时平均电耗空着, 过一会儿才出来」; 分组/多选的 info 直填
    (2026-09-23) 盖不住这条路。字段与流式首行同构 (MergedTrack)。"""
    # 汇总头不掺补点, 但与整包/流式共用 fills 分量 (少一套口径, 补路落库一起重校验)
    etag = _track_etag(repository.fills_version(own), "ms", ids)
    if (nm := _cacheable(request, response, etag)) is not None:
        return nm
    id_list = _merged_id_list(ids, db)
    if len(id_list) < 2:                    # 上限 2026-09-25 用户点名撤掉
        raise HTTPException(400, "ids 需至少 2 个行程")
    try:
        return repository.merged_track_plan(db, id_list).header
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/merged_stream", response_model=None)
def get_merged_track_stream(ids: str, request: Request,
                            db: Session = Depends(database.get_db),
                            own: Session = Depends(database.get_own_db)) -> Response:
    """合并轨迹 NDJSON 流: 首行汇总头, 之后每行一段 (pts/ts)。

    38 段的轨迹整包要好几秒, 前端弹层先开、第一段到了就开播, 后续
    段到了追加 —— 不让用户对着死屏等全部数据下载完。"""
    etag = _track_etag(repository.fills_version(own), "s", ids)
    # 流式自己 new Response 直接返回, 不吃注入 response 的头合并 → 头挂
    # 两路响应自己身上 (304 在 plan 之前, 重开连头部查询都省)
    cc: dict[str, str] = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=cc)
    id_list = _merged_id_list(ids, db)
    if len(id_list) < 2:                    # 上限 2026-09-25 用户点名撤掉
        raise HTTPException(400, "ids 需至少 2 个行程")
    try:
        plan = repository.merged_track_plan(db, id_list)   # 校验 + 头部 (404 在流开始前)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc

    def gen() -> Iterator[str]:
        yield json.dumps({"summary": plan.header.model_dump(by_alias=True),
                          "segs": len(plan.budgets)},   # 有轨迹数据的段数 (前端判下载中断用)
                         ensure_ascii=False, separators=(",", ":")) + "\n"
        for seg_pts, seg_ts, seg_gaps, seg_t0 in repository.merged_track_segments(db, own, plan):
            yield json.dumps({"pts": seg_pts, "ts": seg_ts, "gaps": seg_gaps,
                              "t0": seg_t0},     # 段首时刻: 标题随段切换 (ts 是行驶秒推不出日期)
                             separators=(",", ":")) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson",
                             headers=cc)


@router.post("/gap_fill")
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


@router.get("/{drive_id}/track", response_model=TripTrack)
def get_trip_track(drive_id: int, request: Request, response: Response,
                   db: Session = Depends(database.get_db),
                   own: Session = Depends(database.get_own_db)) -> TripTrack | Response:
    """单条行程全精度轨迹: pts 为 [lng, lat, speed_km_h, power_kW]
    (power 原生就是千瓦, 正=放电 负=动能回收, 可能为 null); ts 为相对起点
    的秒偏移 (与 pts 下标对齐, 播放动画里用来算"已行驶时长"和平均功耗)。"""
    # ETag 只对已结束行程安全: 开放行程 positions 一直在长而 ETag 分量不
    # 变, 20s 重拉全被 304 冻在打开时刻 (2026-09-27 驾驶态轨迹尾巴拉直
    # 实报, 全过程见 repository.drive_open 注) —— 开放行程不带 ETag
    # (API 默认 no-store 每拉全量), 关闭后轨迹不可变, ETag 照常生效。
    if not repository.drive_open(db, drive_id):
        etag = _track_etag(repository.fills_version(own), "d", str(drive_id))
        if (nm := _cacheable(request, response, etag)) is not None:
            return nm
    try:
        return repository.trip_track(db, own, drive_id)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
