// The solar system in three dimensions, turnable, with real surfaces.
//
// The radial scale is logarithmic, because Neptune at 30 AU and the boundary at
// 2,219 AU cannot share a linear axis: on a linear one Neptune would be a dot at
// the centre. The mapping is the same one the flat chart uses, so the two views
// agree about where the boundary is.
//
// Assets, all self-hosted, no network at runtime:
//   three.js r187 and OrbitControls, MIT, mrdoob/three.js
//   planet and sky textures, CC BY 4.0, Solar System Scope
//     https://www.solarsystemscope.com/textures/
// The textures are the only imagery on the page that is not our own data, and
// they are used for the bodies, never for the measurement.

import * as THREE from "../assets/vendor/js/three.module.min.js";
import { OrbitControls } from "../assets/vendor/js/OrbitControls.js";

const INNER_AU = 1;
const OUTER_AU = 100000;
const RADIUS = 3.2;

const TEXTURES = "../assets/vendor/textures/";

function radiusOf(au) {
  const t = (Math.log10(au) - Math.log10(INNER_AU)) / (Math.log10(OUTER_AU) - Math.log10(INNER_AU));
  return t * RADIUS;
}

// Equatorial coordinates to a point on a sphere. The scene is drawn with the
// ecliptic as the horizontal plane, so the sky is rotated by the obliquity.
const OBLIQUITY = (23.44 * Math.PI) / 180;

function skyPoint(raDeg, decDeg, radius) {
  const ra = (raDeg * Math.PI) / 180;
  const dec = (decDeg * Math.PI) / 180;
  const x = Math.cos(dec) * Math.cos(ra);
  const y = Math.cos(dec) * Math.sin(ra);
  const z = Math.sin(dec);
  const y2 = y * Math.cos(OBLIQUITY) - z * Math.sin(OBLIQUITY);
  const z2 = y * Math.sin(OBLIQUITY) + z * Math.cos(OBLIQUITY);
  return new THREE.Vector3(x * radius, z2 * radius, y2 * radius);
}

function ring(radius, colour, opacity, segments = 160) {
  const points = [];
  for (let i = 0; i <= segments; i += 1) {
    const a = (i / segments) * Math.PI * 2;
    points.push(new THREE.Vector3(Math.cos(a) * radius, 0, Math.sin(a) * radius));
  }
  return new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(points),
    new THREE.LineBasicMaterial({ color: colour, transparent: true, opacity }),
  );
}

export function setupSystem(host, parallax, patches) {
  // The host has no padding, so the canvas fills it exactly and the frame sits
  // flush against the scene.
  const width = Math.max(320, host.clientWidth || 640);
  const height = Math.max(240, host.clientHeight || 420);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0a0a);

  const camera = new THREE.PerspectiveCamera(38, width / height, 0.1, 200);
  camera.position.set(6.4, 3.4, 6.4);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  renderer.setSize(width, height, false);
  host.replaceChildren(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 4.5;
  controls.maxDistance = 18;
  controls.enablePan = false;
  controls.rotateSpeed = 0.6;
  controls.zoomSpeed = 0.7;
  // The scene turns slowly on its own so it reads as a place rather than a
  // picture, and stops the moment a hand touches it.
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.35;

  // Light, so the bodies have a lit side and a dark side instead of reading as
  // flat discs. The Sun is the only source, which is also the truth.
  scene.add(new THREE.AmbientLight(0xffffff, 0.18));
  const sunLight = new THREE.PointLight(0xfff2dd, 2.4, 0, 0);
  sunLight.position.set(0, 0, 0);
  scene.add(sunLight);

  const loader = new THREE.TextureLoader();

  // A real starfield: three thousand points on a sphere, so the background has
  // depth and parallax instead of being a flat photograph.
  const starCount = 3000;
  const starPositions = new Float32Array(starCount * 3);
  const starSizes = new Float32Array(starCount);
  for (let i = 0; i < starCount; i += 1) {
    const u = Math.random() * 2 - 1;
    const theta = Math.random() * Math.PI * 2;
    const r = RADIUS * 5.5;
    const s2 = Math.sqrt(1 - u * u);
    starPositions[i * 3] = r * s2 * Math.cos(theta);
    starPositions[i * 3 + 1] = r * u;
    starPositions[i * 3 + 2] = r * s2 * Math.sin(theta);
    starSizes[i] = Math.random() * 0.9 + 0.25;
  }
  const starGeometry = new THREE.BufferGeometry();
  starGeometry.setAttribute("position", new THREE.BufferAttribute(starPositions, 3));
  starGeometry.setAttribute("size", new THREE.BufferAttribute(starSizes, 1));
  const stars = new THREE.Points(
    starGeometry,
    new THREE.PointsMaterial({
      color: 0xcfc9bb,
      size: 0.035,
      sizeAttenuation: true,
      transparent: true,
      opacity: 0.85,
    }),
  );
  scene.add(stars);

  // The sky behind everything, so the scene reads as space rather than as a void.
  const sky = new THREE.Mesh(
    new THREE.SphereGeometry(RADIUS * 6, 48, 32),
    new THREE.MeshBasicMaterial({
      map: loader.load(`${TEXTURES}2k_stars_milky_way.jpg`),
      side: THREE.BackSide,
      color: 0x555555,
    }),
  );
  scene.add(sky);

  const crossing = (parallax.geometry_full_baseline[0].dist_au
    * parallax.geometry_full_baseline[0].peak_shift_arcsec) / parallax.half_field_arcsec;

  // The ecliptic as a grid rather than a filled disc: a dark disc reads as a
  // shadow behind the Sun, which is not what it is.
  const grid = new THREE.PolarGridHelper(RADIUS, 8, 6, 96, 0x2a2a2a, 0x242424);
  grid.material.transparent = true;
  grid.material.opacity = 0.55;
  scene.add(grid);

  // Decade rings, so the log scale is readable.
  for (const au of [10, 100, 1000, 10000]) {
    const decade = ring(radiusOf(au), 0x2a2a2a, 0.9);
    decade.position.y = 0.006;
    scene.add(decade);
  }

  // Neptune, with its real surface, on its orbit.
  const neptune = new THREE.Mesh(
    new THREE.SphereGeometry(0.11, 32, 24),
    new THREE.MeshStandardMaterial({
      map: loader.load(`${TEXTURES}2k_neptune.jpg`),
      roughness: 0.85,
      metalness: 0.0,
    }),
  );
  neptune.position.set(radiusOf(30), 0, 0);
  scene.add(neptune);
  const neptuneOrbit = ring(radiusOf(30), 0xe7e2d5, 0.5);
  neptuneOrbit.position.y = 0.008;
  scene.add(neptuneOrbit);

  // The Sun, with its real surface, and a glow so it reads as the light source.
  const sun = new THREE.Mesh(
    new THREE.SphereGeometry(0.22, 32, 24),
    new THREE.MeshBasicMaterial({ map: loader.load(`${TEXTURES}2k_sun.jpg`) }),
  );
  scene.add(sun);
  // A glow as a sprite, not a sphere: a back-facing sphere inside the Sun renders
  // as a dark shell, which is what the first attempt looked like.
  const glowCanvas = document.createElement("canvas");
  glowCanvas.width = 128;
  glowCanvas.height = 128;
  const gctx = glowCanvas.getContext("2d");
  const gradient = gctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  gradient.addColorStop(0, "rgba(255,220,150,0.55)");
  gradient.addColorStop(0.35, "rgba(232,163,61,0.18)");
  gradient.addColorStop(1, "rgba(232,163,61,0)");
  gctx.fillStyle = gradient;
  gctx.fillRect(0, 0, 128, 128);
  const glow = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(glowCanvas),
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    }),
  );
  glow.scale.set(1.5, 1.5, 1);
  scene.add(glow);

  // The boundary: inside it the cutout cannot follow an object. A ring, not a
  // sphere, because a sphere hides the inside and the inside is the point.
  // A flat annulus rather than a line, because WebGL ignores line width and the
  // boundary has to be the heaviest ring in the scene.
  const boundaryRing = new THREE.Mesh(
    new THREE.RingGeometry(radiusOf(crossing) - 0.012, radiusOf(crossing) + 0.012, 160),
    new THREE.MeshBasicMaterial({
      color: 0xe8a33d,
      transparent: true,
      opacity: 0.9,
      side: THREE.DoubleSide,
    }),
  );
  boundaryRing.rotation.x = -Math.PI / 2;
  // Lifted off the plane, or the two surfaces fight for the same depth.
  boundaryRing.position.y = 0.012;
  scene.add(boundaryRing);
  scene.add(ring(RADIUS, 0xe8a33d, 0.30));

  // The patches, as directions on the outer sphere.
  // The patches are directions, so they are drawn as small rings facing the
  // centre rather than as dots, which would read as stars.
  const patchMaterial = new THREE.MeshBasicMaterial({
    color: 0xe7e2d5,
    transparent: true,
    opacity: 0.85,
    side: THREE.DoubleSide,
  });
  for (const patch of patches) {
    if (typeof patch.ra_deg !== "number" || typeof patch.dec_deg !== "number") continue;
    const marker = new THREE.Mesh(new THREE.RingGeometry(0.035, 0.055, 20), patchMaterial);
    marker.position.copy(skyPoint(patch.ra_deg, patch.dec_deg, RADIUS * 0.99));
    marker.lookAt(0, 0, 0);
    scene.add(marker);
  }

  // Clicking a body opens a bubble with what is known about it. The bodies are
  // the only things in the scene that carry a fact, so they are the only things
  // that respond to a click.
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const bubble = document.createElement("div");
  bubble.className = "scene-bubble";
  bubble.hidden = true;
  host.append(bubble);

  const FACTS = {
    sun: {
      title: "The Sun",
      lines: [
        ["distance", "1 AU"],
        ["role here", "the light source, and the origin of the distance scale"],
      ],
    },
    neptune: {
      title: "Neptune",
      lines: [
        ["distance", "30 AU"],
        ["role here", "the reference orbit every reader knows"],
      ],
    },
  };

  const pickable = [
    { mesh: sun, key: "sun" },
    { mesh: neptune, key: "neptune" },
  ];

  renderer.domElement.addEventListener("click", (event) => {
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects(pickable.map((p) => p.mesh), false);
    if (hits.length === 0) {
      bubble.hidden = true;
      return;
    }
    const hit = hits[0].object;
    const entry = pickable.find((p) => p.mesh === hit);
    const facts = FACTS[entry.key];
    bubble.replaceChildren();
    const title = document.createElement("strong");
    title.textContent = facts.title;
    bubble.append(title);
    for (const [name, value] of facts.lines) {
      const row = document.createElement("span");
      row.textContent = `${name}: ${value}`;
      bubble.append(row);
    }
    bubble.style.left = `${event.clientX - rect.left + 14}px`;
    bubble.style.top = `${event.clientY - rect.top - 10}px`;
    bubble.hidden = false;
  });

  let idleTimer = null;
  const wake = () => {
    controls.autoRotate = false;
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => { controls.autoRotate = true; }, 4000);
  };
  renderer.domElement.addEventListener("pointerdown", wake);
  renderer.domElement.addEventListener("wheel", wake, { passive: true });

  let frame = 0;
  function animate() {
    frame = requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();

  return {
    // Exposed so a test can prove the controls actually move the camera.
    get camera() { return camera; },
    resize() {
      const w = Math.max(320, host.clientWidth || width);
      const h = Math.max(240, host.clientHeight || height);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h, false);
    },
    dispose() {
      cancelAnimationFrame(frame);
      clearTimeout(idleTimer);
      controls.dispose();
      renderer.dispose();
      scene.traverse((node) => {
        if (node.geometry) node.geometry.dispose();
        if (node.material) {
          if (node.material.map) node.material.map.dispose();
          node.material.dispose();
        }
      });
    },
  };
}
