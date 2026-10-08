"""常去地点管理写侧 (2026-10-08 从 trip_places 再拆家: 那边顶到 200 行
硬上限)。隐藏 (hidden_places) 与改名 (place_aliases) 只动统计视图,
行程数据不碰 —— 统计读侧见 trip_places。"""
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...models import HiddenPlace, PlaceAlias


def place_hidden_set(own: Session) -> set[str]:
    """隐藏名单 (常用地点删除, 2026-10-03): raw 原名或组显示名, 管理页
    「已删除」分区照单全列。"""
    return set(own.scalars(select(HiddenPlace.place)).all())


def set_place_hidden(own: Session, places: list[str], hidden: bool) -> None:
    """删/恢复常用地点: hidden=True 落行 (统计读侧消失), False 删行恢复。
    行程数据不动 —— 删除只是统计视图的开关。"""
    if hidden:
        for place in places:
            own.merge(HiddenPlace(place=place))
    else:
        for place in places:
            own.execute(delete(HiddenPlace).where(HiddenPlace.place == place))
    own.commit()


def set_place_alias(own: Session, places: list[str], alias: str) -> None:
    """改/还原常用地点名 (统计读侧见 trip_locations; 并组多名一起改,
    空 alias = 删行还原原名)。"""
    if alias:
        for place in places:
            own.merge(PlaceAlias(place=place, alias=alias,
                                 updated_at=datetime.now()))
    else:
        for place in places:
            own.execute(delete(PlaceAlias).where(PlaceAlias.place == place))
    own.commit()
