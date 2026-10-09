"""Tesla 全页截图射手: 16 个视图各一张, iPhone 视口 (内容区 393x764) dsf=2。

用法: /tmp/pw-verify/bin/python shots/shoot.py [名字过滤词]
依赖: 种子服务器已起 (shots/seed_server.py, 默认 127.0.0.1:8901)。
环境: SHOT_BASE 服务地址 (默认 http://127.0.0.1:8901)
      SHOT_PAGES 原图输出目录 (默认 ~/shotlab/pages)
      SHOT_TRIP_ID 行程弹层的行程 id (默认 972 = 惠州西湖→家 100.6km 跨城
      长途; 过滤词 sheet 只拍行程弹层)
2026-10-08 视口 798→764: 底部留 34px (iOS 安全区), 合成时由页面底行
拉伸补齐 —— 应用自己的底部控件抬出屏幕圆角 (官方 bezel 圆角 75px, 控件
贴底会进角)。
开场动画一律等收完 (用户点名「有动画就截动画完成的一帧」): settle() 等
document.getAnimations 清零 (一次性 CSS transition 结束即自摘), 循环动画
(转圈/呼吸) 等不到就 4s 超时放行, 再加固定缓冲。足迹地图的首开回放与
行程弹层的轨迹回放是两个特例 —— 不是等它放完, 是手动定格到终帧
(见 tesla_map / tesla_trip)。"""
import asyncio
import json
import os
import sys

os.environ.setdefault(
    "LD_LIBRARY_PATH", "/home/admin/pwlibs/extracted/usr/lib/x86_64-linux-gnu")
from playwright.async_api import async_playwright  # noqa: E402

BASE = os.environ.get("SHOT_BASE", "http://127.0.0.1:8901")
OUT = os.environ.get("SHOT_PAGES",
                    os.path.expanduser("~/shotlab/pages"))
TRIP_ID = os.environ.get("SHOT_TRIP_ID", "972")
os.makedirs(OUT, exist_ok=True)

VIEWPORT = {"width": 393, "height": 764}   # 852-54 状态栏-34 底部安全区
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 "
      "Safari/604.1")


async def ctx_new(browser, last_view):
    """独立 context + 预置上次停留视图 —— 壳冷启按 localStorage 恢复视图,
    每个 key 一份干净 localStorage (地图的首开回放也靠这个每次触发)。"""
    ctx = await browser.new_context(
        viewport=VIEWPORT, device_scale_factor=2, is_mobile=True,
        has_touch=True, user_agent=UA, locale="zh-CN",
        timezone_id="Asia/Shanghai")
    await ctx.add_init_script(
        f"try{{localStorage.setItem('tesla.lastView','{last_view}')}}catch(e){{}}")
    return ctx


async def login(ctx, user="admin", password="shot-pass-123"):
    r = await ctx.request.post(
        BASE + "/api/login",
        data=json.dumps({"user": user, "password": password}),
        headers={"Content-Type": "application/json"})
    assert r.ok, f"登录失败 {r.status} {await r.text()}"


async def settle(page, ms=1200):
    """开场动画收尾: 等动画清零 (一次性 transition 完成即自摘), 循环动画
    等不到就超时放行, 再加固定缓冲让末帧布局/贴图落定。"""
    try:
        await page.wait_for_function(
            "() => document.getAnimations().length === 0", timeout=4000)
    except Exception:                                  # noqa: BLE001
        pass                                           # 循环动画常驻, 尽力而为
    await page.wait_for_timeout(ms)


async def shoot_view(browser, key, ready_js, last_ms=1200):
    """通用射手: 登录 → 壳冷启恢复到 key 视图 → 等数据锚点 → settle → 截图。"""
    page = await (await ctx_new(browser, key)).new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    await login(page.context)
    await page.goto(BASE + "/tesla", wait_until="domcontentloaded")
    await page.wait_for_selector(f"#view-{key}:not([hidden])", timeout=30000)
    await page.wait_for_function(ready_js, timeout=60000)
    await settle(page, last_ms)
    await page.screenshot(path=f"{OUT}/tesla-{key}.png")
    if errors:
        print(f"  [{key}] console errors: {errors[:5]}", flush=True)
    print(f"  tesla-{key} done", flush=True)


# 各视图数据就绪锚点 (等真实数据渲染完, 不是骨架出现):
#   live        booting 占位收起 + 速度格有值
#   trips       列表首批卡片落 DOM
#   tripstats   顶部里程累计 = 服务端汇总 (非空)
#   groups      分组卡落 DOM
#   charging    瀑布流首批卡
#   stats       顶部电量累计
#   battery     加载占位收起
#   chargemap   加载占位收起 (热力点坐标在种子库里)
#   settings-*  表单回显到位 (账号名 / TeslaMate host / Key 掩码 / 驾驶员行 / 地点行)
#   changelog   版本卡落 DOM
READY = {
    "live": "document.querySelector('#live') "
            "&& !document.querySelector('#live').hidden "
            "&& document.querySelector('#lv-speed').textContent.trim() !== ''",
    "trips": "document.querySelectorAll('#list > *').length >= 5",
    "tripstats": "document.querySelector('#ts-km-total')"
                 ".textContent.trim() !== ''",
    "groups": "document.querySelectorAll('#gp-list .gp-item').length > 0",
    "charging": "document.querySelectorAll('#chg-masonry > *').length > 0",
    "stats": "document.querySelector('#mkwh-total').textContent.trim() !== ''",
    "battery": "document.querySelector('#bh-loader').hidden === true",
    "chargemap": "document.querySelector('#cm-loading').hidden === true",
    "settings-account": "document.querySelector('#acct-name')"
                        ".textContent.trim() !== ''",
    "settings-db": "document.querySelector('#tm-host').value !== ''",
    "settings-map": "(document.querySelector('#amap-key')"
                    ".placeholder || '').includes('****')",
    "settings-drivers": "document.querySelectorAll('#drv-list .drv-item')"
                        ".length >= 2",
    "settings-places": "document.querySelectorAll('#plc-list .plc-item')"
                       ".length > 0 && document.querySelector('#plc-loading')"
                       ".hidden",
    "changelog": "document.querySelectorAll('#cl-list > *').length > 0 "
                 "&& document.querySelector('#loading').hidden",
}
# 各视图收尾缓冲 (地图/图表类要等贴图和 canvas 动画); live 是驾驶态地图
# (LIVE_DRIVE=1 起服): 蓝点 + 速度色轨迹 + 瓦片, 与行程弹层同款缓冲
EXTRA = {"charging": 3000, "chargemap": 2500, "tripstats": 2000,
         "stats": 2000, "battery": 1500, "live": 3500}


async def tesla_map(browser):
    """足迹地图: 首开自动回放, 手动定格最后一帧 (2026-10-08 用户点名
    「手动结束动画播放, 在最后一帧截图」)。headless 里 >1s 的帧间隔会触发
    走带自动暂停, 「等自然放完」不可靠 (上轮只铺出 9 条); 改为: 暂停后把
    进度杆拖到 1000 → fpPlaySeek 整段分帧重铺全部 986 条 (80/帧), 镜头一步
    落全网框, 顶部两格累计 = 服务端汇总 —— 浮标计数 n/n 即重铺完成的信号。
    暂停要按钮状态来: 已被自动暂停时再点一下会变续播 (change 就带
    autoplay 把收场暗铺又招来了), 只有图标是 pause (在放) 才点。"""
    page = await (await ctx_new(browser, "map")).new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    await login(page.context)
    await page.goto(BASE + "/tesla", wait_until="domcontentloaded")
    await page.wait_for_selector("#view-map canvas", timeout=30000)
    await page.wait_for_function("fpPlaying", timeout=120000)
    await page.evaluate("""() => {
        const btn = document.querySelector('#fp-play');
        if (btn.dataset.ic === 'pause') btn.click();
    }""")
    await page.wait_for_function(
        "() => document.querySelector('#fp-play').dataset.ic === 'play'",
        timeout=10000)
    await page.evaluate("""() => {
        const bar = document.querySelector('#fp-seek');
        bar.value = '1000';
        bar.dispatchEvent(new Event('change'));
    }""")
    await page.wait_for_function(
        "() => { const m = document.querySelector('#fp-play-date')"
        ".textContent.match(/(\\d+) \\/ (\\d+)$/);"
        " return m && m[1] === m[2] && +m[1] > 0; }", timeout=60000)
    # 终帧定格后手动收场: 相机已被拖杆一步落定全网框 (z<15 不裁视野),
    # 此刻 fpPlayExit(true) 的兜底暗铺拿到的 roadsById 是全部 986 条 ——
    # 整版重铺、镜头不动、图例亮回、统计还原服务端汇总 (19,878.6km)。
    await page.evaluate("fpPlayExit(true)")
    await page.wait_for_function("!fpPlaying && !tracksRendering", timeout=60000)
    await page.wait_for_timeout(2500)          # 换装亮回一帧 + 落定
    km = await page.locator("#st-km").text_content()
    drv_hidden = await page.locator("#fp-drv").is_hidden()
    print(f"  st-km={km!r} driver-chip hidden={drv_hidden}", flush=True)
    await page.screenshot(path=f"{OUT}/tesla-map.png")
    if errors:
        print(f"  [map] console errors: {errors[:5]}", flush=True)
    print("  tesla-map done", flush=True)


async def tesla_trip(browser):
    """单个行程弹层 (2026-10-09 用户点名「截图还差单个行程的界面」): 深链
    ?view=trips&id= 直开 (壳冷启消费参数, 列表照常后台拉), 等数字带落值、
    预载完起播 (anim), 再 skipAnim() 一键定格终帧 —— 全程亮线 + 镜头一步
    拉远全轨框, 播放条播完自收; 与足迹地图同款「截最后一帧」口径。"""
    page = await (await ctx_new(browser, "trips")).new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    await login(page.context)
    await page.goto(f"{BASE}/tesla?view=trips&id={TRIP_ID}",
                    wait_until="domcontentloaded")
    await page.wait_for_selector("#sheet.show", timeout=30000)
    await page.wait_for_function(
        "document.querySelector('#sh-km').textContent.trim() !== ''",
        timeout=60000)
    await page.wait_for_function("!!anim", timeout=120000)  # 预载完起播
    await page.evaluate("skipAnim()")
    # finish() 是「停表+拉远, 控制条留着」: anim 不归零 (那是关弹层的
    # stopAnim), 置 anim.finished; 定格 = 全量速度线 + 镜头拉远全轨框 +
    # 播放条转重播态 (进度 100%) —— 弹层打开的默认观感
    await page.wait_for_function("anim && anim.finished", timeout=60000)
    await settle(page, 3500)          # 拉远全局后新档位瓦片落定
    km = await page.locator("#sh-km").text_content()
    kwh = await page.locator("#sh-kwh").text_content()
    print(f"  sh-km={km!r} sh-kwh={kwh!r}", flush=True)
    await page.screenshot(path=f"{OUT}/tesla-trip.png")
    if errors:
        print(f"  [trip] console errors: {errors[:5]}", flush=True)
    print("  tesla-trip done", flush=True)


async def main():
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            args=["--autoplay-policy=no-user-gesture-required"])
        if not only or "map" in only:
            print("shooting tesla-map...", flush=True)
            try:
                await tesla_map(browser)
            except Exception as exc:                   # noqa: BLE001
                print(f"  !! tesla-map FAILED: {exc}", flush=True)
        if not only or "sheet" in only:
            print("shooting tesla-trip...", flush=True)
            try:
                await tesla_trip(browser)
            except Exception as exc:                   # noqa: BLE001
                print(f"  !! tesla-trip FAILED: {exc}", flush=True)
        for key, ready_js in READY.items():
            if only and only not in key:
                continue
            print(f"shooting tesla-{key}...", flush=True)
            try:
                await shoot_view(browser, key, ready_js,
                                 EXTRA.get(key, 1200))
            except Exception as exc:                   # noqa: BLE001
                print(f"  !! tesla-{key} FAILED: {exc}", flush=True)
        await browser.close()
    print("ALL DONE", flush=True)


asyncio.run(main())
