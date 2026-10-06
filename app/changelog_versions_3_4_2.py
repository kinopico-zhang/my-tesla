"""更新日志归档: 3.4.2 批次 (2026-10-05 拆出 —— 充电地图屏缘缝条批,
照 3.4.1 的规矩按批次单独拆一个文件; 列表拼接后顺序不变 (新→老))。
2026-10-05 晚全批文案重写: 站在使用者视角报好处, 不再引对话原话。"""
from typing import Final

from .schemas import ChangelogItem, ChangelogVersion

VERSIONS_3_4_2: Final[list[ChangelogVersion]] = [
    ChangelogVersion(version="3.4.2", date="2026-10-05", items=[
        ChangelogItem(kind="修复", text="充电地图从屏幕最右边缘右划也能呼出"
                                       "菜单了 —— 原先恰好那一条边划不动, 手"
                                       "指从边缘起划次次落空。"),
    ]),
]
