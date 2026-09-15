"""设置 API: 地图配置 + 驾驶员管理 (自有库)。"""
import threading
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ... import database
from .. import repository, settings_store, tracks_cache
from ..schemas import SettingsState, SettingsUpdate, DriverInfo, DriverIn, DriverUpdate
from ...schemas import OkResponse


settingsapi = APIRouter(prefix="/tesla/api")


@settingsapi.get("/settings")
def get_settings(own: Session = Depends(database.get_own_db)) -> SettingsState:
    """设置现值 (秘密打码, 密码只报是否在用)。"""
    return settings_store.settings_state(own)


@settingsapi.post("/settings")
def save_settings(body: SettingsUpdate,
                  own: Session = Depends(database.get_own_db)) -> SettingsState:
    """保存设置: 留空字段不动; TeslaMate 连接变了 → 换引擎实测, 连不上整体回滚。"""
    try:
        state, engine_changed = settings_store.save_settings(own, body)
    except settings_store.EngineError as exc:
        raise HTTPException(400, str(exc)) from exc
    except settings_store.StyleError as exc:
        raise HTTPException(400, str(exc)) from exc
    if engine_changed:
        # 换库了: 旧轨迹缓存全作废, 后台重灌 (不阻塞响应)
        tracks_cache.reset()
        threading.Thread(target=tracks_cache.warm,
                         args=(database.session_factory(),), daemon=True).start()
    return state


@settingsapi.get("/drivers")
def get_drivers(own: Session = Depends(database.get_own_db)) -> list[DriverInfo]:
    """全部驾驶员。"""
    return settings_store.list_drivers(own)


@settingsapi.post("/drivers")
def add_driver(body: DriverIn,
               own: Session = Depends(database.get_own_db)) -> DriverInfo:
    """添加驾驶员。"""
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "名字不能为空")
    return settings_store.create_driver(own, name)


@settingsapi.patch("/drivers/{driver_id}")
def change_driver(driver_id: int, body: DriverUpdate,
                  own: Session = Depends(database.get_own_db)) -> DriverInfo:
    """改驾驶员: 改名 / 设默认 (全库至多一个默认)。"""
    name = body.name.strip() if body.name is not None else None
    if name == "":
        raise HTTPException(400, "名字不能为空")
    try:
        return settings_store.update_driver(own, driver_id, name, body.is_default)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@settingsapi.delete("/drivers/{driver_id}")
def remove_driver(driver_id: int,
                  own: Session = Depends(database.get_own_db)) -> OkResponse:
    """删驾驶员。"""
    try:
        settings_store.delete_driver(own, driver_id)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    return OkResponse(ok=True)
