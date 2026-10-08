"""更新日志归档: 3.5.1 批次 (2026-10-08 —— 行程统计弱网提速批; 照
3.4.2 的规矩按批次单独拆文件, 列表拼接后顺序不变 (新→老))。文案照
3.3.3 起的重写规矩: 使用者视角, 报好处。"""
from typing import Final

from .schemas import ChangelogItem, ChangelogVersion

VERSIONS_3_5_1: Final[list[ChangelogVersion]] = [
    ChangelogVersion(version="3.5.1", date="2026-10-08", items=[
        ChangelogItem(kind="修复", text="手机在外网打开行程统计慢: 图表库"
                                       "下载一次后长存手机 (不再每次进页面"
                                       "重新校验、缓存一失效就整包重拉), "
                                       "常去地点也只带画图要用的行, 回包瘦"
                                       "身近九成。"),
    ]),
]
