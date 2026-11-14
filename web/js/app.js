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
