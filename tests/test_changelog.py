"""更新日志页测试: 人工维护的版本数据 (合并批次, 用户视角) + 条目接口 + 页面骨架 + 入口。

版本号 x.y.z —— x 大改版, y 新功能, z 问题修复; 一个版本 = 一批改动的合并
(可以同时含新增/改进/修复), 不逐提交记版本。条目按新→老输出。
"""
from app import changelog

PAGES = ["/tesla/charging", "/tesla/stats", "/tesla/chargemap", "/tesla/map",
         "/tesla/trips", "/tesla/groups", "/tesla/live", "/tesla/settings",
         "/tesla/changelog"]


# ---------------------------------------------------------------- 数据
def test_versions_newest_first_and_wellformed():
    """新→老; 每版字段齐全, 文案是用户视角的一句话 (不夹技术黑话)。"""
    vs = changelog.entries()
    assert [v.version for v in vs] == [
        "2.6.0", "2.5.1", "2.5.0", "2.4.0", "2.3.0", "2.2.0", "2.1.0",
        "2.0.0", "1.1.0", "1.0.0"]
    assert vs[0].date == "2026-09-15" and vs[-1].date == "2026-09-08"
    for v in vs:
        assert v.items                                  # 每版至少一条
        assert len(v.date) == 10 and v.date[4] == "-"   # YYYY-MM-DD
        for it in v.items:
            assert it.kind in ("新增", "改进", "修复")
            assert len(it.text) >= 4                    # 不是光秃秃的词
            # 站在用户视角: 不夹接口路径 / 链接等技术黑话
            assert "api/" not in it.text and "http" not in it.text
    # 合并批次的立意: 三类合在一起发, 不再一个提交一版 (单功能的小批次
    # 可以只有一类 —— 2.6.0 只有菜单显示账号这一件事, 硬凑修复反而失真)
    kinds = {it.kind for it in vs[0].items}
    assert kinds <= {"新增", "改进", "修复"}


# ---------------------------------------------------------------- 接口
def test_changelog_entries_endpoint(auth):
    """条目接口原样吐数据 (新→老), 字段形状与前端渲染对齐。"""
    es = auth.get("/tesla/changelog/api/entries").json()
    assert [e["version"] for e in es] == [v.version for v in changelog.entries()]
    for e, v in zip(es, changelog.entries()):
        assert e["date"] == v.date
        assert e["items"] == [{"kind": it.kind, "text": it.text}
                              for it in v.items]
    assert es[0]["items"][0]["kind"] == "新增"


# ---------------------------------------------------------------- 页面
def test_changelog_page_skeleton(auth):
    """更新日志页: 版本块 (徽标/日期 + 逐条改动行, 类型胶囊)。"""
    html = auth.get("/tesla/changelog").text
    # 类型胶囊的样式拆去了 css/tesla-changelog.css (结构化重构), 拼进来查
    html += auth.get("/tesla/static/css/tesla-changelog.css?v=1").text
    html += auth.get("/static/changelog-page.js?v=1").text
    for frag in [
        "<title>更新日志 · My Tesla</title>",
        '<a class="on" href="/tesla/changelog">更新日志</a>',   # 菜单 (自身亮)
        'id="brand-menu"', 'id="logout"',
        'id="entries"', 'id="list"', 'id="loading"', 'id="error"', 'id="retry"',
        '"/tesla/changelog/api/entries"',                       # 数据源
        'class="v-badge"', 'class="v-head"', 'class="v-date"',  # 版本头
        '<ul class="v-items">', 'class="t"',                    # 改动清单
        '.k-add', '.k-imp', '.k-fix',                           # 类型胶囊 (蓝/橙/绿)
        'const KIND_CLS = { "新增": "add", "改进": "imp", "修复": "fix" };',
        "更新日志 · My Tesla",
    ]:
        assert frag in html, f"更新日志页缺少 {frag}"
    assert 'class="rule"' not in html   # 版本号规则说明行已按用户要求撤掉


def test_changelog_link_in_settings(auth):
    """软件设置页'关于'卡里有更新日志入口。"""
    assert '<a class="about-link" href="/tesla/changelog">更新日志' \
        in auth.get("/tesla/settings").text


def test_changelog_link_in_all_nav_menus(auth):
    """每个业务页的页签菜单都有更新日志入口 (含 on 态: 更新日志页自身)。"""
    for path in PAGES:
        assert 'href="/tesla/changelog">更新日志</a>' \
            in auth.get(path).text, path


def test_changelog_in_lastpage_and_login_whitelist(auth):
    """上次停留页/登录回跳白名单收录 (子页可停留, 直链可回跳)。"""
    lastpage = auth.get("/tesla/static/js/lastpage.js?v=1").text
    assert '"/tesla/settings", "/tesla/changelog"]' in lastpage
    login_js = auth.get("/static/login.js?v=1").text
    assert "live|settings|changelog)" in login_js


def test_music_items_moved_out_of_tesla_changelog():
    """My Music 的批次拆去听歌应用自己的日志, 这里不再出现。"""
    texts = " ".join(it.text for v in changelog.entries() for it in v.items)
    assert "My Music" not in texts
    assert "听歌" not in texts
    assert "歌词" not in texts
