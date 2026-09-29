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
                 '<script src="/tesla/static/js/view/groups-page.js?v=7"></script>',
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
    js = auth.get("/tesla/static/js/view/groups-page.js?v=7").text
    for frag in ['"/tesla/trips/api/groups"', "function rowHTML(",
                 "async function gpLoad()",
                 'sheetFrom = "groups"',
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
    assert "css/tesla-groups.css?v=9" in html   # v9: sec-head 顶距 0 (v8 落后一版)
