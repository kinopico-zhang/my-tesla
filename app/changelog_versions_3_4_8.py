"""更新日志归档: 3.4.8 批次 (2026-10-07 —— 数据来源卡表单排版 + 左缘
右划呼出菜单全页面统一; 照 3.4.2 的规矩按批次单独拆文件, 列表拼接后
顺序不变 (新→老))。文案照 3.3.3 起的重写规矩: 使用者视角, 报好处。"""
from typing import Final

from .schemas import ChangelogItem, ChangelogVersion

VERSIONS_3_4_8: Final[list[ChangelogVersion]] = [
    ChangelogVersion(version="3.4.8", date="2026-10-07", items=[
        ChangelogItem(kind="改进", text="左边屏幕边缘往右一划就能呼出菜"
                                       "单 —— 所有页面都一样, 不再有哪个角"
                                       "落划不出来。"),
        ChangelogItem(kind="改进", text="数据来源页的连接信息重排: 主机和"
                                       "端口同一行, 数据库名、账号、密码各"
                                       "占一行, 好看也好填。"),
    ]),
]
