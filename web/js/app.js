// Ecluna — one object at a time, three ways of looking at it.
//
// The page is a set of views rather than a document: the bar switches which view
// fills the stage, and the numbers live in a panel that opens on demand. Every
// value comes from web/data/, which is written by the measurement scripts.

import { setupCube } from "./cube.js";

const DATA = "data/";
const NAMES = {
  barnard: "Barnard's Star",
  epsindb: "Epsilon Indi B",
  wise0855: "WISE 0855",
  rwaur: "RW Aurigae",
  rdra: "R Draconis",
};
const BLINK_ID = { epsindb: "epsindib" };

const state = {
  views: null,
  blink: null,
  current: null,
  index: 0,
  timer: null,
  chart: null,
  cube: null,
};

async function loadJSON(name) {
  const response = await fetch(DATA + name, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${name}: ${response.status}`);
  return response.json();
}

const nameOf = (object) => NAMES[object.id] || object.name;

// ---------------------------------------------------------------- view switching

function setupViews() {
  const tabs = [...document.querySelectorAll(".view-tab")];
  const views = [...document.querySelectorAll(".view")];

  const show = (id) => {
    for (const tab of tabs) {
      tab.classList.toggle("is-active", tab.dataset.view === id);
    }
    for (const view of views) {
      const active = view.id === `view-${id}`;
      view.classList.toggle("is-active", active);
      view.hidden = !active;
    }
    // The chart and the box are drawn at a pixel size, so they are redrawn when
    // their view becomes visible rather than stretched from a hidden layout.
    if (id === "curve") drawCurve();
    if (id === "track") drawCube();
  };

  for (const tab of tabs) {
    tab.addEventListener("click", () => {
      show(tab.dataset.view);
      setNote(tab.dataset.view);
      // The view is in the address so a link can point at one of them.
      history.replaceState(null, "", `#${tab.dataset.view}`);
    });
  }

  const notes = {
    blink: "Each frame is one SPHEREx visit of the same patch, aligned onto one grid. The object stays near the centre; the background is what moves.",
    track: "Sky on two axes, time on the third. A star that does not move draws a vertical line; an object that moves draws a line that leans. Drag to turn.",
    curve: "One point per visit, with that visit's noise as a band. A star that varies moves outside its own noise; a steady one stays inside it.",
  };
  const note = document.getElementById("view-note");
  const bottom = document.querySelector(".overlay-bottom");
  const setNote = (id) => {
    if (note) note.textContent = notes[id] || "";
    // The object picker and the scrubber belong to the flip view; showing them
    // over the box or the chart would offer controls that do nothing there.
    if (bottom) bottom.hidden = id !== "blink";
  };

  const initial = location.hash.replace("#", "");
  const start = tabs.some((t) => t.dataset.view === initial) ? initial : "blink";
  show(start);
  setNote(start);
}

// ------------------------------------------------------------------------ panel

function setupPanel() {
  const panel = document.getElementById("panel");
  const toggle = document.getElementById("panel-toggle");
  const close = document.getElementById("panel-close");
  if (!panel || !toggle) return;

  const set = (open) => {
    panel.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
  };

  toggle.addEventListener("click", () => set(panel.hidden));
  if (close) close.addEventListener("click", () => set(false));
  set(false);
}

function renderFacts(object) {
  const host = document.getElementById("panel-facts");
  if (!host) return;
  const lc = object.light_curve;
  const st = object.stability;
  const tm = object.track_map;

  const rows = [
    ["Visits", String(lc.visits)],
    ["Baseline", `${lc.baseline_days} days`],
    ["Motion across the series", `${tm.span_px.toFixed(2)} px`],
    ["Detected at", lc.detection_sigma === null
      ? "not resolved"
      : `${lc.detection_sigma} sigma`],
    ["Smallest change resolved", st.smallest_sustained_change_fraction === null
      ? "not resolved"
      : `${(st.smallest_sustained_change_fraction * 100).toFixed(1)} percent`],
    ["Detection threshold", st.limit_threshold === null
      ? "not measured"
      : st.limit_threshold.toFixed(1)],
  ];

  const list = document.createElement("dl");
  for (const [term, value] of rows) {
    const wrap = document.createElement("div");
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = value;
    wrap.append(dt, dd);
    list.append(wrap);
  }
  host.replaceChildren(list);
}

// ------------------------------------------------------------------------ blink

function framesFor(object) {
  const id = BLINK_ID[object.id] || object.id;
  const entry = state.blink.objects.find((o) => o.id === id);
  return entry ? entry.frames : [];
}

function showFrame() {
  const frame = document.getElementById("blink-frame");
  const caption = document.getElementById("blink-caption");
  const range = document.getElementById("blink-range");
  if (!frame || !state.current) return;

  const frames = framesFor(state.current);
  if (frames.length === 0) {
    frame.removeAttribute("src");
    caption.textContent = "No frames for this object";
    return;
  }

  state.index = Math.max(0, Math.min(state.index, frames.length - 1));
  const f = frames[state.index];
  frame.src = f.png;
  frame.alt = `Visit ${state.index + 1} of ${frames.length}, MJD ${f.mjd_label}.`;
  range.value = String(state.index);
  caption.textContent = `Visit ${state.index + 1} of ${frames.length} · MJD ${f.mjd_label}`;
}

function stopPlay() {
  clearInterval(state.timer);
  state.timer = null;
  const play = document.getElementById("blink-play");
  if (play) play.textContent = "Play";
}

function setupBlink() {
  const range = document.getElementById("blink-range");
  const play = document.getElementById("blink-play");
  if (!range || !play) return;

  range.addEventListener("input", () => {
    stopPlay();
    state.index = Number(range.value);
    showFrame();
  });

  play.addEventListener("click", () => {
    if (state.timer !== null) {
      stopPlay();
      return;
    }
    const frames = framesFor(state.current);
    if (state.index >= frames.length - 1) state.index = -1;
    play.textContent = "Pause";
    state.timer = setInterval(() => {
      const list = framesFor(state.current);
      if (state.index >= list.length - 1) {
        stopPlay();
        return;
      }
      state.index += 1;
      showFrame();
    }, 260);
  });
}

// ------------------------------------------------------------------------ curve

function drawCurve() {
  const host = document.getElementById("curve-chart");
  if (!host || !state.current || typeof uPlot !== "function") return;

  const lc = state.current.light_curve;
  const xs = lc.mjd.map((_, i) => i + 1);
  const ys = lc.flux_mjy_sr_px;
  const noise = lc.per_visit_noise_mjy_sr_px;
  const upper = ys.map((v, i) => v + noise[i]);
  const lower = ys.map((v, i) => v - noise[i]);

  const width = Math.max(320, host.clientWidth - 8);
  const height = Math.max(240, host.clientHeight - 8);

  const options = {
    width,
    height,
    padding: [10, 14, 0, 0],
    cursor: { drag: { x: true, y: false } },
    scales: { x: { time: false } },
    axes: [
      {
        stroke: "#8f8f8f",
        grid: { stroke: "#2a2a2a", width: 1 },
        ticks: { stroke: "#2a2a2a" },
        font: "11px Instrument Sans, sans-serif",
        label: "visit number",
        labelSize: 20,
        labelFont: "11px Instrument Sans, sans-serif",
      },
      {
        stroke: "#8f8f8f",
        grid: { stroke: "#2a2a2a", width: 1 },
        ticks: { stroke: "#2a2a2a" },
        font: "11px Instrument Sans, sans-serif",
        label: "brightness, MJy/sr per pixel",
        labelSize: 20,
        labelFont: "11px Instrument Sans, sans-serif",
        size: 64,
      },
    ],
    legend: { show: false },
    // The noise is a band, not two more lines: drawn as lines it reads as a second
    // measurement that happens to cross the first.
    bands: [{ series: [2, 3], fill: "rgba(232,163,61,0.10)" }],
    series: [
      {},
      {
        label: "brightness",
        stroke: "#e7e2d5",
        width: 2,
        points: { show: true, size: 6, fill: "#e7e2d5", stroke: "#121212", width: 1 },
      },
      { label: "noise upper", stroke: "rgba(232,163,61,0.0)", width: 0, points: { show: false } },
      { label: "noise lower", stroke: "rgba(232,163,61,0.0)", width: 0, points: { show: false } },
    ],
  };

  if (state.chart) state.chart.destroy();
  state.chart = new uPlot(options, [xs, ys, upper, lower], host);
}

// ------------------------------------------------------------------------ track

function drawCube() {
  const host = document.getElementById("cube-stage");
  if (!host || !state.current) return;
  if (state.cube) state.cube.dispose();
  state.cube = setupCube(host, state.current);
}

// ------------------------------------------------------------------------- main

function selectObject(id) {
  const object = state.views.objects.find((o) => o.id === id) || state.views.objects[0];
  state.current = object;
  state.index = 0;
  stopPlay();

  const select = document.getElementById("blink-object");
  if (select) select.value = object.id;

  const range = document.getElementById("blink-range");
  const frames = framesFor(object);
  if (range) range.max = String(Math.max(0, frames.length - 1));

  showFrame();
  renderFacts(object);
  drawCurve();
  drawCube();
}

async function main() {
  try {
    const [views, blink] = await Promise.all([
      loadJSON("views.json"),
      loadJSON("blink.json"),
    ]);
    state.views = views;
    state.blink = blink;

    const options = views.objects.map((object) => {
      const option = document.createElement("option");
      option.value = object.id;
      option.textContent = nameOf(object);
      return option;
    });

    const select = document.getElementById("blink-object");
    if (select) {
      select.replaceChildren(...options);
      select.addEventListener("change", () => selectObject(select.value));
    }

    setupViews();
    setupPanel();
    setupBlink();

    let pending = null;
    window.addEventListener("resize", () => {
      clearTimeout(pending);
      pending = setTimeout(() => {
        drawCurve();
        if (state.cube) state.cube.resize();
      }, 150);
    });

    selectObject(views.objects[0].id);
  } catch (error) {
    const stage = document.querySelector(".stage");
    if (stage) {
      stage.textContent = `The measurements could not be read: ${error.message}`;
    }
  }
}

main();
