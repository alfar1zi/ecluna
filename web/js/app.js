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
    if (id === "candidates") drawCandidates();
    if (id === "limit") drawLimit();
    if (id === "reach") drawReach();
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
    answer: "The conclusion first, then the evidence for it. Every number on this page is read from a file in results/.",
    blink: "Each frame is one SPHEREx visit of the same patch, aligned onto one grid. The object stays near the centre; the background is what moves.",
    track: "Sky on two axes, time on the third. A star that does not move draws a vertical line; an object that moves draws a line that leans. Drag to turn.",
    curve: "One point per visit, with that visit's noise as a band. A star that varies moves outside its own noise; a steady one stays inside it.",
    candidates: "Every source the pipeline found, against the catalogue. Grey: listed. Cream: not listed but still. Amber: not listed and moving.",
    limit: "Sources of a known brightness were injected into the real frames. The curve is the fraction recovered, with its interval, against the significance of the injection.",
    reach: "The shift falls as one over distance, so there is exactly one distance at which it equals the width of the cutout. Nearer than that, the object leaves the frame.",
  };
  const note = document.getElementById("view-note");
  const bottom = document.querySelector(".overlay-bottom");
  const setNote = (id) => {
    if (note) note.textContent = notes[id] || "";
    // The object picker and the scrubber belong to the flip view; showing them
    // over the box or the chart would offer controls that do nothing there.
    if (bottom) bottom.hidden = id !== "blink" && id !== "candidates";
    // The scrubber and the play button only move the flip view. The object picker
    // belongs to every view that draws one object.
    if (bottom) {
      for (const el of bottom.querySelectorAll(".scrub, .play")) {
        el.hidden = id !== "blink";
      }
    }
  };

  // The links on the answer view go to the evidence for the sentence above them.
  for (const link of document.querySelectorAll(".answer-link")) {
    link.addEventListener("click", () => {
      const id = link.dataset.goto;
      show(id);
      setNote(id);
      history.replaceState(null, "", `#${id}`);
    });
  }

  const initial = location.hash.replace("#", "");
  const start = tabs.some((t) => t.dataset.view === initial) ? initial : "answer";
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

// ------------------------------------------------------------------ candidates

// The catalogue is a subtractor: what it does not list is the interesting part.
// But most sources it does not list are still, so a dot that moves is the only
// one worth checking, and it is drawn in the one accent colour.
const CAND_ROWS = [
  { key: "catalogue", label: "in the catalogue", colour: "#5a5a5a", size: 3 },
  { key: "still", label: "not in the catalogue, still", colour: "#8f8f8f", size: 4 },
  { key: "moving", label: "not in the catalogue, moving", colour: "#e8a33d", size: 11 },
];

function candRow(source) {
  if (source.in_catalogue) return "catalogue";
  return source.moving ? "moving" : "still";
}

function clearCandReadout() {
  const box = document.getElementById("cand-readout");
  if (box) box.hidden = true;
}

function showCandReadout(source, object) {
  const box = document.getElementById("cand-readout");
  if (!box) return;
  const row = CAND_ROWS.find((r) => r.key === candRow(source));
  const speed = source.speed_px_per_visit ?? null;
  const nearest = source.nearest_catalogue_arcsec ?? null;

  box.replaceChildren();
  const title = document.createElement("h3");
  title.textContent = row.label;
  box.append(title);

  const list = document.createElement("dl");
  const facts = [
    ["position", `${source.ra_deg.toFixed(4)} ${source.dec_deg.toFixed(4)}`],
    ["brightness", `${source.brightness_mjy_sr.toFixed(2)} MJy/sr`],
    ["signal to noise", source.signal_to_noise.toFixed(1)],
    ["motion test", source.track_statistic.toFixed(1)],
    ["speed", speed === null ? "not measured" : `${speed.toFixed(3)} px per visit`],
    ["nearest catalogue star", nearest === null ? "not measured" : `${nearest.toFixed(1)} arcsec`],
  ];
  for (const [name, value] of facts) {
    const dt = document.createElement("dt");
    dt.textContent = name;
    const dd = document.createElement("dd");
    dd.textContent = value;
    list.append(dt, dd);
  }
  box.append(list);

  const note = document.createElement("p");
  note.textContent = source.moving
    ? "The catalogue does not list this source and its track moves. That makes it worth a check, not a discovery."
    : "The catalogue does not list this source, but its track does not move. A faint star the catalogue missed is the likeliest reading.";
  box.append(note);

  box.hidden = false;
}

function drawCandidates() {
  const host = document.getElementById("cand-chart");
  if (!host || !state.current || typeof uPlot !== "function") return;
  clearCandReadout();

  const object = state.current;
  const c = object.candidates;
  if (!c || !c.sources || c.sources.length === 0) {
    host.replaceChildren();
    const empty = document.createElement("p");
    empty.style.color = "#8f8f8f";
    empty.style.fontSize = "0.85rem";
    empty.textContent = "No source list was classified for this object.";
    host.append(empty);
    return;
  }

  // Offsets in arcseconds from the object, east and north.
  const cosDec = Math.cos((object.dec_deg * Math.PI) / 180);
  const points = c.sources.map((source) => {
    const east = (source.ra_deg - object.ra_deg) * cosDec * 3600;
    const north = (source.dec_deg - object.dec_deg) * 3600;
    return { ...source, east, north, row: candRow(source) };
  });
  points.sort((a, b) => a.east - b.east);

  const xs = points.map((p) => p.east);
  const series = CAND_ROWS.map((row) => ({
    label: row.label,
    stroke: row.colour,
    width: 0,
    paths: () => null,
    // The moving points get a dark ring so they stand off the still field.
    points: {
      show: true,
      size: row.size,
      width: row.key === "moving" ? 2 : 0,
      stroke: row.key === "moving" ? "#121212" : row.colour,
      fill: row.colour,
    },
    value: (u, v) => (v === null ? "--" : v.toFixed(1)),
  }));
  const ys = CAND_ROWS.map((row) => points.map((p) => (p.row === row.key ? p.north : null)));

  // The chart is drawn at a pixel size, so the padding is taken off the box
  // rather than assumed: clientHeight counts padding, and the axis labels need
  // the room the padding reserves.
  const box = getComputedStyle(host);
  const padX = parseFloat(box.paddingLeft) + parseFloat(box.paddingRight);
  const padY = parseFloat(box.paddingTop) + parseFloat(box.paddingBottom);
  const width = Math.max(320, host.clientWidth - padX - 8);
  const height = Math.max(260, host.clientHeight - padY - 8);
  if (state.cand) state.cand.destroy();
  clearCandReadout();

  const options = {
    width,
    height,
    padding: [12, 18, 0, 0],
    legend: { show: false },
    cursor: { drag: { x: false, y: false }, points: { show: false } },
    scales: { x: { time: false }, y: { time: false } },
    axes: [
      {
        stroke: "#8f8f8f",
        grid: { stroke: "#2a2a2a", width: 1 },
        ticks: { stroke: "#2a2a2a" },
        font: "11px Instrument Sans, sans-serif",
        label: "east of the object, arcseconds",
        labelSize: 20,
        labelFont: "11px Instrument Sans, sans-serif",
      },
      {
        stroke: "#8f8f8f",
        grid: { stroke: "#2a2a2a", width: 1 },
        ticks: { stroke: "#2a2a2a" },
        font: "11px Instrument Sans, sans-serif",
        label: "north, arcseconds",
        labelSize: 20,
        labelFont: "11px Instrument Sans, sans-serif",
      },
    ],
    series: [{}, ...series],
    hooks: {
      setCursor: [
        (u) => {
          const idx = u.cursor.idx;
          if (idx === null || idx === undefined) return;
          const point = points[idx];
          if (point) showCandReadout(point, object);
        },
      ],
    },
  };

  state.cand = new uPlot(options, [xs, ...ys], host);

  const legend = document.createElement("p");
  legend.className = "cand-legend";
  for (const row of CAND_ROWS) {
    const item = document.createElement("span");
    const dot = document.createElement("i");
    dot.style.background = row.colour;
    dot.style.width = dot.style.height = row.key === "moving" ? "9px" : "5px";
    dot.style.borderRadius = "50%";
    dot.style.display = "inline-block";
    dot.style.marginRight = "5px";
    dot.style.verticalAlign = "middle";
    item.append(dot, document.createTextNode(row.label));
    item.style.marginRight = "1.1rem";
    legend.append(item);
  }
  legend.style.cssText += "color:#8f8f8f;font-size:0.72rem;margin:0 0 0.7rem;text-align:center;";
  host.replaceChildren(legend, state.cand.root);
}

// -------------------------------------------------------------------- answer

// The page states one conclusion, and every number in it is read from a file.
// The two completeness points are chosen by significance, not by amplitude, so
// the sentence does not depend on a photometric zeropoint we do not trust.
function drawAnswer(completeness, recovery) {
  const set = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  };

  if (completeness && Array.isArray(completeness.reported_curve)) {
    const curve = completeness.reported_curve;
    const high = curve.reduce((a, b) => (b.median_snr > a.median_snr ? b : a));
    const low = curve.reduce((a, b) => {
      const da = Math.abs(a.median_snr - 5);
      const db = Math.abs(b.median_snr - 5);
      return db < da ? b : a;
    });
    set("ans-high", `${(high.completeness * 100).toFixed(0)}%`);
    set("ans-high-snr", high.median_snr.toFixed(1));
    set("ans-low", `${(low.completeness * 100).toFixed(0)}%`);
    set("ans-low-snr", low.median_snr.toFixed(1));
  }

  if (recovery && recovery.summary) {
    const s = recovery.summary;
    set("ans-rec", String(s.n_recovered));
    set("ans-notrec", String(s.n_not_recovered));
    set("ans-noteval", String(s.n_not_evaluated));
  }

  const list = document.getElementById("ans-objects");
  if (!list || !recovery || !Array.isArray(recovery.objects)) return;
  list.replaceChildren();
  for (const object of recovery.objects) {
    const item = document.createElement("li");
    const verdict = String(object.verdict || "");
    const kind = verdict.startsWith("PULIH")
      ? "is-recovered"
      : verdict.startsWith("TIDAK DIEVALUASI")
        ? "is-unevaluated"
        : "is-missing";
    item.className = kind;
    const shape = document.createElement("span");
    shape.className = "mark-shape";
    const label = document.createElement("span");
    label.textContent = object.name;
    const word = document.createElement("span");
    word.className = "mark-word";
    word.textContent = kind === "is-recovered"
      ? "recovered"
      : kind === "is-unevaluated"
        ? "not evaluated"
        : "not recovered";
    item.append(shape, label, word);
    item.title = verdict;
    list.append(item);
  }
}

// --------------------------------------------------------------------- limit

// The completeness curve is the claim: what fraction of sources at a given
// significance the pipeline recovers. The interval is Wilson, not normal, because
// at 2.5% recovered a normal interval would run below zero.
function drawLimit() {
  const host = document.getElementById("limit-chart");
  if (!host || typeof uPlot !== "function") return;
  const data = state.completeness;
  if (!data || !Array.isArray(data.reported_curve)) return;

  const curve = data.reported_curve;
  const xs = curve.map((r) => r.median_snr);
  const ys = curve.map((r) => r.completeness);
  const lo = curve.map((r) => r.wilson95[0]);
  const hi = curve.map((r) => r.wilson95[1]);

  const box = getComputedStyle(host);
  const padX = parseFloat(box.paddingLeft) + parseFloat(box.paddingRight);
  const padY = parseFloat(box.paddingTop) + parseFloat(box.paddingBottom);
  const width = Math.max(320, host.clientWidth - padX - 8);
  const height = Math.max(240, host.clientHeight - padY - 8);

  if (state.limit) state.limit.destroy();

  const options = {
    width,
    height,
    padding: [12, 16, 0, 0],
    legend: { show: false },
    cursor: { drag: { x: false, y: false }, points: { show: false } },
    scales: { x: { time: false }, y: { time: false, range: [0, 1] } },
    axes: [
      {
        stroke: "#8f8f8f",
        grid: { stroke: "#2a2a2a", width: 1 },
        ticks: { stroke: "#2a2a2a" },
        font: "11px Instrument Sans, sans-serif",
        label: "detection significance, peak over MAD",
        labelSize: 20,
        labelFont: "11px Instrument Sans, sans-serif",
      },
      {
        stroke: "#8f8f8f",
        grid: { stroke: "#2a2a2a", width: 1 },
        ticks: { stroke: "#2a2a2a" },
        font: "11px Instrument Sans, sans-serif",
        size: 46,
        values: (u, vals) => vals.map((v) => `${(v * 100).toFixed(0)}%`),
        label: "recovered",
        labelSize: 20,
        labelFont: "11px Instrument Sans, sans-serif",
      },
    ],
    series: [
      {},
      {
        label: "recovered",
        stroke: "#e7e2d5",
        width: 2,
        points: { show: true, size: 6, width: 0, fill: "#e7e2d5" },
        value: (u, v) => (v === null ? "--" : `${(v * 100).toFixed(1)}%`),
      },
    ],
    hooks: {
      draw: [
        (u) => {
          const { ctx } = u;
          // The Wilson interval, drawn as a band. uPlot's own bands option does
          // not render here, so the polygon is built from the same numbers.
          ctx.save();
          // Behind the line, not over it: the curve is the claim and the band
          // is its uncertainty, so the curve has to stay on top.
          ctx.globalCompositeOperation = "destination-over";
          ctx.beginPath();
          for (let i = 0; i < xs.length; i += 1) {
            const px = u.valToPos(xs[i], "x", true);
            const py = u.valToPos(hi[i], "y", true);
            if (i === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
          }
          for (let i = xs.length - 1; i >= 0; i -= 1) {
            ctx.lineTo(u.valToPos(xs[i], "x", true), u.valToPos(lo[i], "y", true));
          }
          ctx.closePath();
          ctx.fillStyle = "rgba(232,163,61,0.20)";
          ctx.fill();
          ctx.restore();

          // The threshold the pipeline actually uses, drawn where it falls.
          const x = u.valToPos(5, "x", true);
          if (!Number.isFinite(x)) return;
          ctx.save();
          ctx.strokeStyle = "#e8a33d";
          ctx.setLineDash([4, 4]);
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(x, u.bbox.top);
          ctx.lineTo(x, u.bbox.top + u.bbox.height);
          ctx.stroke();
          ctx.restore();
        },
      ],
    },
  };

  state.limit = new uPlot(options, [xs, ys], host);
  host.replaceChildren(state.limit.root);

  const caption = document.getElementById("limit-caption");
  if (caption) {
    caption.textContent = "The dashed line is the 5 sigma threshold the pipeline uses. The band is the Wilson 95% interval.";
  }

  const list = document.getElementById("limit-not-claimed");
  if (list && Array.isArray(data.not_claimed)) {
    list.replaceChildren();
    for (const item of data.not_claimed) {
      const li = document.createElement("li");
      li.textContent = item;
      list.append(li);
    }
  }

  const facts = document.getElementById("limit-facts");
  if (facts) {
    facts.replaceChildren();
    const rows = [
      ["frames", String(data.frames ? data.frames.length : "--")],
      ["injections per point", String(curve[0] ? curve[0].n : "--")],
      ["stack MAD", data.stack_mad.toFixed(5)],
      ["PSF FWHM", `${data.psf_fwhm_px.toFixed(1)} px`],
      ["threshold", `${data.detect_sigma.toFixed(1)} sigma`],
      ["final seed", String(data.final_seed)],
    ];
    for (const [name, value] of rows) {
      const dt = document.createElement("dt");
      dt.textContent = name;
      const dd = document.createElement("dd");
      dd.textContent = value;
      facts.append(dt, dd);
    }
  }
}

// --------------------------------------------------------------------- reach

// The parallax finding is a threshold, not a volume: the shift falls as 1/d, so
// there is exactly one distance at which it equals the half field. A log-log
// chart shows that crossing and a 3D cone would only hide it.
function drawReach() {
  const host = document.getElementById("reach-chart");
  if (!host || typeof uPlot !== "function") return;
  const data = state.parallax;
  if (!data || !Array.isArray(data.geometry_full_baseline)) return;

  const rows = data.geometry_full_baseline;
  const xs = rows.map((r) => r.dist_au);
  const ys = rows.map((r) => r.peak_shift_arcsec);
  const half = data.half_field_arcsec;
  const crossing = (rows[0].dist_au * rows[0].peak_shift_arcsec) / half;

  const box = getComputedStyle(host);
  const padX = parseFloat(box.paddingLeft) + parseFloat(box.paddingRight);
  const padY = parseFloat(box.paddingTop) + parseFloat(box.paddingBottom);
  const width = Math.max(320, host.clientWidth - padX - 8);
  const height = Math.max(240, host.clientHeight - padY - 8);

  if (state.reach) state.reach.destroy();

  const options = {
    width,
    height,
    padding: [12, 16, 0, 0],
    legend: { show: false },
    cursor: { drag: { x: false, y: false }, points: { show: false } },
    scales: {
      x: { time: false, distr: 3, log: 10 },
      y: { time: false, distr: 3, log: 10 },
    },
    axes: [
      {
        stroke: "#8f8f8f",
        grid: { stroke: "#2a2a2a", width: 1 },
        ticks: { stroke: "#2a2a2a" },
        font: "11px Instrument Sans, sans-serif",
        values: (u, vals) => vals.map((v) => (v == null ? "" : v >= 1000 ? `${v / 1000}k` : String(v))),
        label: "distance, astronomical units",
        labelSize: 20,
        labelFont: "11px Instrument Sans, sans-serif",
      },
      {
        stroke: "#8f8f8f",
        grid: { stroke: "#2a2a2a", width: 1 },
        ticks: { stroke: "#2a2a2a" },
        font: "11px Instrument Sans, sans-serif",
        size: 52,
        values: (u, vals) => vals.map((v) => (v == null ? "" : v >= 1000 ? `${v / 1000}k` : String(v))),
        label: "shift over the baseline, arcseconds",
        labelSize: 20,
        labelFont: "11px Instrument Sans, sans-serif",
      },
    ],
    series: [
      {},
      {
        label: "shift",
        stroke: "#e7e2d5",
        width: 2,
        points: { show: true, size: 6, width: 0, fill: "#e7e2d5" },
        value: (u, v) => (v === null ? "--" : `${v.toFixed(1)} arcsec`),
      },
    ],
    hooks: {
      draw: [
        (u) => {
          const { ctx } = u;
          const yHalf = u.valToPos(half, "y", true);
          const xCross = u.valToPos(crossing, "x", true);
          if (!Number.isFinite(yHalf) || !Number.isFinite(xCross)) return;

          ctx.save();
          // Beyond the crossing the object leaves the cutout, so that side of
          // the chart is the part a full-baseline search cannot use.
          ctx.fillStyle = "rgba(232,163,61,0.10)";
          ctx.fillRect(u.bbox.left, u.bbox.top, xCross - u.bbox.left, u.bbox.height);

          ctx.strokeStyle = "#e8a33d";
          ctx.setLineDash([4, 4]);
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(u.bbox.left, yHalf);
          ctx.lineTo(u.bbox.left + u.bbox.width, yHalf);
          ctx.stroke();
          ctx.beginPath();
          ctx.moveTo(xCross, u.bbox.top);
          ctx.lineTo(xCross, u.bbox.top + u.bbox.height);
          ctx.stroke();
          ctx.restore();
        },
      ],
    },
  };

  state.reach = new uPlot(options, [xs, ys], host);
  host.replaceChildren(state.reach.root);

  const caption = document.getElementById("reach-caption");
  if (caption) {
    caption.textContent = `The dashed lines meet at ${Math.round(crossing).toLocaleString("en-US")} AU: closer than that, an object moves further than the cutout is wide.`;
  }

  const meaning = document.getElementById("reach-meaning");
  if (meaning) {
    meaning.textContent = `A full-baseline parallax search inside a 0.1 degree cutout can only follow objects beyond about ${Math.round(crossing).toLocaleString("en-US")} AU. Anything nearer leaves the frame, so the search that was run is a search of the far field, and its negative result says nothing about the near field.`;
  }

  const list = document.getElementById("reach-not-claimed");
  if (list && Array.isArray(data.not_claimed)) {
    list.replaceChildren();
    for (const item of data.not_claimed) {
      const li = document.createElement("li");
      li.textContent = item;
      list.append(li);
    }
  }

  const facts = document.getElementById("reach-facts");
  if (facts) {
    facts.replaceChildren();
    const rowsOut = [
      ["baseline", `${data.baseline_days.toFixed(1)} days`],
      ["half field", `${half.toFixed(1)} arcsec`],
      ["pixel scale", `${data.pixel_scale_arcsec.toFixed(2)} arcsec`],
      ["frames", String(data.n_frames)],
      ["crossing", `${Math.round(crossing).toLocaleString("en-US")} AU`],
    ];
    for (const [name, value] of rowsOut) {
      const dt = document.createElement("dt");
      dt.textContent = name;
      const dd = document.createElement("dd");
      dd.textContent = value;
      facts.append(dt, dd);
    }
  }
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
  drawCandidates();
}

async function main() {
  try {
    const [views, blink, completeness, recovery, parallax] = await Promise.all([
      loadJSON("views.json"),
      loadJSON("blink.json"),
      loadJSON("completeness.json").catch(() => null),
      loadJSON("named_recovery_summary.json").catch(() => null),
      loadJSON("parallax.json").catch(() => null),
    ]);
    state.views = views;
    state.blink = blink;
    state.completeness = completeness;
    state.parallax = parallax;
    drawAnswer(completeness, recovery);

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

    // The address can name the object and the view, so one link can point at
    // one measurement rather than at the front page.
    const asked = new URLSearchParams(location.search).get("o");
    const first = views.objects.find((o) => o.id === asked) || views.objects[0];
    selectObject(first.id);
  } catch (error) {
    const stage = document.querySelector(".stage");
    if (stage) {
      stage.textContent = `The measurements could not be read: ${error.message}`;
    }
  }
}

main();
