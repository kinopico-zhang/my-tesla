"""iPhone 设备边框合成: 每页原图 → 官方 iPhone 17 Pro 银钛 bezel 设备图。

官方资源 (developer.apple.com/design/resources/ 的 Bezel-iPhone-17.dmg,
undmg.py 纯 python 解 UDIF 后 carve 出 PNG) 只含边框环 + 灵动岛, 屏幕区全
透明 —— 内容贴进开窗、官方 PNG 盖顶, 真岛自然浮于内容上方。时间/电池垂直
中心对齐官方岛心 (内容 CSS y=31.2); 左右留白 29.5/30px 是调好的墨迹对称值,
不动。开窗 1206×2622 @3x = 402×874pt; 内容 393×852 @2x 原生贴窗零重采样,
边框整体缩 ~0.65。

2026-10-08 三修 (四角白弧根除): 资产透明留白带的 RGB 是白的 (255,255,255,0),
直通 alpha 的 LANCZOS 缩放把这份白渗进半透明描边 → 白底上四角浮白弧。
改预乘缩放 (RGB 先 ×A, 缩完再除回, 边缘只吃真实像素的颜色); 洞形蒙版同轮
外扩 4px (MaxFilter), 内容伸进边框内唇的软过渡之下, 内缘亮线也一并压掉。
角出框的洞形蒙版 (对缩放后 bezel 的透明区从外部洪泛, 包不进来的透明区
= 屏幕洞) 贴内容, 方角内容永远出不了圆角开窗。
页高按 pages/*.png 实际尺寸自适应 (764 视口 + 34px 底条拉伸补齐安全区)。

用法: /tmp/pw-verify/bin/python shots/composite.py
环境: SHOTLAB 工作目录 (默认 /tmp/shotlab; 内含 bezel-png/010_1350x2760.png
      与 pages/*.png), 输出 LAB/final/。
依赖: icons 在本目录 assets/ (自制, 随仓); bezel PNG 是 Apple 官方资产
      不随仓 (公开仓不可再分发), 由 README 的下载 + undmg.py 步骤再生。"""
import base64
import os
import pathlib

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageMath
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
LAB = pathlib.Path(os.environ.get("SHOTLAB", "/tmp/shotlab"))
PAGES = LAB / "pages"
FINAL = LAB / "final"
FINAL.mkdir(exist_ok=True)

# 全部 tesla-*.png 逐一合成 (射手产多少合多少)
SHOTS = sorted(p.stem for p in PAGES.glob("tesla-*.png"))


def b64(p):
    return base64.b64encode(pathlib.Path(p).read_bytes()).decode()


ICONS = {n: b64(HERE / f"assets/icons/{n}.png") for n in ("status", "home")}


def topbar_b64(name):
    """页面顶 2 设备像素行 → 拉伸成 54 CSS px 的状态栏底色块 (无缝)。"""
    im = Image.open(PAGES / f"{name}.png").convert("RGB")
    row = im.crop((0, 0, im.width, 2)).resize((im.width, 108))
    out = LAB / "topbar"
    out.mkdir(exist_ok=True)
    f = out / f"{name}.png"
    row.save(f)
    return base64.b64encode(f.read_bytes()).decode()


def botbar_b64(name):
    """页面底 2 设备像素行 → 拉伸成底部安全区色块 (34 CSS px, 无缝)。"""
    im = Image.open(PAGES / f"{name}.png").convert("RGB")
    row = im.crop((0, im.height - 2, im.width, im.height)).resize((im.width, 68))
    out = LAB / "botbar"
    out.mkdir(exist_ok=True)
    f = out / f"{name}.png"
    row.save(f)
    return base64.b64encode(f.read_bytes()).decode()


HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
* {margin:0;padding:0;box-sizing:border-box}
body {background:transparent}
#phone {position:relative;width:393px;height:852px;
  background:#0e0e11;font-family:-apple-system,'SF Pro Text','PingFang SC','Noto Sans SC',sans-serif}
.statusbg {position:absolute;left:0;top:0;width:393px;height:54px}
.statusbg img {width:100%;height:100%;display:block}
.time {position:absolute;left:29.5px;top:0;height:62.4px;line-height:62.4px;
  font-size:17px;font-weight:600;color:#fff}
.sicons {position:absolute;right:30px;top:24.2px;width:80px;height:14px}
.sicons img {width:100%;height:100%;display:block}
.page {position:absolute;left:0;top:54px;width:393px;height:__H__px}
.page img {width:100%;height:100%;display:block}
.botbar {position:absolute;left:0;top:__BOT__px;width:393px;height:__BH__px}
.botbar img {width:100%;height:100%;display:block}
.homebar {position:absolute;left:102px;top:844px;width:189px;height:4.5px}
.homebar img {width:100%;height:100%;display:block}
</style></head><body>
<div id="phone">
  <div class="statusbg"><img src="data:image/png;base64,__TOPBAR__"></div>
  <div class="page"><img src="data:image/png;base64,__PAGE__"></div>
  __BOTBAR__
  <div class="time">19:26</div>
  <div class="sicons"><img src="data:image/png;base64,__STATUS__"></div>
  <div class="homebar"><img src="data:image/png;base64,__HOME__"></div>
</div>
</body></html>"""

# ---- 官方 bezel: 一次缩放, 全部页共用 ----
WIN = (72, 69, 1278, 2691)              # 开窗 @3x = 402×874pt (实测 flood-fill)
SCR_W, SCR_H = 786, 1704                # 内容 393×852 @2x, 原生贴窗
MARGIN = 24                             # 设备外透明留白 (设备 px)
fx = SCR_W / (WIN[2] - WIN[0])          # 0.6517
fy = SCR_H / (WIN[3] - WIN[1])          # 0.6499
BEZEL = pathlib.Path(os.environ.get(
    "SHOT_BEZEL", LAB / "bezel-png/010_1350x2760.png"))
bezel = Image.open(BEZEL).convert("RGBA")


# 预乘缩放 (PIL 12.3 无 ImageChops.divide, 除回走 ImageMath): 透明留白的
# RGB 是垃圾值 (角区纯白), 直通 alpha 缩放会把它渗进半透明描边
def pm_resize(im, size):
    r, g, b, a = im.split()
    pm = Image.merge("RGBA", (ImageChops.multiply(r, a),
                              ImageChops.multiply(g, a),
                              ImageChops.multiply(b, a), a))
    pm = pm.resize(size, Image.LANCZOS)
    r2, g2, b2, a2 = pm.split()

    def undiv(c):
        return ImageMath.unsafe_eval("convert((c * 255) / (a + 1), 'L')",
                                     c=c, a=a2)
    return Image.merge("RGBA", (undiv(r2), undiv(g2), undiv(b2), a2))


dev = pm_resize(bezel, (round(bezel.width * fx), round(bezel.height * fy)))
WX, WY = round(WIN[0] * fx), round(WIN[1] * fy)     # 47, 45

# ---- 洞形蒙版: 缩放后 bezel 的透明区从外部洪泛, 包住的 = 屏幕洞 ----
_a = dev.getchannel("A").point(lambda v: 255 if v < 8 else 0)
ImageDraw.floodfill(_a, (0, 0), 128, thresh=60)
HOLE = _a.point(lambda v: 255 if v == 255 else 0)
# 外扩 4px: 内容伸到边框内唇软过渡之下 (内缘亮线同轮压掉)
HOLE_CROP = HOLE.crop((WX, WY, WX + SCR_W, WY + SCR_H)) \
              .filter(ImageFilter.MaxFilter(9))


def build(screen):
    """屏幕内容 (786×1704) → 官方边框设备图 (RGBA)。"""
    canvas = Image.new("RGBA",
                       (dev.width + 2 * MARGIN, dev.height + 2 * MARGIN),
                       (0, 0, 0, 0))
    # 洞形蒙版贴内容: 官方开窗是圆角, 方角内容只落在洞内, 四角出不去
    canvas.paste(screen, (MARGIN + WX, MARGIN + WY), HOLE_CROP)
    canvas.alpha_composite(dev, (MARGIN, MARGIN))
    return canvas


with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 393, "height": 852},
                          device_scale_factor=2)
    for name in SHOTS:
        page_h = Image.open(PAGES / f"{name}.png").height // 2   # CSS px
        bot_h = 798 - page_h          # 底条 = 798-页高 (764 视口 → 34 安全区)
        botbar = (f'<div class="botbar"><img src="data:image/png;base64,'
                  f'{botbar_b64(name)}"></div>') if bot_h > 0 else ""
        html = (HTML.replace("__H__", str(page_h))
                    .replace("__BOT__", str(54 + page_h))
                    .replace("__BH__", str(bot_h))
                    .replace("__BOTBAR__", botbar)
                    .replace("__TOPBAR__", topbar_b64(name))
                    .replace("__PAGE__", b64(PAGES / f"{name}.png"))
                    .replace("__STATUS__", ICONS["status"])
                    .replace("__HOME__", ICONS["home"]))
        pg.set_content(html)
        pg.wait_for_function(
            "document.images.length && [...document.images]"
            ".every(i => i.complete && i.naturalWidth)")
        raw = LAB / "raw"
        raw.mkdir(exist_ok=True)
        pg.locator("#phone").screenshot(path=str(raw / f"{name}.png"),
                                        omit_background=True)
        screen = Image.open(raw / f"{name}.png").convert("RGBA")
        build(screen).save(FINAL / f"{name}.png")
        print("ok", name, f"(page {page_h} + bot {bot_h})", flush=True)
    browser.close()
