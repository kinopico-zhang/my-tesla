"""更新日志归档: 3.4.5 批次 (2026-10-06 —— 常用地点详情改右滑全屏页; 照
3.4.2 的规矩按批次单独拆文件, 列表拼接后顺序不变 (新→老))。文案照 3.3.3
起的重写规矩: 使用者视角, 报好处。"""
from typing import Final

from .schemas import ChangelogItem, ChangelogVersion

VERSIONS_3_4_5: Final[list[ChangelogVersion]] = [
    ChangelogVersion(version="3.4.5", date="2026-10-06", items=[
        ChangelogItem(kind="改进", text="常用地点点开变成从右侧滑入的全屏页, "
                                       "地图和列表都宽敞了; 看完在屏幕左缘往"
                                       "右一拖就能把页面推出去 (跟手, 松手自"
                                       "动收回或弹回), 左上角也有返回按钮。"),
        ChangelogItem(kind="改进", text="点开页里的地点列表换成一张张圆角小"
                                       "卡, 停车次数排在右侧, 选中的那张一眼"
                                       "能认出。"),
        ChangelogItem(kind="改进", text="地图设置里两把 Key 各添一枚「测试」"
                                       "按钮, 测的就是框里刚填的那把: 通过了"
                                       "显示「正常」, 也只有测试通过才能保"
                                       "存 —— 错 Key 从根上存不进去, 不用再"
                                       "开足迹地图猜哪里坏了。"),
    ]),
]
