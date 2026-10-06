"""更新日志归档: 3.4.7 批次 (2026-10-06 —— 地图设置说明折叠/掩码回显/
保存闸收紧 + 足迹地图按 Key 有无开闸; 同日第三批, 照 3.4.2 的规矩按批次
单独拆文件, 列表拼接后顺序不变 (新→老))。文案照 3.3.3 起的重写规矩:
使用者视角, 报好处。"""
from typing import Final

from .schemas import ChangelogItem, ChangelogVersion

VERSIONS_3_4_7: Final[list[ChangelogVersion]] = [
    ChangelogVersion(version="3.4.7", date="2026-10-06", items=[
        ChangelogItem(kind="改进", text="地图设置里的「Key 获取方式」平时收"
                                       "成一行, 点开是分步清单, 高德控制台的"
                                       "链接点一下就能去办。"),
        ChangelogItem(kind="改进", text="已填的 Key、安全码、Web 服务 Key 在"
                                       "输入框里都显示头尾几位加星号, 一眼认"
                                       "出存的是哪一把。"),
        ChangelogItem(kind="改进", text="保存按钮平时是灰的: 改动要重新测过"
                                       "才能存, 存完立刻回灰 —— 错的 Key 从"
                                       "根上存不进去。"),
        ChangelogItem(kind="改进", text="还没配道路拟合 Key 的时候, 足迹地图"
                                       "在菜单里灰掉不可点; 配上 Key 菜单自动"
                                       "亮, 不用刷新。"),
    ]),
]
