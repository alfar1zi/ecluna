// Ecluna — the object list is built from the measured files, never from a constant.
//
// Two sources: web/data/views.json carries the per-object measurements, and
// web/data/blink.json carries the frames. If a number is missing, the row says so
// instead of showing a zero.

const DATA = "data/";

async function loadJSON(name) {
  const response = await fetch(DATA + name, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${name}: ${response.status}`);
  return response.json();
}

function fmtPercent(value) {
  if (value === null || value === undefined) return null;
  // A change smaller than one part in a thousand is quoted as such rather than
  // as 0.0 percent, which would read as "no change at all".
  if (value < 0.001) return "<0.1";
  return (value * 100).toFixed(1);
}

function fmtNumber(value, digits = 1) {
  if (value === null || value === undefined) return null;
  return value.toFixed(digits);
}

function figure(value, unit, label, { unknown = "not resolved" } = {}) {
  const cell = document.createElement("div");
  const shown = value === null || value === undefined ? unknown : value;
  cell.className = "figure" + (value === null || value === undefined ? " is-unknown" : "");
  cell.textContent = unit ? `${shown}\u2009${unit}` : shown;
  const caption = document.createElement("span");
  caption.textContent = label;
  cell.append(caption);
  return cell;
}

function row(object, frames) {
  const item = document.createElement("li");
  item.className = "object-row";

  const name = document.createElement("div");
  name.className = "object-name";
  name.textContent = object.name;
  const sub = document.createElement("small");
  const covers = frames ? `, ${frames} frames ready to flip` : "";
  sub.textContent = `${object.n_epochs} visits${covers}`;
  name.append(sub);

  const motion = object.track_map && object.track_map.span_px;
  const change = object.stability
    ? fmtPercent(object.stability.smallest_sustained_change_fraction)
    : null;
  const limit = object.stability ? fmtNumber(object.stability.limit_threshold, 1) : null;

  item.append(
    name,
    figure(motion === null || motion === undefined ? null : fmtNumber(motion, 2), "px",
      "motion across the series"),
    figure(change, "%", "smallest change resolved"),
    figure(limit, null, "detection threshold"),
  );
  return item;
}

async function main() {
  const list = document.getElementById("object-list");
  if (!list) return;

  try {
    const [views, blink] = await Promise.all([
      loadJSON("views.json"),
      loadJSON("blink.json"),
    ]);

    const framesById = new Map(
      blink.objects.map((o) => [o.id, (o.frames || []).length]),
    );
    // The identifier differs for one object: the page calls it epsindb, the data
    // folder calls it epsindib.
    const blinkId = (id) => (id === "epsindb" ? "epsindib" : id);

    const rows = views.objects.map((object) =>
      row(object, framesById.get(blinkId(object.id))));
    list.replaceChildren(...rows);

    setupBlink(blink);
    setupCurve(views);
  } catch (error) {
    const failure = document.createElement("li");
    failure.className = "object-row";
    failure.textContent = `The measurements could not be read: ${error.message}`;
    list.replaceChildren(failure);
  }
}

main();

// Blink: one frame at a time, driven by the slider or by play.
//
// The frames are pre-rendered PNGs on a common grid, so flipping them shows the
// object against a fixed background. Playback stops on its own after one pass
// rather than looping, because a loop that never ends is noise.

const BLINK_INTERVAL_MS = 260;

function setupBlink(blink) {
  const select = document.getElementById("blink-object");
  const range = document.getElementById("blink-range");
  const play = document.getElementById("blink-play");
  const frame = document.getElementById("blink-frame");
  const caption = document.getElementById("blink-caption");
  if (!select || !range || !play || !frame || !caption) return;

  const objects = blink.objects.filter((o) => (o.frames || []).length > 1);
  if (objects.length === 0) {
    caption.textContent = "No object has more than one visit in this build.";
    return;
  }

  let current = objects[0];
  let index = 0;
  let timer = null;

  const label = (o) => {
    const n = o.frames.length;
    return `${o.id === "epsindib" ? "Epsilon Indi B" : o.id} — ${n} visits`;
  };

  for (const object of objects) {
    const option = document.createElement("option");
    option.value = object.id;
    option.textContent = label(object);
    select.append(option);
  }

  function show(i) {
    index = Math.max(0, Math.min(i, current.frames.length - 1));
    const f = current.frames[index];
    frame.src = f.png;
    frame.alt = `Visit ${index + 1} of ${current.frames.length}, MJD ${f.mjd_label}.`;
    range.value = String(index);
    caption.textContent =
      `Visit ${index + 1} of ${current.frames.length} · MJD ${f.mjd_label}`;
  }

  function stop() {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
      play.textContent = "Play";
    }
  }

  function start() {
    if (timer !== null) return;
    if (index >= current.frames.length - 1) index = -1;
    play.textContent = "Pause";
    timer = setInterval(() => {
      if (index >= current.frames.length - 1) {
        stop();
        return;
      }
      show(index + 1);
    }, BLINK_INTERVAL_MS);
  }

  select.addEventListener("change", () => {
    stop();
    current = objects.find((o) => o.id === select.value) || objects[0];
    range.max = String(current.frames.length - 1);
    show(0);
  });

  range.addEventListener("input", () => {
    stop();
    show(Number(range.value));
  });

  play.addEventListener("click", () => {
    if (timer === null) start();
    else stop();
  });

  range.max = String(current.frames.length - 1);
  show(0);
}

// Light curve: one point per visit, with the visit's own noise as a bar.
//
// The question is "did the brightness change", so the chart shows brightness
// against time and nothing else. The numbers beside it carry what a line cannot:
// how many visits, how large a change the series would have resolved, and whether
// the object was detected at all.

const CURVE_NAMES = {
  barnard: "Barnard's Star",
  epsindb: "Epsilon Indi B",
  wise0855: "WISE 0855",
  rwaur: "RW Aurigae",
  rdra: "R Draconis",
};

function curveFacts(object) {
  const lc = object.light_curve;
  const st = object.stability;
  const rows = [
    ["Visits", String(lc.visits)],
    ["Baseline", `${lc.baseline_days} days`],
    ["Detected at", lc.detection_sigma === null
      ? "not resolved"
      : `${lc.detection_sigma} sigma`],
    ["Smallest change resolved", st.smallest_sustained_change_fraction === null
      ? "not resolved"
      : `${(st.smallest_sustained_change_fraction * 100).toFixed(1)} percent`],
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
  return list;
}

function setupCurve(views) {
  const host = document.getElementById("curve-chart");
  const select = document.getElementById("curve-object");
  const facts = document.getElementById("curve-facts");
  if (!host || !select || !facts) return;
  if (typeof uPlot !== "function") {
    host.textContent = "The chart library did not load.";
    return;
  }

  const objects = views.objects.filter((o) => o.light_curve.visits > 1);
  if (objects.length === 0) {
    host.textContent = "No object has more than one visit in this build.";
    return;
  }

  for (const object of objects) {
    const option = document.createElement("option");
    option.value = object.id;
    option.textContent = CURVE_NAMES[object.id] || object.name;
    select.append(option);
  }

  let chart = null;

  function draw(object) {
    const lc = object.light_curve;
    // Visits are not evenly spaced in time: Barnard has a dense run in 2025 and a
    // few in 2026, so plotting against the date compresses the first run into a
    // flat line. The question is whether the brightness changed between visits, so
    // the axis is the visit number and the dates stay in the caption.
    const xs = lc.mjd.map((_, i) => i + 1);
    const ys = lc.flux_mjy_sr_px;
    const noise = lc.per_visit_noise_mjy_sr_px;

    // The bar is the visit's own noise, drawn as a band rather than a whisker so
    // the eye reads it as "this much is not a change".
    const upper = ys.map((v, i) => v + noise[i]);
    const lower = ys.map((v, i) => v - noise[i]);

    const data = [xs, ys, upper, lower];
    const width = Math.max(320, host.clientWidth || 640);
    const options = {
      width,
      height: 320,
      padding: [12, 12, 0, 0],
      cursor: { drag: { x: true, y: false } },
      scales: { x: { time: false } },
      tooltips: undefined,
      axes: [
        {
          stroke: "#9aa8c0",
          grid: { stroke: "#1d3357", width: 1 },
          ticks: { stroke: "#1d3357" },
          font: "11px Instrument Sans, sans-serif",
          label: "visit number",
          labelSize: 22,
          labelFont: "11px Instrument Sans, sans-serif",
        },
        {
          stroke: "#9aa8c0",
          grid: { stroke: "#1d3357", width: 1 },
          ticks: { stroke: "#1d3357" },
          font: "11px Instrument Sans, sans-serif",
          label: "brightness",
          labelSize: 20,
          labelFont: "11px Instrument Sans, sans-serif",
          size: 64,
        },
      ],
      legend: { show: false },
      series: [
        {},
        {
          label: "brightness",
          stroke: "#e7e2d5",
          width: 2,
          points: { show: true, size: 7, fill: "#e7e2d5", stroke: "#08152b", width: 1 },
        },
        { label: "noise upper", stroke: "rgba(232,163,61,0.35)", width: 1, points: { show: false } },
        { label: "noise lower", stroke: "rgba(232,163,61,0.35)", width: 1, points: { show: false } },
      ],
    };

    if (chart) chart.destroy();
    chart = new uPlot(options, data, host);
    facts.replaceChildren(curveFacts(object));
  }

  select.addEventListener("change", () => {
    const object = objects.find((o) => o.id === select.value) || objects[0];
    draw(object);
  });

  // The chart is drawn at a fixed pixel width, so it is redrawn when the column
  // changes size rather than stretched. The first draw waits for layout, because
  // the column has no width before the stylesheet has been applied.
  let pending = null;
  const redraw = () => {
    if (pending) clearTimeout(pending);
    pending = setTimeout(() => {
      const object = objects.find((o) => o.id === select.value) || objects[0];
      draw(object);
    }, 120);
  };

  if (typeof ResizeObserver === "function") {
    new ResizeObserver(redraw).observe(host);
  } else {
    window.addEventListener("resize", redraw);
  }

  requestAnimationFrame(() => draw(objects[0]));
}
