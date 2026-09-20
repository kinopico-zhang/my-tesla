"""更新日志视图测试: 人工维护的版本数据 (合并批次, 用户视角) + 条目接口 + 壳内视图骨架 + 入口。

版本号 x.y.z —— x 大改版, y 新功能, z 问题修复; 一个版本 = 一批改动的合并
(可以同时含新增/改进/修复), 不逐提交记版本。条目按新→老输出。
"""
from app import changelog
from tests.tesla_static_files import page_js, served_page

SHELL = "/tesla"


# ---------------------------------------------------------------- 数据
def test_versions_newest_first_and_wellformed():
    """新→老; 每版字段齐全, 文案是用户视角的一句话 (不夹技术黑话)。"""
    vs = changelog.entries()
    assert [v.version for v in vs] == [
        "3.0.1", "3.0.0", "2.6.0", "2.5.1", "2.5.0", "2.4.0", "2.3.0", "2.2.0",
        "2.1.0", "2.0.0", "1.1.0", "1.0.0"]
    assert vs[0].date == "2026-09-20" and vs[-1].date == "2026-09-08"
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
    # 头条是主打: 新功能或修的主 bug; 纯打磨的批次整版都是改进, 不硬凑
    # (3.0.1 是纯修足迹地图细化的批次, 头条就是修复)
    assert es[0]["items"][0]["kind"] in ("新增", "修复") \
        or {i["kind"] for i in es[0]["items"]} == {"改进"}


# ---------------------------------------------------------------- 视图
def test_changelog_view_skeleton(auth):
    """更新日志视图: 版本块 (徽标/日期 + 逐条改动行, 类型胶囊) + 失败重试。"""
    html = served_page(auth, SHELL)
    for frag in [
        'id="view-changelog"', 'data-view="changelog"',
        'id="entries"', 'id="cl-list"', 'id="loading"', 'id="error"',
        'id="cl-retry"',
        '"/tesla/changelog/api/entries"',                       # 数据源
        '<ul class="v-items">', 'class="t"',                    # 改动清单
        '.k-add', '.k-imp', '.k-fix',                           # 类型胶囊 (蓝/橙/绿)
        'const KIND_CLS = { "新增": "add", "改进": "imp", "修复": "fix" };',
    ]:
        assert frag in html, f"更新日志视图缺少 {frag}"
    assert 'class="rule"' not in html   # 版本号规则说明行已按用户要求撤掉


def test_changelog_link_in_drawer(auth):
    """更新日志入口: 壳的抽屉设置组 (3.0 唯一入口)。"""
    assert '{ key: "changelog", lb: "更新日志" }' in page_js(auth, SHELL)


def test_login_whitelist_keeps_old_links(auth):
    """登录回跳白名单仍收旧子页: 2.x 存的上次停留值 (localStorage 里可能
    还留着) 登录后跳旧路径, 302 落回壳对应视图, 不丢。"""
    login_js = auth.get("/static/login.js?v=1").text
    assert "live|settings|changelog)" in login_js


def test_music_items_moved_out_of_tesla_changelog():
    """My Music 的批次拆去听歌应用自己的日志, 这里不再出现。"""
    texts = " ".join(it.text for v in changelog.entries() for it in v.items)
    assert "My Music" not in texts
    assert "听歌" not in texts
    assert "歌词" not in texts
