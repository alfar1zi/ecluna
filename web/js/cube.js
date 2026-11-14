// Space-time cube: the one three-dimensional view on the page.
//
// The axes are sky east, sky north, and time. A star that does not move draws a
// vertical line; an object that moves draws a line that leans. The box is two
// pixels of sky wide, so the lean is the motion at the same scale as the frames.
//
// three.js is vendored; the drag handler is the only glue written here, because
// the vendored build carries no controls module.

import * as THREE from "../assets/vendor/js/three.module.min.js";

const CUBE_NAMES = {
  barnard: "Barnard's Star",
  epsindb: "Epsilon Indi B",
  wise0855: "WISE 0855",
  rwaur: "RW Aurigae",
  rdra: "R Draconis",
};

const SKY_HALF_PX = 1.0;   // the box spans two pixels of sky
const TIME_HEIGHT = 2.4;   // time is drawn taller than the sky, and labelled so

function buildScene(host, object) {
  const width = host.clientWidth || 640;
  const height = host.clientHeight || 420;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x1c1c1c);

  const camera = new THREE.PerspectiveCamera(32, width / height, 0.1, 100);
  camera.position.set(5.0, 2.4, 5.0);
  camera.lookAt(0, 0, 0);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(width, height, false);
  host.replaceChildren(renderer.domElement);

  // The box: sky on two axes, time on the third.
  const box = new THREE.LineSegments(
    new THREE.EdgesGeometry(
      new THREE.BoxGeometry(SKY_HALF_PX * 2, TIME_HEIGHT, SKY_HALF_PX * 2),
    ),
    new THREE.LineBasicMaterial({ color: 0x2a2a2a }),
  );
  scene.add(box);

  // One horizontal layer per visit, so the reader can count the visits.
  const points = object.track_map.points;
  const layerMaterial = new THREE.LineBasicMaterial({
    color: 0x3a3a3a,
    transparent: true,
    opacity: 0.9,
  });
  const n = points.length;
  // Time is the real interval between visits, not the visit number: Barnard has a
  // 196 day gap in the middle, and drawing that gap as one step makes the track
  // look like it jumps when it is a straight line.
  const t0 = points[0].mjd;
  const t1 = points[n - 1].mjd;
  const span = Math.max(1e-6, t1 - t0);
  const heightAt = (mjd) => -TIME_HEIGHT / 2 + (TIME_HEIGHT * (mjd - t0)) / span;
  // One layer per visit would be a solid stack when the visits cluster; every
  // fourth visit keeps the layers readable and the count is stated in the panel.
  const stride = Math.max(1, Math.round(n / 9));
  for (let i = 0; i < n; i += stride) {
    const y = heightAt(points[i].mjd);
    const geometry = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(-SKY_HALF_PX, y, -SKY_HALF_PX),
      new THREE.Vector3(SKY_HALF_PX, y, -SKY_HALF_PX),
      new THREE.Vector3(SKY_HALF_PX, y, SKY_HALF_PX),
      new THREE.Vector3(-SKY_HALF_PX, y, SKY_HALF_PX),
      new THREE.Vector3(-SKY_HALF_PX, y, -SKY_HALF_PX),
    ]);
    scene.add(new THREE.Line(geometry, layerMaterial));
  }

  // The track: east and north in pixels, time as height.
  const first = points[0];
  const track = points.map((p) => {
    const y = heightAt(p.mjd);
    return new THREE.Vector3(
      (p.east_px - first.east_px) / SKY_HALF_PX,
      y,
      (p.north_px - first.north_px) / SKY_HALF_PX,
    );
  });

  scene.add(new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(track),
    new THREE.LineBasicMaterial({ color: 0xe7e2d5, linewidth: 2 }),
  ));

  // A vertical reference from the first position: what a star that does not move
  // would draw. The gap between the two lines is the motion.
  scene.add(new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, -TIME_HEIGHT / 2, 0),
      new THREE.Vector3(0, TIME_HEIGHT / 2, 0),
    ]),
    new THREE.LineDashedMaterial({
      color: 0xe8a33d,
      dashSize: 0.08,
      gapSize: 0.06,
      transparent: true,
      opacity: 0.9,
    }),
  ));

  // Drag to turn. No auto-rotation: the page does not move on its own.
  let dragging = false;
  let lastX = 0;
  let lastY = 0;
  let yaw = 0.7;
  let pitch = 0.28;

  const apply = () => {
    const radius = 7.4;
    camera.position.set(
      radius * Math.cos(pitch) * Math.sin(yaw),
      radius * Math.sin(pitch),
      radius * Math.cos(pitch) * Math.cos(yaw),
    );
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
  };

  host.addEventListener("pointerdown", (event) => {
    dragging = true;
    lastX = event.clientX;
    lastY = event.clientY;
    host.setPointerCapture(event.pointerId);
  });

  host.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    yaw -= (event.clientX - lastX) * 0.008;
    pitch = Math.max(-1.2, Math.min(1.2, pitch + (event.clientY - lastY) * 0.006));
    lastX = event.clientX;
    lastY = event.clientY;
    apply();
  });

  const release = () => { dragging = false; };
  host.addEventListener("pointerup", release);
  host.addEventListener("pointercancel", release);

  apply();

  return {
    resize() {
      const w = host.clientWidth || width;
      const h = host.clientHeight || height;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h, false);
      apply();
    },
    dispose() {
      renderer.dispose();
      host.replaceChildren();
    },
  };
}

function cubeFacts(object) {
  const t = object.track_map;
  const rows = [
    ["Visits", String(t.points.length)],
    ["Motion across the series", `${t.span_px.toFixed(2)} px`],
    ["Box width", "2 px of sky"],
    ["Motion source", "catalogued proper motion"],
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

export function setupCube(host, object) {
  // A hidden view has no size, and a canvas built at zero size stays invisible.
  // The scene is built on the first frame where the stage has a width, and rebuilt
  // when the stage changes size.
  let scene = null;
  let observer = null;

  const build = () => {
    if (host.clientWidth < 40 || host.clientHeight < 40) return;
    if (scene) scene.dispose();
    scene = buildScene(host, object);
  };

  if (typeof ResizeObserver === "function") {
    observer = new ResizeObserver(() => {
      if (!scene) build();
      else scene.resize();
    });
    observer.observe(host);
  }

  build();

  return {
    resize() { if (scene) scene.resize(); },
    dispose() {
      if (observer) observer.disconnect();
      if (scene) scene.dispose();
      scene = null;
    },
  };
}
