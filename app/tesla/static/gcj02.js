/* WGS-84 → GCJ-02 坐标转换 (火星坐标)。
   TeslaMate 记录的是 GPS 原始坐标 (WGS-84), 高德地图使用 GCJ-02,
   不转换会整体偏移几百米。国测局算法为公开近似式, 精度 ~1-2m。
   UMD 包装: 浏览器挂 window.GCJ02, node (测试) 走 module.exports。 */
/* UMD 挂载层: node (测试 require) 与浏览器 (生产 <script> 加载) 二选一。
   浏览器分支在 node 覆盖率里天然统计不到 (require 时 module 一定存在),
   c8 标记忽略; 挂载行为由 *_test 的 eval 桩用例验证。 */
/* c8 ignore start */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.GCJ02 = factory();
})(/** @type {Window | Record<string, unknown>} */(typeof self !== "undefined" ? self : this), function () {
/* c8 ignore stop */
  "use strict";
  const PI = 3.14159265358979324;
  const A = 6378245.0;            // 长半轴
  const EE = 0.00669342162296594323;  // 偏心率平方

  function outOfChina(lng, lat) {
    return !(lng > 73.66 && lng < 135.05 && lat > 3.86 && lat < 53.55);
  }

  function transformLat(x, y) {
    let ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y
              + 0.2 * Math.sqrt(Math.abs(x));
    ret += (20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0 / 3.0;
    ret += (20.0 * Math.sin(y * PI) + 40.0 * Math.sin(y / 3.0 * PI)) * 2.0 / 3.0;
    ret += (160.0 * Math.sin(y / 12.0 * PI) + 320.0 * Math.sin(y * PI / 30.0)) * 2.0 / 3.0;
    return ret;
  }

  function transformLng(x, y) {
    let ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y
              + 0.1 * Math.sqrt(Math.abs(x));
    ret += (20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0 / 3.0;
    ret += (20.0 * Math.sin(x * PI) + 40.0 * Math.sin(x / 3.0 * PI)) * 2.0 / 3.0;
    ret += (150.0 * Math.sin(x / 12.0 * PI) + 300.0 * Math.sin(x / 30.0 * PI)) * 2.0 / 3.0;
    return ret;
  }

  function delta(lng, lat) {
    let dLat = transformLat(lng - 105.0, lat - 35.0);
    let dLng = transformLng(lng - 105.0, lat - 35.0);
    const radLat = lat / 180.0 * PI;
    let magic = Math.sin(radLat);
    magic = 1 - EE * magic * magic;
    const sqrtMagic = Math.sqrt(magic);
    dLat = (dLat * 180.0) / ((A * (1 - EE)) / (magic * sqrtMagic) * PI);
    dLng = (dLng * 180.0) / (A / sqrtMagic * Math.cos(radLat) * PI);
    return [dLng, dLat];
  }

  function wgs84ToGcj02(lng, lat) {
    if (outOfChina(lng, lat)) return [lng, lat];
    const d = delta(lng, lat);
    return [lng + d[0], lat + d[1]];
  }

  // 近似逆变换 (误差 < 1m, 足够展示用途)
  function gcj02ToWgs84(lng, lat) {
    if (outOfChina(lng, lat)) return [lng, lat];
    const d = delta(lng, lat);
    return [lng - d[0], lat - d[1]];
  }

  return { outOfChina: outOfChina, wgs84ToGcj02: wgs84ToGcj02, gcj02ToWgs84: gcj02ToWgs84 };
});
