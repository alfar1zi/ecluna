// The answer figure in three dimensions: the cutout as a plane, the track as a
// line that crosses it and leaves. Turning it shows the geometry that the flat
// chart can only imply, which is that the track is far wider than the frame.
//
// three.js and OrbitControls are vendored; nothing is fetched at runtime.

import * as THREE from "../assets/vendor/js/three.module.min.js";
import { OrbitControls } from "../assets/vendor/js/OrbitControls.js";

// The cutout is 360 arcseconds across and the track spans 997, so the scene is
// built at that ratio: the plane is 2 units and the track is 5.5.
const PLANE = 2.0;
const TRACK = (997 / 360) * PLANE;

export function setupAnswerFigure(host, parallax) {
  const width = host.clientWidth || 640;
  const height = host.clientHeight || 220;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x1c1c1c);

  const camera = new THREE.PerspectiveCamera(34, width / height, 0.1, 100);
  camera.position.set(1.7, 1.3, 2.2);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(width, height, false);
  host.replaceChildren(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enablePan = false;
  controls.minDistance = 1.6;
  controls.maxDistance = 7;
  controls.rotateSpeed = 0.6;
  controls.zoomSpeed = 0.7;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.5;

  // The cutout carries a real frame, not a grey square: a reader who has never
  // seen a cutout needs to see that it is a photograph of the sky.
  const loader = new THREE.TextureLoader();
  const frameTexture = loader.load("../assets/blink/barnard/60908-9819.png");
  frameTexture.colorSpace = THREE.SRGBColorSpace;
  const plane = new THREE.Mesh(
    new THREE.PlaneGeometry(PLANE, PLANE),
    new THREE.MeshBasicMaterial({ map: frameTexture, side: THREE.DoubleSide }),
  );
  plane.rotation.x = -Math.PI / 2;
  scene.add(plane);

  const edge = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.PlaneGeometry(PLANE, PLANE)),
    new THREE.LineBasicMaterial({ color: 0x8f8f8f }),
  );
  edge.rotation.x = -Math.PI / 2;
  scene.add(edge);

  // The track: a line that enters low and leaves high, crossing the plane.
  const half = TRACK / 2;
  const rise = PLANE * 0.9;
  const trackPoints = [
    new THREE.Vector3(-half, -rise / 2, 0),
    new THREE.Vector3(half, rise / 2, 0),
  ];
  const track = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(trackPoints),
    new THREE.LineDashedMaterial({
      color: 0xe8a33d,
      dashSize: 0.14,
      gapSize: 0.10,
      linewidth: 3,
    }),
  );
  track.computeLineDistances();
  scene.add(track);

  // Where the track leaves the plane, marked, because that is the moment the
  // object is lost.
  const exitX = PLANE / 2;
  const exitY = (rise / 2) * (exitX / half);
  const exit = new THREE.Mesh(
    new THREE.SphereGeometry(0.055, 16, 12),
    new THREE.MeshBasicMaterial({ color: 0xe8a33d }),
  );
  exit.position.set(exitX, exitY, 0);
  scene.add(exit);

  // A small body on the track, so the line reads as an object rather than as a
  // rule. It sits where the track crosses the frame edge.
  const body = new THREE.Mesh(
    new THREE.SphereGeometry(0.085, 20, 14),
    new THREE.MeshBasicMaterial({ color: 0xe7e2d5 }),
  );
  body.position.set(exitX, exitY, 0.06);
  scene.add(body);

  // The two ends, so the reader can see the track continues past the frame.
  const endMaterial = new THREE.MeshBasicMaterial({ color: 0x8f8f8f });
  for (const point of trackPoints) {
    const dot = new THREE.Mesh(new THREE.SphereGeometry(0.035, 12, 10), endMaterial);
    dot.position.copy(point);
    scene.add(dot);
  }

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
    resize() {
      const w = host.clientWidth || width;
      const h = host.clientHeight || height;
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
        if (node.material) node.material.dispose();
      });
    },
  };
}
