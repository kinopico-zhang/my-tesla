// 前端类型补充声明 (tsc --checkJs 用, 见 tsconfig.json)
// iOS Safari 专有: 主屏全屏 App 里 navigator.standalone === true
// (lib.dom 没有收录, lastpage.js 靠它区分主屏 App 与 Safari 页内访问)
interface Navigator {
  readonly standalone?: boolean;
}

// UMD 挂载点: 浏览器侧 window.GCJ02 / window.TrackUtil (node 测试侧走
// module.exports, 由 import 直接拿到推断类型 —— 这里只补 Window 声明,
// 让 checkJs 过 UMD 边界那一行)
interface Window {
  GCJ02: object;
  TrackUtil: object;
  FormatUtil: object;     // format.js (三页共用格式化)
  TripPlayback: object;   // trip-playback.js (行程播放纯逻辑)
}

// trip-playback.js 的 UMD 头在 node 分支 require("./trackutil.js"):
// types:[] 排除了 @types/node, 这里补 require 的最小声明 (any 即可,
// 精确类型走工厂内 import() 断言拿到)
declare function require(moduleId: string): any;
