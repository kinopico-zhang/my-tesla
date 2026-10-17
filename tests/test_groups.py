"""行程分组视图测试: 壳内骨架 + 分组视图交互片段 (CRUD 走 trips 的
api/groups, 已在 test_trips 覆盖; 这里只管视图挂载)。3.0 单壳后旧页的
顶栏/页签菜单没了 —— 骨架断言只留视图自身标记 (生命周期/手势断言在
test_shell_views)。"""

from tests.tesla_static_files import served_page

SHELL = "/tesla"


def test_groups_page_served(auth):
    """分组视图: 列表骨架 (转圈/列表/空态/错误重试) + 计数徽标 (toast 在壳层)。"""
    html = served_page(auth, SHELL)
    for frag in ['data-view="groups"', 'id="gp-count-badge"', 'id="gp-spin"',
                 'id="gp-list"', 'id="gp-empty"', 'id="gp-errbox"',
                 'id="gp-retry"', 'id="toast"',
                 '<script src="/tesla/static/js/view/groups-page.js?v=9"></script>',
                 '在行程列表长按多选行程后点「存为分组」']:
        assert frag in html, f"分组视图缺少 {frag}"
    # 弹层块已升壳级 (2026-09-22): 分组页打开的合并弹层宿主是分组视图,
    # 行程视图藏起时这层照常显 —— 背后不再闪「行程轨迹」(用户实报)
    assert 'id="backdrop"' in html and 'id="sheet"' in html
    assert html.index('id="sheet"') > html.index('<aside id="drawer"')   # 壳级: 在抽屉之后


def test_groups_page_interactions(auth):
    """分组视图脚本: 打开 = 壳级合并弹层直接开 (弹层带分组名当标题,
    sheetFrom 记来源, 关弹层原地刷新分组列表; 不跳行程视图), 改名行内
    编辑, 删除二次确认, 卡片化样式对齐行程列表 (card-t 同一套)。行内
    重渲染会脱链事件目标 —— 委托先判 isConnected (与行程页同一坑)。"""
    js = auth.get("/tesla/static/js/view/groups-page.js?v=9").text
    for frag in ['"/tesla/trips/api/groups"', "function rowHTML(",
                 "async function gpLoad()",
                 'sheetFrom = "groups"',
                 # 3.10.0 起每次进都重拉 (明细页会改分组, 回来要新数据);
                 # 转圈只在没数据时亮 (gpBooted 门控), 静默换血不闪白屏
                 'show() { gpLoad(); }', "gpBooted",
                 "if (!gpBooted || groups.length === 0) $(\"#gp-spin\").hidden = false;",
                 # 整个分组条目随键传给 openMerged (带汇总, 弹层数字带一开
                 # 就显数, 2026-09-23 用户点名「加载完地图才显示」)
                 "openMerged(item.dataset.ids, null, group)",
                 'classList.add("arm")', "确认删除",
                 'method: "DELETE"', 'method: "PATCH"',
                 'gp-list").addEventListener("click"',
                 'gp-list").addEventListener("keydown"',
                 "!t.isConnected", 'status === 401',
                 'class="gp-input"', 'maxlength="30"',
                 'class="gp-item card-t"', 'class="gp-acts"']:
        assert frag in js, f"groups-page.js 缺少 {frag}"
    # 不再跳行程视图 (背后停在分组列表); 离开视图与行程 hide 同一套收尾
    assert 'navigate("trips")' not in js
    assert "bumpOpenSeq();" in js and "stopRecExport(true)" in js
    # 改名/删除按钮有结果才动列表; Enter 提交 / Esc 放弃
    assert 'e.target.classList.contains("gp-input")' in js
    assert 'e.key === "Enter"' in js and 'e.key === "Escape"' in js


def test_groups_card_span_not_clipped(auth):
    """跨度没显示全 (2026-09-25 用户两轮实报): 分组卡统计格沿用行程卡的
    .ct-cells 对半分 (flex:1), 那是给短数值设计的; 跨度是日期串在半格里
    必触发 .val 的省略号截尾。三重修复都要在:
    1) 里程格收成按内容宽, 跨度格吃剩下整段 (只钉 .gp-list 下, 行程卡
       三格照旧均分);
    2) 字号真收一档: 旧 .gp-span (0,1,0) 永远输给后加载 trips-cards 的
       .ct-cell .val (0,2,0), 从未生效 —— 跨度一直按 17px 渲染, 这就是
       第一轮修复后用户仍报显示不全的根因; .gp-list .val.gp-span 抬到
       (0,3,0) 才压得过;
    3) nowrap/省略号改 normal: 服务端日期已是紧凑斜杠 (2026/09/09,
       斜杠是干净断行点), 真装不下按 / 换行保底显示全。"""
    css = auth.get("/tesla/static/css/tesla-groups.css").text
    assert ".gp-list .ct-cell:first-child { flex: none; }" in css
    assert ".gp-list .val.gp-span { font-size: 15px; white-space: normal; }" in css
    assert ".gp-span { font-size: 15px; }" not in css   # 死规则 (0,1,0) 不回潮
    trips_css = auth.get("/tesla/static/css/tesla-trips-cards.css").text
    assert ".ct-cell { flex: 1; min-width: 0;" in trips_css   # 行程卡均分不动
    assert ".ct-cell .val {" in trips_css   # 特异性对手 (0,2,0): 跨度规则必须更高
    html = served_page(auth, SHELL)
    assert "css/tesla-groups.css?v=14" in html   # v12: 宽度查询折叠 (v11: 大屏手机一列, v10: 3.10.0 弹层批破缓存 +1)


# ---------------------------------------------------------------- 分组明细 (3.10.0)

def test_group_trips_page_skeleton(auth):
    """分组明细第四页骨架 (3.10.0 用户点名「详细行程跟行驶轨迹/行驶数据/
    行驶统计并列, 左右滑切页」+ 两轮极简: 页头标题/段数与口径说明全撤,
    行内加/移按钮换右上选圈 —— 进入即多选态, 页底常驻「取消/确定」):
    分页器里的第四个 section —— 分组弹层才有, 整页与第四枚页标 hidden
    起步, trips-sheet-stats 随载荷 gid 挂上/摘下; 组内外行程一列 (两端
    加载提示行/转圈/错误重试)。独立二级视图与底行入口按钮 (前两版方案)
    整套撤掉。"""
    html = served_page(auth, SHELL)
    for frag in ['class="tp-gtr" id="tp-gtr" hidden', 'id="gtr-scroll"',
                 'id="gtr-top"', 'id="gtr-list"',
                 'id="gtr-tail"', 'id="gtr-spin"', 'id="gtr-errbox"',
                 'id="gtr-retry"',
                 '<div class="gtr-bar" id="gtr-bar">',
                 'id="gtr-cancel">取消</button>', 'id="gtr-ok">确定</button>',
                 '<span class="tp-dots" id="tp-dots"><i class="on"></i><i></i>'
                 '<i></i><i hidden></i></span>',
                 'css/tesla-group-trips.css?v=6',
                 '<script src="/tesla/static/js/view/group-trips-stream.js?v=5"></script>',
                 '<script src="/tesla/static/js/view/group-trips-marks.js?v=4"></script>']:
        assert frag in html, f"分组明细第四页缺少 {frag}"
    # 第四页在分页器里: 统计页之后、底行之前 (底行页标第四枚随它亮/藏)
    assert html.index('id="tp-hist"') < html.index('id="tp-gtr"')
    assert html.index('id="tp-gtr"') < html.index('id="tp-foot"')
    # 极简两轮: 页头 (分组名/段数) 与口径说明撤净; 标记条无计数标签且常驻
    # (进页即多选, 不靠标记亮起); 行内加/移按钮不回潮
    for gone in ['id="gtr-name"', 'id="gtr-count"', 'gtr-head', 'class="gtr-tip"',
                 'id="gtr-bar-lb"', 'gtr-acts', 'gtr-add', 'gtr-rm']:
        assert gone not in html, f"{gone} 应已退役"
    # 独立二级视图/底行入口按钮 (前两版方案) 不许回潮
    assert 'data-view="group-trips"' not in html
    assert "sh-group-btn" not in html and "tp-foot-row" not in html
    assert "gtr-back" not in html


def test_group_trips_page_interactions(auth):
    """分组明细第四页接线 (3.10.0): 挂/摘页随载荷 gid —— openTrip 开弹层
    即调 gtrPageSync (分组页打开的合并载荷带 gid, 多选合并/深链没有),
    hideSheet 走 gtrDetach 收尾; 页数按可见页现算 (hidden 子元素不占页
    位, 绕回/夹板都按可见数); 挂页即拉组内全部并整组起钩 (gtrStart 复位
    钩集), ptr 共享提示字随页换「松开加载更早」; 进入即多选: 点行打/撤
    钩 (组内中段撤钩拦 toast, 断连续), 页底常驻「取消/确定」—— 取消整
    批回原样, 确定按钩集与原组的差整批提交 (连续性服务端守: 加 = 区间
    外延吸收, 移 = 只收两端); 顶部下拉 prepend 回补 scrollTop 不跳位,
    尾部触底 IO 链式续载, 就地翻行不整页重拉。"""
    stats_js = auth.get("/tesla/static/js/view/trips-sheet-stats.js?v=43").text
    for frag in ['const FOOT_LB = ["行驶轨迹", "行驶数据", "行驶统计", "详细行程"];',
                 "const nPages = () => [...pager.children].filter(el => !el.hidden).length || 1;",
                 "const next = (page + 1) % nPages();",
                 "root.gtrPageSync = it => {",
                 "root.gtrDetach = () => root.gtrPageSync(null);",
                 "gtrPage.hidden = !on;",
                 'gtrHint.textContent = on ? "松开加载更早" : "松开刷新";',
                 "if (on) gtrStart(it.gid);",
                 "else if (page > 2) pager.scrollLeft = 2 * pager.clientWidth;"]:
        assert frag in stats_js, f"trips-sheet-stats.js 缺少 {frag}"
    open_js = auth.get("/tesla/static/js/view/trips-sheet-open.js?v=12").text
    assert "gtrPageSync(it);" in open_js, "openTrip 没挂第四页同步"
    close_js = auth.get("/tesla/static/js/view/trips-sheet-close.js?v=14").text
    assert "gtrDetach();" in close_js, "hideSheet 没摘第四页"
    stream_js = auth.get("/tesla/static/js/view/group-trips-stream.js?v=5").text
    for frag in ["const GTR_PAGE = 24",
                 "before=${gtrStream[0].id}&limit=${GTR_PAGE}",
                 "after=${gtrStream[gtrStream.length - 1].id}&limit=${GTR_PAGE}",
                 "sc.scrollTop += sc.scrollHeight - h0;",   # prepend 视口钉原首行
                 "d.items.concat(gtrStream)", "gtrStream.concat(d.items)",
                 "has_more_before", "has_more_after",
                 "new IntersectionObserver", 'rootMargin: PRELOAD_PX + "px"',
                 'class="pick"',   # 右上选圈: 进入即多选态 (行程列表多选同位)
                 "let gtrSel = new Set();",   # 钩集 (组内全部起钩), marks 侧增删
                 "function gtrResetSel()",
                 "gtrStream.filter(x => x.in_group).map(x => x.id)",
                 "function gtrRefreshRows()",
                 "el.replaceWith(gtrRow(it))", "function gtrStart(gid)",
                 'bindGestures($("#gtr-scroll"), { drawer: false, ptr: true,',
                 "onRefresh: () => gtrLoadBefore()",   # 流文件后加载: 箭头延迟解析
                 "gtrMarquee()"]:
        assert frag in stream_js, f"group-trips-stream.js 缺少 {frag}"
    marks_js = auth.get("/tesla/static/js/view/group-trips-marks.js?v=4").text
    for frag in ["function gtrKeptEnds(orig)",   # 原组保留钩的端点 (判中段)
                 # 点行 = 打/撤钩 (整行都是点击目标, 与全 app 列表行同一习惯;
                 # 只有钮可点被用户报「item 点不了」)
                 "gtrSel.has(it.id)", "gtrSel.delete(it.id)", "gtrSel.add(it.id)",
                 "gtrKeptEnds(orig)",
                 'toast("只能移出最前或最后的行程")',   # 组内中段撤钩: 断连续
                 # 确定: 钩集与原组的差整批提交; 成功钩集复位对齐真身
                 "/tesla/trips/api/groups/${gtrGid}/changes", "{ adds, removes }",
                 "!adds.length && !removes.length",   # 无改动点了 no-op
                 "已保存分组修改", "inNew.has(x.id)", "gtrResetSel();",
                 "gtrLoad();"]:   # 服务端拒了整页重拉对齐真身 (钩集随重拉复位)
        assert frag in marks_js, f"group-trips-marks.js 缺少 {frag}"
    # 选圈样式 (行程列表多选同款几何) + 未选降透明 + 整行可点按压反馈
    gtr_css = auth.get("/tesla/static/css/tesla-group-trips.css?v=6").text
    assert ".gtr-row .pick {" in gtr_css and ".gtr-row.in .pick::after" in gtr_css
    assert ".gtr-row:not(.in)" in gtr_css
    assert ".gtr-row { cursor: pointer;" in gtr_css and ".gtr-row:active" in gtr_css
    # gid 载荷链: openMerged 只在分组页打开时带 gid (第四页随它挂上)
    merged_js = auth.get("/tesla/static/js/view/trips-sheet-page.js?v=10").text
    assert "gid: info && info.id != null ? info.id : null" in merged_js
