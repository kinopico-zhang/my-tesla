// trips-export-video.js — 播放 (12/13): 导出视频 —— 地图各画布逐帧合成到
// 录制画布, captureStream + MediaRecorder (mp4 优先), 从头整段重播, 播完
// 自动收片; 存储分平台 (苹果触屏走分享单, 其余直接落盘)。
// 由 trips.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 trips.html
// 里的顺序加载, 跨模块引用走全局); 录制状态 rec 在 trips-playback-bar.js
// (播放条那边提前绑好的钩子要读它)。
/* global $, toast, anim, rec: writable, pbRec */
/* exported stopRecExport */
"use strict";
/* ---------- 导出视频: 播放地图录成视频存相册 ---------- */
/* 链路: 逐帧把地图各画布与可视区的相交子矩形合成到录制画布 →
   captureStream(30) + MediaRecorder (mp4 优先) → 从头整段重播, 播完自动
   收片 → 预览弹层。存储分平台: 苹果触屏设备网页没有直写相册的 API,
   只能拉系统分享单点一下「存储视频」(最短路径, 面板免不了); 其他平台
   (安卓/桌面) <a download> 直接落盘进相册/下载夹, 不弹任何面板。
   播放条等覆盖层是 DOM, 不入镜 —— 视频里只有地图本体。 */
let recFile = null, recURL = null;   // 上次成片 (分享用 / 预览 src 用)

// 苹果触屏设备 (iPhone/iPad): iPadOS 13+ 的 Safari 装成 Mac, 触点数补判
const IS_APPLE_TOUCH = /iphone|ipad|ipod/i.test(navigator.userAgent)
  || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

function recMime() {    // Safari 与新版 Chrome 都能直出 mp4, 老内核退 webm
  for (const t of ["video/mp4;codecs=avc1", "video/mp4", "video/webm;codecs=vp9", "video/webm"])
    if (window.MediaRecorder && MediaRecorder.isTypeSupported(t)) return t;
  return "";
}

function recCompose() {    // 每帧合成: 环形容器比可视区大, 各画布取相交子
  const wrap = document.querySelector(".trip-map-wrap");   // 矩形映射过来 (dbg90 教训: 目的原点要先减可视区原点)
  if (!wrap || !rec) return;
  const wr = wrap.getBoundingClientRect();
  const { ctx, out } = rec;
  ctx.fillStyle = "#0b0d10";
  ctx.fillRect(0, 0, out.width, out.height);
  for (const c of wrap.querySelectorAll("canvas")) {
    if (!c.width || !c.height) continue;
    const r = c.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const kx = c.width / r.width, ky = c.height / r.height;
    const wx0 = (wr.left - r.left) * kx, wy0 = (wr.top - r.top) * ky;   // 可视区原点 (画布坐标)
    const sx0 = Math.max(0, wx0), sy0 = Math.max(0, wy0);
    const sx1 = Math.min(c.width, wx0 + wr.width * kx);
    const sy1 = Math.min(c.height, wy0 + wr.height * ky);
    if (sx1 <= sx0 || sy1 <= sy0) continue;
    ctx.drawImage(c, sx0, sy0, sx1 - sx0, sy1 - sy0,
      (sx0 - wx0) / (wr.width * kx) * out.width,
      (sy0 - wy0) / (wr.height * ky) * out.height,
      (sx1 - sx0) / (wr.width * kx) * out.width,
      (sy1 - sy0) / (wr.height * ky) * out.height);
  }
  rec.raf = requestAnimationFrame(recCompose);
}

function startRecExport() {
  if (!anim) { toast("轨迹还没开始播放"); return; }
  const mime = recMime();
  if (!mime || !HTMLCanvasElement.prototype.captureStream) { toast("此浏览器不支持录制视频"); return; }
  const wr = document.querySelector(".trip-map-wrap").getBoundingClientRect();
  const k = Math.min(devicePixelRatio || 1, 2);   // dpr 3 的手机也只录 2 倍: 够清晰省码率
  const out = document.createElement("canvas");
  out.width = Math.round(wr.width * k); out.height = Math.round(wr.height * k);
  rec = { out, ctx: out.getContext("2d"), chunks: [], mime, raf: 0, mr: null,
          name: "MyTesla轨迹-" + $("#sh-date").textContent.trim() };
  try {
    rec.mr = new MediaRecorder(out.captureStream(30), { mimeType: mime, videoBitsPerSecond: 6e6 });
  } catch {
    rec = null; toast("此浏览器不支持录制视频"); return;
  }
  const r = rec;   // ondataavailable 回调里 rec 可能已被清空, 捕获本体
  r.mr.ondataavailable = e => { if (e.data && e.data.size) r.chunks.push(e.data); };
  r.mr.start(500);
  pbRec.classList.add("rec");
  recCompose();
  toast("开始录制, 播完自动生成");
  anim.restart();     // 整段从头重播 (倍速沿用当前档)
}

function stopRecExport(cancel) {
  const r = rec;
  if (!r) return;
  rec = null;
  cancelAnimationFrame(r.raf);
  pbRec.classList.remove("rec");
  if (!r.mr || r.mr.state === "inactive") return;
  r.mr.onstop = () => { if (!cancel) recShowResult(r); };
  r.mr.stop();
}

function recShowResult(r) {
  const blob = new Blob(r.chunks, { type: r.mime });
  if (blob.size < 8192) { toast("录制失败 (没有内容)"); return; }   // 全黑/没帧
  const ext = r.mime.includes("mp4") ? "mp4" : "webm";
  recFile = new File([blob], r.name + "." + ext, { type: r.mime });
  if (recURL) URL.revokeObjectURL(recURL);
  recURL = URL.createObjectURL(blob);
  $("#rec-video").src = recURL;
  // 存储按钮: 录完一定给 (2026-09-13 二连修: 先按 canShare 门控藏了按钮 ——
  // iOS Safari 没实现 canShare; 改按 share 存在性仍藏 —— share 是 secure
  // context 限定, HTTP 部署里同样不存在)。按钮文案: 有 share = 「存到相册」
  // (苹果设备经分享单、其余平台直落); 没有 = 「保存视频」(下载到「文件」App)。
  const shareOK = typeof navigator.share === "function";
  $("#rec-save").hidden = false;
  $("#rec-save").textContent = shareOK ? "存到相册" : "保存视频";
  $("#rec-modal").hidden = false;
}

function recCloseModal() {
  $("#rec-modal").hidden = true;
  $("#rec-video").removeAttribute("src");
  $("#rec-video").load();    // 释放解码资源 (iOS 上 blob 视频挂着会占内存)
  if (recURL) { URL.revokeObjectURL(recURL); recURL = null; }
  recFile = null;
}

pbRec.addEventListener("click", () => {
  if (rec) { stopRecExport(true); toast("已取消录制"); }
  else startRecExport();
});
function saveVideoFile() {   // 下载兜底: iOS 存「文件」App (经共享再入相册), 桌面浏览器直接落盘
  const a = document.createElement("a");
  a.href = recURL; a.download = recFile.name;
  document.body.appendChild(a); a.click(); a.remove();
}

$("#rec-save").addEventListener("click", async () => {
  if (!recFile) return;
  // 苹果触屏: 只有系统分享单这一条入相册的路 (点「存储视频」);
  // 其余平台: 直接下载落盘, 不弹面板 —— 安卓的下载视频会进相册。
  if (!IS_APPLE_TOUCH || typeof navigator.share !== "function") {
    saveVideoFile();
    toast(/android/i.test(navigator.userAgent) ? "已保存到相册" : "视频已保存");
    return;
  }
  try { await navigator.share({ files: [recFile], title: recFile.name }); }
  catch (e) { if (e.name !== "AbortError") saveVideoFile(); }   // 分享失败 (如不支持文件) 也别让视频白录
});
$("#rec-close").addEventListener("click", recCloseModal);
$("#rec-modal").addEventListener("click", e => { if (e.target.id === "rec-modal") recCloseModal(); });
