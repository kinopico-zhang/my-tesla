"""更新日志归档: 3.3.5 批次 (2026-10-02 拆出 —— 常去地点改问高德批,
照 3.3.4 的规矩按批次单独拆一个文件; 列表拼接后顺序不变 (新→老))。
2026-10-05 晚全批文案重写: 站在使用者视角报好处, 不再引对话原话。"""
from typing import Final

from .schemas import ChangelogItem, ChangelogVersion

VERSIONS_3_3_5: Final[list[ChangelogVersion]] = [
    ChangelogVersion(version="3.3.5", date="2026-10-02", items=[
        ChangelogItem(kind="改进", text="常去地点的名字改问高德: 优先取 300 "
                                       "米内最近的兴趣点, 其次 100 米内的道路"
                                       "名, 再不行才是区+街道 —— 认得出的地"
                                       "名多了, 不再一堆「XX街道」式的兜底。"
                                       "原有的地名重命名作废, 按高德的名重新"
                                       "分布; 之后的改名照旧好使。"),
    ]),
]
