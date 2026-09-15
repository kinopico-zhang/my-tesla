"""My Tesla 的静态页面 (充电/地图/行程/设置等, 页面文件在 app/tesla/static)。"""
from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse

from ._common import page_response


router = APIRouter()


@router.get("/tesla")
def tesla_home() -> RedirectResponse:
    """/tesla → 默认充电页。"""
    return RedirectResponse("/tesla/charging", status_code=302)

@router.get("/tesla/charging")
def charging_page() -> FileResponse:
    """充电记录页。"""
    return page_response("index.html")

@router.get("/tesla/stats")
def stats_page() -> FileResponse:
    """充电统计页: 统计卡片 + 各维度图表 (记录列表留在充电记录页)。"""
    return page_response("stats.html")

@router.get("/tesla/chargemap")
def chargemap_page() -> FileResponse:
    """充电地图页: 热力图按充电点聚合, 颜色权重可切 电量/次数/费用 三种视图。"""
    return page_response("chargemap.html")

@router.get("/tesla/map")
def map_page() -> FileResponse:
    """足迹地图页。"""
    return page_response("map.html")

@router.get("/tesla/trips")
def trips_page() -> FileResponse:
    """行程轨迹页。"""
    return page_response("trips.html")

@router.get("/tesla/groups")
def groups_page() -> FileResponse:
    """行程分组页: 分组的浏览/打开/改名/删除 (创建入口在行程列表)。"""
    return page_response("groups.html")

@router.get("/tesla/live")
def live_page() -> FileResponse:
    """当前驾驶页: 在开时实时速度 / 位置 / 电耗 / 剩余电量。"""
    return page_response("live.html")

@router.get("/tesla/settings")
def settings_page() -> FileResponse:
    """设置页: TeslaMate 数据库 / 高德 Key / 驾驶员 / 账号。"""
    return page_response("settings.html")

@router.get("/tesla/changelog")
def changelog_page() -> FileResponse:
    """更新日志页: 合并批次的版本条目, 用户视角文案。"""
    return page_response("changelog.html")
