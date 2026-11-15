/* Ecluna SPHEREx time-domain explorer.
   Reads only local JSON and PNG assets. No runtime network calls. */

const state = {
  images: [],
  diffs: [],
  index: 0,
  playing: false,
  timer: null,
  fps: 4,
  mode: "single",
  cmpA: 0,
  cmpB: 0,
  diffIndex: 0,
  lang: "en",
  objects: [],
  obj: null,
  coord: null,
  coverage: null,
  patches: [],
  patchRadiusDeg: null,
  alignment: null,
  series: null,
  seriesVariant: null,
  seriesRecovery: null,
  seriesObj: null,
  seriesChain: "main",
  seriesIndex: 0,
  seriesPlaying: false,
  seriesTimer: null,
  seriesFps: 2,
};

const reduceMotion = () => window.matchMedia
  && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

/* Certainty markers, DESIGN_SYSTEM.md section 3. Shape plus text plus colour, never colour alone. */
const MARK_LABEL = {
  measured: { en: "measured" },
  projected: { en: "projected" },
  unknown: { en: "not known" },
};

const FIELD_LABELS = {
  P1: "South Ecliptic Pole",
  P2: "South Ecliptic Mid-Latitude",
  P3: "North Ecliptic High-Latitude",
  C1: "North Ecliptic Pole",
  C2: "North Ecliptic Deep Field",
  C3: "South Galactic Cap",
};

function fieldDisplayName(p) {
  if (!p) return "n/a";
  if (typeof p === "string") return FIELD_LABELS[p] || "Listed sky field";
  return FIELD_LABELS[p.id] || "Listed sky field";
}

function cutoutDisplayName(file, index) {
  const s = String(file || "");
  if (s.includes("_p2_a")) return "South Ecliptic Mid-Latitude, cutout A";
  if (s.includes("_p2_b")) return "South Ecliptic Mid-Latitude, cutout B";
  return `Reference cutout ${index + 1}`;
}

function translateVerdict(raw) {
  const v = String(raw || "").trim();
  if (!v) return "Not available";
  if (v === "PULIH (jenuh)") return "Recovered (bright core saturated)";
  if (v === "PULIH") return "Recovered";
  if (v.startsWith("PULIH")) return "Recovered";
  if (v === "TIDAK PULIH") return "Not recovered";
  if (v.startsWith("TIDAK PULIH")) return "Not recovered";
  if (v === "TIDAK DIEVALUASI") return "Not evaluated";
  if (v.startsWith("TIDAK DIEVALUASI")) return "Not evaluated";
  return v;
}

function translateVerdictShort(raw) {
  const v = String(raw || "").trim();
  if (!v) return "";
  if (v.startsWith("PULIH")) return "Recovered";
  if (v.startsWith("TIDAK PULIH")) return "Not recovered";
  if (v.startsWith("TIDAK DIEVALUASI")) return "Not evaluated";
  return v.split(" (")[0];
}

function translateGateStatus(raw) {
  const v = String(raw || "").trim().toUpperCase();
  if (v === "FAIL" || v === "GAGAL") return "Not passed";
  if (v === "PASS" || v === "LULUS") return "Passed";
  return raw ? String(raw) : "Not measured";
}

function cleanSourceLabel(sourceStr) {
  const s = String(sourceStr || "");
  if (!s) return "Catalog reference";
  if (s.includes("SIMBAD")) return "SIMBAD astronomical catalog (J2000)";
  if (s.includes("challenge statement")) return "NASA Space Apps 2026 challenge coordinates";
  return "Recorded astronomical catalog";
}

function markerHTML(level, textOverride) {
  const lv = MARK_LABEL[level] ? level : "unknown";
  const label = textOverride || MARK_LABEL[lv].en;
  return `<span class="mark mark-${lv}"><span class="mark-shape" aria-hidden="true"></span>` +
         `<span class="mark-text">${escapeAttr(label)}</span></span>`;
}
/* One marker level per row, so a reader can tell measured from projected from absent. */
function tableMarker(td) {
  return `<td class="cell-mark">${markerHTML(td, null)}</td>`;
}

async function loadJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

function fmt(v, digits = 4) {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  if (typeof v !== "number") return String(v);
  return v.toFixed(digits);
}

/* ---------- single viewer ---------- */

function renderFrame() {
  const img = state.images[state.index];
  if (!img) return;
  if (state.coverage && state.coverage.level !== "frames") return;
  $("#stage-img").src = `assets/img/${img.file}`;
  $("#stage-img").alt = `Aligned SPHEREx exposure observed ${img.date_utc}`;
  $("#epoch-label").textContent = `${img.date_utc}  MJD ${fmt(img.mjd, 3)}`;
  $("#epoch-counter").textContent = `${state.index + 1}/${state.images.length}`;
  $("#epoch-slider").value = state.index;
  $("#epoch-slider").setAttribute("aria-valuetext",
    `${state.index + 1} of ${state.images.length}, ${img.date_utc}`);
}

/* One 400 ms opacity fade per epoch change, DESIGN_SYSTEM section 5. Never an animation of numbers. */
function blinkOnce(imgEl) {
  if (!imgEl || reduceMotion()) return;
  imgEl.classList.add("is-fading");
  setTimeout(() => imgEl.classList.remove("is-fading"), 120);
}

function play() {
  if (state.playing) return;
  if (state.coverage && state.coverage.level !== "frames") return;
  state.playing = true;
  $("#btn-play").textContent = "Pause sequence";
  $("#btn-play").setAttribute("aria-pressed", "true");
  $("#btn-play").classList.add("active");
  state.timer = setInterval(() => {
    state.index = (state.index + 1) % state.images.length;
    renderFrame();
    blinkOnce($("#stage-img"));
  }, 1000 / state.fps);
}

function pause() {
  state.playing = false;
  $("#btn-play").textContent = "Play sequence";
  $("#btn-play").setAttribute("aria-pressed", "false");
  $("#btn-play").classList.remove("active");
  clearInterval(state.timer);
}
function togglePlay() {
  state.playing ? pause() : play();
}

/* ---------- compare viewer ---------- */

function renderCompare(side) {
  const idx = side === "a" ? state.cmpA : state.cmpB;
  const img = state.images[idx];
  if (!img) return;
  $(`#cmp-img-${side}`).src = `assets/img/${img.file}`;
  $(`#cmp-label-${side}`).textContent = `${img.date_utc}`;
  $(`#cmp-counter-${side}`).textContent = `${idx + 1}/${state.images.length}`;
  $(`#cmp-slider-${side}`).value = idx;
}

/* ---------- difference viewer ---------- */

function renderDiff() {
  const d = state.diffs[state.diffIndex];
  if (!d) return;
  $("#diff-img").src = `assets/img/${d.file}`;
  $("#diff-label").textContent = `${d.epoch_a} to ${d.epoch_b}`;
  $("#diff-counter").textContent = `${state.diffIndex + 1}/${state.diffs.length}`;
  $("#diff-slider").value = state.diffIndex;
  const meta = $("#diff-meta");
  if (!meta) return;
  meta.innerHTML = `
    <div class="meta-row"><dt>Observation A</dt><dd>${d.epoch_a}</dd></div>
    <div class="meta-row"><dt>Observation B</dt><dd>${d.epoch_b}</dd></div>
    <div class="meta-row"><dt>Time span (days)</dt><dd>${fmt(d.mjd_b - d.mjd_a, 3)}</dd></div>
    <div class="meta-row"><dt>Display scale</dt><dd>${fmt(d.scale_mjy_sr, 4)} MJy/sr</dd></div>
    <div class="meta-row"><dt>Image size</dt><dd>${d.width} x ${d.height} px</dd></div>
  `;
}

/* ---------- mode switching ---------- */

function setMode(mode) {
  state.mode = mode;
  $$(".mode-tabs .btn").forEach((b) => {
    const active = b.dataset.mode === mode;
    b.classList.toggle("active", active);
    b.setAttribute("aria-selected", active ? "true" : "false");
  });
  $("#view-single").hidden = mode !== "single";
  $("#view-compare").hidden = mode !== "compare";
  $("#view-difference").hidden = mode !== "difference";
  if (mode !== "single") pause();
}
/* ---------- atlas table ---------- */

function renderAtlas(patches) {
  $("#atlas-body").innerHTML = patches.map((p) => {
    const av = p.area_valid_pct;
    const avText = av.value === null ? t("notMeasuredWord") : fmt(av.value, 2) + "%";
    return `<tr>
      <td>${escapeAttr(fieldDisplayName(p))}</td>
      <td class="num">${fmt(p.ra_deg, 3)}</td>
      <td class="num">${fmt(p.dec_deg, 3)}</td>
      <td class="num">${fmt(p.ecl_lat_deg, 2)}</td>
      <td class="num">${fmt(p.gal_lat_deg, 2)}</td>
      <td class="num">${p.n_exposures}</td>
      <td class="num">${p.n_dates}</td>
      <td class="num">${fmt(p.f_k15, 3)}</td>
      <td class="num">${(p.p_clear_n4 * 100).toFixed(2)}%</td>
      <td class="num">${(p.p_clear_n12 * 100).toFixed(2)}%</td>
      <td class="num">${avText}</td>
      ${tableMarker(av.status)}
    </tr>`;
  }).join("");
}

/* ---------- controls table ---------- */

function renderControls(controls) {
  $("#controls-body").innerHTML = controls.map((c, idx) => `<tr>
    <td>${escapeAttr(cutoutDisplayName(c.file, idx))}</td>
    <td class="num">${c.n_catalog_sources}</td>
    <td class="num">${c.n_accepted}</td>
    <td class="num">${fmt(c.median_offset_px, 3)}</td>
    <td class="num">${fmt(c.max_offset_px, 3)}</td>
    ${tableMarker("measured")}
  </tr>`).join("");
}
/* ---------- parallax table ---------- */

function renderParallax(par) {
  if (!par || !par.geometry_full_baseline) return;
  $("#parallax-body").innerHTML = par.geometry_full_baseline.map((g) => `<tr>
      <td class="num">${g.dist_au}</td>
      <td class="num">${g.peak_shift_arcsec.toFixed(1)}</td>
      <td class="num">${g.peak_shift_px.toFixed(1)}</td>
      ${tableMarker(g.stays_in_half_field ? "measured" : "projected")}
    </tr>`).join("");
  $("#parallax-note").textContent =
    `Geometric projection across a ${par.baseline_days}-day span with a ${par.half_field_arcsec} arcsec half-field. Objects closer than the widest field radius drift out of a small cutout over the full baseline, so wide-baseline searches require full-frame exposures.`;
  const intro = $("#parallax-intro");
  if (intro && par.baseline_days) {
    intro.textContent = t("parallaxIntro", {
      base: par.baseline_days, half: par.half_field_arcsec,
    });
  }
}

/* ---------- completeness table ---------- */

function renderCompleteness(c) {
  if (!c || !c.reported_curve) return;
  $("#completeness-body").innerHTML = c.reported_curve.map((r) => `<tr>
    <td class="num">${r.amplitude_mjy_sr.toFixed(3)}</td>
    <td class="num">${r.median_snr.toFixed(2)}</td>
    <td class="num">${r.n}</td>
    <td class="num">${r.recovered}</td>
    <td class="num">${(r.completeness * 100).toFixed(1)}%</td>
    <td class="num">[${(r.wilson95[0]*100).toFixed(1)}, ${(r.wilson95[1]*100).toFixed(1)}]%</td>
  </tr>`).join("");
  const nTrials = c.reported_curve[0] ? c.reported_curve[0].n : 0;
  $("#completeness-note").textContent =
    `Brightness is reported in MJy/sr per PSF-normalized injection (surface brightness). Converting to apparent magnitude requires an external zero-point calibration with a wide band-dependent range and is not claimed here. Horizontal chart axis: detection significance (peak divided by background scatter), independent of zero-point.`;
  renderCompletenessChart(c.reported_curve);
  const peak = c.reported_curve.reduce((a, b) => (b.completeness > a.completeness ? b : a));
  const leg = $("#completeness-legend");
  if (leg) {
    const half = c.reported_curve.find((r) => r.completeness >= 0.5);
    leg.innerHTML = markerHTML("measured") + " " +
      `<span class="t-small c-fg3">${escapeAttr(t("chartCaption", {
        sig: peak.median_snr.toFixed(2),
        pct: (peak.completeness * 100).toFixed(1),
        half: half ? half.median_snr.toFixed(2) : "n/a",
        n: nTrials,
      }))}</span>`;
  }
}

/* Measured curve only: connect the reported points, draw the 50 percent rule. */
function renderCompletenessChart(curve) {
  const host = $("#completeness-chart");
  if (!host || !curve || !curve.length) return;
  const W = 520, H = 300, L = 48, R = 16, T = 16, B = 40;
  const xs = curve.map((r) => r.median_snr);
  const xmin = 0;
  const xmax = Math.ceil(Math.max(...xs));
  const px = (v) => L + (v - xmin) / (xmax - xmin) * (W - L - R);
  const py = (v) => T + (1 - v) * (H - T - B);
  const pts = curve.map((r) => `${px(r.median_snr).toFixed(1)},${py(r.completeness).toFixed(1)}`).join(" ");
  const ticks = [];
  for (let v = 0; v <= xmax; v += 1) {
    ticks.push(`<line class="grid-line" x1="${px(v).toFixed(1)}" y1="${T}" x2="${px(v).toFixed(1)}" y2="${H - B}"/>` +
      `<text x="${px(v).toFixed(1)}" y="${H - B + 16}" text-anchor="middle">${v}</text>`);
  }
  for (const v of [0, 0.5, 1]) {
    ticks.push(`<text x="${L - 8}" y="${(py(v) + 4).toFixed(1)}" text-anchor="end">${(v * 100).toFixed(0)}%</text>`);
  }
  host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${escapeAttr(t("chartAlt"))}">
    ${ticks.join("")}
    <line class="axis" x1="${L}" y1="${T}" x2="${L}" y2="${H - B}"/>
    <line class="axis" x1="${L}" y1="${H - B}" x2="${W - R}" y2="${H - B}"/>
    <line class="half-rule" x1="${L}" y1="${py(0.5).toFixed(1)}" x2="${W - R}" y2="${py(0.5).toFixed(1)}"/>
    <polyline class="curve" points="${pts}"/>
    ${curve.map((r) => `<circle class="plot-dot" cx="${px(r.median_snr).toFixed(1)}" cy="${py(r.completeness).toFixed(1)}" r="2.5"/>`).join("")}
    <text x="${W - R}" y="${T + 4}" text-anchor="end">${escapeAttr(t("chartXAxis"))}</text>
  </svg>`;
}

/* ---------- shift-and-stack cards ---------- */

function renderShiftStack(s, thresholds) {
  if (!s || !s.threshold_verdict) return;
  const v = s.threshold_verdict;
  const feas = s.requested_grid_feasibility || {};
  const best = s.best_hypothesis || {};
  const nHyp = (feas.grid || {}).n_hypotheses || 0;
  const nEval = feas.n_evaluable || 0;
  const maxRate = (feas.max_rate_keeping_full_overlap_arcsec_per_h || 0).toFixed(4);
  const cards = [
    ["Strongest trial score vs background", v.best_T.toFixed(1), "measured",
      `Highest trial score ${v.best_T.toFixed(1)} compared with the 99.9th-percentile background reference (${v.empirical_threshold_p999.toFixed(1)}, n = ${v.n_null_trajectories || 0} background tracks). Exceeds reference: ${v.exceeds_empirical_p999 ? "yes" : "no"}.`],
    ["Moving-object verdict", v.detection ? "candidate" : "none", "measured",
      `No moving object detected. The strongest trial aligns with a stationary star (stationary-star share = ${best.static_source_fraction_above_5sigma !== undefined ? Number(best.static_source_fraction_above_5sigma).toFixed(2) : "n/a"}).`],
    ["Testable motion hypotheses", `${nEval}/${nHyp}`, "measured",
      `Only ${nEval} of ${nHyp} trial motion vectors keep overlapping sky pixels across the full time span; full overlap holds up to ${maxRate} arcsec/hour.`],
  ];
  if (thresholds) {
    const tk = thresholds.t_thr_kerja_P2 || {};
    const nb = thresholds.null_baru_P2 || {};
    const ar = thresholds.depth_gain_arsip || {};
    cards.push(
      ["Working comparison level (this run)", tk.value !== undefined ? Number(tk.value).toFixed(2) : "n/a", "measured",
        `Working reference level ${tk.value !== undefined ? Number(tk.value).toFixed(2) : "n/a"} on identical overlapping sky pixels. Used for exploratory comparison only, not a pass claim.`],
      ["Uncalibrated background ceiling", nb.value !== undefined ? Number(nb.value).toFixed(1) : "n/a", "unknown",
        `Raw background ceiling ${nb.value !== undefined ? Number(nb.value).toFixed(1) : "n/a"} recorded before final calibration. Displayed for transparency only, not used as a detection threshold.`],
      ["Archived depth-gain figure", ar.value !== undefined ? Number(ar.value).toFixed(2) : "n/a", "unknown",
        `Historical depth-gain ratio (${ar.value !== undefined ? Number(ar.value).toFixed(2) : "n/a"}) retained in the archive record and excluded from active claims.`],
    );
  }
  $("#shiftstack-cards").innerHTML = cards.map(([label, val, level, note]) => `
    <div class="card">
      <div class="finding-label t-micro">${escapeAttr(label)}</div>
      <div class="finding-value">${escapeAttr(val)}</div>
      <div class="finding-note">${escapeAttr(note)}</div>
      <div>${markerHTML(level)}</div>
    </div>`).join("");
  $("#shiftstack-note").textContent =
    `Motion trials must fit inside the overlapping cutout across the full observation span (up to ${maxRate} arcsec/hour for full overlap); faster motions walk off the small field and require wider images.`;
}
/* ---------- named object series viewer ---------- */

function seriesFor(objId) {
  if (!objId || !state.series || !Array.isArray(state.series.objects)) return null;
  return state.series.objects.find((o) => o.id === objId) || null;
}

function variantFor(objId) {
  const v = state.seriesVariant;
  if (!objId || !v || !Array.isArray(v.objects)) return null;
  const found = v.objects.find((o) => o.id === objId || o.variant_of === objId);
  return found || null;
}

function activeSeries() {
  if (!state.seriesObj) return null;
  if (state.seriesChain === "variant") return variantFor(state.seriesObj.id) || state.seriesObj;
  return state.seriesObj;
}

function recoveryFor(objId) {
  if (!objId || !state.seriesRecovery || !Array.isArray(state.seriesRecovery.objects)) return null;
  return state.seriesRecovery.objects.find((o) => o.id === objId) || null;
}

function fmtEm(lo, hi) {
  return `${fmt(lo, 4)} to ${fmt(hi, 4)} um`;
}

function mjdToIso(mjdVal) {
  if (typeof mjdVal !== "number" || !Number.isFinite(mjdVal)) return "";
  const ms = (mjdVal - 40587) * 86400000;
  return new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
}

function epochIsoFull(ep) {
  if (!ep) return "n/a";
  if (ep.date_obs) return String(ep.date_obs);
  const m = typeof ep.mjd_start === "number" ? ep.mjd_start : ep.mjd;
  return mjdToIso(m) || `MJD ${ep.mjd}`;
}

function epochDateStr(ep) {
  const iso = epochIsoFull(ep);
  return iso.length >= 10 && iso.includes("-") ? iso.slice(0, 10) : iso;
}

function seriesDateSpan(obj) {
  const eps = (obj && Array.isArray(obj.epochs)) ? obj.epochs : [];
  if (eps.length > 0) {
    const mjds = eps.map((e) => (typeof e.mjd_start === "number" ? e.mjd_start : e.mjd))
      .filter((v) => typeof v === "number" && Number.isFinite(v));
    if (mjds.length > 0) {
      const minM = Math.min(...mjds);
      const maxM = Math.max(...mjds);
      return {
        d0: mjdToIso(minM).slice(0, 10),
        d1: mjdToIso(maxM).slice(0, 10),
        base: Math.round(maxM - minM),
      };
    }
  }
  const dr = (obj && obj.date_range) || {};
  return {
    d0: dr.start_iso ? String(dr.start_iso).slice(0, 10) : "n/a",
    d1: dr.end_iso ? String(dr.end_iso).slice(0, 10) : "n/a",
    base: dr.baseline_days || 0,
  };
}

function epochLabel(ep) {
  return `${epochDateStr(ep)}  MJD ${ep.mjd}`;
}

function verdictTier(rec) {
  const v = String((rec && rec.verdict) || "");
  if (!rec) return "unknown";
  if (v.startsWith("PULIH")) return "measured";
  if (v.startsWith("TIDAK DIEVALUASI")) return "unknown";
  return "measured";
}

function renderSeriesFor(objId) {
  const obj = seriesFor(objId);
  const empty = $("#series-empty");
  if (!obj) {
    state.seriesObj = null;
    pauseSeries();
    renderSeriesEpoch();
    renderVerdict();
    empty.hidden = false;
    $("#series-empty-text").textContent = t(objId ? "seriesNone" : "seriesPick");
    $("#series-chain-note").hidden = true;
    $("#series-chains").hidden = true;
    return;
  }
  state.seriesObj = obj;
  state.seriesChain = "main";
  state.seriesIndex = 0;
  pauseSeries();
  empty.hidden = true;

  $("#series-obj-name").textContent = obj.name;
  $("#series-obj-coord").textContent =
    `RA ${obj.ra_str}  Dec ${obj.dec_str}  |  ${obj.band}  |  ${obj.stamp.npix} x ${obj.stamp.npix} px at ${obj.stamp.pixel_scale_arcsec} arcsec/px`;

  const agg = state.seriesRecovery && state.seriesRecovery.summary;
  const sum = $("#epochs-summary");
  const span = seriesDateSpan(obj);
  if (sum) {
    sum.textContent = agg && agg.n_objects && obj.epochs.length > 1
      ? t("epochsSummary", {
        n: obj.epochs.length, name: obj.name, base: span.base,
      })
      : t("epochsSummaryPlain", { n: obj.epochs.length, name: obj.name });
  }
  const variant = variantFor(obj.id);
  const chains = $("#series-chains");
  chains.hidden = !variant;
  if (variant) {
    $("#series-chain-label").textContent = t("chainLabel");
    $("#chain-btn-main").textContent = t("chainMain");
    $("#chain-btn-variant").textContent = t("chainVariant");
    setChainButtons("main");
  }
  renderChainNote(obj, variant);
  renderSeriesEpoch();
  renderSeriesIntro();
  renderLegend();
  renderVerdict();
  renderPresets();
}

function renderSeriesIntro() {
  const el = $("#series-obj-coord");
  if (!el) return;
  const obj = state.seriesObj;
  if (!obj) return;
  el.textContent =
    `RA ${obj.ra_str}  Dec ${obj.dec_str}  |  ${obj.band}  |  ${obj.stamp.npix} x ${obj.stamp.npix} px at ${obj.stamp.pixel_scale_arcsec} arcsec/px`;
}

function setChainButtons(chain) {
  $$("#series-chains .chain-btn").forEach((b) => {
    b.setAttribute("aria-checked", b.dataset.chain === chain ? "true" : "false");
    b.tabIndex = b.dataset.chain === chain ? 0 : -1;
  });
}

function renderChainNote(obj, variant) {
  const note = $("#series-chain-note");
  if (!variant) {
    note.hidden = true;
    note.textContent = "";
    return;
  }
  note.hidden = false;
  const off = state.seriesRecovery && state.seriesRecovery.variant_offset;
  const offTxt = off && off.n_epochs
    ? t("chainOffset", {
      med: off.median_px.toFixed(2), min: off.min_px.toFixed(2),
      max: off.max_px.toFixed(2), n: off.n_epochs,
    })
    : t("chainOffsetUnknown");
  let text = t("chainNote", { off: offTxt });

  // The position offset measured for this chain, shown as a caveat when the
  // data record carries one.
  const caveat = obj && obj.position_caveat;
  if (caveat && state.seriesChain === "main") {
    text += " " + t("positionCaveat", {
      med: fmt(caveat.offset_px_median, 1),
      min: fmt(caveat.offset_px_range[0], 1),
      max: fmt(caveat.offset_px_range[1], 1),
      arcsec: fmt(caveat.offset_arcsec_median, 1),
    });
  }
  note.textContent = text;
}

function renderSeriesEpoch() {
  const obj = activeSeries();
  if (!obj || !obj.epochs.length) return;
  const n = obj.epochs.length;
  if (state.seriesIndex >= n) state.seriesIndex = 0;
  const ep = obj.epochs[state.seriesIndex];
  const pm = obj.proper_motion || {};
  const applied = ep.pm_applied === true;

  const dateShort = epochDateStr(ep);
  const dateFull = epochIsoFull(ep);
  const bandName = ep.band || obj.band || "SPHEREx";
  const detNum = ep.detector_header !== undefined ? ep.detector_header : obj.detector;
  const emLo = ep.em_min_um !== undefined ? ep.em_min_um : (Array.isArray(obj.band_em_um) ? obj.band_em_um[0] : null);
  const emHi = ep.em_max_um !== undefined ? ep.em_max_um : (Array.isArray(obj.band_em_um) ? obj.band_em_um[1] : null);
  const pixSummary = typeof ep.nan_frac === "number"
    ? t("metaPixelsValue", {
      med: fmt(ep.median_mjy_sr, 4), sig: fmt(ep.robust_sigma, 4), nan: (ep.nan_frac * 100).toFixed(3),
    })
    : `median ${fmt(ep.median_mjy_sr, 4)} MJy/sr, background scatter ${fmt(ep.robust_sigma, 4)} MJy/sr`;

  $("#series-img").src = ep.png;
  $("#series-img").alt = t("seriesAlt", {
    name: obj.name, date: dateShort, mjd: ep.mjd, band: bandName,
  });
  $("#series-label").textContent = epochLabel(ep);
  $("#series-band-label").textContent = emLo !== null && emHi !== null
    ? `${bandName}  ${fmt(emLo, 3)}-${fmt(emHi, 3)} um`
    : bandName;
  $("#series-counter").textContent = `${state.seriesIndex + 1}/${n}`;

  const slider = $("#series-slider");
  slider.max = String(n - 1);
  slider.value = String(state.seriesIndex);
  slider.disabled = n < 2;
  slider.setAttribute("aria-valuetext", t("sliderValue", {
    i: state.seriesIndex + 1, n, date: dateShort,
  }));

  renderDial(obj, n, ep);

  const hasPmNumbers = typeof pm.pm_ra_cosdec_mas_yr === "number"
    && typeof pm.pm_dec_mas_yr === "number";
  let pmText;
  if (applied) {
    pmText = t("pmApplied", {
      ra: fmt(pm.pm_ra_cosdec_mas_yr, 3), dec: fmt(pm.pm_dec_mas_yr, 3),
    });
  } else if (hasPmNumbers) {
    pmText = t("pmNotApplied", {
      ra: fmt(pm.pm_ra_cosdec_mas_yr, 3), dec: fmt(pm.pm_dec_mas_yr, 3),
    });
  } else {
    pmText = t("pmNotAppliedNoValue");
  }

  $("#series-meta").innerHTML = `
    <div class="meta-row"><dt>${t("metaDate")}</dt><dd>${escapeAttr(dateFull)}</dd></div>
    <div class="meta-row"><dt>${t("metaMjd")}</dt><dd>${ep.mjd} (start ${fmt(ep.mjd_start, 3)})</dd></div>
    <div class="meta-row"><dt>${t("metaBand")}</dt><dd>${escapeAttr(bandName)}${detNum !== undefined ? ` (detector ${escapeAttr(detNum)})` : ""}</dd></div>
    <div class="meta-row"><dt>${t("metaWavelength")}</dt><dd>${emLo !== null && emHi !== null ? fmtEm(emLo, emHi) : "n/a"}</dd></div>
    <div class="meta-row"><dt>${t("metaPm")}</dt><dd>${escapeAttr(pmText)}</dd></div>
    <div class="meta-row"><dt>${t("metaObs")}</dt><dd>${escapeAttr(ep.obs_id)}</dd></div>
    <div class="meta-row"><dt>${t("metaEvidence")}</dt><dd>${markerHTML("measured")} ${t("metaMeasuredNote")}</dd></div>
    <div class="meta-row"><dt>${t("metaPixels")}</dt><dd>${escapeAttr(pixSummary)}</dd></div>
  `;

  const single = n < 2;
  $("#series-play").hidden = single || reduceMotion();
  $("#series-slider").hidden = single;
  $("#series-prev").hidden = single;
  $("#series-next").hidden = single;
  const note = $("#series-single-note");
  note.hidden = !single;
  if (single) {
    note.textContent = t("singleEpochNote", {
      name: obj.name,
      cand: obj.candidate_days_total,
      date: dateShort,
    });
  }
  const motionNote = $("#series-motion-note");
  const motionOff = reduceMotion() && !single;
  motionNote.hidden = !motionOff;
  if (motionOff) motionNote.textContent = t("motionNote");

  renderRecovery(obj);
  renderVerdict();
  renderSeriesSource(obj, ep);
}

function renderRecovery(obj) {
  const block = $("#series-panel");
  const rec = recoveryFor(obj.id);
  if (!rec) {
    block.hidden = true;
    return;
  }
  block.hidden = false;
  $("#series-recovery-title").textContent = t("recoveryDetailTitle");

  const inSeries = Array.isArray(rec.series_obs_ids) && rec.series_obs_ids.includes(rec.main_obs_id);
  const snrTxt = rec.snr_3x3 !== null && rec.snr_3x3 !== undefined
    ? `${fmt(rec.snr_3x3, 3)} (3 by 3 pixel window)`
    : t("snrInvalid", { sig: fmt(rec.peak_snr, 2), off: fmt(rec.peak_offset_px, 2) });

  const c = rec.criteria || {};
  const v = rec.verdicts || {};
  const rows = [
    [t("recFrame"), `MJD ${fmt(rec.mjd_avg, 3)}`],
    [t("recFrameMatch"), inSeries ? t("recFrameInSeries") : t("recFrameNotInSeries")],
    [t("recSnr"), snrTxt],
    [t("recPeak"), `${fmt(rec.peak_snr, 2)} at ${fmt(rec.peak_offset_px, 2)} px`],
    [t("recRegistration"), `${fmt(rec.registration_scatter_px, 3)} px (${rec.registration_valid ? t("validWord") : t("invalidWord")})`],
    [t("recCriteria"), `Signal ${yn(c.R1_pass)}, Position ${yn(c.R2_pass)}, Alignment ${yn(c.R3_pass)}, Saturation ${yn(c.R4_pass)}`],
    [t("recVersions"), `Rule 1: ${translateVerdict(v.v1)}; Rule 2: ${translateVerdict(v.v2)}; Rule 3: ${translateVerdict(v.v3)}`],
  ];

  $("#series-recovery-body").innerHTML = `
    <div class="meta-list">
      ${rows.map(([k, val]) => `<div class="meta-row"><dt>${k}</dt><dd>${escapeAttr(val)}</dd></div>`).join("")}
    </div>
  `;
}

function yn(b) {
  return b === true ? t("yesWord") : b === false ? t("noWord") : "n/a";
}

/* ---------- time dial, inline SVG epoch navigator ---------- */

const DIAL_R = 88;
const DIAL_C = 108;

function dialPoint(i, n) {
  const a = (i / n) * Math.PI * 2 - Math.PI / 2;
  return [DIAL_C + DIAL_R * Math.cos(a), DIAL_C + DIAL_R * Math.sin(a)];
}

function renderDial(obj, n, ep) {
  const host = $("#dial");
  if (!host) return;
  const usable = obj && obj.epochs.length > 1;
  const count = usable ? n : (obj ? 1 : 0);
  host.setAttribute("aria-valuemin", "1");
  host.setAttribute("aria-valuemax", String(Math.max(1, count)));
  host.setAttribute("aria-valuenow", String(state.seriesIndex + 1));
  host.setAttribute("aria-disabled", usable ? "false" : "true");
  host.setAttribute("tabindex", usable ? "0" : "-1");
  host.setAttribute("aria-valuetext", ep
    ? t("dialValue", { i: state.seriesIndex + 1, n: count, mjd: ep.mjd })
    : t("dialEmpty"));

  const ticks = [];
  const hits = [];
  for (let i = 0; i < count; i++) {
    const [x, y] = dialPoint(i, count);
    const [hx, hy] = dialPoint(i, count);
    const hitR = Math.max(7, Math.min(14, (2 * Math.PI * DIAL_R) / Math.max(count, 2) / 2));
    hits.push(`<circle class="dial-hit" data-i="${i}" cx="${hx.toFixed(2)}" cy="${hy.toFixed(2)}" r="${hitR.toFixed(2)}"/>`);
    ticks.push(`<circle class="dial-tick${i === state.seriesIndex ? " is-current" : ""}" cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="${i === state.seriesIndex ? 5 : 3}"/>`);
  }
  const [hx, hy] = dialPoint(state.seriesIndex, Math.max(count, 1));
  const hand = usable
    ? `<line class="dial-hand" x1="${DIAL_C}" y1="${DIAL_C}" x2="${hx.toFixed(2)}" y2="${hy.toFixed(2)}"/>`
    : "";
  host.innerHTML = `<svg viewBox="0 0 216 216" aria-hidden="true" focusable="false">
    <circle class="dial-ring" cx="${DIAL_C}" cy="${DIAL_C}" r="${DIAL_R}"/>
    ${ticks.join("")}
    ${hits.join("")}
    ${hand}
    <circle class="dial-hub" cx="${DIAL_C}" cy="${DIAL_C}" r="4"/>
  </svg>`;
  const readout = $("#dial-readout");
  if (readout) {
    readout.textContent = ep
      ? t("dialReadout", { i: state.seriesIndex + 1, n: count, mjd: ep.mjd })
      : t("dialEmpty");
  }
}

function initDial() {
  const host = $("#dial");
  if (!host) return;
  host.addEventListener("click", (e) => {
    const hit = e.target.closest(".dial-hit");
    if (!hit) return;
    const obj = activeSeries();
    if (!obj || obj.epochs.length < 2) return;
    pauseSeries();
    state.seriesIndex = Number(hit.dataset.i);
    renderSeriesEpoch();
    syncURL();
  });
  host.addEventListener("keydown", (e) => {
    const obj = activeSeries();
    if (!obj || obj.epochs.length < 2) return;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); stepSeries(1); }
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); stepSeries(-1); }
    else if (e.key === "Home") {
      e.preventDefault(); pauseSeries(); state.seriesIndex = 0; renderSeriesEpoch(); syncURL();
    } else if (e.key === "End") {
      e.preventDefault(); pauseSeries();
      state.seriesIndex = obj.epochs.length - 1; renderSeriesEpoch(); syncURL();
    }
  });
}

/* ---------- verdict and aggregate cards in the numbers zone ---------- */

function renderVerdict() {
  const card = $("#verdict-card");
  const rec = state.seriesObj ? recoveryFor(state.seriesObj.id) : null;
  const value = $("#verdict-value");
  const mk = $("#verdict-marker");
  const reason = $("#verdict-reason");
  const rows = $("#verdict-rows");
  const src = $("#verdict-source");
  if (!card) return;
  card.className = "card is-verdict-" + verdictTier(rec);
  mk.innerHTML = markerHTML(verdictTier(rec));
  if (!rec) {
    value.textContent = t("verdictNoSeries");
    reason.textContent = t("verdictNoSeriesNote");
    rows.innerHTML = "";
    src.textContent = "";
    return;
  }
  value.textContent = translateVerdict(rec.verdict);
  reason.textContent = t("verdictPeak", {
    sig: fmt(rec.peak_snr, 1), off: fmt(rec.peak_offset_px, 2),
  });
  const snr3 = rec.snr_3x3 === null || rec.snr_3x3 === undefined ? "not computable (saturated core)" : fmt(rec.snr_3x3, 3);
  const pair = [
    [t("vPeakSnr"), fmt(rec.peak_snr, 1)],
    [t("vOffset"), fmt(rec.peak_offset_px, 2) + " px"],
    [t("vSnr3"), snr3],
    [t("vFrame"), `MJD ${fmt(rec.mjd_avg, 3)}`],
  ];
  rows.innerHTML = pair.map(([k, v]) =>
    `<div class="verdict-row"><span class="k">${escapeAttr(k)}</span><span class="v">${escapeAttr(v)}</span></div>`).join("");
  const so = state.seriesRecovery && state.seriesRecovery.source;
  src.textContent = so ? t("verdictSrc", { ver: so.criteria_version || "recorded" }) : "";
  renderAggregate();
}

function renderAggregate() {
  const agg = state.seriesRecovery && state.seriesRecovery.summary;
  const mk = $("#aggregate-marker");
  const val = $("#aggregate-value");
  const reason = $("#aggregate-reason");
  const src = $("#aggregate-source");
  if (!mk) return;
  if (!agg) {
    mk.innerHTML = markerHTML("unknown");
    val.textContent = "n/a";
    reason.textContent = t("aggregateMissing");
    src.textContent = "";
    return;
  }
  mk.innerHTML = markerHTML("measured");
  val.textContent = t("aggregateCount", { rec: agg.n_recovered, total: agg.n_objects });
  reason.textContent = t("aggregateBreakdown", {
    rec: agg.n_recovered, none: agg.n_not_recovered,
    ne: agg.n_not_evaluated, total: agg.n_objects,
  });
  const off = state.seriesRecovery.variant_offset;
  src.innerHTML = escapeAttr(t("aggregateSrc")) + (off && off.n_epochs
    ? "<br>" + escapeAttr(t("aggregateOffset", {
      med: off.median_px.toFixed(2), min: off.min_px.toFixed(2),
      max: off.max_px.toFixed(2), n: off.n_epochs,
    }))
    : "");
}

function renderSeriesSource(obj, ep) {
  const rec = recoveryFor(obj.id);
  const refLabel = state.seriesChain === "variant"
    ? "SIMBAD J2000 + proper motion series"
    : "Challenge coordinate series";
  const parts = [
    t("srcSeries", { ref: refLabel }),
    t("srcEpoch", { sha: String(ep.png_sha256 || "").slice(0, 16) }),
  ];
  if (rec && state.seriesRecovery && state.seriesRecovery.source) {
    parts.push(t("srcRecovery", {
      sha: String(state.seriesRecovery.source.sha256 || "").slice(0, 16),
      ver: state.seriesRecovery.source.criteria_version || "v3",
    }));
  }
  const line = $("#series-source-line");
  if (line) line.innerHTML = parts.join("<br>");
}

function pauseSeries() {
  state.seriesPlaying = false;
  clearInterval(state.seriesTimer);
  state.seriesTimer = null;
  const btn = $("#series-play");
  if (btn) {
    btn.textContent = t("playWord");
    btn.setAttribute("aria-pressed", "false");
  }
}

function playSeries() {
  const obj = activeSeries();
  if (!obj || obj.epochs.length < 2 || reduceMotion()) return;
  if (state.seriesPlaying) return;
  state.seriesPlaying = true;
  const btn = $("#series-play");
  btn.textContent = t("pauseWord");
  btn.setAttribute("aria-pressed", "true");
  state.seriesTimer = setInterval(() => {
    const o = activeSeries();
    if (!o) return pauseSeries();
    state.seriesIndex = (state.seriesIndex + 1) % o.epochs.length;
    renderSeriesEpoch();
    blinkOnce($("#series-img"));
  }, 1000 / state.seriesFps);
}

function toggleSeries() {
  state.seriesPlaying ? pauseSeries() : playSeries();
}

function stepSeries(delta) {
  const obj = activeSeries();
  if (!obj) return;
  pauseSeries();
  const n = obj.epochs.length;
  state.seriesIndex = (state.seriesIndex + delta + n) % n;
  renderSeriesEpoch();
  syncURL();
}

function setSeriesChain(chain) {
  if (!state.seriesObj) return;
  if (chain === "variant" && !variantFor(state.seriesObj.id)) return;
  pauseSeries();
  state.seriesChain = chain;
  state.seriesIndex = 0;
  setChainButtons(chain);
  renderChainNote(state.seriesObj, variantFor(state.seriesObj.id));
  renderSeriesEpoch();
  syncURL();
}

function initSeriesUI() {
  $("#series-play").addEventListener("click", toggleSeries);
  $("#series-prev").addEventListener("click", () => stepSeries(-1));
  $("#series-next").addEventListener("click", () => stepSeries(1));
  $("#series-slider").addEventListener("input", (e) => {
    pauseSeries();
    state.seriesIndex = Number(e.target.value);
    renderSeriesEpoch();
    syncURL();
  });
  $("#series-stage").addEventListener("keydown", (e) => {
    const obj = activeSeries();
    if (!obj || obj.epochs.length < 2) return;
    if (e.key === "ArrowLeft") { e.preventDefault(); stepSeries(-1); }
    else if (e.key === "ArrowRight") { e.preventDefault(); stepSeries(1); }
    else if (e.key === "Home") {
      e.preventDefault();
      state.seriesIndex = 0;
      pauseSeries();
      renderSeriesEpoch();
      syncURL();
    }
    else if (e.key === "End") {
      e.preventDefault();
      state.seriesIndex = obj.epochs.length - 1;
      pauseSeries();
      renderSeriesEpoch();
      syncURL();
    }
  });
  $$("#series-chains .chain-btn").forEach((b) => {
    b.addEventListener("click", () => setSeriesChain(b.dataset.chain));
    b.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      const chain = state.seriesChain === "main" ? "variant" : "main";
      setSeriesChain(chain);
      const target = chain === "main" ? $("#chain-btn-main") : $("#chain-btn-variant");
      if (target) target.focus();
    });
  });
}

/* ---------- coordinate input, presets, URL state ---------- */

const I18N = {
  en: {
    langBtn: "EN",
    presetTitle: "Known objects from the challenge",
    canvasLabel: "Image viewer",
    numbersLabel: "Results for this position",
    epochsLabel: "Observation times",
    metaLabel: "Observation details",
    controlTitle: "Known-object summary",
    labTitle: "Geometry check",
    brandSub: "SPHEREx image explorer",
    topbarNote: "No discovery claim",
    navExplorer: "Compare images",
    navAtlas: "Sky fields",
    navControls: "Position checks",
    navFinding: "Detection limits",
    navControl: "Known objects",
    navParallax: "Geometry",
    navCompleteness: "Completeness",
    navShiftstack: "Motion test",
    navMethod: "Methods",
    statImages: "aligned images",
    statPatches: "candidate sky fields",
    statGate0: "Field readiness check",
    statStacking: "Stacking claim",
    helpSummary: "Coordinate formats",
    prevMark: "<",
    nextMark: ">",
    notMeasuredWord: "NOT MEASURED",
    claimedWord: "claimed",
    notClaimedWord: "not claimed",
    noVerdictWord: "no verdict",
    epochsSummary: "{name}, {n} observations spanning {base} days",
    epochsSummaryPlain: "{name}, {n} observation",
    dialValue: "Observation {i} of {n}, MJD {mjd}",
    dialReadout: "image {i}/{n}  MJD {mjd}",
    dialEmpty: "no image series loaded",
    verdictNoSeries: "No object selected",
    verdictNoSeriesNote: "Select a named object on the left to inspect its real SPHEREx image stamp and recorded recovery outcome.",
    verdictPeak: "Peak detection significance {sig} at {off} px from the catalog position.",
    vPeakSnr: "Peak significance",
    vOffset: "Position offset",
    vSnr3: "3 by 3 pixel significance",
    vFrame: "Evaluated observation",
    verdictSrc: "Recorded recovery check ({ver} rules)",
    recoveryDetailTitle: "Measured quantities",
    aggregateCount: "{rec} of {total}",
    aggregateBreakdown: "Recovered: {rec} | Not recovered: {none} | Not evaluated: {ne} (of {total} challenge objects)",
    aggregateSrc: "Bundled named-object recovery record",
    aggregateOffset: "Coordinate-reference offset: median {med} px (range {min} to {max} px across {n} observations)",
    aggregateMissing: "The recovery summary record is not loaded.",
    chartCaption: "Measured recovery curve: peaks at {pct}% (significance {sig}); crosses 50% near {half}. Sample count n = {n} injections per point.",
    chartAlt: "Measured synthetic-source recovery fraction against detection significance",
    chartXAxis: "Detection significance",
    parallaxIntro: "As Earth orbits the Sun, a nearby solar-system object shifts against background stars. Over our {base}-day span, an object at 400 AU shifts far beyond the {half} arcsec half-width of a small cutout, leaving the frame. Wide-baseline searches therefore need full-frame images.",
    labNote: "Geometry projection only. This calculator shows apparent sky shift by distance and never states a probability that Planet X exists.",
    labBadge: "drifts outside small cutout",
    labNoData: "Enter a positive distance in AU to inspect the projected sky shift.",
    labShift: "At {au} AU, projected shift is {arcsec} arcsec ({px} px at this image scale)",
    labHalfField: "Cutout half-width: {half} arcsec over {base} days. Nearest tabulated distance at or below input: {min} AU.",
    coordTitle: "Or enter sky coordinates",
    coordIntro: "Enter right ascension and declination, or pick one of the five challenge objects above. The viewer only displays real SPHEREx images bundled with this page; uncovered positions are reported plainly.",
    lblRa: "Right ascension (RA)",
    lblDec: "Declination (Dec)",
    apply: "Show position",
    help: "RA accepts hours-minutes-seconds (17h57m48.5s, 17 57 48.5, 17:57:48.5) or decimal degrees (269.4521). Dec accepts degrees-arcminutes-arcseconds (-7d14m42.53s, -7 14 42.53, -7:14:42.53) or decimal degrees (-7.2451). Valid ranges: RA 0 to 360 deg, Dec -90 to +90 deg.",
    errRaFormat: "RA could not be read. Enter hours, minutes, and seconds, or decimal degrees.",
    errDecFormat: "Dec could not be read. Enter degrees, arcminutes, and arcseconds, or decimal degrees.",
    errRaRange: "RA is outside the valid range of 0 to 360 degrees (0 to 24 hours).",
    errDecRange: "Dec is outside the valid range of -90 to +90 degrees.",
    errMinutes: "Minutes and seconds must be between 0 and 59.99.",
    errBoth: "Both RA and Dec are required.",
    stCoveredHead: "Covered: aligned SPHEREx image series available",
    stCoveredDetail: "This coordinate falls inside the aligned sky cutout ({w} x {h} px at {scale} arcsec/px). The main viewer displays the real observations.",
    stPartialHead: "Field listed, but no image series bundled",
    stPartialDetail: "This coordinate lies inside {field} ({n} recorded visits), which has summary measurements below but no bundled image series on this page. No substitute sky image is shown.",
    stUncoveredHead: "Not covered: outside bundled SPHEREx images",
    stUncoveredDetail: "This coordinate is {sep} degrees from the nearest listed field ({field}), outside its {radius}-degree footprint. No bundled images cover this sky position.",
    stNoPatches: "Sky-field coverage table could not be loaded.",
    stSeriesHead: "Covered: real SPHEREx observations for this challenge object",
    stSeriesDetailMany: "{name} has {n} real {band} observations from {d0} to {d1} ({base} days). Frames are shown at their recorded observation times without interpolation.",
    stSeriesDetailOne: "Only one verified {band} observation on {d0} is bundled for {name} ({cand} candidate observation date listed; archive retrieval was unavailable during collection). Blinking is disabled rather than inventing extra frames.",
    stSeriesAlsoGrid: "This position also lies inside the main aligned sky field.",
    stSeriesNotInGrid: "This position lies {sep} degrees from the nearest survey field ({field}), so the object-stamp viewer displays its dedicated cutouts.",
    stSeriesNote: "Object cutouts are 95 x 95 px stamps at 6.15 arcsec/px read directly from SPHEREx calibrated exposures.",
    coordLine: "Coordinates: RA {ra}, Dec {dec} ({raDeg} deg, {decDeg} deg).",
    objLine: "Selected object: {name} ({source}).",
    viewerEmpty: "No aligned survey-field cutout covers RA {raDeg} deg, Dec {decDeg} deg (nearest field: {field}, {sep} degrees away). If you selected a challenge object, inspect its dedicated object stamp below; otherwise no substitute sky image is shown.",
    viewerEmptyNoPatch: "No bundled image series covers RA {raDeg} deg, Dec {decDeg} deg.",
    seriesPick: "Select one of the five challenge objects on the left to inspect its SPHEREx image series.",
    seriesNone: "No SPHEREx image series is bundled for this object.",
    chainLabel: "Coordinate reference",
    chainMain: "Challenge coordinates (as published)",
    chainVariant: "SIMBAD J2000 + proper motion",
    chainNote: "Two coordinate references are available for the same exposures. The main series uses the published challenge coordinates without proper-motion propagation, while the SIMBAD series propagates proper motion (-8123.7, +673.2 mas/yr) to each observation date, shifting the stamp center by {off}. Both coordinate chains yield the same recovery outcome (Not recovered); only centering changes.",
    chainOffset: "a median of {med} px across {n} observations (range {min} to {max} px)",
    chainOffsetUnknown: "the recorded catalog offset",
    positionCaveat: "Note on centering: without an epoch attached to the challenge coordinates, the target position can sit about {med} px ({arcsec} arcsec, range {min} to {max} px) from the stamp center, still well inside the 95 px cutout.",
    sliderValue: "Observation {i} of {n}, {date}",
    metaDate: "Date (UTC)",
    metaMjd: "Modified Julian Date",
    metaBand: "Infrared band",
    metaWavelength: "Wavelength range",
    metaPm: "Proper motion",
    metaObs: "Observation ID",
    metaEvidence: "Evidence status",
    metaMeasuredNote: "direct SPHEREx calibrated pixel values without rescaling",
    metaPixels: "Cutout pixel summary",
    metaPixelsValue: "median {med} MJy/sr, background scatter {sig} MJy/sr, masked {nan}%",
    pmApplied: "Applied ({ra}, {dec} mas/yr propagated from J2000)",
    pmNotApplied: "Not applied to center ({ra}, {dec} mas/yr recorded in catalog)",
    pmNotAppliedNoValue: "Not applied (published challenge coordinates carry no reference epoch for propagation)",
    singleEpochNote: "Only one verified observation on {date} is bundled for {name} ({cand} candidate date listed; additional archive cutouts were unavailable during collection). Automatic blinking is disabled so no artificial frames are shown.",
    motionNote: "Reduced-motion preference detected: automatic blinking is paused. Step through observations with Previous, Next, the slider, or arrow keys.",
    recoveryTitle: "Recovery outcome for this object",
    recFrame: "Evaluated date",
    recFrameMatch: "Included in this series",
    recFrameInSeries: "Yes (same calibrated exposure)",
    recFrameNotInSeries: "Measured on a separate reference exposure",
    recSnr: "3 by 3 window significance",
    snrInvalid: "Core saturated (masked pixels); nearest peak significance {sig} at {off} px",
    recPeak: "Nearest signal peak",
    recRegistration: "Star-alignment scatter",
    recCriteria: "Check rules",
    recVersions: "Rule-set comparison",
    validWord: "valid",
    invalidWord: "outside tolerance",
    yesWord: "pass",
    noWord: "fail",
    srcSeries: "Series: {ref}",
    srcEpoch: "Image checksum (SHA-256): <code>{sha}...</code>",
    srcRecovery: "Recovery checksum (SHA-256): <code>{sha}...</code> ({ver})",
    playWord: "Play",
    pauseWord: "Pause",
    prevWord: "Previous observation",
    nextWord: "Next observation",
    sliderAria: "Choose object observation",
    stageAria: "Challenge object image stamp. Use left and right arrow keys to step across observation times.",
    seriesAlt: "SPHEREx image stamp of {name} on {date} (MJD {mjd}, {band})",
  },
};
function t(key, vars) {
  const table = I18N[state.lang] || I18N.en;
  let s = table[key] !== undefined ? table[key] : I18N.en[key];
  if (s === undefined) return key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v));
  }
  return s;
}

function splitSexagesimal(raw) {
  const cleaned = raw.trim().replace(/[hmsd°′″'"]/gi, " ").trim();
  if (!cleaned) return null;
  const parts = cleaned.split(/[\s:]+/).filter((p) => p.length > 0);
  if (parts.length < 2 || parts.length > 3) return null;
  const nums = parts.map((p) => Number(p));
  if (nums.some((n) => !Number.isFinite(n))) return null;
  if (nums.some((n, i) => i > 0 && (n < 0 || n >= 60))) return null;
  return nums;
}

function parseRA(raw) {
  const s = raw.trim();
  if (!s) return { error: "errBoth" };
  if (/^[+]?\d+(\.\d+)?$/.test(s)) {
    const v = Number(s);
    if (!(v >= 0 && v < 360)) return { error: "errRaRange" };
    return { deg: v, text: `${v.toFixed(6)} deg` };
  }
  const nums = splitSexagesimal(s);
  if (!nums) return { error: "errRaFormat" };
  const [h, m = 0, sec = 0] = nums;
  if (h < 0 || h >= 24) return { error: "errRaRange" };
  const deg = (h + m / 60 + sec / 3600) * 15;
  return { deg, text: `${h}h${String(m).padStart(2, "0")}m${sec.toFixed(3)}s` };
}

function parseDec(raw) {
  const s = raw.trim();
  if (!s) return { error: "errBoth" };
  if (/^[+-]?\d+(\.\d+)?$/.test(s)) {
    const v = Number(s);
    if (!(v >= -90 && v <= 90)) return { error: "errDecRange" };
    return { deg: v, text: `${v >= 0 ? "+" : "-"}${Math.abs(v).toFixed(6)} deg` };
  }
  const sign = s.startsWith("-") ? -1 : 1;
  const body = s.replace(/^[+-]/, "");
  const nums = splitSexagesimal(body);
  if (!nums) return { error: "errDecFormat" };
  const [d, m = 0, sec = 0] = nums;
  if (d > 90) return { error: "errDecRange" };
  if (d === 90 && (m > 0 || sec > 0)) return { error: "errDecRange" };
  const deg = sign * (d + m / 60 + sec / 3600);
  return {
    deg,
    text: `${sign < 0 ? "-" : "+"}${String(d).padStart(2, "0")}d${String(m).padStart(2, "0")}m${sec.toFixed(3)}s`,
  };
}

function angSepDeg(ra1, dec1, ra2, dec2) {
  const r = Math.PI / 180;
  const d1 = dec1 * r;
  const d2 = dec2 * r;
  const dra = (ra1 - ra2) * r;
  const c = Math.sin(d1) * Math.sin(d2) + Math.cos(d1) * Math.cos(d2) * Math.cos(dra);
  return Math.acos(Math.min(1, Math.max(-1, c))) / r;
}

function wrapDeg(d) {
  let x = d % 360;
  if (x > 180) x -= 360;
  if (x < -180) x += 360;
  return x;
}

function footprint() {
  const a = state.alignment;
  if (!a || !Array.isArray(a.target_crval) || !Array.isArray(a.common_region)) return null;
  const [x0, x1, y0, y1] = a.common_region;
  const w = Math.abs(x1 - x0);
  const h = Math.abs(y1 - y0);
  const scale = Number(a.pixel_scale_arcsec);
  if (!(w > 0) || !(h > 0) || !(scale > 0)) return null;
  return {
    cra: Number(a.target_crval[0]),
    cdec: Number(a.target_crval[1]),
    w, h, scale,
    halfWArcsec: (w / 2) * scale,
    halfHArcsec: (h / 2) * scale,
  };
}

function evaluateCoordinate(ra, dec) {
  const fp = footprint();
  let insideFrames = false;
  if (fp) {
    const draArcsec = wrapDeg(ra - fp.cra) * Math.cos(fp.cdec * Math.PI / 180) * 3600;
    const ddecArcsec = (dec - fp.cdec) * 3600;
    insideFrames = Math.abs(draArcsec) <= fp.halfWArcsec &&
                   Math.abs(ddecArcsec) <= fp.halfHArcsec;
  }
  let best = null;
  for (const p of state.patches) {
    if (typeof p.ra_deg !== "number" || typeof p.dec_deg !== "number") continue;
    const sep = angSepDeg(ra, dec, p.ra_deg, p.dec_deg);
    if (!best || sep < best.sep) best = { patch: p, sep };
  }
  const radius = state.patchRadiusDeg;
  if (insideFrames) return { level: "frames", patch: best ? best.patch : null, sep: best ? best.sep : null, fp };
  if (best && radius !== null && best.sep <= radius) {
    return { level: "patch", patch: best.patch, sep: best.sep, fp };
  }
  return { level: "none", patch: best ? best.patch : null, sep: best ? best.sep : null, fp };
}

function setStatus(level, html) {
  const el = $("#coord-status");
  el.className = `coord-status is-${level === "frames" ? "covered" : level === "patch" ? "partial" : level === "series" ? "series" : "uncovered"}`;
  el.innerHTML = html;
}

function renderStatus(coverage, coord, obj, seriesObj) {
  if (seriesObj) {
    const eps = seriesObj.epochs.length;
    const span = seriesDateSpan(seriesObj);
    const body = eps > 1
      ? t("stSeriesDetailMany", {
        name: seriesObj.name, n: eps, band: seriesObj.band,
        d0: span.d0,
        d1: span.d1,
        base: span.base,
      })
      : t("stSeriesDetailOne", {
        name: seriesObj.name, band: seriesObj.band,
        d0: span.d0,
        cand: seriesObj.candidate_days_total,
      });
    const gridLine = coverage.level === "frames"
      ? t("stSeriesAlsoGrid")
      : t("stSeriesNotInGrid", {
        sep: coverage.patch ? coverage.sep.toFixed(3) : "n/a",
        field: coverage.patch ? fieldDisplayName(coverage.patch) : "n/a",
      });
    setStatus("series", `
      <span class="status-head">${t("stSeriesHead")}</span>
      <span>${body}</span>
      <span class="status-detail">${gridLine} ${t("coordLine", {
        ra: coord.raText, dec: coord.decText,
        raDeg: coord.ra.toFixed(6), decDeg: coord.dec.toFixed(6),
      })}</span>
    `);
    $("#coord-coverage-note").textContent = t("stSeriesNote");
    return;
  }
  const head = coverage.level === "frames" ? "stCoveredHead"
    : coverage.level === "patch" ? "stPartialHead" : "stUncoveredHead";
  let body;
  if (coverage.level === "frames") {
    body = t("stCoveredDetail", {
      w: coverage.fp.w, h: coverage.fp.h, scale: coverage.fp.scale,
    });
  } else if (coverage.level === "patch") {
    body = t("stPartialDetail", {
      field: fieldDisplayName(coverage.patch), n: coverage.patch.n_exposures,
    });
  } else if (coverage.patch) {
    body = t("stUncoveredDetail", {
      sep: coverage.sep.toFixed(3), field: fieldDisplayName(coverage.patch),
      radius: state.patchRadiusDeg !== null ? state.patchRadiusDeg : "n/a",
    });
  } else {
    body = t("stNoPatches");
  }
  const coordLine = t("coordLine", {
    ra: coord.raText, dec: coord.decText,
    raDeg: coord.ra.toFixed(6), decDeg: coord.dec.toFixed(6),
  });
  const objLine = obj ? t("objLine", { name: obj.name, source: cleanSourceLabel(obj.sumber || obj.source) }) : "";
  setStatus(coverage.level, `
    <span class="status-head">${t(head)}</span>
    <span>${body}</span>
    <span class="status-detail">${coordLine}${objLine ? " " + objLine : ""}</span>
  `);
  $("#coord-coverage-note").textContent = "";
}

function applyCoverageToViewer(coverage, coord) {
  const covered = coverage.level === "frames";
  $("#stage-img").hidden = !covered;
  $("#viewer-empty").hidden = covered;
  $("#btn-play").disabled = !covered;
  $("#epoch-slider").disabled = !covered;
  if (!covered) {
    pause();
    if (state.mode !== "single") setMode("single");
    $("#stage-img").removeAttribute("src");
    $("#epoch-label").textContent = "Outside main field";
    $("#epoch-counter").textContent = "0/0";
    const sepTxt = coverage.patch ? coverage.sep.toFixed(3) : "n/a";
    $("#viewer-empty-text").textContent = coverage.patch
      ? t("viewerEmpty", {
        raDeg: coord.ra.toFixed(4), decDeg: coord.dec.toFixed(4),
        field: fieldDisplayName(coverage.patch), sep: sepTxt,
      })
      : t("viewerEmptyNoPatch", {
        raDeg: coord.ra.toFixed(4), decDeg: coord.dec.toFixed(4),
      });
  } else {
    renderFrame();
  }
}

function applyCoordinate(raInput, decInput, objId) {
  const err = $("#coord-error");
  const raRaw = raInput !== undefined ? raInput : $("#coord-ra").value;
  const decRaw = decInput !== undefined ? decInput : $("#coord-dec").value;

  const ra = parseRA(raRaw);
  const dec = parseDec(decRaw);
  const fail = ra.error || dec.error;
  if (fail) {
    err.textContent = t(fail === "errBoth" && !raRaw.trim() && !decRaw.trim() ? "errBoth" : fail);
    err.hidden = false;
    $("#coord-ra").setAttribute("aria-invalid", ra.error ? "true" : "false");
    $("#coord-dec").setAttribute("aria-invalid", dec.error ? "true" : "false");
    return false;
  }
  err.hidden = true;
  $("#coord-ra").removeAttribute("aria-invalid");
  $("#coord-dec").removeAttribute("aria-invalid");

  const obj = objId ? state.objects.find((o) => o.id === objId) || null : null;
  if (objId && !obj) state.obj = null;

  state.coord = { ra: ra.deg, dec: dec.deg, raText: ra.text, decText: dec.text };
  state.obj = obj ? obj.id : null;
  const coverage = evaluateCoordinate(ra.deg, dec.deg);
  state.coverage = coverage;

  const seriesObj = obj ? seriesFor(obj.id) : null;
  renderStatus(coverage, state.coord, obj, seriesObj);
  applyCoverageToViewer(coverage, state.coord);
  renderSeriesFor(obj ? obj.id : null);
  renderPresets();
  syncURL();
  return true;
}

function renderPresets() {
  const grid = $("#preset-grid");
  if (!grid) return;
  grid.innerHTML = state.objects.map((o) => {
    const pressed = state.obj === o.id ? "true" : "false";
    const rec = recoveryFor(o.id);
    const short = rec ? translateVerdictShort(rec.verdict) : "";
    const tier = verdictTier(rec);
    const verdictLine = short
      ? `<span class="obj-verdict is-${tier}">${escapeAttr(short)}</span>`
      : `<span class="obj-verdict is-${tier}">${escapeAttr(t("noVerdictWord"))}</span>`;
    return `<button class="obj-row preset" type="button" data-obj="${o.id}"
        aria-pressed="${pressed}" aria-label="${escapeAttr(o.name)}: RA ${escapeAttr(o.ra_str)} Dec ${escapeAttr(o.dec_str)}, ${escapeAttr(short || t("noVerdictWord"))}">
      <span><span class="obj-name">${escapeAttr(o.name)}</span>${verdictLine}</span>
      <span class="obj-dot is-${tier}" aria-hidden="true"></span>
    </button>`;
  }).join("");
  grid.querySelectorAll(".obj-row").forEach((b) => {
    b.addEventListener("click", () => {
      const o = state.objects.find((x) => x.id === b.dataset.obj);
      if (!o) return;
      $("#coord-ra").value = o.ra_str;
      $("#coord-dec").value = o.dec_str;
      applyCoordinate(o.ra_str, o.dec_str, o.id);
    });
  });
}

function escapeAttr(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function syncURL() {
  if (!statesafe()) return;
  const u = new URL(window.location.href);
  if (state.coord) {
    u.searchParams.set("ra", state.coord.ra.toFixed(6));
    u.searchParams.set("dec", state.coord.dec.toFixed(6));
  }
  if (state.obj) u.searchParams.set("obj", state.obj);
  else u.searchParams.delete("obj");
  if (state.obj && state.seriesObj && state.seriesChain === "variant") u.searchParams.set("chain", "variant");
  else u.searchParams.delete("chain");
  if (state.obj && state.seriesObj && state.seriesIndex > 0) u.searchParams.set("epoch", String(state.seriesIndex));
  else u.searchParams.delete("epoch");
  if (state.lang === "id") u.searchParams.set("lang", "id");
  else u.searchParams.delete("lang");
  history.replaceState(null, "", u);
}

function statesafe() {
  return typeof history !== "undefined" && history.replaceState;
}

function applyLang() {
  state.lang = "en";
  document.documentElement.setAttribute("lang", "en");
  document.documentElement.setAttribute("lang", state.lang);
  $("#z1-label").textContent = t("presetTitle");
  $("#coord-title").textContent = t("coordTitle");
  $("#coord-intro").textContent = t("coordIntro");
  $("#lbl-ra").textContent = t("lblRa");
  $("#lbl-dec").textContent = t("lblDec");
  $("#coord-apply").textContent = t("apply");
  $("#coord-help").textContent = t("help");
  $("#coord-help-summary").textContent = t("helpSummary");
  $("#z2-label").textContent = t("canvasLabel");
  $("#z3-label").textContent = t("numbersLabel");
  $("#epochs-label").textContent = t("epochsLabel");
  $("#viewer-title").textContent = "Aligned SPHEREx images";
  $("#z3-meta").textContent = t("metaLabel");
  $("#verdict-label").textContent = t("recoveryTitle");
  $("#aggregate-label").textContent = t("controlTitle");
  $("#parallax-label").textContent = t("labTitle");
  $("#nav-explorer").textContent = t("navExplorer");
  $("#nav-atlas").textContent = t("navAtlas");
  $("#nav-controls").textContent = t("navControls");
  $("#nav-finding").textContent = t("navFinding");
  $("#nav-control").textContent = t("navControl");
  $("#nav-parallax").textContent = t("navParallax");
  $("#nav-completeness").textContent = t("navCompleteness");
  $("#nav-shiftstack").textContent = t("navShiftstack");
  $("#nav-method").textContent = t("navMethod");
  $("#brand-sub").textContent = t("brandSub");
  $("#topbar-note").textContent = t("topbarNote");
  $("#stat-images-label").textContent = t("statImages");
  $("#stat-patches-label").textContent = t("statPatches");
  $("#stat-gate0-label").textContent = t("statGate0");
  $("#stat-stacking-label").textContent = t("statStacking");
  renderLegend();
  $("#series-play").textContent = t("playWord");
  $("#series-play").setAttribute("aria-pressed", state.seriesPlaying ? "true" : "false");
  $("#series-prev").setAttribute("aria-label", t("prevWord"));
  $("#series-next").setAttribute("aria-label", t("nextWord"));
  $("#series-prev").textContent = t("prevMark");
  $("#series-next").textContent = t("nextMark");
  $("#series-slider").setAttribute("aria-label", t("sliderAria"));
  $("#series-stage").setAttribute("aria-label", t("stageAria"));
  if (state.coord) {
    const obj = state.obj ? state.objects.find((o) => o.id === state.obj) : null;
    const seriesObj = obj ? seriesFor(obj.id) : null;
    renderStatus(state.coverage || evaluateCoordinate(state.coord.ra, state.coord.dec), state.coord, obj, seriesObj);
    applyCoverageToViewer(state.coverage || evaluateCoordinate(state.coord.ra, state.coord.dec), state.coord);
  }
  renderPresets();
  if (state.seriesObj) {
    const variant = variantFor(state.seriesObj.id);
    if (variant) {
      $("#series-chain-label").textContent = t("chainLabel");
      $("#chain-btn-main").textContent = t("chainMain");
      $("#chain-btn-variant").textContent = t("chainVariant");
      setChainButtons(state.seriesChain);
      renderChainNote(state.seriesObj, variant);
    }
    const wasPlaying = state.seriesPlaying;
    renderSeriesEpoch();
    if (wasPlaying && !reduceMotion()) playSeries();
  } else {
    renderVerdict();
    $("#series-empty-text").textContent = t("seriesPick");
  }
  renderLab();
  if (state.parallax) renderParallax(state.parallax);
  if (state.completeness) renderCompleteness(state.completeness);
}

function renderLegend() {
  const html = ["measured", "projected", "unknown"]
    .map((lv) => markerHTML(lv)).join("");
  for (const id of ["#hero-legend", "#zone-legend", "#zone-legend-notes"]) {
    const el = $(id);
    if (el) el.innerHTML = html;
  }
}

function initCoordinateUI() {
  $("#coord-form").addEventListener("submit", (e) => {
    e.preventDefault();
    applyCoordinate();
  });
}

function readURLState() {
  const params = new URLSearchParams(window.location.search);
  state.lang = "en";
  const objId = params.get("obj");
  const raRaw = params.get("ra");
  const decRaw = params.get("dec");
  let obj = objId ? state.objects.find((o) => o.id === objId) || null : null;
  let applied = false;
  if (raRaw && decRaw) {
    const ra = parseRA(raRaw);
    const dec = parseDec(decRaw);
    if (!ra.error && !dec.error) {
      $("#coord-ra").value = raRaw;
      $("#coord-dec").value = decRaw;
      applied = applyCoordinate(raRaw, decRaw, obj ? obj.id : null);
    }
  }
  if (!applied && obj) {
    $("#coord-ra").value = obj.ra_str;
    $("#coord-dec").value = obj.dec_str;
    applied = applyCoordinate(obj.ra_str, obj.dec_str, obj.id);
  }
  if (!applied) {
    // Default: the bundled P2 grid centre, read from images.json alignment.
    const fp = footprint();
    if (fp) {
      const raRaw2 = fp.cra.toFixed(6);
      const decRaw2 = fp.cdec.toFixed(6);
      $("#coord-ra").value = raRaw2;
      $("#coord-dec").value = decRaw2;
      applied = applyCoordinate(raRaw2, decRaw2, null);
    }
  }
  applyLang();

  // Deep link: optional chain and epoch index, applied only when the preset resolved.
  if (state.seriesObj) {
    const chain = params.get("chain");
    if (chain === "variant" && variantFor(state.seriesObj.id)) setChainInitial(chain);
    const epochRaw = Number(params.get("epoch"));
    const eps = activeSeries().epochs.length;
    if (Number.isInteger(epochRaw) && epochRaw >= 0 && epochRaw < eps) {
      state.seriesIndex = epochRaw;
      renderSeriesEpoch();
    }
    syncURL();
  }
  return applied;
}

function setChainInitial(chain) {
  state.seriesChain = chain;
  setChainButtons(chain);
  renderChainNote(state.seriesObj, variantFor(state.seriesObj.id));
  renderSeriesEpoch();
}


/* ---------- hypothesis lab, geometry only ---------- */

function labRow(par, distAu) {
  const rows = (par && par.geometry_full_baseline) || [];
  if (!rows.length) return null;
  /* Use the nearest tabulated row at or below the entered distance, so the printed
     shift is never larger than the true one for the requested distance. */
  let best = rows[0];
  for (const r of rows) {
    if (r.dist_au <= distAu && r.dist_au > best.dist_au) best = r;
    if (best.dist_au > distAu && r.dist_au < best.dist_au) best = r;
  }
  return best;
}

function renderLab() {
  const host = $("#lab-status");
  const note = $("#lab-note");
  if (!host) return;
  if (note) note.textContent = t("labNote");
  const par = state.parallax;
  if (!par || !par.geometry_full_baseline) {
    host.className = "status-strip is-uncovered";
    host.innerHTML = `<span class="status-head">${escapeAttr(t("labNoData"))}</span>`;
    return;
  }
  const raw = Number(String($("#lab-dist").value || "").replace(",", "."));
  if (!Number.isFinite(raw) || raw <= 0) {
    host.className = "status-strip is-uncovered";
    host.innerHTML = `<span class="status-head">${escapeAttr(t("labNoData"))}</span>`;
    return;
  }
  const row = labRow(par, raw);
  const inside = row.stays_in_half_field;
  host.className = "status-strip " + (inside ? "is-covered" : "is-partial");
  host.innerHTML = `
    <span>${markerHTML(inside ? "projected" : "unknown", inside ? null : t("labBadge"))}</span>
    <span class="status-head">${escapeAttr(t("labShift", {
      au: row.dist_au, arcsec: row.peak_shift_arcsec.toFixed(0),
      px: row.peak_shift_px.toFixed(1),
    }))}</span>
    <span class="status-detail">${escapeAttr(t("labHalfField", {
      half: par.half_field_arcsec, base: par.baseline_days,
      min: par.geometry_full_baseline[0].dist_au,
    }))}</span>`;
}

function initLab() {
  const input = $("#lab-dist");
  if (!input) return;
  input.addEventListener("input", renderLab);
  renderLab();
}

/* ---------- boot ---------- */

async function boot() {
  const [images, patches, controls, diff, parallax, completeness, shiftstack, thresholds, objects,
    series, seriesVariant, seriesRecovery] = await Promise.all([
    loadJSON("data/images.json"),
    loadJSON("data/patches.json"),
    loadJSON("data/wcs_controls.json"),
    loadJSON("data/diff.json").catch(() => ({ diffs: [], geometry_full_baseline: null })),
    loadJSON("data/parallax.json").catch(() => null),
    loadJSON("data/completeness.json").catch(() => null),
    loadJSON("data/shift_stack.json").catch(() => null),
    loadJSON("data/thresholds.json").catch(() => null),
    loadJSON("data/named_objects.json").catch(() => null),
    loadJSON("data/named_series.json").catch(() => null),
    loadJSON("data/named_series_wise0855_simbad.json").catch(() => null),
    loadJSON("data/named_recovery_summary.json").catch(() => null),
  ]);

  state.images = images.images;
  state.alignment = images.alignment || null;
  state.patches = Array.isArray(patches.patches) ? patches.patches : [];
  state.patchRadiusDeg = typeof patches.patch_radius_deg === "number" ? patches.patch_radius_deg : null;
  state.objects = objects && Array.isArray(objects.objects) ? objects.objects : [];
  state.series = series && Array.isArray(series.objects) ? series : null;
  state.seriesVariant = seriesVariant && Array.isArray(seriesVariant.objects) ? seriesVariant : null;
  state.seriesRecovery = seriesRecovery && Array.isArray(seriesRecovery.objects) ? seriesRecovery : null;
  state.parallax = parallax || null;
  state.completeness = completeness || null;
  state.diffs = diff.diffs || [];
  state.cmpA = state.images.length - 1;
  state.cmpB = 0;

  // Single viewer
  $("#epoch-slider").max = state.images.length - 1;
  $("#epoch-slider").addEventListener("input", (e) => {
    pause();
    state.index = Number(e.target.value);
    renderFrame();
  });
  $("#btn-play").addEventListener("click", togglePlay);

  // Compare viewer
  $("#cmp-slider-a").max = state.images.length - 1;
  $("#cmp-slider-b").max = state.images.length - 1;
  $("#cmp-slider-a").addEventListener("input", (e) => {
    state.cmpA = Number(e.target.value);
    renderCompare("a");
  });
  $("#cmp-slider-b").addEventListener("input", (e) => {
    state.cmpB = Number(e.target.value);
    renderCompare("b");
  });

  // Difference viewer
  if (state.diffs.length > 0) {
    $("#diff-slider").max = state.diffs.length - 1;
    $("#diff-slider").addEventListener("input", (e) => {
      state.diffIndex = Number(e.target.value);
      renderDiff();
    });
    renderDiff();
  }

  // Mode tabs
  $$(".mode-tabs .btn").forEach((b) =>
    b.addEventListener("click", () => setMode(b.dataset.mode)));

  initCoordinateUI();
  initSeriesUI();
  initDial();
  initLab();
  renderLegend();
  renderPresets();
  readURLState();

  renderFrame();
  renderCompare("a");
  renderCompare("b");
  renderAtlas(patches.patches);
  renderControls(controls.controls);
  renderParallax(state.parallax);
  renderCompleteness(state.completeness);
  renderShiftStack(shiftstack, thresholds);
  renderVerdict();

  $("#stat-images").textContent = state.images.length;
  $("#stat-patches").textContent = patches.patches.length;
  $("#stat-gate0").textContent = translateGateStatus(patches.generated_from.gate0_verdict);
  $("#stat-stacking").textContent = patches.generated_from.stacking_claimed
    ? t("claimedWord") : t("notClaimedWord");
}

document.addEventListener("DOMContentLoaded", boot);
