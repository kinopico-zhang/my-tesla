"""运行时设置与驾驶员 (自有库): 设置页可改, 未设字段回落 env/.env 默认值。

TeslaMate 连接改动会换引擎重连 (database.rebuild_engine) 并实测 SELECT 1,
连不上整体回滚 (设置与引擎都退回旧值); 高德 Key 即时生效 (map config
端点每次现读)。密码/Key 只存不回显: GET 打码, 前端留空 = 保持现值。
"""
import os
import re

from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .. import database
from .models import AppSetting, Driver, TripDriver
from .schemas import (AmapSettings, DriverInfo, SettingsState,
                      SettingsUpdate, TeslaMateSettings)
from .repository import NotFound

_FIELDS = ("tmdb_host", "tmdb_port", "tmdb_user", "tmdb_password", "tmdb_name",
           "amap_key", "amap_security_code")


class EngineError(RuntimeError):
    """新 TeslaMate 连接验证失败 (调用方转 400; 已整体回滚, 服务未中断)。"""


class StyleError(ValueError):
    """地图样式格式不合法 (调用方转 400, 未写库)。"""


# 地图样式: amap://styles/<官方样式名或自定义ID>。默认幻影黑 (dark) —— 底色
# 纯黑 (#111) 与 App 深灰 UI 最协调。深色样式的地名标注依赖样式数据异步
# 加载, 首次打开过一两秒才出现 (各页建图后有延时补重渲染), 不是样式没字。
# (编辑器里标注是开着的, 容器实测 dark 标注是"首帧不画重渲染才画"的容器
# 伪象, 真机 (用户 iPhone) 上确实无字)。
AMAP_STYLE_DEFAULT = "amap://styles/dark"
_STYLE_RE = re.compile(r"^amap://styles/[A-Za-z0-9_-]{1,64}$")


def _row(own: Session) -> AppSetting:
    """取设置行 (没有就建, 恒单行 id=1)。"""
    row = own.get(AppSetting, 1)
    if row is None:
        row = AppSetting(id=1)
        own.add(row)
        own.commit()
    return row


def _masked(value: str) -> str:
    """半遮回显 (ab12****yz89): 识别够了, 完整值不外泄。"""
    if not value:
        return ""
    return f"{value[:4]}****{value[-4:]}" if len(value) > 8 else "****"


def effective_tmdb(own: Session) -> dict[str, str]:
    """TeslaMate 连接各字段现值: 设置行 > env (host 再回落 docker 容器定位)。

    docker 定位失败不炸 GET (host 留空展示), URL 拼接时才真正报错。"""
    row = _row(own)
    host = row.tmdb_host or os.environ.get("TMDB_HOST", "")
    if not host:
        try:
            host = database.resolve_db_host()
        except RuntimeError:
            host = ""
    return {
        "host": host,
        "port": row.tmdb_port or os.environ.get("TMDB_PORT", "5432"),
        "user": row.tmdb_user or os.environ.get("TMDB_USER", "teslamate"),
        "password": row.tmdb_password or os.environ.get("TMDB_PASS", ""),
        "name": row.tmdb_name or os.environ.get("TMDB_NAME", "teslamate"),
    }


def engine_url(own: Session) -> str:
    """TeslaMate 连接串 (设置行 > env): 启动建引擎用。"""
    return database.build_db_url(effective_tmdb(own))


def amap_values(own: Session) -> tuple[str | None, str | None]:
    """高德 Key 现值 (设置行 > env): map config 端点每次现读, 改完即生效。"""
    row = _row(own)
    return (row.amap_key or os.environ.get("AMAP_KEY") or None,
            row.amap_security_code or os.environ.get("AMAP_SECURITY_CODE") or None)


def amap_style_value(own: Session) -> str:
    """地图样式现值 (设置行 > env > 标准图): map config 端点每次现读。"""
    return (_row(own).amap_style or os.environ.get("AMAP_STYLE")
            or AMAP_STYLE_DEFAULT)


def settings_state(own: Session) -> SettingsState:
    """设置页状态: 各字段现值 (回落 env 后的效果), 秘密只报在用/打码。"""
    eff = effective_tmdb(own)
    row = _row(own)
    key = row.amap_key or os.environ.get("AMAP_KEY", "")
    code = row.amap_security_code or os.environ.get("AMAP_SECURITY_CODE", "")
    return SettingsState(
        tmdb=TeslaMateSettings(
            host=eff["host"], port=eff["port"], user=eff["user"],
            name=eff["name"], password_set=bool(eff["password"])),
        amap=AmapSettings(key_masked=_masked(key), security_code_set=bool(code),
                          style=amap_style_value(own)))


def save_settings(own: Session, body: SettingsUpdate) -> tuple[SettingsState, bool]:
    """保存设置 (留空字段不动)。

    TeslaMate 连接串变了 → 换引擎并实测 SELECT 1; 连不上抛 EngineError,
    设置行与引擎都回滚到旧值 (服务不断)。返回 (新状态, 是否换了引擎)。"""
    row = _row(own)
    style = body.amap_style.strip()
    if style and not _STYLE_RE.fullmatch(style):
        raise StyleError(f"地图样式不合法: {style} (应为 amap://styles/<样式名或ID>)")
    old_url = database.build_db_url(effective_tmdb(own))
    old_values = {f: getattr(row, f) for f in _FIELDS}
    old_values["amap_style"] = row.amap_style   # 引擎验证失败要一起回滚
    for field in _FIELDS:
        value = getattr(body, field).strip()
        if value:
            setattr(row, field, value)
    if style:
        row.amap_style = style
    own.commit()
    new_url = database.build_db_url(effective_tmdb(own))
    if new_url == old_url:
        return settings_state(own), False
    database.rebuild_engine(new_url)
    try:
        with database.session_factory()() as session:   # pylint: disable=not-callable
            session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        for field, value in old_values.items():
            setattr(row, field, value)
        own.commit()
        database.rebuild_engine(old_url)
        detail = str(getattr(exc, "orig", None) or exc)[:200]
        raise EngineError(f"新连接连不上: {detail}") from exc
    return settings_state(own), True


# ---------------------------------------------------------------- 驾驶员

def _info(driver: Driver) -> DriverInfo:
    """ORM 行 → API 条目。"""
    return DriverInfo(id=driver.id, name=driver.name,
                      is_default=driver.is_default)


def list_drivers(own: Session) -> list[DriverInfo]:
    """全部驾驶员 (添加顺序)。"""
    return [_info(d) for d in
            own.scalars(select(Driver).order_by(Driver.id)).all()]


def create_driver(own: Session, name: str) -> DriverInfo:
    """添加驾驶员。"""
    driver = Driver(name=name)
    own.add(driver)
    own.commit()
    return _info(driver)


def update_driver(own: Session, driver_id: int,
                  name: str | None, is_default: bool | None) -> DriverInfo:
    """改驾驶员: 改名 / 设默认 (设默认会把其他人的默认清掉, 全库至多一个)。"""
    driver = own.get(Driver, driver_id)
    if driver is None:
        raise NotFound("驾驶员不存在")
    if name is not None:
        driver.name = name
    if is_default is True:
        own.execute(update(Driver).values(is_default=False))
        driver.is_default = True
    elif is_default is False:
        driver.is_default = False
    own.commit()
    return _info(driver)


def delete_driver(own: Session, driver_id: int) -> None:
    """删驾驶员 (标注联动清掉, 行程展示回默认兜底; 默认被删后暂时无默认)。"""
    driver = own.get(Driver, driver_id)
    if driver is None:
        raise NotFound("驾驶员不存在")
    own.execute(delete(TripDriver).where(TripDriver.driver_id == driver_id))
    own.delete(driver)
    own.commit()
