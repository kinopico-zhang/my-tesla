"""更新日志归档: 3.3.4 批次 (2026-10-02 拆出 —— 足迹地图性能与播放条布局批,
照 3.3.3 的规矩按批次单独拆一个文件; 列表拼接后顺序不变 (新→老))。
2026-10-05 晚全批文案重写: 站在使用者视角报好处, 不再引对话原话。"""
from typing import Final

from .schemas import ChangelogItem, ChangelogVersion

VERSIONS_3_3_4: Final[list[ChangelogVersion]] = [
    ChangelogVersion(version="3.3.4", date="2026-10-02", items=[
        ChangelogItem(kind="修复", text="足迹地图不卡了: 播放、缩放、滑动都"
                                       "跟手, 打开快了百倍以上; 打开就自动播"
                                       "放, 起步视角框住刚画出的路, 不再把线"
                                       "甩在屏外; 任何时候切换驾驶员都重播该"
                                       "驾驶员的线路。"),
        ChangelogItem(kind="改进", text="播放条变短, 驾驶员筛选并进同一行; "
                                       "✕ 退出钮去掉, 只留播放/暂停和进度条。"),
        ChangelogItem(kind="改进", text="地点命名弹层: 地图放大到约半屏; 输"
                                       "入框能下拉选已经存在的名字 (选已有名 "
                                       "= 两处并成同一个地点)。"),
        ChangelogItem(kind="修复", text="地图上的弹层 (下拉名单/筛选气泡) 点"
                                       "外面就能收起; 行程详情、驾驶员选单、"
                                       "录制预览按 Esc 也能关, 一次只关一层。"),
    ]),
]
