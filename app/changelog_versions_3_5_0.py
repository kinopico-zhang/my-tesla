"""更新日志归档: 3.5.0 批次 (2026-10-07 —— 首启引导页: 空账号库第一次
启动, 浏览器里三步完成初始化; 照 3.4.2 的规矩按批次单独拆文件, 列表
拼接后顺序不变 (新→老))。文案照 3.3.3 起的重写规矩: 使用者视角, 报好处。"""
from typing import Final

from .schemas import ChangelogItem, ChangelogVersion

VERSIONS_3_5_0: Final[list[ChangelogVersion]] = [
    ChangelogVersion(version="3.5.0", date="2026-10-07", items=[
        ChangelogItem(kind="新增", text="第一次部署不用再编辑配置文件: 打开"
                                       "页面就进三步引导 —— 注册管理员、填数"
                                       "据来源、配地图 Key, 每一步都可以先"
                                       "跳过, 以后在设置页随时补。"),
        ChangelogItem(kind="改进", text="登录页认得出这是全新部署, 自动带去"
                                       "引导页; 用惯了的老部署一切照旧。"),
    ]),
]
