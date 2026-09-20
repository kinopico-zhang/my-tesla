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
                 '<script src="/tesla/static/js/view/groups-page.js?v=1"></script>',
                 '在行程列表长按多选行程后点「存为分组」']:
        assert frag in html, f"分组视图缺少 {frag}"


def test_groups_page_interactions(auth):
    """分组视图脚本: 打开 = 内存跳行程视图合并播放 (零历史条目), 改名行内
    编辑, 删除二次确认。行内重渲染会脱链事件目标 —— 委托先判 isConnected
    (与行程页同一坑)。"""
    js = auth.get("/tesla/static/js/view/groups-page.js?v=1").text
    for frag in ['"/tesla/trips/api/groups"', "function rowHTML(",
                 "async function gpLoad()",
                 'navigate("trips")', "openMerged(item.dataset.ids)",
                 'classList.add("arm")', "确认删除",
                 'method: "DELETE"', 'method: "PATCH"',
                 'gp-list").addEventListener("click"',
                 'gp-list").addEventListener("keydown"',
                 "!t.isConnected", 'status === 401',
                 'class="gp-input"', 'maxlength="30"']:
        assert frag in js, f"groups-page.js 缺少 {frag}"
    # 改名/删除按钮有结果才动列表; Enter 提交 / Esc 放弃
    assert 'e.target.classList.contains("gp-input")' in js
    assert 'e.key === "Enter"' in js and 'e.key === "Escape"' in js
