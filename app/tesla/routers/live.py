"""当前驾驶 API: 未结束行程的实时状态。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ... import database
from .. import repository
from ..schemas import LiveStatus


live = APIRouter(prefix="/tesla/live/api")


# ---------------------------------------------------------------- 当前驾驶 API

@live.get("/status")
def get_live_status(db: Session = Depends(database.get_db)) -> LiveStatus:
    """当前驾驶状态 (未结束行程 + 足够新的位置点, 前端轮询)。"""
    return repository.live_status(db)
