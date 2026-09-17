"""充电费用编辑测试: 越界拒绝, 修改入库, 清空, 两位小数; 费用
红显与图表接线。
拆自 test_charging.py (结构化重构, 代码逐字节未动)。"""

from app.tesla.models import ChargingProcess
from tests.seed_factories import seed_addresses, seed_charging
from tests.charging_page_scripts import CHARGING_ASSETS, _page_scripts

# ---------------------------------------------------------------- 费用编辑
def test_cost_patch_rejects_out_of_range(auth):
    for bad in (-1, 100001):
        r = auth.patch("/tesla/charging/api/sessions/1/cost", json={"cost": bad})
        assert r.status_code == 400, bad
        assert "金额" in r.json()["detail"]


def test_cost_patch_unknown_session(auth):
    r = auth.patch("/tesla/charging/api/sessions/99999/cost", json={"cost": 10})
    assert r.status_code == 404


def test_cost_patch_updates_db(auth, db):
    seed_addresses(db)
    seed_charging(db, id=332)      # used 48 kWh
    r = auth.patch("/tesla/charging/api/sessions/332/cost", json={"cost": 30})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["cost"] == 30.0
    assert d["price_per_kwh"] == round(30.0 / 48.0, 3)
    # 真实写库: 换个会话能看到 (金额四舍五入到 2 位)
    assert db.get(ChargingProcess, 332).cost == 30.0


def test_cost_patch_clear_with_null(auth, db):
    seed_addresses(db)
    seed_charging(db, id=332, cost=30.0)
    r = auth.patch("/tesla/charging/api/sessions/332/cost", json={"cost": None})
    assert r.status_code == 200
    assert r.json()["cost"] is None
    assert db.get(ChargingProcess, 332).cost is None


def test_cost_patch_rounds_to_two_decimals(auth, db):
    seed_addresses(db)
    seed_charging(db, id=332)
    r = auth.patch("/tesla/charging/api/sessions/332/cost",
                   json={"cost": 30.456})
    assert r.status_code == 200
    assert db.get(ChargingProcess, 332).cost == 30.46


def test_charging_page_single_column_and_lazy_chain(auth):
    """充电列表单列 (手机优先, 对齐行程页) + Chrome 懒加载修复 (装载后链式续载)。"""
    html = auth.get("/tesla/charging").text
    html += _page_scripts(auth, *CHARGING_ASSETS)
    for frag in ['id="masonry"', "flex-direction: column", "PRELOAD_PX = 800",
                 'rootMargin: PRELOAD_PX + "px"',
                 "getBoundingClientRect().top < window.innerHeight + PRELOAD_PX",
                 "max-width: 760px"]:
        assert frag in html, f"充电页缺少 {frag}"
    # 多列瀑布流的列容器/列数逻辑已删
    assert "m-col" not in html and "colCount" not in html


def test_charging_page_unrecorded_cost_red(auth):
    """没记费用的充电记录红标醒目: 卡片红色"添加费用"胶囊 + 详情费用格红字。"""
    html = auth.get("/tesla/charging").text
    html += _page_scripts(auth, *CHARGING_ASSETS)
    for frag in [
        '<button class="cs-cost none" data-cost>＋ 添加费用</button>',
        ".cs-cost.none {", "background: #e5484d",   # 红色实心胶囊
        '未记费用',                                   # 详情格文案
        ".st-cost .val.red { color: #e5484d; }",     # 详情红字
        'cv.classList.toggle("red", cost == null)',  # 记完费用就地摘红
    ]:
        assert frag in html, f"充电页缺少 {frag}"


def test_charging_page_soc_axis_fixed_and_dense(auth):
    """SOC 轴固定 0-100% 量程: 标签按真实百分比定位 (贴边的 space-between 读起来像自适应);
    电量与费用并入一行, 收紧卡片纵向留白。"""
    html = auth.get("/tesla/charging").text
    html += _page_scripts(auth, *CHARGING_ASSETS)
    assert "soc-lbl" not in html                 # 贴边标签行已删
    assert 'class="sa-lb"' in html               # 轴标签钉在真实位置
    assert "Math.min(it.start_soc, 93)" in html  # 左标签左缘 = 充电起点
    assert "right:${100 - it.end_soc}%" in html  # 右标签右缘 = 终点
    assert 'class="cs-main"' in html             # 电量 + 费用同行


def test_charging_page_soc_labels_merge_on_short_charges(auth):
    """短充电 (起止差 < 15%) 两端标签钉真实百分比会叠字: 并成一个 "起 → 终"
    标签居中钉在轨迹中点, 中点钳 15~85% (标签再宽也不出卡)。"""
    html = auth.get("/tesla/charging").text
    html += _page_scripts(auth, *CHARGING_ASSETS)
    assert "it.end_soc - it.start_soc >= 15" in html   # 阈值: 起止差 ≥15% 仍钉两端
    assert "Math.min(Math.max((it.start_soc + it.end_soc) / 2, 15), 85)" in html
    assert "transform:translateX(-50%)" in html        # 合并标签按中心定位
    assert "${it.start_soc} → ${it.end_soc}%" in html
