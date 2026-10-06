"""高德逆地理命名缓存的存取 (2026-10-02 用户点名「用 GPS 坐标结合高德,
不要相信 teslamate」): place_worker 回填写, 常去地点统计读。

place_names 一址一行 (键 = TeslaMate address_id): 读侧 IN 查只回 ok 且
有名字的行; 没查到/境外/失败的地址, 读侧自然回退 TeslaMate 名 (旧行为)。
all_address_coords 是 TeslaMate 侧的全量坐标清单 (worker 的待办面)。"""
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Address, PlaceName


def place_name_map(own: Session, ids: Iterable[int]) -> dict[int, str]:
    """地址 id → 高德名 (只回 ok 且有名字的; 空 ids 短路回空表 ——
    in_() 吃空列表会查成全表)。"""
    keys = list(ids)
    if not keys:
        return {}
    rows = own.execute(
        select(PlaceName.address_id, PlaceName.name)
        .where(PlaceName.address_id.in_(keys),
               PlaceName.status == "ok", PlaceName.name != "")).all()
    return {r[0]: r[1] for r in rows}


def done_address_ids(own: Session, ver: int) -> set[int]:
    """已处理水位 (ok/skip 都算, 只按 v): 策略版本没到的重查。"""
    return set(own.scalars(
        select(PlaceName.address_id).where(PlaceName.v == ver)))


def save_place_name(own: Session, row: PlaceName) -> None:
    """命名结果落库: 一址一行, 重写 = 先删后插 (save_road 同款)。"""
    own.execute(delete(PlaceName)
                .where(PlaceName.address_id == row.address_id))
    own.add(row)
    own.commit()


def all_address_coords(session: Session) -> list[tuple[int, float, float]]:
    """TeslaMate 全量地址坐标 (worker 待办面): 停车点的 WGS-84 GPS,
    空坐标的地址这里就排除 (读侧回退 TeslaMate 名)。"""
    return [(a.id, float(a.latitude), float(a.longitude))
            for a in session.scalars(select(Address))
            if a.latitude is not None and a.longitude is not None]


def place_name_row(address_id: int, status: str, v: int,
                   name: str = "") -> PlaceName:
    """工厂 (road_row 同款): name 截 60 字, 与改名接口的 max_length 对齐。"""
    return PlaceName(address_id=address_id, name=name[:60],
                     status=status, v=v)
