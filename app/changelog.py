"""更新日志数据: 每个版本 = 一批改动的合并, 文案站在使用者视角。

不逐提交记版本 (一个版本可以同时含多个修复和多个功能); 版本号 x.y.z ——
x 大改版 · y 新功能 · z 问题修复, 新批次加在最上面 (新→老)。
只记 My Tesla 自己的版本线; My Music / My Money 的变化在各自应用的
日志页看 (2026-09-14 起各自独立)。
"""
from typing import Final

from .schemas import ChangelogItem, ChangelogVersion

VERSIONS: Final[list[ChangelogVersion]] = [
    ChangelogVersion(version="2.6.0", date="2026-09-15", items=[
        ChangelogItem(kind="新增", text="左上角的菜单顶部现在显示当前登录的是谁 (管理员带标记), 换账号、看家人有没有登录一目了然;"
                                       " 三个应用的菜单都一样"),
    ]),
    ChangelogVersion(version="2.5.1", date="2026-09-14", items=[
        ChangelogItem(kind="新增", text="加密访问: 网站有了带锁的新地址 kinopico.duckdns.org:8500, 在家、在外打开都一样"),
        ChangelogItem(kind="改进", text="地址从一串会变的数字换成固定域名 —— 家里宽带 IP 以后再变也照常用, 不用改收藏; 旧的数字地址停用"),
        ChangelogItem(kind="修复", text="以前登录密码在网上是明文传输的, 现在全程加密;"
                                       " 第一次用新地址要重新登录一次, 主屏幕图标删掉重新添加"),
    ]),
    ChangelogVersion(version="2.5.0", date="2026-09-13", items=[
        ChangelogItem(kind="新增", text="多账号: 管理员生成邀请链接发给家人, 注册后各有各的账号; 除账号管理外的功能都能用"),
        ChangelogItem(kind="新增", text="账号管理页 (仅管理员): 看账号列表, 生成 / 撤销注册邀请, 一键复制邀请链接"),
        ChangelogItem(kind="新增", text="设置页可以改自己的名称和密码"),
        ChangelogItem(kind="改进", text="服务定名 My Home: 登录后是家门厅, My Tesla (车辆) 和 My Money (记账)"
                                       " 两个应用都从这里进"),
        ChangelogItem(kind="改进", text="门厅搬到了根路径: 打开就是两个应用的大卡片, 点一下就进; 门厅自己也有主屏图标 (黑底白房子)"),
        ChangelogItem(kind="改进", text="账号管理从 My Tesla 搬进门厅: 账号是全家共用的, 不属于任何一个应用; 旧地址和老邀请链接自动跳转,"
                                       " 不会失效"),
        ChangelogItem(kind="修复", text="登录页显示 / 隐藏密码的两个图标并排显示"),
        ChangelogItem(kind="修复", text="iPhone Safari 上复制邀请链接没反应: 换了兜底拷贝方案, 实在拷不了就直接弹分享面板 (里面也能拷贝,"
                                       " 还能直接发给家人)"),
        ChangelogItem(kind="修复", text="账号列表里「管理员」标签的椭圆外框只剩上半截"),
    ]),
    ChangelogVersion(version="2.4.0", date="2026-09-13", items=[
        ChangelogItem(kind="新增", text="充电详情可以导航到充电站, 自己挑手机里的地图 App (高德 / 百度 / 腾讯 / 苹果地图),"
                                       " 没装的地图长按就能隐藏"),
        ChangelogItem(kind="新增", text="每个页面的顶栏都有刷新按钮了"),
        ChangelogItem(kind="改进", text="充电页的地点筛选改成省 → 市 → 区县三级展开, 任选一级都能筛"),
        ChangelogItem(kind="改进", text="更新日志页和录制弹层的说明文字更简洁了"),
        ChangelogItem(kind="修复", text="充电详情里的国标标签 (GB_DC / Gb 这类) 撤掉了, 国内充电桩都是国标没有信息量"),
        ChangelogItem(kind="修复", text="iPhone 上充电详情顶部把手拉不动、点一下也没反应"),
        ChangelogItem(kind="修复", text="手机上录完视频一定有保存按钮, 不支持系统分享时存到「文件」再转存相册"),
    ]),
    ChangelogVersion(version="2.3.0", date="2026-09-13", items=[
        ChangelogItem(kind="新增", text="充电统计页: 快慢充占比、充电时段、常去充电点、城市分布等图表"),
        ChangelogItem(kind="新增", text="充电地图页: 常去充电点的热力图, 按电量 / 次数 / 费用三种视角着色, 点一下看明细"),
        ChangelogItem(kind="新增", text="更新日志页 (本页), 加入每页的菜单"),
        ChangelogItem(kind="新增", text="行程分组独立成页, 行程页只保留创建入口"),
        ChangelogItem(kind="新增", text="轨迹播放可以录成视频, 播完一键存到相册"),
        ChangelogItem(kind="新增", text="充电记录可按「已记费用 / 未记费用」筛选, 逐条补录更顺手"),
        ChangelogItem(kind="新增", text="足迹地图可按驾驶员筛选"),
        ChangelogItem(kind="改进", text="页签更名: 充电记录 / 足迹地图 / 行程列表 / 软件设置"),
        ChangelogItem(kind="改进", text="充电详情和轨迹弹层可以拽着顶部把手下拉关闭"),
        ChangelogItem(kind="修复", text="各页顶栏统一: 时间范围一律进顶栏, 行程分组和软件设置页的顶栏与全站对齐"),
        ChangelogItem(kind="修复", text="录完视频在 iPhone 上没有「存到相册」按钮"),
        ChangelogItem(kind="修复", text="充电时间很短的卡片, 电量起止标签会叠在一起"),
    ]),
    ChangelogVersion(version="2.2.0", date="2026-09-12", items=[
        ChangelogItem(kind="新增", text="当前驾驶页: 车在开时实时看车速、电量、续航和已驶里程, 行程结束自动转到行程页"),
        ChangelogItem(kind="新增", text="加到主屏幕后的全屏体验完善: 整个 App 都在全屏里, 冷启动回到上次看的页面"),
        ChangelogItem(kind="新增", text="没记费用的充电在列表里有红色标记, 补录后自动恢复正常"),
        ChangelogItem(kind="改进", text="播放视角可手动锁定, 播放条 +/− 整体调远近并记住; 播放中不会自动熄屏"),
        ChangelogItem(kind="改进", text="地图默认深色, 与 App 风格一致 (可在设置页换)"),
        ChangelogItem(kind="改进", text="合并播放上限提到 100 段, 全选一键补齐"),
        ChangelogItem(kind="修复", text="全屏 App 里跳页面会弹出 Safari 菜单、实时数字位数变化挤乱布局等一批问题"),
    ]),
    ChangelogVersion(version="2.1.0", date="2026-09-11", items=[
        ChangelogItem(kind="新增", text="软件设置页: TeslaMate 连接、高德 Key、驾驶员名单都在页面里改"),
        ChangelogItem(kind="新增", text="行程可标注驾驶员, 行程列表按驾驶员筛选"),
        ChangelogItem(kind="新增", text="高速费估价: 按实际走过的路线估算, 打开行程自动估一次"),
        ChangelogItem(kind="新增", text="行程分组: 常跑的线路存成命名分组, 一键合并播放"),
        ChangelogItem(kind="改进", text="播放镜头随车速平滑拉远近, 长轨迹播放放慢到肉眼跟得上"),
        ChangelogItem(kind="修复", text="手机端自定义日历出屏、下拉菜单被遮挡等一批问题"),
    ]),
    ChangelogVersion(version="2.0.0", date="2026-09-10", items=[
        ChangelogItem(kind="新增", text="行程列表页: 每段行程的里程、时长、起终点, 点开看轨迹地图"),
        ChangelogItem(kind="新增", text="轨迹动画播放: 视角跟着车走, 按车速着色, GPS 断档沿真实道路补连"),
        ChangelogItem(kind="新增", text="多选连续行程合并成一条长轨迹播放, 链接可直接分享"),
        ChangelogItem(kind="新增", text="时间范围和城市筛选, 筛选条件写进链接可直接分享"),
        ChangelogItem(kind="改进", text="服务架构整体重写, 数据链路全类型化, 更快更稳"),
        ChangelogItem(kind="修复", text="手机端地图缩放被劫持、日期筛选报错、浏览器缓存旧脚本等一批问题"),
    ]),
    ChangelogVersion(version="1.1.0", date="2026-09-09", items=[
        ChangelogItem(kind="新增", text="足迹地图: 一张地图看所有走过的路线, 越放大越精细"),
        ChangelogItem(kind="新增", text="登录保护: 密码可显示, 输错会提示原因"),
        ChangelogItem(kind="新增", text="费用补录: 忘记记金额的充电点一下就能补上, 写回 TeslaMate"),
        ChangelogItem(kind="改进", text="轨迹数据服务端缓存, 第二次打开更快"),
    ]),
    ChangelogVersion(version="1.0.0", date="2026-09-08", items=[
        ChangelogItem(kind="新增", text="My Tesla 上线: 手机上翻看特斯拉充电历史 (电量 / 时长 / 费用)"),
        ChangelogItem(kind="新增", text="充电详情: 每次充电的过程曲线"),
    ]),
]


def entries() -> list[ChangelogVersion]:
    """全部版本, 新→老。"""
    return VERSIONS
