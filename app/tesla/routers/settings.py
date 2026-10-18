"""设置 API: 地图配置 + 驾驶员管理 + 地点显示模板 (自有库; 驾驶员 CRUD
在 drivers_store)。"""
import logging
import threading
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ... import database
from .. import (drivers_store, place_tpl_store, repository, settings_store,
                tracks_cache)
from ..place_naming import render_place
from ..schemas import (SettingsState, SettingsUpdate, DriverInfo, DriverIn,
                       DriverUpdate, TmdbTest, TmdbTestIn,
                       PlaceTplExample, PlaceTplPreview, PlaceTplState,
                       PlaceTplUpdate)
from ...schemas import OkResponse


settingsapi = APIRouter(prefix="/tesla/api")

# 蹭 uvicorn 的输出道: app 自身没有日志配置, 挂这里日志才落 nas-run.log
# (跟访问日志同屏, 2026-10-12 向导验证排障用)
_log = logging.getLogger("uvicorn.error")


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
    if engine_changed:
        # 换库了: 旧轨迹缓存全作废, 后台重灌 (不阻塞响应)
        tracks_cache.reset()
        threading.Thread(target=tracks_cache.warm,
                         args=(database.session_factory(),), daemon=True).start()
    return state


@settingsapi.post("/settings/test", response_model=TmdbTest)
def test_settings_tmdb(body: TmdbTestIn,
                       own: Session = Depends(database.get_own_db)) -> TmdbTest:
    """首启引导数据源步「测试连接」: 候选实测 (空字段回落现值), 不落库
    不换引擎 —— 通过了前端才解锁「下一步」。"""
    ok, detail = settings_store.test_tmdb(own, body)
    # 排障日志: 浏览器到底送了什么候选 + 实测结果 (密码永不入日志; 空字段
    # 实际回落的服务端现值, 报错详情里带的地址就是它实际连的)
    _log.info("引导测试连接: host=%s port=%s user=%s name=%s -> ok=%s (%s)",
              body.tmdb_host or "(空=现值)", body.tmdb_port or "(空=现值)",
              body.tmdb_user or "(空=现值)", body.tmdb_name or "(空=现值)",
              ok, detail)
    return TmdbTest(ok=ok, detail=detail)


@settingsapi.get("/place-templates", response_model=PlaceTplState)
def get_place_templates(own: Session = Depends(database.get_own_db)) -> PlaceTplState:
    """地点显示模板现值 (三界面; 空串 = 默认口径)。"""

    return place_tpl_store.place_tpl_state(own)


@settingsapi.post("/place-templates", response_model=PlaceTplState)
def save_place_templates(body: PlaceTplUpdate,
                         own: Session = Depends(database.get_own_db)) -> PlaceTplState:
    """保存地点显示模板: 全量提交, 空串也是有效值 (= 回默认) —— 与主设置
    的「留空不动」密码语义相反, 所以单独一对端点。"""

    return place_tpl_store.save_place_tpl(own, body)


@settingsapi.post("/place-templates/preview",
                  response_model=PlaceTplPreview)
def preview_place_templates(
        body: PlaceTplUpdate,
        own: Session = Depends(database.get_own_db)) -> PlaceTplPreview:
    """预览: 缓存里挑组件最全的 2-3 条地名当样例, 三条候选各渲染一遍 ——
    渲染单一源在服务端 (render_place), 前端只搬运不重抄 (设置页一卡一条
    例子区)。还没跑过命名 (没样例) 时 rows 空, 前端提示「暂无样例」。"""

    return PlaceTplPreview(rows=[
        PlaceTplExample(sample=i.name,
                        trips=render_place(body.trips, i),
                        charging=render_place(body.charging, i),
                        places=render_place(body.places, i))
        for i in repository.sample_place_infos(own)])


@settingsapi.get("/drivers")
def get_drivers(own: Session = Depends(database.get_own_db)) -> list[DriverInfo]:
    """全部驾驶员。"""
    return drivers_store.list_drivers(own)


@settingsapi.post("/drivers")
def add_driver(body: DriverIn,
               own: Session = Depends(database.get_own_db)) -> DriverInfo:
    """添加驾驶员。"""
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "名字不能为空")
    return drivers_store.create_driver(own, name)


@settingsapi.patch("/drivers/{driver_id}")
def change_driver(driver_id: int, body: DriverUpdate,
                  own: Session = Depends(database.get_own_db)) -> DriverInfo:
    """改驾驶员: 改名 / 设默认 (全库至多一个默认)。"""
    name = body.name.strip() if body.name is not None else None
    if name == "":
        raise HTTPException(400, "名字不能为空")
    try:
        return drivers_store.update_driver(own, driver_id, name, body.is_default)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@settingsapi.delete("/drivers/{driver_id}")
def remove_driver(driver_id: int,
                  own: Session = Depends(database.get_own_db)) -> OkResponse:
    """删驾驶员。"""
    try:
        drivers_store.delete_driver(own, driver_id)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    return OkResponse(ok=True)
