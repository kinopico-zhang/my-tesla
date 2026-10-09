"""My Tesla 的页面路由 (3.0 单壳切换, 用户原话: api 是 /tesla 没有后面的
app, 原先的下掉): /tesla 是唯一页面; 壳的 P2-P6 开发地址 /tesla/app 与
9 个旧页路由全部 302 回壳, query 原样带过去 (深链不丢: ?id=/?ids= 行程
直开, ?driver_id=/?range= 等加载期消费), 旧页特有的参数在重定向时换名
(充电地图的度量 ?view= → ?metric=, ?view= 让给视图选择)。"""
from urllib.parse import urlencode

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.requests import Request

from ... import database
from .. import settings_store
from ._common import page_response


router = APIRouter()


@router.get("/tesla", response_model=None)
def shell_page(own: Session = Depends(database.get_own_db)
               ) -> FileResponse | RedirectResponse:
    """3.0 单壳: 全部 11 个视图的宿主 (充电 3 + 行程 3 + 驾驶 1 + 设置 4)。

    首启引导没走完 (TeslaMate 连接或高德 Key 还缺) 一律 302 回 /setup ——
    引导不允许跳过, 三步配齐才放行 (组合仓部署共用这个门)。"""
    if settings_store.wizard_missing(own):
        return RedirectResponse("/setup", status_code=302)
    return page_response("app.html")


def _to_shell(request: Request, view: str | None) -> RedirectResponse:
    """旧页路由 302 回壳: query 保留; 充电地图旧页的度量参数换名
    (?view= 度量 → ?metric= —— 3.0 的 ?view= 是视图选择)。"""
    params = dict(request.query_params)
    if request.url.path == "/tesla/chargemap" and "view" in params:
        params["metric"] = params.pop("view")
    if view is not None:
        params["view"] = view
    qs = urlencode(params)
    return RedirectResponse("/tesla" + (f"?{qs}" if qs else ""), status_code=302)


@router.get("/tesla/app")
def shell_dev_address(request: Request) -> RedirectResponse:
    """壳的 P2-P6 开发地址: 洗成 /tesla。"""
    return _to_shell(request, None)


@router.get("/tesla/charging")
def charging_page(request: Request) -> RedirectResponse:
    """旧充电记录页 → 裸壳 (视图跟上次走的)。

    不指 view=charging: 2.x 时代 manifest 的 start_url 是 /tesla/charging,
    已装到主屏的图标把它烙死在安装档里 —— 指了 view= 就永远压过壳的
    「记住上次视图」(用户报每次冷启都是充电页)。其余旧页路由的 view=
    是真深链 (收藏/聊天记录), 保留。"""
    return _to_shell(request, None)


@router.get("/tesla/stats")
def stats_page(request: Request) -> RedirectResponse:
    """旧充电统计页 → 壳充电统计视图。"""
    return _to_shell(request, "stats")


@router.get("/tesla/chargemap")
def chargemap_page(request: Request) -> RedirectResponse:
    """旧充电地图页 → 壳充电地图视图 (度量参数换名, 见 _to_shell)。"""
    return _to_shell(request, "chargemap")


@router.get("/tesla/map")
def map_page(request: Request) -> RedirectResponse:
    """旧足迹地图页 → 壳足迹地图视图 (?driver_id= 深链保留)。"""
    return _to_shell(request, "map")


@router.get("/tesla/trips")
def trips_page(request: Request) -> RedirectResponse:
    """旧行程轨迹页 → 壳行程视图 (?id=/?ids= 分享链接直开)。"""
    return _to_shell(request, "trips")


@router.get("/tesla/groups")
def groups_page(request: Request) -> RedirectResponse:
    """旧行程分组页 → 壳行程分组视图。"""
    return _to_shell(request, "groups")


@router.get("/tesla/live")
def live_page(request: Request) -> RedirectResponse:
    """旧当前驾驶页 → 壳驾驶视图。"""
    return _to_shell(request, "live")


@router.get("/tesla/settings")
def settings_page(request: Request) -> RedirectResponse:
    """旧软件设置页 → 壳数据来源视图 (旧页的内容就是数据来源表单;
    2026-09-27 账号设置拆独立页排设置组首位后, 旧链仍落数据来源)。"""
    return _to_shell(request, "settings-db")


@router.get("/tesla/changelog")
def changelog_page(request: Request) -> RedirectResponse:
    """旧更新日志页 → 壳更新日志视图。"""
    return _to_shell(request, "changelog")
