"""地点显示模板的存取 (2026-10-17 用户点名「高德给的地址要完完整整的
结构化地存起来, 然后在设置界面, 可以设置各个界面显示地点的模板」):
行程起终点 / 充电地点 / 常用地点三界面各一条, 空串 = 默认口径 (不套)。

存 app_settings 单行 (drivers_store 同款拆家: settings_store 顶到行数
上限); 读侧每请求现读 —— 设置页改完即生效, 三处消费 (行程/充电/常用
地点) 不用重启。保存是全量提交: 空串也是有效值 (= 回默认), 与主设置的
「留空 = 保持现值」密码语义相反 —— 端点也为此单独一对 (routers/settings)。"""
from sqlalchemy.orm import Session

from .schemas import PlaceTplState, PlaceTplUpdate
from .settings_store import _row


def place_tpl_values(own: Session) -> tuple[str, str, str]:
    """三界面模板现值 (trips/charging/places); 空串 = 默认口径 (不套)。"""
    row = _row(own)
    return (row.place_tpl_trips, row.place_tpl_charging, row.place_tpl_places)


def place_tpl_state(own: Session) -> PlaceTplState:
    """现值打成接口形状 (GET 端点直接回; 关键字构造, *tuple 会被 pylint
    当成 pydantic 构造器超参误报)。"""
    trips, charging, places = place_tpl_values(own)
    return PlaceTplState(trips=trips, charging=charging, places=places)


def save_place_tpl(own: Session, body: PlaceTplUpdate) -> PlaceTplState:
    """保存: 全量提交, 空串 = 回默认。截长兜底 80 (schema 已限, 手搓请求
    也进不来超长)。"""
    row = _row(own)
    row.place_tpl_trips = body.trips.strip()[:80]
    row.place_tpl_charging = body.charging.strip()[:80]
    row.place_tpl_places = body.places.strip()[:80]
    own.commit()
    return place_tpl_state(own)
