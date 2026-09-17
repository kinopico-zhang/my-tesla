"""充电地点: 省市区逐级匹配筛选 + 地点计数树 (级联下拉数据源)。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Address, ChargingProcess
from ..region_tree import _acc_region_tree, parse_region
from ...schemas import RegionNode


def _match_region(address: Address | None, path: str) -> bool:
    """充电地点筛选: 地址剥出的省市区对 "/" 路径做逐级匹配。

    段数即精确到哪一级 (1=省 2=市 3=区县), 没给的层不陪绑;
    无地址 / 解析不出省 = 不命中。与地点树、行程页 region_address_ids 同一口径。
    """
    segs = [seg for seg in (t.strip() for t in path.split("/")) if seg]
    if not segs or address is None:
        return False
    region = parse_region(address.display_name or "")
    return region[:len(segs)] == tuple(segs)


def charging_region_tree(session: Session) -> list[RegionNode]:
    """充电地点省→市→区县计数树 (按充电次数降序), 地点级联下拉数据源。

    与行程页同款树 (同一解析器); 解析不出省的地址不进树, 但仍参与列表展示。
    """
    rows = session.execute(
        select(Address.display_name)
        .join(ChargingProcess, ChargingProcess.address_id == Address.id)).all()
    return _acc_region_tree(name for (name,) in rows)
