/* ============================================================================
   Cinematic landing intro — a suspicious data packet travels across a
   network toward a central server, then a "threat detected" pulse fires,
   before the camera settles and the login console is revealed. Built with
   Three.js, kept lightweight (capped node count, pauses off-screen/reduced
   motion) — same conservative approach as the rest of the app's 3D bits.
============================================================================ */
(function () {
  const host = document.getElementById('introCanvas');
  if (!host) return;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (typeof THREE === 'undefined') { window.introSkip3D = true; return; }

  const NODE_COLOR = 0x2fe6b8;
  const LINK_COLOR = 0x1f6e5c;
  const SERVER_COLOR = 0x4da3ff;
  const THREAT_COLOR = 0xff5f70;

  const isMobile = window.innerWidth < 700;
  const NODE_COUNT = isMobile ? 26 : 46;
  const FIELD = isMobile ? 10 : 14;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 100);
  camera.position.set(0, 1.2, 16);

  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.setSize(window.innerWidth, window.innerHeight);
  host.appendChild(renderer.domElement);

  const group = new THREE.Group();
  scene.add(group);

  // ---- peripheral nodes ----
  const nodeGeo = new THREE.SphereGeometry(0.05, 8, 8);
  const nodeMat = new THREE.MeshBasicMaterial({ color: NODE_COLOR, transparent: true, opacity: 0.7 });
  const nodes = [];
  for (let i = 0; i < NODE_COUNT; i++) {
    const m = new THREE.Mesh(nodeGeo, nodeMat.clone());
    const angle = Math.random() * Math.PI * 2;
    const radius = FIELD * (0.4 + Math.random() * 0.6);
    m.position.set(Math.cos(angle) * radius, (Math.random() - 0.5) * FIELD * 0.5, Math.sin(angle) * radius);
    group.add(m);
    nodes.push(m);
  }

  // ---- central server node ----
  const serverGeo = new THREE.IcosahedronGeometry(0.4, 0);
  const serverMat = new THREE.MeshBasicMaterial({ color: SERVER_COLOR, wireframe: true });
  const server = new THREE.Mesh(serverGeo, serverMat);
  group.add(server);

  // ---- links from every node to the server (faint) ----
  const linkGeo = new THREE.BufferGeometry();
  const positions = new Float32Array(nodes.length * 2 * 3);
  nodes.forEach((n, i) => {
    positions[i * 6 + 0] = n.position.x; positions[i * 6 + 1] = n.position.y; positions[i * 6 + 2] = n.position.z;
    positions[i * 6 + 3] = 0; positions[i * 6 + 4] = 0; positions[i * 6 + 5] = 0;
  });
  linkGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  const linkMat = new THREE.LineBasicMaterial({ color: LINK_COLOR, transparent: true, opacity: 0.25 });
  group.add(new THREE.LineSegments(linkGeo, linkMat));

  // ---- the suspicious packet ----
  const packetGeo = new THREE.SphereGeometry(0.09, 10, 10);
  const packetMat = new THREE.MeshBasicMaterial({ color: THREAT_COLOR });
  const packet = new THREE.Mesh(packetGeo, packetMat);
  const originNode = nodes[Math.floor(Math.random() * nodes.length)];
  packet.position.copy(originNode.position);
  group.add(packet);

  // ---- threat pulse ring (hidden until the packet arrives) ----
  const ringGeo = new THREE.RingGeometry(0.4, 0.42, 48);
  const ringMat = new THREE.MeshBasicMaterial({ color: THREAT_COLOR, transparent: true, opacity: 0, side: THREE.DoubleSide });
  const ring = new THREE.Mesh(ringGeo, ringMat);
  ring.rotation.x = Math.PI / 2;
  group.add(ring);

  let phase = 'travel'; // travel -> impact -> settle
  let t = 0;
  let impactT = 0;

  function resize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  }
  window.addEventListener('resize', resize);

  let visible = !document.hidden;
  document.addEventListener('visibilitychange', () => { visible = !document.hidden; });

  function animate() {
    requestAnimationFrame(animate);
    if (!visible) return;
    t += 1;

    group.rotation.y += 0.0012;
    server.rotation.y += 0.01;
    server.rotation.x += 0.006;

    if (phase === 'travel') {
      const progress = Math.min(1, t / (reduced ? 1 : 110));
      packet.position.lerpVectors(originNode.position, server.position, progress);
      packet.material.opacity = 1;
      if (progress >= 1) { phase = 'impact'; impactT = 0; }
    } else if (phase === 'impact') {
      impactT += 1;
      const p = Math.min(1, impactT / 40);
      ring.scale.setScalar(0.5 + p * 6);
      ring.material.opacity = 0.9 * (1 - p);
      server.material.color.setHex(THREAT_COLOR);
      if (impactT === 1) document.dispatchEvent(new CustomEvent('intro:threat-detected'));
      if (impactT > 40) { phase = 'settle'; server.material.color.setHex(SERVER_COLOR); }
    }

    renderer.render(scene, camera);
  }
  animate();
})();
