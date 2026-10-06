"""速度档直方图接口 (行程弹层统计三卡): 2026-09-27 从 trip_tracks 拆出
(trip_tracks 被缓存批次顶到行数上限; 缓存小件 _track_etag/_cacheable 与
区间展开 _merged_id_list 仍住在 trip_tracks, 同包内取用)。"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .... import database
from ... import repository
from ...schemas import TrackHist
from .trip_tracks import _cacheable, _merged_id_list, _track_etag

router = APIRouter()


@router.get("/hist", response_model=TrackHist)
def get_track_hist(ids: str, request: Request, response: Response,
                   db: Session = Depends(database.get_db),
                   own: Session = Depends(database.get_own_db)) -> TrackHist | Response:
    """速度档直方图 (统计页三卡, 懒加载): 单条/合并同途, ids 写法与
    /merged 一致 (单 id / 逗号 / 首尾区间)。原始 positions 上 SQL 聚合,
    电耗卡口径对齐 TeslaMate SpeedRates 面板 (官方公式 + 平地地形;
    档沿自然十进, 与面板四舍五入档有意差半档, 见 trip_hist 模块注);
    合并分组首开要几秒 (每段原料算好落自有库缓存, 已结束行程永久有
    效), 弹层数字带不等它。"""
    # 直方图在原始 positions 上聚合, 补路点不是采样 (不进直方图) → 不带 fills
    etag = _track_etag(0, "hist", ids)
    if (nm := _cacheable(request, response, etag)) is not None:
        return nm
    id_list = _merged_id_list(ids, db)
    if not id_list:
        raise HTTPException(400, "ids 不能为空")
    hist = repository.track_hist(db, own, id_list)
    if hist is None:
        raise HTTPException(404, "这些行程没有轨迹数据")
    return hist
