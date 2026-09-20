// tesla-car-switcher — 抽屉车辆切换 (P1 后端已穿 car_id): /car 列表 →
// pills [全部 + 每台车]。用户定案: "全部"恒在且默认 (现口径, 全车合看);
// 单车用户显示静态车名行 (无从切); ≥2 台才出现 pills。切换 = 一次性整体
// 切换 (setCar → 订阅方 refreshCurrent, 当前视图整页按新车重拉)。
"use strict";
/* global $, esc, getJSON, shellState, setCar */
/* exported bootCarSwitcher */

function renderCars(cars) {
  const wrap = $("#drw-cars"), pills = $("#car-pills");
  if (!wrap || !pills) return;
  if (!cars.length) { wrap.hidden = true; return; }
  wrap.hidden = false;
  if (cars.length === 1) {   // 单车: 静态车名 (信息行, 不可切)
    pills.innerHTML = `<span class="car-pill on">${esc(cars[0].model)} · ${esc(cars[0].name)}</span>`;
    return;
  }
  pills.innerHTML =
    `<button type="button" class="car-pill${shellState.carId == null ? " on" : ""}" data-car="">全部</button>` +
    cars.map(c => `<button type="button" class="car-pill${shellState.carId === c.id ? " on" : ""}"
      data-car="${c.id}">${esc(c.model)} · ${esc(c.name)}</button>`).join("");
}

function bootCarSwitcher() {
  const pills = $("#car-pills");
  if (!pills) return;
  pills.addEventListener("click", e => {
    const b = e.target.closest("button.car-pill");
    if (!b) return;
    pills.querySelectorAll(".car-pill").forEach(p => p.classList.toggle("on", p === b));
    setCar(b.dataset.car === "" ? null : +b.dataset.car);
  });
  getJSON("/tesla/charging/api/car").then(renderCars)
    .catch(() => { const w = $("#drw-cars"); if (w) w.hidden = true; });   // 拉不到: 整行藏起
}
