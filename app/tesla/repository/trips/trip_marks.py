"""行程标注: 驾驶员归集 (标注/兜底口径/SQL 与缓存两种过滤) + 高速费估价。"""
import json

from sqlalchemy import ColumnElement, delete, or_, select
from sqlalchemy.orm import Session

from ...models import Drive, Driver, TripDriver, TripToll
from ..common import NotFound
from ...schemas import MapTrack, TripItem, TripTollIn


def driver_scope(own: Session,
                 driver_id: int) -> tuple[set[int], set[int], bool] | None:
    """按驾驶员筛选的行程 id 口径: (标注它的, 任何标注过的, 是否默认驾驶员)。
    与卡片展示同口径 —— 选默认驾驶员时未标注的也算 (未标注在卡片上就显示
    默认驾驶员名)。驾驶员不存在 → None (调用方按空结果处理)。

    标注表在自有库, 与 TeslaMate 库不是同一个连接 —— 先取 id 集合再下推
    条件 (SQL 端) 或后置过滤 (轨迹缓存端), 不能跨库做子查询。"""
    driver = own.get(Driver, driver_id)
    if driver is None:
        return None
    marked = set(own.scalars(
        select(TripDriver.drive_id).where(TripDriver.driver_id == driver_id)).all())
    all_marked = set(own.scalars(select(TripDriver.drive_id)).all())
    return marked, all_marked, bool(driver.is_default)


def _driver_condition(own: Session, driver_id: int) -> ColumnElement[bool]:
    """按驾驶员筛选 (SQL 端), 口径见 driver_scope。"""
    scope = driver_scope(own, driver_id)
    if scope is None:
        return Drive.id.in_(set())   # 驾驶员不存在 → 空
    marked, all_marked, is_default = scope
    if is_default:
        return or_(Drive.id.in_(marked), Drive.id.not_in(all_marked))
    return Drive.id.in_(marked)


def filter_map_tracks_by_driver(tracks: list[MapTrack], own: Session,
                                driver_id: int) -> list[MapTrack]:
    """缓存轨迹按驾驶员后置过滤 (口径同 _driver_condition)。

    轨迹缓存只从 TeslaMate 库构建, 标注在自有库且会随标/清变动 —— 缓存里
    不落 driver_id, 每次请求现算 id 集合过滤 (全量轨迹在内存, 代价可忽略)。"""
    scope = driver_scope(own, driver_id)
    if scope is None:
        return []
    marked, all_marked, is_default = scope
    return [t for t in tracks
            if t.id in marked or (is_default and t.id not in all_marked)]


def annotate_drivers(own: Session, items: list[TripItem]) -> None:
    """行程条目补驾驶员: 显式标注 > 默认驾驶员兜底 (都没配 = None 不显示)。

    标注指向的驾驶员已被删时按未标注处理 (标注行会随删驾驶员联动清掉,
    这里再兜一层, 库里残留脏行也不致显示错名字)。"""
    if not items:
        return
    drivers = {d.id: d for d in own.scalars(select(Driver)).all()}
    default = next((d for d in drivers.values() if d.is_default), None)
    marks = {m.drive_id: m.driver_id for m in own.scalars(
        select(TripDriver)
        .where(TripDriver.drive_id.in_([i.id for i in items]))).all()}
    for it in items:
        did = marks.get(it.id)
        driver = drivers.get(did) if did is not None else None
        it.driver_id = driver.id if driver is not None else None
        shown = driver or default
        it.driver = shown.name if shown is not None else None


def annotate_tolls(own: Session, items: list[TripItem]) -> None:
    """行程条目补高速费估价 (算过的才有, 没算过保持 None)。"""
    if not items:
        return
    rows = own.scalars(select(TripToll).where(
        TripToll.drive_id.in_([i.id for i in items]))).all()
    by_id = {r.drive_id: r for r in rows}
    for it in items:
        row = by_id.get(it.id)
        if row is not None:
            it.toll = row.tolls
            it.toll_km = row.toll_km


def save_trip_toll(own: Session, drive_id: int, body: TripTollIn) -> None:
    """存/更新一条行程的高速费估价 (算过重算 = 覆盖)。"""
    row = own.scalars(select(TripToll).where(TripToll.drive_id == drive_id)).first()
    if row is None:
        row = TripToll(drive_id=drive_id)
        own.add(row)
    row.tolls = body.tolls
    row.toll_km = body.toll_km
    row.distance = body.distance
    row.roads = json.dumps([r.model_dump() for r in body.roads],
                           ensure_ascii=False, separators=(",", ":"))
    own.commit()


def set_trip_driver(own: Session, drive_id: int, driver_id: int | None) -> None:
    """标/清行程驾驶员 (清 = 删标注行, 展示回默认兜底)。"""
    if driver_id is not None and own.get(Driver, driver_id) is None:
        raise NotFound("驾驶员不存在")
    own.execute(delete(TripDriver).where(TripDriver.drive_id == drive_id))
    if driver_id is not None:
        own.add(TripDriver(drive_id=drive_id, driver_id=driver_id))
    own.commit()
