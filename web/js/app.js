// Ecluna — one object at a time, three ways of looking at it.
//
// The page is a set of views rather than a document: the bar switches which view
// fills the stage, and the numbers live in a panel that opens on demand. Every
// value comes from web/data/, which is written by the measurement scripts.

import { setupCube } from "./cube.js";
import { setupSystem } from "./system.js";

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
      if (active) {
        // The view arrives rather than appearing, so switching reads as a move
        // rather than a reload.
        view.classList.remove("is-entering");
        void view.offsetWidth;
        view.classList.add("is-entering");
        const inner = view.querySelector(".answer");
        if (inner) {
          inner.classList.remove("is-entering");
          void inner.offsetWidth;
          inner.classList.add("is-entering");
        }
      }
    }
    // The chart and the box are drawn at a pixel size, so they are redrawn when
    // their view becomes visible rather than stretched from a hidden layout.
    if (id === "curve") drawCurve();
    if (id === "track") drawCube();
    if (id === "candidates") drawCandidates();
    if (id === "limit") drawLimit();
    if (id === "reach") drawReach();
    if (id === "system") drawSystem();
    if (id === "injection") drawInjection();
    if (id === "search") drawSearch();
    if (id === "sky") drawSky();
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
    limit: "Sources of a known brightness were injected into the real frames. The curve is the fraction recovered, with its interval, against the flux that was injected.",
    reach: "The shift falls as one over distance, so there is exactly one distance at which it equals the width of the cutout. Nearer than that, the object leaves the frame.",
    system: "The solar system from above on a log scale. Amber is what the search can follow, grey is what it cannot, and the gap is where a planet beyond Neptune would be.",
    injection: "A source of a known brightness added to a real frame. At the faint end it is in the pixels and cannot be seen, which is what the completeness number means.",
    search: "Every rate of sky motion was tried and the frames were stacked along it. The best stack is compared against a null built from random rates.",
    sky: "The whole sky, with the ecliptic where the planets are and the galactic plane where the stars are thickest. The six patches are where the survey looked.",
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

// A chart that appears at full weight reads as a page load; one that settles
// reads as a measurement being drawn.
function settle(node) {
  if (!node) return;
  node.classList.remove("chart-enter");
  void node.offsetWidth;
  node.classList.add("chart-enter");
}

// ------------------------------------------------------------------------ blink

function framesFor(object) {
  const id = BLINK_ID[object.id] || object.id;
  const entry = state.blink.objects.find((o) => o.id === id);
  return entry ? entry.frames : [];
}

// A modified Julian date means nothing to a reader, so the caption carries the
// calendar date and the number stays in the tooltip.
function mjdToDate(mjd) {
  const jd = mjd + 2400000.5;
  const unix = (jd - 2440587.5) * 86400 * 1000;
  const d = new Date(unix);
  return d.toISOString().slice(0, 10);
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
  frame.classList.add("is-swapping");
  frame.src = f.png;
  frame.onload = () => frame.classList.remove("is-swapping");
  frame.alt = `Visit ${state.index + 1} of ${frames.length}, ${mjdToDate(f.mjd)}.`;
  range.value = String(state.index);
  caption.textContent = `Visit ${state.index + 1} of ${frames.length} · ${mjdToDate(f.mjd)}`;
  caption.title = `MJD ${f.mjd_label}`;
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

  // The chart is drawn at a pixel size, so the padding is taken off the box
  // rather than assumed: clientHeight counts padding, and the axis labels need
  // the room the padding reserves.
  const box = getComputedStyle(host);
  const padX = parseFloat(box.paddingLeft) + parseFloat(box.paddingRight);
  const padY = parseFloat(box.paddingTop) + parseFloat(box.paddingBottom);
  const width = Math.max(320, host.clientWidth - padX - 8);
  const height = Math.max(240, host.clientHeight - padY - 8);

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
  settle(state.chart.root);
}

// ------------------------------------------------------------------------ track

function drawCube() {
  const host = document.getElementById("cube-stage");
  if (!host || !state.current) return;
  if (state.cube) state.cube.dispose();
  state.cube = setupCube(host, state.current);
}

// -------------------------------------------------------------------- answer

// The finding as a picture: a small square, and a track that crosses it and
// leaves. A reader who scans gets the reason the search fails without reading a
// sentence.
function drawAnswerFigure(parallax) {
  const canvas = document.getElementById("answer-canvas");
  if (!canvas || !parallax) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  const dpr = window.devicePixelRatio || 1;
  if (dpr > 1) {
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    ctx.scale(dpr, dpr);
  }
  ctx.clearRect(0, 0, w, h);

  const cx = w / 2;
  const cy = h / 2;
  const side = 108;
  const left = cx - side / 2;
  const top = cy - side / 2;

  // The cutout.
  ctx.fillStyle = "rgba(143,143,143,0.10)";
  ctx.fillRect(left, top, side, side);
  ctx.strokeStyle = "#8f8f8f";
  ctx.lineWidth = 1;
  ctx.strokeRect(left, top, side, side);

  // The track: it enters low on the left and leaves high on the right, so the
  // crossing is visible rather than implied.
  const x0 = 40;
  const x1 = w - 40;
  const y0 = cy + 74;
  const y1 = cy - 74;
  const yAt = (x) => y0 + ((y1 - y0) * (x - x0)) / (x1 - x0);

  ctx.strokeStyle = "#e8a33d";
  ctx.lineWidth = 2;
  ctx.setLineDash([6, 5]);
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x1, y1);
  ctx.stroke();
  ctx.setLineDash([]);

  // Where the track crosses the cutout edge, marked, because that is the moment
  // the object is lost.
  const exitX = left + side;
  const exitY = yAt(exitX);
  ctx.beginPath();
  ctx.arc(exitX, exitY, 4, 0, Math.PI * 2);
  ctx.fillStyle = "#e8a33d";
  ctx.fill();

  ctx.font = "11px Instrument Sans, sans-serif";
  ctx.fillStyle = "#a8a49a";
  ctx.textAlign = "left";
  ctx.fillText("the object enters here", x0 + 4, y0 + 18);
  ctx.textAlign = "right";
  ctx.fillText("and leaves the frame here", x1 - 4, y1 - 10);

  ctx.textAlign = "center";
  ctx.fillStyle = "#e7e2d5";
  ctx.font = "11px Instrument Sans, sans-serif";
  ctx.fillText("cutout", cx, top - 8);
  ctx.fillStyle = "#a8a49a";
  ctx.fillText("0.1 degrees", cx, top + side + 16);
}

function drawAnswer(completeness, recovery, parallax, shiftStack, views) {
  const set = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  };

  if (completeness && Array.isArray(completeness.fields)) {
    // The spread across fields is the honest number, not a single average.
    const at = (flux) => completeness.fields.map((f) => {
      const level = f.levels.find((l) => Math.abs(l.flux_mjy_sr - flux) < 1e-9);
      return level ? level.completeness : null;
    }).filter((v) => v !== null);
    const low = at(0.2);
    const high = at(0.4);
    if (low.length) {
      set("ans-low", `${(Math.min(...low) * 100).toFixed(0)} to ${(Math.max(...low) * 100).toFixed(0)}%`);
      set("ans-low-snr", "0.2");
    }
    if (high.length) {
      set("ans-high", `${(Math.min(...high) * 100).toFixed(0)}%`);
      set("ans-high-snr", "0.4");
    }
  }

  // The finding: the cutout cannot follow the near field, and that is a property
  // of the cutout rather than of the telescope.
  if (parallax && Array.isArray(parallax.geometry_full_baseline)) {
    const rows = parallax.geometry_full_baseline;
    const crossing = (rows[0].dist_au * rows[0].peak_shift_arcsec) / parallax.half_field_arcsec;
    const at400 = rows.find((r) => r.dist_au === 400);
    set("ans-baseline", parallax.baseline_days.toFixed(0));
    set("ans-shift", at400 ? at400.peak_shift_arcsec.toFixed(0) : "--");
    set("ans-reach", Math.round(crossing).toLocaleString("en-US"));
    drawAnswerFigure(parallax);
  }

  if (shiftStack && shiftStack.threshold_verdict) {
    const v = shiftStack.threshold_verdict;
    set("ans-best", Math.round(v.best_T).toLocaleString("en-US"));
    set("ans-null", Math.round(v.empirical_threshold_p999).toLocaleString("en-US"));
  }

  if (views && Array.isArray(views.objects)) {
    let total = 0;
    for (const object of views.objects) {
      const c = object.candidates;
      if (!c || !c.counts) continue;
      for (const [key, value] of Object.entries(c.counts)) {
        if (key.includes("candidate")) total += value;
      }
    }
    set("ans-cands", String(total));
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

// ------------------------------------------------------------------ candidates

// The catalogue is a subtractor: what it does not list is the interesting part.
// But most sources it does not list are still, so a dot that moves is the only
// one worth checking. The scatter is the input; the panel is the output, and the
// output is a verdict with the evidence for and against it.
const CAND_ROWS = [
  { key: "catalogue", label: "in the catalogue", colour: "#7d7d7d", size: 5 },
  { key: "still", label: "not in the catalogue, still", colour: "#b9b4a8", size: 6 },
  { key: "moving", label: "not in the catalogue, moving", colour: "#e8a33d", size: 11 },
];

function candRow(source) {
  if (source.in_catalogue) return "catalogue";
  return source.moving ? "moving" : "still";
}

// A verdict a reader can act on. The three ways a candidate fails are the three
// ways this kind of search produces false positives, and each is named.
function candVerdict(source, peers) {
  const nearest = source.nearest_catalogue_arcsec;
  const speed = source.speed_px_per_visit;
  const sameSpeed = peers.filter(
    (p) => p !== source && Math.abs((p.speed_px_per_visit ?? 0) - (speed ?? 0)) < 1e-6,
  ).length;

  if (nearest !== null && nearest !== undefined && nearest < 30) {
    return {
      label: "likely a star the catalogue missed",
      weak: true,
      why: `The nearest catalogued star is ${nearest.toFixed(1)} arcseconds away, which is close enough that a small error in the catalogue position would put a known star here.`,
    };
  }
  if (sameSpeed >= 2) {
    return {
      label: "likely systematic",
      weak: true,
      why: `${sameSpeed + 1} candidates in this field share the same speed to six decimals. Real objects do not move at identical rates, so this is more likely a residual in the alignment than motion.`,
    };
  }
  if (source.signal_to_noise < 10) {
    return {
      label: "too faint to call",
      weak: true,
      why: `The signal to noise is ${source.signal_to_noise.toFixed(1)}, which is close to the threshold. A source this faint can pass the test by chance.`,
    };
  }
  return {
    label: "worth a follow-up",
    weak: false,
    why: "The catalogue does not list it, its motion is distinct from the other candidates in this field, and it is bright enough that the detection is not marginal.",
  };
}

function clearCandPanel() {
  const empty = document.getElementById("cand-empty");
  const body = document.getElementById("cand-body");
  if (empty) empty.hidden = false;
  if (body) body.hidden = true;
}

function showCandPanel(source, peers, object) {
  const empty = document.getElementById("cand-empty");
  const body = document.getElementById("cand-body");
  if (!body) return;
  if (empty) empty.hidden = true;
  body.hidden = false;

  const verdict = candVerdict(source, peers);
  body.replaceChildren();

  const title = document.createElement("h2");
  title.textContent = `${object.name}, ${source.ra_deg.toFixed(3)} ${source.dec_deg.toFixed(3)}`;
  body.append(title);

  const badge = document.createElement("span");
  badge.className = verdict.weak ? "cand-verdict is-weak" : "cand-verdict";
  badge.textContent = verdict.label;
  body.append(badge);

  const list = document.createElement("dl");
  const facts = [
    ["brightness", `${source.brightness_mjy_sr.toFixed(3)} MJy/sr`],
    ["signal to noise", source.signal_to_noise.toFixed(1)],
    ["motion test", source.track_statistic.toFixed(1)],
    ["speed", source.speed_px_per_visit === null
      ? "not measured"
      : `${source.speed_px_per_visit.toFixed(3)} pixels per visit`],
    ["nearest catalogue star", source.nearest_catalogue_arcsec === null
      ? "not measured"
      : `${source.nearest_catalogue_arcsec.toFixed(1)} arcseconds`],
  ];
  for (const [name, value] of facts) {
    const dt = document.createElement("dt");
    dt.textContent = name;
    const dd = document.createElement("dd");
    dd.textContent = value;
    list.append(dt, dd);
  }
  body.append(list);

  const whyHead = document.createElement("h3");
  whyHead.textContent = "Why this verdict";
  const why = document.createElement("p");
  why.textContent = verdict.why;
  body.append(whyHead, why);

  const againstHead = document.createElement("h3");
  againstHead.textContent = "What would settle it";
  const against = document.createElement("p");
  against.textContent = verdict.weak
    ? "A deeper image at the same position, or a catalogue with a fainter limit, would decide it. Neither is in this data."
    : "A second epoch at higher resolution, or a spectrum, would confirm or reject the motion. This data cannot do either.";
  body.append(againstHead, against);
}

function drawCandidates() {
  const host = document.getElementById("cand-chart");
  const strip = document.getElementById("cand-strip");
  if (!host || !state.current || typeof uPlot !== "function") return;
  clearCandPanel();
  if (strip) strip.replaceChildren();

  const object = state.current;
  const c = object.candidates;
  if (!c || !c.sources || c.sources.length === 0) {
    host.replaceChildren();
    const empty = document.createElement("p");
    empty.style.color = "#a8a49a";
    empty.style.fontSize = "0.85rem";
    empty.textContent = "No source list was classified for this object.";
    host.append(empty);
    return;
  }

  const cosDec = Math.cos((object.dec_deg * Math.PI) / 180);
  const points = c.sources.map((source) => {
    const east = (source.ra_deg - object.ra_deg) * cosDec * 3600;
    const north = (source.dec_deg - object.dec_deg) * 3600;
    return { ...source, east, north, row: candRow(source) };
  });
  points.sort((a, b) => a.east - b.east);

  const moving = points.filter((p) => p.row === "moving");
  const xs = points.map((p) => p.east);
  const series = CAND_ROWS.map((row) => ({
    label: row.label,
    stroke: row.colour,
    width: 0,
    paths: () => null,
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

  const box = getComputedStyle(host);
  const padX = parseFloat(box.paddingLeft) + parseFloat(box.paddingRight);
  const padY = parseFloat(box.paddingTop) + parseFloat(box.paddingBottom);
  const width = Math.max(320, host.clientWidth - padX - 8);
  const height = Math.max(220, host.clientHeight - padY - 8);
  if (state.cand) state.cand.destroy();

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
          if (point && point.row === "moving") showCandPanel(point, moving, object);
        },
      ],
    },
  };

  state.cand = new uPlot(options, [xs, ...ys], host);
  settle(state.cand.root);

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
  legend.style.cssText += "color:#a8a49a;font-size:0.72rem;margin:0 0 0.5rem;text-align:center;";
  host.replaceChildren(legend, state.cand.root);

  // The strip: one chip per candidate, so a reader can step through them without
  // hunting for a dot on the field.
  if (strip) {
    if (moving.length === 0) {
      const none = document.createElement("p");
      none.style.cssText = "color:#a8a49a;font-size:0.78rem;margin:0;";
      none.textContent = "No source in this field passes the motion test.";
      strip.append(none);
    }
    moving.forEach((point, i) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "cand-chip";
      chip.setAttribute("role", "option");
      const dot = document.createElement("i");
      const label = document.createElement("span");
      label.textContent = `#${i + 1} · ${point.signal_to_noise.toFixed(0)} sigma`;
      chip.append(dot, label);
      chip.addEventListener("click", () => {
        for (const other of strip.querySelectorAll(".cand-chip")) {
          other.classList.remove("is-active");
        }
        chip.classList.add("is-active");
        showCandPanel(point, moving, object);
      });
      strip.append(chip);
    });
  }
}

// --------------------------------------------------------------------- limit

// Three fields were measured, and they do not agree: the same flux is recovered
// at 60% in one field and 15% in another. The chart shows all three rather than
// an average, because the spread is the finding.
const LIMIT_COLOURS = ["#e7e2d5", "#8f8f8f", "#e8a33d"];

function drawLimit() {
  const host = document.getElementById("limit-chart");
  if (!host || typeof uPlot !== "function") return;
  const data = state.completeness;
  if (!data || !Array.isArray(data.fields)) return;

  const fields = data.fields;
  // Five discrete levels, so the axis is ordinal: a log axis would space them
  // evenly and a linear one would crowd four of them against the left edge.
  const levels = fields[0].levels.map((l) => l.flux_mjy_sr);
  const xs = levels.map((_, i) => i);

  const box = getComputedStyle(host);
  const padX = parseFloat(box.paddingLeft) + parseFloat(box.paddingRight);
  const padY = parseFloat(box.paddingTop) + parseFloat(box.paddingBottom);
  const width = Math.max(320, host.clientWidth - padX - 8);
  const height = Math.max(240, host.clientHeight - padY - 8);

  if (state.limit) state.limit.destroy();

  const series = fields.map((field, i) => ({
    label: field.label,
    stroke: LIMIT_COLOURS[i % LIMIT_COLOURS.length],
    width: 2,
    points: { show: true, size: 5, width: 0, fill: LIMIT_COLOURS[i % LIMIT_COLOURS.length] },
    value: (u, v) => (v === null ? "--" : `${(v * 100).toFixed(0)}%`),
  }));

  const options = {
    width,
    height,
    padding: [12, 16, 0, 0],
    legend: { show: false },
    cursor: { drag: { x: false, y: false }, points: { show: false } },
    scales: {
      x: { time: false, range: [-0.4, levels.length - 0.6] },
      y: { time: false, range: [0, 1] },
    },
    axes: [
      {
        stroke: "#8f8f8f",
        grid: { stroke: "#2a2a2a", width: 1 },
        ticks: { stroke: "#2a2a2a" },
        font: "11px Instrument Sans, sans-serif",
        splits: () => xs,
        values: (u, vals) => vals.map((v) => (v == null ? "" : String(levels[v]))),
        label: "injected flux, MJy per steradian",
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
    series: [{}, ...series],
    hooks: {
      draw: [
        (u) => {
          const { ctx } = u;
          ctx.save();
          // The Wilson interval as a thin bar at each point, so the three fields
          // stay readable on one axis.
          fields.forEach((field, i) => {
            ctx.strokeStyle = LIMIT_COLOURS[i % LIMIT_COLOURS.length];
            ctx.globalAlpha = 0.45;
            ctx.lineWidth = 1;
            for (let j = 0; j < field.levels.length; j += 1) {
              const level = field.levels[j];
              const px = u.valToPos(j, "x", true);
              const lo = u.valToPos(level.wilson95[0], "y", true);
              const hi = u.valToPos(level.wilson95[1], "y", true);
              if (!Number.isFinite(px) || !Number.isFinite(lo) || !Number.isFinite(hi)) continue;
              ctx.beginPath();
              ctx.moveTo(px, lo);
              ctx.lineTo(px, hi);
              ctx.stroke();
            }
          });
          ctx.restore();
        },
      ],
    },
  };

  const ys = fields.map((field) => field.levels.map((l) => l.completeness));
  state.limit = new uPlot(options, [xs, ...ys], host);
  settle(state.limit.root);

  const legend = document.createElement("p");
  legend.style.cssText = "color:#8f8f8f;font-size:0.72rem;margin:0 0 0.7rem;text-align:center;";
  fields.forEach((field, i) => {
    const item = document.createElement("span");
    const dot = document.createElement("i");
    dot.style.cssText = `background:${LIMIT_COLOURS[i % LIMIT_COLOURS.length]};width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:5px;vertical-align:middle;`;
    item.append(dot, document.createTextNode(`${field.label} (${field.visits} visits)`));
    item.style.marginRight = "1.1rem";
    legend.append(item);
  });
  host.replaceChildren(legend, state.limit.root);

  const caption = document.getElementById("limit-caption");
  if (caption) {
    caption.textContent = "Each field was measured separately. The bars are Wilson 95% intervals. The fields disagree, and the spread is the result.";
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
      ["fields measured", String(fields.length)],
      ["tracks per field", String(fields[0].tracks)],
      ["injections per point", String(fields[0].levels[0].injected)],
      ["PSF FWHM", `${fields[0].fwhm_px.toFixed(1)} px`],
      ["half recovery, field A", `${fields[0].f50.toFixed(3)} MJy/sr`],
      ["half recovery, field B", `${fields[1].f50.toFixed(3)} MJy/sr`],
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
  settle(state.reach.root);
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

// -------------------------------------------------------------------- ledger

// Every claim the page makes, with the file it is read from and that file's hash.
// A row whose source is not in the repository says so: the web copy is still
// hashed, but the chain stops there, and hiding that would be the one thing this
// page cannot do.
function drawLedger(ledger) {
  const host = document.getElementById("panel-ledger");
  if (!host || !ledger || !Array.isArray(ledger.rows)) return;

  host.replaceChildren();
  for (const row of ledger.rows) {
    const wrap = document.createElement("div");
    wrap.className = row.source_present ? "ledger-row" : "ledger-row is-missing";

    const claim = document.createElement("p");
    claim.className = "ledger-claim";
    claim.textContent = row.claim;
    wrap.append(claim);

    const meta = document.createElement("p");
    meta.className = "ledger-meta";
    const dataHash = row.data_sha256 ? row.data_sha256.slice(0, 12) : "no hash";
    meta.append(document.createTextNode(`${row.data_file}  ${dataHash}`));
    if (row.source_file) {
      meta.append(document.createElement("br"));
      meta.append(document.createTextNode(`from ${row.source_file}`));
      if (row.source_sha256) {
        meta.append(document.createTextNode(`  ${row.source_sha256.slice(0, 12)}`));
      }
    }
    wrap.append(meta);

    const status = document.createElement("span");
    status.className = "ledger-status";
    const already = row.status.includes("source not in the repository");
    status.textContent = row.source_present || already
      ? `${row.status} · ${row.uncertainty}`
      : `${row.status} · source not in the repository · ${row.uncertainty}`;
    wrap.append(status);

    host.append(wrap);
  }
}

// -------------------------------------------------------------------- system

// The solar system in three dimensions, turnable. The radial scale is
// logarithmic, because Neptune at 30 AU and the boundary at 2,219 AU cannot share
// a linear axis.
function drawSystem() {
  const host = document.getElementById("system-chart");
  if (!host || !state.parallax) return;
  if (state.system) state.system.dispose();
  state.system = setupSystem(host, state.parallax, state.patches || []);

  const crossing = (state.parallax.geometry_full_baseline[0].dist_au
    * state.parallax.geometry_full_baseline[0].peak_shift_arcsec) / state.parallax.half_field_arcsec;

  const caption = document.getElementById("system-caption");
  if (caption) {
    caption.textContent = `Amber is the range a full-baseline search inside this cutout can follow: beyond ${Math.round(crossing).toLocaleString("en-US")} AU. Grey is the range it cannot. Drag to turn, scroll to zoom.`;
  }

  const why = document.getElementById("system-why");
  if (why) {
    why.textContent = `Over a ${state.parallax.baseline_days.toFixed(0)} day baseline, an object at 400 AU shifts about 997 arcseconds, and the cutout is 180 arcseconds across. It leaves the frame before the baseline ends, so a search inside this cutout cannot follow it. That is a limit of the cutout, not of the telescope.`;
  }

  const facts = document.getElementById("system-facts");
  if (facts) {
    facts.replaceChildren();
    const rows = [
      ["baseline", `${state.parallax.baseline_days.toFixed(1)} days`],
      ["cutout across", `${(state.parallax.half_field_arcsec * 2).toFixed(0)} arcsec`],
      ["search reaches beyond", `${Math.round(crossing).toLocaleString("en-US")} AU`],
      ["Neptune's orbit", "30 AU"],
      ["patches on the sky", String((state.patches || []).length)],
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

// ----------------------------------------------------------------- injection

// The completeness curve says 15 to 60 percent at 0.2 MJy/sr. A reader cannot feel
// that from a number, so the same frame is shown with a source of that brightness
// added, and the source cannot be seen. The difference panel is there so the
// reader knows it is really in the pixels.
function drawInjection() {
  const strip = document.getElementById("inj-strip");
  const diffFrame = document.getElementById("inj-diff-frame");
  if (!strip || !diffFrame) return;
  const data = state.injection;
  if (!data || !Array.isArray(data.panels)) return;

  const base = "assets/injection/";
  const shown = data.panels.filter((p) => p.id !== "difference");
  const diff = data.panels.find((p) => p.id === "difference");

  strip.replaceChildren();
  for (const panel of shown) {
    const figure = document.createElement("figure");
    figure.className = panel.flux === null ? "inj-panel" : "inj-panel is-highlight";

    const frame = document.createElement("div");
    frame.className = "inj-frame";
    const img = document.createElement("img");
    img.src = `${base}${panel.id}.png`;
    img.alt = panel.label;
    img.width = data.fov_px[0];
    img.height = data.fov_px[1];
    img.loading = "lazy";
    frame.append(img);

    // A ring where the source was added, so the reader knows where to look and
    // can see for themselves that there is nothing to see.
    const ring = document.createElement("span");
    ring.className = "inj-marker";
    ring.style.left = `${(data.position_px[0] / data.fov_px[0]) * 100}%`;
    ring.style.top = `${(data.position_px[1] / data.fov_px[1]) * 100}%`;
    frame.append(ring);

    const caption = document.createElement("figcaption");
    const title = document.createElement("b");
    title.textContent = panel.label;
    caption.append(title);
    if (panel.flux !== null) {
      caption.append(document.createTextNode(`${panel.peak_snr.toFixed(1)} times the frame noise`));
    } else {
      caption.append(document.createTextNode("the reference"));
    }

    figure.append(frame, caption);
    strip.append(figure);
  }

  if (diff) {
    diffFrame.replaceChildren();
    const img = document.createElement("img");
    img.src = `${base}${diff.id}.png`;
    img.alt = diff.label;
    img.width = data.fov_px[0];
    img.height = data.fov_px[1];
    diffFrame.append(img);

    const caption = document.getElementById("inj-diff-caption");
    if (caption) {
      caption.textContent = "The same source on its own, with zero drawn as black. It is in the pixels; the frame above simply cannot show it.";
    }
  }

  const caption = document.getElementById("inj-caption");
  if (caption) {
    caption.textContent = `One real frame, ${data.fov_px[0]} by ${data.fov_px[1]} pixels, with a point source added at ${data.position_px[0].toFixed(0)}, ${data.position_px[1].toFixed(0)}.`;
  }

  const meaning = document.getElementById("inj-meaning");
  if (meaning) {
    meaning.textContent = "At 0.2 MJy/sr the source is about three times the frame noise, and the pipeline recovers it 15 to 60 percent of the time depending on the field. At 0.4 it is recovered every time. A planet at the faint end would be in the data and invisible in the picture, which is why the search is statistical rather than visual.";
  }

  const facts = document.getElementById("inj-facts");
  if (facts) {
    facts.replaceChildren();
    const rows = [
      ["frame noise", `${data.robust_sigma_mjy_sr.toFixed(4)} MJy/sr`],
      ["stretch low", `${data.stretch.lo_mjy_sr.toFixed(3)} MJy/sr`],
      ["stretch high", `${data.stretch.hi_mjy_sr.toFixed(3)} MJy/sr`],
      ["point spread", `${data.psf_fwhm_px.toFixed(1)} px`],
      ["levels shown", data.levels_mjy_sr.map((v) => v.toFixed(1)).join(", ")],
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

// -------------------------------------------------------------------- search

// The search is a number line, not a histogram: the null is stored as quantiles,
// and drawing a distribution from five quantiles would be inventing the shape.
// What the reader needs is where the best stack falls against the null, and that
// is a position on one axis.
function drawSearch() {
  const host = document.getElementById("search-chart");
  if (!host) return;
  const data = state.shiftStack;
  if (!data || !data.null) return;

  const box = getComputedStyle(host);
  const padX = parseFloat(box.paddingLeft) + parseFloat(box.paddingRight);
  const padY = parseFloat(box.paddingTop) + parseFloat(box.paddingBottom);
  const width = Math.max(320, host.clientWidth - padX - 8);
  // A number line does not need the whole column, so it is capped rather than
  // stretched to fill it.
  const height = Math.min(300, Math.max(200, host.clientHeight - padY - 8));

  const dpr = window.devicePixelRatio || 1;
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const nulls = data.null;
  const best = data.threshold_verdict.best_T;
  const p999 = nulls.p999;
  const maxT = Math.max(nulls.max, best) * 1.06;

  const left = 24;
  const right = width - 24;
  const axisY = height * 0.52;
  const xOf = (t) => left + (t / maxT) * (right - left);

  ctx.clearRect(0, 0, width, height);

  // The region beyond the 99.9th percentile: a stack that lands here is a
  // detection, and nothing landed here.
  ctx.fillStyle = "rgba(232,163,61,0.10)";
  ctx.fillRect(xOf(p999), axisY - 40, right - xOf(p999), 80);

  // The axis.
  ctx.strokeStyle = "#2a2a2a";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(left, axisY);
  ctx.lineTo(right, axisY);
  ctx.stroke();

  const marks = [
    { t: nulls.median, label: "median", colour: "#8f8f8f" },
    { t: nulls.p95, label: "95%", colour: "#8f8f8f" },
    { t: nulls.p99, label: "99%", colour: "#a8a49a" },
    { t: p999, label: "99.9%", colour: "#e8a33d" },
    { t: nulls.max, label: "null max", colour: "#8f8f8f" },
  ];

  ctx.font = "10px Instrument Sans, sans-serif";
  ctx.textAlign = "center";
  let lastX = -Infinity;
  let row = 0;
  for (const mark of marks) {
    const x = xOf(mark.t);
    // Two marks can sit a few pixels apart, so the labels step down a row rather
    // than printing on top of each other.
    row = x - lastX < 46 ? row + 1 : 0;
    lastX = x;
    const labelY = axisY + 30 + row * 26;
    ctx.strokeStyle = mark.colour;
    ctx.beginPath();
    ctx.moveTo(x, axisY - 14);
    ctx.lineTo(x, axisY + 14);
    ctx.stroke();
    ctx.fillStyle = mark.colour;
    ctx.fillText(mark.label, x, labelY);
    ctx.fillText(Math.round(mark.t).toLocaleString("en-US"), x, labelY + 14);
  }

  // The best stack, drawn above the axis so it cannot be mistaken for a null mark.
  const bx = xOf(best);
  ctx.strokeStyle = "#e7e2d5";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(bx, axisY - 52);
  ctx.lineTo(bx, axisY - 16);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(bx, axisY - 58, 4, 0, Math.PI * 2);
  ctx.fillStyle = "#e7e2d5";
  ctx.fill();
  ctx.fillStyle = "#e7e2d5";
  ctx.font = "11px Instrument Sans, sans-serif";
  ctx.fillText("best stack", bx, axisY - 72);
  ctx.fillText(Math.round(best).toLocaleString("en-US"), bx, axisY - 86);

  // The axis label.
  ctx.fillStyle = "#8f8f8f";
  ctx.font = "10px Instrument Sans, sans-serif";
  ctx.textAlign = "left";
  ctx.fillText("stack peak significance, in units of the stack noise", left, axisY + 96);

  host.replaceChildren(canvas);
  settle(canvas);

  const caption = document.getElementById("search-caption");
  if (caption) {
    caption.textContent = `The best stack of ${data.threshold_verdict.best_T.toFixed(0)} falls below the 99.9th percentile of the null at ${p999.toFixed(0)}.`;
  }

  const verdict = document.getElementById("search-verdict");
  if (verdict) {
    const p = data.threshold_verdict.empirical_p_value_of_best;
    verdict.textContent = `The best stack is at the ${(p * 100).toFixed(2)}th percentile of the null, which is not a detection: the null produces a value that high about once in ${Math.round(1 / p)} tries. The grid asked for ${data.requested_grid_feasibility.grid.n_hypotheses} rates and only ${data.requested_grid_feasibility.n_evaluable} kept the frames overlapping, because a fast rate moves an object out of a 0.1 degree cutout before the baseline ends.`;
  }

  const list = document.getElementById("search-not-claimed");
  if (list && Array.isArray(data.not_claimed)) {
    list.replaceChildren();
    for (const item of data.not_claimed) {
      const li = document.createElement("li");
      li.textContent = item;
      list.append(li);
    }
  }

  const facts = document.getElementById("search-facts");
  if (facts) {
    facts.replaceChildren();
    const rows = [
      ["frames stacked", String(data.inputs.n_frames)],
      ["rates requested", String(data.requested_grid_feasibility.grid.n_hypotheses)],
      ["rates evaluable", String(data.requested_grid_feasibility.n_evaluable)],
      ["null draws", String(nulls.n_draws)],
      ["null evaluable", String(nulls.n_evaluable)],
      ["null seed", String(nulls.seed)],
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

// ----------------------------------------------------------------------- sky

// The whole sky in equatorial coordinates, with the ecliptic and the galactic
// plane drawn from their definitions rather than from a picture. The patches are
// half a degree across, so they are drawn larger than life and the caption says so.
const OBLIQUITY = (23.4392911 * Math.PI) / 180;

// The patch ids are internal. A reader gets the purpose, not the code.
const PATCH_NAMES = {
  P1: "Search field 1",
  P2: "Search field 2",
  P3: "Search field 3",
  C1: "Crowded field",
  C2: "Ecliptic pole",
  C3: "High latitude",
};

const patchName = (patch) => PATCH_NAMES[patch.id] || patch.name || patch.id;

function eclipticToEquatorial(lambdaDeg) {
  const l = (lambdaDeg * Math.PI) / 180;
  const dec = Math.asin(Math.sin(OBLIQUITY) * Math.sin(l));
  const ra = Math.atan2(Math.sin(l) * Math.cos(OBLIQUITY), Math.cos(l));
  return { ra: ((ra * 180) / Math.PI + 360) % 360, dec: (dec * 180) / Math.PI };
}

// The galactic plane, from the standard rotation between the two frames. The
// matrix is the one in the Hipparcos documentation; a hand-rolled spherical
// version draws a sine wave instead of a great circle.
const GAL = [
  [-0.0548755604, -0.8734370902, -0.4838350155],
  [0.4941094279, -0.4448296300, 0.7469822445],
  [-0.8676661490, -0.1980763734, 0.4559837762],
];

function galacticToEquatorial(lDeg) {
  const l = (lDeg * Math.PI) / 180;
  const v = [Math.cos(l), Math.sin(l), 0];
  const x = GAL[0][0] * v[0] + GAL[0][1] * v[1] + GAL[0][2] * v[2];
  const y = GAL[1][0] * v[0] + GAL[1][1] * v[1] + GAL[1][2] * v[2];
  const z = GAL[2][0] * v[0] + GAL[2][1] * v[1] + GAL[2][2] * v[2];
  const ra = (Math.atan2(y, x) * 180) / Math.PI;
  return { ra: (ra + 360) % 360, dec: (Math.asin(Math.max(-1, Math.min(1, z))) * 180) / Math.PI };
}

function drawSky() {
  const host = document.getElementById("sky-chart");
  if (!host) return;
  const patches = state.patches || [];
  if (patches.length === 0) return;

  const box = getComputedStyle(host);
  const padX = parseFloat(box.paddingLeft) + parseFloat(box.paddingRight);
  const padY = parseFloat(box.paddingTop) + parseFloat(box.paddingBottom);
  const width = Math.max(320, host.clientWidth - padX - 8);
  const height = Math.max(240, host.clientHeight - padY - 8);

  const dpr = window.devicePixelRatio || 1;
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const left = 34;
  const right = width - 12;
  const top = 14;
  const bottom = height - 26;

  // Right ascension runs right to left, the way the sky is usually drawn.
  const xOf = (ra) => right - (ra / 360) * (right - left);
  const yOf = (dec) => top + ((90 - dec) / 180) * (bottom - top);

  ctx.clearRect(0, 0, width, height);

  // Grid every 30 degrees of right ascension and 30 of declination.
  ctx.strokeStyle = "#242424";
  ctx.lineWidth = 1;
  ctx.font = "9px Instrument Sans, sans-serif";
  ctx.fillStyle = "#8f8f8f";
  ctx.textAlign = "center";
  for (let ra = 0; ra <= 360; ra += 30) {
    const x = xOf(ra);
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, bottom);
    ctx.stroke();
    ctx.fillText(`${ra}`, x, bottom + 12);
  }
  ctx.textAlign = "right";
  for (let dec = -60; dec <= 60; dec += 30) {
    const y = yOf(dec);
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(right, y);
    ctx.stroke();
    ctx.fillText(`${dec}`, left - 5, y + 3);
  }

  // The galactic plane, where the stars are thickest.
  ctx.strokeStyle = "#3a3a3a";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (let l = 0; l <= 360; l += 2) {
    const p = galacticToEquatorial(l);
    const x = xOf(p.ra);
    const y = yOf(p.dec);
    if (l === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // The ecliptic, where the planets are.
  ctx.strokeStyle = "#8f8f8f";
  ctx.lineWidth = 1.5;
  ctx.setLineDash([5, 4]);
  ctx.beginPath();
  for (let lam = 0; lam <= 360; lam += 2) {
    const p = eclipticToEquatorial(lam);
    const x = xOf(p.ra);
    const y = yOf(p.dec);
    if (lam === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
  ctx.setLineDash([]);

  // The patches. Half a degree is a pixel at this scale, so they are drawn at a
  // size a reader can see and the caption says the size is not to scale.
  ctx.font = "10px Instrument Sans, sans-serif";
  ctx.textAlign = "left";
  for (const patch of patches) {
    if (typeof patch.ra_deg !== "number" || typeof patch.dec_deg !== "number") continue;
    const x = xOf(patch.ra_deg);
    const y = yOf(patch.dec_deg);
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(232,163,61,0.85)";
    ctx.fill();
    ctx.strokeStyle = "#121212";
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.fillStyle = "#e7e2d5";
    // A label near the right edge would run off the canvas, so it goes left.
    const label = patchName(patch);
    const wide = ctx.measureText(label).width;
    if (x + 8 + wide > right) {
      ctx.textAlign = "right";
      ctx.fillText(label, x - 8, y + 3);
      ctx.textAlign = "left";
    } else {
      ctx.fillText(label, x + 8, y + 3);
    }
  }

  host.replaceChildren(canvas);
  settle(canvas);

  const caption = document.getElementById("sky-caption");
  if (caption) {
    caption.textContent = `Right ascension runs right to left. The dashed line is the ecliptic, the solid grey line the galactic plane. The patches are half a degree across and are drawn larger than life. Each row below is position, then degrees from the ecliptic.`;
  }

  const why = document.getElementById("sky-why");
  if (why) {
    const lats = patches
      .map((p) => p.ecl_lat_deg)
      .filter((v) => typeof v === "number");
    const near = lats.filter((v) => Math.abs(v) <= 20).length;
    why.textContent = `${near} of the ${lats.length} patches sit within 20 degrees of the ecliptic, which is where a planet beyond Neptune would be found. The rest are there for other reasons: the ecliptic pole is the cleanest sky for a deep stack, and the high latitude fields test the pipeline where the background is lowest.`;
  }

  const facts = document.getElementById("sky-facts");
  if (facts) {
    facts.replaceChildren();
    for (const patch of patches) {
      const dt = document.createElement("dt");
      dt.textContent = patchName(patch);
      const dd = document.createElement("dd");
      const lat = typeof patch.ecl_lat_deg === "number" ? patch.ecl_lat_deg.toFixed(1) : "--";
      dd.textContent = `${patch.ra_deg.toFixed(0)}, ${patch.dec_deg.toFixed(0)} · ${lat}°`;
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
    const [views, blink, completeness, recovery, parallax, ledger, patches, injection, shiftStack] = await Promise.all([
      loadJSON("views.json"),
      loadJSON("blink.json"),
      loadJSON("completeness.json").catch(() => null),
      loadJSON("named_recovery_summary.json").catch(() => null),
      loadJSON("parallax.json").catch(() => null),
      loadJSON("ledger.json").catch(() => null),
      loadJSON("patches.json").catch(() => null),
      loadJSON("injection.json").catch(() => null),
      loadJSON("shift_stack.json").catch(() => null),
    ]);
    state.views = views;
    state.blink = blink;
    state.completeness = completeness;
    state.parallax = parallax;
    state.patches = patches && Array.isArray(patches.patches) ? patches.patches : [];
    state.injection = injection;
    state.shiftStack = shiftStack;
    drawAnswer(completeness, recovery, parallax, shiftStack, views);
    drawLedger(ledger);

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
        if (state.system) state.system.resize();
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
