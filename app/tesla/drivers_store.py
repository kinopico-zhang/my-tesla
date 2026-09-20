"""驾驶员管理 (自有库): 添加/改名/设默认/删除。

拆自 settings_store (200 行上限): 驾驶员与运行时设置是两个域, 各管各的。
默认驾驶员全库至多一个 (设默认会把其他人的默认清掉); 删除时标注联动清掉,
行程展示回默认兜底。
"""
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .models import Driver, TripDriver
from .schemas import DriverInfo
from .repository import NotFound


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
