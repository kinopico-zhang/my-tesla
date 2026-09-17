"""行程轨迹 API: 单条全精度轨迹 + 合并轨迹 (整包/NDJSON 流式) + 断档补路回传。"""
import json
import math
import re
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
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


@router.get("/merged")
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


@router.get("/merged_stream")
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


@router.get("/{drive_id}/track")
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
