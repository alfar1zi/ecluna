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
  } catch (error) {
    const failure = document.createElement("li");
    failure.className = "object-row";
    failure.textContent = `The measurements could not be read: ${error.message}`;
    list.replaceChildren(failure);
  }
}

main();
