"""更新日志归档: 3.4.1 批次 (2026-10-04 拆出 —— 常用地点组详情层批,
z 位改进批次; 照 3.3.5 的规矩按批次单独拆一个文件; 列表拼接后顺序
不变 (新→老))。2026-10-05 晚全批文案重写: 站在使用者视角报好处, 不再
引对话原话; 被后续批次即刻取代的条目 (原名小字 / 地点行左滑编辑) 不留。"""
from typing import Final

from .schemas import ChangelogItem, ChangelogVersion

VERSIONS_3_4_1: Final[list[ChangelogVersion]] = [
    ChangelogVersion(version="3.4.1", date="2026-10-04", items=[
        ChangelogItem(kind="修复", text="右划呼出菜单偶发失灵后能自愈, 不用"
                                       "再整页重载 —— 原先一旦哑火, 怎么划都"
                                       "没反应。"),
        ChangelogItem(kind="修复", text="状态页左缘右划一次就能呼出菜单, 不"
                                       "用再划好多次。"),
        ChangelogItem(kind="修复", text="下拉刷新时顶部的图标和数字不再沉进"
                                       "地图后面。"),
        ChangelogItem(kind="修复", text="常用地点删除改成一次点、一次确认, "
                                       "不用再连点好多次。"),
        ChangelogItem(kind="修复", text="常用地点详情页整片都能下滑收起, 不"
                                       "用再掐顶部那条小把手。"),
        ChangelogItem(kind="修复", text="常用地点列表每行之间都有分隔线了。"),
        ChangelogItem(kind="修复", text="地图设置的两张卡之间有了间距, 不再"
                                       "贴死。"),
        ChangelogItem(kind="修复", text="足迹地图播完不再像又加载一遍。"),
        ChangelogItem(kind="改进", text="常用地点点开是详情页: 上面地图把这组"
                                       "的每个地点逐点标出, 下面是地点列表 "
                                       "(各停过几次); 点列表里的一项, 地图跳"
                                       "到那个位置并高亮。"),
        ChangelogItem(kind="改进", text="删除改过名的常用地点变成解除编组: "
                                       "组里的地点恢复原名、各自单独列出。想"
                                       "从统计里去掉某个地点, 在详情页删单个 "
                                       "(底部「已删除」分区里能恢复)。"),
        ChangelogItem(kind="改进", text="常用地点的次数统一另起一行, 管理页"
                                       "和详情页一个长相。"),
        ChangelogItem(kind="改进", text="驾驶员列表的行上按钮收进左滑面板: "
                                       "设为默认、行内改名、删除。"),
    ]),
]
