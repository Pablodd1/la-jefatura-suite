/**
 * High-Definition 3D Brain Data Network ("El Cerebro del Jefe")
 * Shared interactive 60 FPS Retina renderer for all Mission Control Website Editions.
 * Features:
 *  - Translucent anatomical 3D cortical shell + 2,500 neural particles
 *  - Dynamic curved 3D cubic Bezier data connector splines
 *  - Luminous streaming data packets with comet trails
 *  - Obsidian depth-of-field knowledge graph plexus + math telemetry overlays
 *  - Holographic circular target reticles & frameless leader labels
 */
(function () {
  function initBrainNetwork(canvasId, paletteMode) {
    const canvas = document.getElementById(canvasId || 'brain3dCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const shellImg = new Image();
    let shellReady = false;
    shellImg.onload = () => { shellReady = true; };
    shellImg.src = '/assets/brain-cortex-cutout.png';

    // Palettes tailored to each Website Edition
    const PALETTES = {
      editorial: {
        bgInner: 'rgba(18, 22, 30, 0.96)',
        bgMid:   'rgba(10, 13, 19, 0.98)',
        bgOuter: 'rgba(5, 7, 11, 1.0)',
        acc: [235, 185, 85],   // warm champagne gold
        amb: [185, 120, 40],   // warm bronze
        cyn: [90, 175, 245]    // Cupertino azure
      },
      bloomberg: {
        bgInner: 'rgba(14, 23, 38, 0.96)',
        bgMid:   'rgba(9, 15, 26, 0.98)',
        bgOuter: 'rgba(5, 9, 16, 1.0)',
        acc: [56, 189, 248],   // sapphire cyan-ice
        amb: [16, 185, 129],   // institutional emerald
        cyn: [245, 190, 65]    // amber-gold accent
      },
      gold: {
        bgInner: 'rgba(25, 31, 39, 0.94)',
        bgMid:   'rgba(13, 16, 21, 0.97)',
        bgOuter: 'rgba(4, 5, 8, 1.0)',
        acc: [255, 204, 48],
        amb: [215, 132, 22],
        cyn: [110, 205, 235]
      }
    };

    let currentPalette = PALETTES[paletteMode] || PALETTES.gold;
    let ACC = currentPalette.acc;
    let AMB = currentPalette.amb;
    let CYN = currentPalette.cyn;
    let glowDot = null;
    let packetDot = null;

    function buildSprites() {
      const s1 = document.createElement('canvas');
      s1.width = s1.height = 64;
      const g1 = s1.getContext('2d');
      const gr1 = g1.createRadialGradient(32, 32, 0, 32, 32, 32);
      gr1.addColorStop(0.0, 'rgba(255, 252, 235, 0.95)');
      gr1.addColorStop(0.22, `rgba(${ACC[0]}, ${ACC[1]}, ${ACC[2]}, 0.78)`);
      gr1.addColorStop(0.55, `rgba(${AMB[0]}, ${AMB[1]}, ${AMB[2]}, 0.22)`);
      gr1.addColorStop(1.0, `rgba(${AMB[0]}, ${AMB[1]}, ${AMB[2]}, 0)`);
      g1.fillStyle = gr1;
      g1.fillRect(0, 0, 64, 64);
      glowDot = s1;

      const s2 = document.createElement('canvas');
      s2.width = s2.height = 64;
      const g2 = s2.getContext('2d');
      const gr2 = g2.createRadialGradient(32, 32, 0, 32, 32, 32);
      gr2.addColorStop(0.0, 'rgba(255, 255, 255, 1)');
      gr2.addColorStop(0.18, 'rgba(255, 250, 220, 0.95)');
      gr2.addColorStop(0.45, `rgba(${ACC[0]}, ${ACC[1]}, ${ACC[2]}, 0.52)`);
      gr2.addColorStop(1.0, `rgba(${ACC[0]}, ${ACC[1]}, ${ACC[2]}, 0)`);
      g2.fillStyle = gr2;
      g2.fillRect(0, 0, 64, 64);
      packetDot = s2;
    }
    buildSprites();

    let width = 0, height = 0, dpr = 2;
    function resize() {
      const rect = canvas.getBoundingClientRect();
      dpr = Math.max(2, Math.min(3, window.devicePixelRatio || 1));
      width = rect.width || 680;
      height = rect.height || 520;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    window.addEventListener('resize', resize);

    let seed = 20261025;
    function rand() {
      seed = (seed * 16807) % 2147483647;
      return (seed - 1) / 2147483646;
    }

    // 1. Background Obsidian Knowledge Graph
    const bgNodes = [];
    const bgEdges = [];
    for (let i = 0; i < 115; i++) {
      const ang = rand() * Math.PI * 2;
      const rad = 0.34 + 0.70 * Math.pow(rand(), 0.72);
      const x = Math.cos(ang) * rad * 430 + (rand() - 0.5) * 60;
      const y = Math.sin(ang) * rad * 275 + (rand() - 0.5) * 40;
      const z = -220 + rand() * 440;
      bgNodes.push({ x, y, z, rSize: 1.0 + rand() * 2.3 });
    }
    for (let i = 0; i < bgNodes.length; i++) {
      const a = bgNodes[i];
      const dists = [];
      for (let j = i + 1; j < bgNodes.length; j++) {
        const b = bgNodes[j];
        const dx = a.x - b.x, dy = a.y - b.y, dz = (a.z - b.z) * 0.5;
        const d2 = dx * dx + dy * dy + dz * dz;
        if (d2 < 15000) dists.push({ d2, j });
      }
      dists.sort((p, q) => p.d2 - q.d2);
      for (let k = 0; k < Math.min(3, dists.length); k++) bgEdges.push([i, dists[k].j]);
    }

    const mathOverlays = [
      { x: -118, y: -152, z: -60, lines: ['X=11.3 Y=42.8 Z=0.081'] },
      { x: 175, y: -132, z: -90, lines: ['SYS:MC.DB // ZERO-GUESS = 1'] },
      { x: 238, y: -18, z: -50, lines: ['U:29 // A:98.7% // S:0.04'] },
      { x: 92, y: 172, z: -40, lines: ['DEV:GEN = 1', '[b=12.401, f=94.12]', '[d=382, t=60fps, h=100%]'] },
      { x: -235, y: 92, z: -80, lines: ['[SLA:24H/48H // LOCK=0]'] }
    ];

    // 2. 3D Anatomical Brain Particles
    function sculptCortexPoint(theta, phi, hemi, shellScale) {
      const sx = Math.sin(phi) * Math.cos(theta);
      const sy = -Math.cos(phi);
      const sz = Math.sin(phi) * Math.sin(theta);
      let x = sx * 116;
      let y = sy * 88;
      let z = hemi * (5 + Math.abs(sz) * 54);
      if (y < 0) y -= Math.cos(sx * 1.15) * 13;
      else {
        if (x < -16) { y *= 0.36; y -= 9; }
        else if (x > 38) { y *= 0.42; y -= 4; }
      }
      const tempMask = Math.exp(-Math.pow((sx - 0.04) / 0.48, 2)) * Math.exp(-Math.pow((sy - 0.45) / 0.38, 2));
      y += tempMask * 26;
      x -= tempMask * 12;
      z += hemi * tempMask * 11;
      const gyri = 1.0
        + 0.046 * Math.sin(x * 0.14 + y * 0.11) * Math.cos(y * 0.16 - z * 0.09)
        + 0.030 * Math.cos(x * 0.23 - y * 0.19 + z * 0.12);
      return { x: x * gyri * shellScale, y: (y * gyri - 12) * shellScale, z: z * gyri * shellScale, sulcus: gyri };
    }

    const particles = [];
    const GOLD = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < 1850; i++) {
      const u = 1 - 2 * (i + 0.5) / 1850;
      const phi = Math.acos(Math.max(-1, Math.min(1, u)));
      const theta = (GOLD * i) % (Math.PI * 2);
      const hemi = (i % 2 === 0) ? 1 : -1;
      const shell = (i % 4 === 0) ? (0.55 + 0.35 * rand()) : (0.93 + 0.08 * rand());
      const p = sculptCortexPoint(theta, phi, hemi, shell);
      const ridgeBoost = Math.max(0.2, Math.min(1.15, (p.sulcus - 0.95) * 11.0));
      particles.push({
        x: p.x, y: p.y, z: p.z,
        nx: p.x / 120, ny: p.y / 95, nz: p.z / 60,
        size: 0.6 + rand() * 1.05,
        bright: (0.32 + 0.62 * ridgeBoost) * (shell > 0.9 ? 1.0 : 0.6),
        kind: 'cortex'
      });
    }
    for (let i = 0; i < 240; i++) {
      const t = (i / 239) * Math.PI * 1.25 - 0.30;
      const rTube = 3.5 + rand() * 8;
      const aTube = rand() * Math.PI * 2;
      const cx = -5 + Math.cos(Math.PI - t) * 52 + Math.cos(aTube) * rTube;
      const cy = -6 - Math.sin(Math.PI - t) * 38 + Math.sin(aTube) * rTube * 0.8;
      const cz = (rand() - 0.5) * 24;
      particles.push({
        x: cx, y: cy, z: cz,
        nx: 0, ny: -0.3, nz: cz >= 0 ? 0.8 : -0.8,
        size: 0.95 + rand() * 1.15,
        bright: 0.8 + rand() * 0.3,
        kind: 'limbic'
      });
    }
    for (let i = 0; i < 360; i++) {
      const u = 1 - 2 * (i + 0.5) / 360;
      const phi = Math.acos(Math.max(-1, Math.min(1, u)));
      const theta = GOLD * i;
      const hemi = (i % 2 === 0) ? 1 : -1;
      const folia = 1.0 + 0.06 * Math.sin(u * 28);
      const sx = Math.sin(phi) * Math.cos(theta);
      const sy = -Math.cos(phi);
      const sz = Math.sin(phi) * Math.sin(theta);
      particles.push({
        x: 40 + sx * 35 * folia,
        y: 48 + sy * 23 * folia,
        z: hemi * (4 + Math.abs(sz) * 30 * folia),
        nx: sx, ny: sy, nz: hemi * Math.abs(sz),
        size: 0.6 + rand() * 0.9,
        bright: 0.42 + 0.45 * Math.abs(Math.sin(u * 28)),
        kind: 'cerebellum'
      });
    }
    for (let i = 0; i < 120; i++) {
      const t = i / 119;
      const ang = GOLD * i;
      const rad = (11.5 - t * 5) * (0.75 + 0.25 * rand());
      particles.push({
        x: 7 + t * 13 + Math.cos(ang) * rad,
        y: 38 + t * 52,
        z: Math.sin(ang) * rad * 0.85,
        nx: Math.cos(ang), ny: 0.2, nz: Math.sin(ang),
        size: 0.6 + rand() * 0.85,
        bright: 0.4 + (1 - t) * 0.35,
        kind: 'stem'
      });
    }

    const webEdges = [];
    for (let i = 0; i < particles.length; i += 2) {
      const a = particles[i];
      let best1 = -1, best2 = -1, d1 = 175, d2 = 175;
      for (let j = i + 1; j < Math.min(particles.length, i + 90); j++) {
        const b = particles[j];
        const dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
        const dd = dx * dx + dy * dy + dz * dz;
        if (dd < d1) { d2 = d1; best2 = best1; d1 = dd; best1 = j; }
        else if (dd < d2) { d2 = dd; best2 = j; }
      }
      if (best1 !== -1) webEdges.push([i, best1]);
      if (best2 !== -1) webEdges.push([i, best2]);
    }

    // 3. Company Nodes & Curved Bezier Splines
    const companyNodes = [
      { id: 'mbmb', title: 'MBMB', metric: '$18.6k/m', x: -175, y: -110, z: 20, labelDy: -14,
        splines: [{ cp1: [-125, -108, 28], cp2: [-82, -88, 22], dst: [-48, -62, 18] }] },
      { id: 'cedexx_l', title: 'CEDEXX', metric: '$12.8k/m', x: -232, y: -18, z: -12, labelDy: -14,
        splines: [{ cp1: [-182, 18, 16], cp2: [-132, 26, 20], dst: [-86, 12, 16] }] },
      { id: 'dlm', title: 'DLM', metric: '$16.8k/m', x: -188, y: 106, z: 14, labelDy: -14,
        splines: [{ cp1: [-134, 108, 18], cp2: [-92, 82, 20], dst: [-46, 36, 18] }] },
      { id: 'cedexx_top', title: 'CEDEXX', metric: '$12.8k/m', x: 108, y: -142, z: -18, labelDy: -8,
        splines: [{ cp1: [58, -138, -8], cp2: [28, -106, 10], dst: [10, -72, 14] }] },
      { id: 'unitec', title: 'UNITEC USA', metric: '29 Leads', x: 162, y: -82, z: 24, labelDy: -8,
        splines: [
          { cp1: [115, -86, 22], cp2: [82, -68, 18], dst: [52, -42, 16] },
          { cp1: [136, -34, 12], cp2: [106, -4, 14], dst: [70, 12, 12] }
        ] },
      { id: 'bapp_top', title: 'BuildingApp.us', metric: '7 VIPs', x: 178, y: -12, z: -8, labelDy: -10,
        splines: [{ cp1: [148, 28, 14], cp2: [114, 42, 16], dst: [76, 22, 14] }] },
      { id: 'bapp_bot', title: 'BuildingApp.us', metric: '130 Renders', x: 154, y: 106, z: 16, labelDy: -10,
        splines: [
          { cp1: [152, 54, 14], cp2: [122, 26, 18], dst: [76, 12, 14] },
          { cp1: [116, 114, 10], cp2: [86, 100, 12], dst: [54, 68, 10] }
        ] }
    ];

    const allSplines = [];
    companyNodes.forEach((cn, cIdx) => {
      cn.splines.forEach((sp, sIdx) => {
        const packets = [];
        const pCount = 2 + ((cIdx + sIdx) % 2);
        for (let k = 0; k < pCount; k++) {
          packets.push({ offset: k / pCount + rand() * 0.22, speed: 0.22 + rand() * 0.12, size: 0.78 + rand() * 0.32 });
        }
        allSplines.push({ p0: [cn.x, cn.y, cn.z], p1: sp.cp1, p2: sp.cp2, p3: sp.dst, packets });
      });
    });

    function evalBezier3D(p0, p1, p2, p3, t) {
      const u = 1 - t;
      const b0 = u * u * u, b1 = 3 * u * u * t, b2 = 3 * u * t * t, b3 = t * t * t;
      return [
        b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0],
        b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1],
        b0 * p0[2] + b1 * p1[2] + b2 * p2[2] + b3 * p3[2]
      ];
    }

    let rotY = 0.0, rotX = -0.08, spinning = true, mode = 'cortex';
    let dragging = false, lastX = 0, lastY = 0;
    canvas.addEventListener('pointerdown', (e) => { dragging = true; lastX = e.clientX; lastY = e.clientY; });
    window.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      rotY += (e.clientX - lastX) * 0.007;
      rotX = Math.max(-0.5, Math.min(0.5, rotX + (e.clientY - lastY) * 0.005));
      lastX = e.clientX; lastY = e.clientY;
    });
    window.addEventListener('pointerup', () => { dragging = false; });

    window.setBrainMode = function (m, btn) {
      mode = m;
      document.querySelectorAll('.brain-mode-btn').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');
    };
    window.toggleBrainSpin = function (btn) {
      spinning = !spinning;
      if (btn) btn.textContent = spinning ? '⏸ Pausar Giro' : '▶ Reanudar Giro';
    };

    function project3D(x, y, z, rotScale = 1.0) {
      const ry = rotY * rotScale;
      const rx = rotX * (0.6 + 0.4 * rotScale);
      const cy = Math.cos(ry), sy = Math.sin(ry);
      const x1 = x * cy + z * sy;
      const z1 = -x * sy + z * cy;
      const cx = Math.cos(rx), sx = Math.sin(rx);
      const y2 = y * cx - z1 * sx;
      const z2 = y * sx + z1 * cx;
      const fov = Math.min(width, height) * 1.18;
      const dist = 520;
      const scale = fov / Math.max(140, dist + z2);
      return { px: width * 0.5 + x1 * scale, py: height * 0.51 + y2 * scale, z: z2, scale };
    }

    let tick = 0;
    function render() {
      tick += 0.016;
      if (spinning && !dragging) {
        if (mode === 'synapse') rotY += 0.0085;
        else {
          rotY = Math.sin(tick * 0.55) * 0.34;
          rotX = -0.07 + Math.cos(tick * 0.4) * 0.04;
        }
      }

      ctx.globalCompositeOperation = 'source-over';
      ctx.clearRect(0, 0, width, height);

      const cx = width * 0.5, cy = height * 0.51;
      const rgbAcc = `${ACC[0]},${ACC[1]},${ACC[2]}`;
      const rgbAmb = `${AMB[0]},${AMB[1]},${AMB[2]}`;
      const rgbCyn = `${CYN[0]},${CYN[1]},${CYN[2]}`;

      const bgGrad = ctx.createRadialGradient(cx, cy, 10, cx, cy, Math.max(width, height) * 0.68);
      bgGrad.addColorStop(0.0, currentPalette.bgInner);
      bgGrad.addColorStop(0.48, currentPalette.bgMid);
      bgGrad.addColorStop(1.0, currentPalette.bgOuter);
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, width, height);

      const coreAura = ctx.createRadialGradient(cx, cy - 4, 8, cx, cy - 4, Math.min(width, height) * 0.38);
      coreAura.addColorStop(0.0, `rgba(${rgbAcc}, 0.22)`);
      coreAura.addColorStop(0.45, `rgba(${rgbAmb}, 0.09)`);
      coreAura.addColorStop(1.0, `rgba(${rgbAmb}, 0)`);
      ctx.fillStyle = coreAura;
      ctx.fillRect(0, 0, width, height);

      // Background Knowledge Graph
      const bgProj = bgNodes.map(n => project3D(n.x, n.y, n.z, 0.28));
      ctx.lineWidth = 0.7;
      for (let i = 0; i < bgEdges.length; i++) {
        const [aIdx, bIdx] = bgEdges[i];
        const pa = bgProj[aIdx], pb = bgProj[bIdx];
        const dof = Math.max(0.04, Math.min(0.26, (240 - Math.abs((pa.z + pb.z) * 0.5)) / 950));
        ctx.strokeStyle = `rgba(175, 195, 215, ${dof.toFixed(3)})`;
        ctx.beginPath(); ctx.moveTo(pa.px, pa.py); ctx.lineTo(pb.px, pb.py); ctx.stroke();
      }
      for (let i = 0; i < bgNodes.length; i++) {
        const p = bgProj[i], n = bgNodes[i];
        const dof = Math.max(0.08, Math.min(0.48, (260 - Math.abs(p.z)) / 620));
        const r = n.rSize * p.scale;
        ctx.fillStyle = (i % 7 === 0) ? `rgba(${rgbAcc}, ${(dof * 0.75).toFixed(3)})` : `rgba(200, 215, 230, ${dof.toFixed(3)})`;
        ctx.beginPath(); ctx.arc(p.px, p.py, Math.max(0.8, r * 0.85), 0, Math.PI * 2); ctx.fill();
      }

      ctx.font = '500 8.5px "SF Mono", "JetBrains Mono", Consolas, monospace';
      mathOverlays.forEach(mo => {
        const mp = project3D(mo.x, mo.y, mo.z, 0.22);
        ctx.fillStyle = 'rgba(165, 185, 205, 0.28)';
        mo.lines.forEach((ln, idx) => ctx.fillText(ln, mp.px, mp.py + idx * 10));
      });

      // Cortical Shell Cutout
      if (shellReady && mode !== 'synapse') {
        ctx.save();
        const breath = 1.0 + Math.sin(tick * 1.4) * 0.012;
        const perspX = Math.cos(rotY * 0.65) * breath;
        const skewY = Math.sin(rotY * 0.5) * 0.06;
        const shellW = Math.min(width, height) * 0.66;
        const shellH = shellW * (696 / 816);
        ctx.translate(cx + Math.sin(rotY) * 10, cy + 2);
        ctx.transform(perspX, skewY, -skewY * 0.5, breath, 0, 0);
        ctx.globalAlpha = 0.92;
        ctx.drawImage(shellImg, -shellW * 0.5, -shellH * 0.5, shellW, shellH);
        ctx.restore();
      }

      // 3D Sparkling Particles & Synaptic Web
      ctx.globalCompositeOperation = 'lighter';
      const pProj = new Array(particles.length);
      const pLum = new Float32Array(particles.length);
      const cyRot = Math.cos(rotY), syRot = Math.sin(rotY);

      for (let i = 0; i < particles.length; i++) {
        const pt = particles[i];
        const pr = project3D(pt.x, pt.y, pt.z, 1.0);
        pProj[i] = pr;
        const nz = -pt.nx * syRot + pt.nz * cyRot;
        const rim = 0.25 + 0.75 * Math.pow(1.0 - Math.min(1.0, Math.abs(nz)), 1.35);
        const frontBoost = pr.z < 15 ? 1.0 : 0.32;
        const pulse = 0.75 + 0.25 * Math.sin(tick * 2.6 + i * 0.13);
        pLum[i] = pt.bright * rim * frontBoost * pulse;
      }

      const BUCKETS = 5;
      const bPaths = Array.from({ length: BUCKETS }, () => []);
      for (let e = 0; e < webEdges.length; e++) {
        const [i, j] = webEdges[e];
        const bi = Math.min(BUCKETS - 1, Math.floor(((pLum[i] + pLum[j]) * 0.5) * BUCKETS));
        bPaths[bi].push(e);
      }
      ctx.lineWidth = mode === 'synapse' ? 0.95 : 0.55;
      for (let b = 0; b < BUCKETS; b++) {
        if (!bPaths[b].length) continue;
        const alpha = (0.03 + (b / BUCKETS) * (mode === 'synapse' ? 0.45 : 0.18)).toFixed(3);
        ctx.strokeStyle = b >= BUCKETS - 2 ? `rgba(${rgbAcc}, ${alpha})` : `rgba(${rgbAmb}, ${alpha})`;
        ctx.beginPath();
        for (const e of bPaths[b]) {
          const p1 = pProj[webEdges[e][0]], p2 = pProj[webEdges[e][1]];
          ctx.moveTo(p1.px, p1.py); ctx.lineTo(p2.px, p2.py);
        }
        ctx.stroke();
      }

      const order = pProj.map((_, i) => i).sort((a, b) => pProj[b].z - pProj[a].z);
      for (let k = 0; k < order.length; k++) {
        const i = order[k];
        const pt = particles[i], pr = pProj[i], l = pLum[i];
        if (l < 0.08) continue;
        const r = pt.size * pr.scale;
        if (pt.kind === 'limbic' || l > 0.64) {
          ctx.globalAlpha = Math.min(0.65, l * 0.48);
          const gr = r * 2.6;
          ctx.drawImage(glowDot, pr.px - gr, pr.py - gr, gr * 2, gr * 2);
        }
        ctx.globalAlpha = Math.min(0.95, 0.20 + l * 0.85);
        ctx.fillStyle = (l > 0.65 || pt.kind === 'limbic') ? '#fff6d6' : (l > 0.35 ? `rgb(${rgbAcc})` : `rgb(${rgbAmb})`);
        ctx.beginPath(); ctx.arc(pr.px, pr.py, Math.max(0.55, r * 0.65), 0, Math.PI * 2); ctx.fill();
      }
      ctx.globalAlpha = 1.0;

      // Curved Bezier Splines & Streaming Packets
      allSplines.forEach((sp) => {
        const SEGS = 34;
        const pts2D = [];
        for (let s = 0; s <= SEGS; s++) {
          const t = s / SEGS;
          const pos3 = evalBezier3D(sp.p0, sp.p1, sp.p2, sp.p3, t);
          pts2D.push(project3D(pos3[0], pos3[1], pos3[2], 0.22 + 0.78 * (t * t)));
        }
        ctx.strokeStyle = `rgba(${rgbAmb}, 0.30)`;
        ctx.lineWidth = 3.0;
        ctx.beginPath();
        pts2D.forEach((p, idx) => idx === 0 ? ctx.moveTo(p.px, p.py) : ctx.lineTo(p.px, p.py));
        ctx.stroke();

        ctx.strokeStyle = `rgba(${rgbAcc}, 0.85)`;
        ctx.lineWidth = 1.25;
        ctx.beginPath();
        pts2D.forEach((p, idx) => idx === 0 ? ctx.moveTo(p.px, p.py) : ctx.lineTo(p.px, p.py));
        ctx.stroke();

        const dstP = pts2D[SEGS];
        ctx.drawImage(glowDot, dstP.px - 9, dstP.py - 9, 18, 18);

        sp.packets.forEach(pk => {
          const tHead = (tick * pk.speed + pk.offset) % 1.0;
          const tailLen = 0.11;
          for (let ts = 0; ts < 7; ts++) {
            const tA = Math.max(0, tHead - (ts / 7) * tailLen);
            const tB = Math.max(0, tHead - ((ts + 1) / 7) * tailLen);
            if (tA <= 0) continue;
            const posA = evalBezier3D(sp.p0, sp.p1, sp.p2, sp.p3, tA);
            const posB = evalBezier3D(sp.p0, sp.p1, sp.p2, sp.p3, tB);
            const pA = project3D(posA[0], posA[1], posA[2], 0.22 + 0.78 * tA * tA);
            const pB = project3D(posB[0], posB[1], posB[2], 0.22 + 0.78 * tB * tB);
            const frac = 1 - ts / 7;
            ctx.strokeStyle = `rgba(255, 248, 210, ${(frac * 0.88).toFixed(2)})`;
            ctx.lineWidth = (0.8 + frac * 2.2) * pk.size;
            ctx.beginPath(); ctx.moveTo(pA.px, pA.py); ctx.lineTo(pB.px, pB.py); ctx.stroke();
          }
          const posH = evalBezier3D(sp.p0, sp.p1, sp.p2, sp.p3, tHead);
          const pH = project3D(posH[0], posH[1], posH[2], 0.22 + 0.78 * tHead * tHead);
          const pr = 5.2 * pk.size * pH.scale;
          ctx.drawImage(packetDot, pH.px - pr, pH.py - pr, pr * 2, pr * 2);

          if (tHead > 0.90) {
            const flash = (1.0 - (1.0 - tHead) / 0.10) * 11;
            ctx.drawImage(packetDot, dstP.px - flash, dstP.py - flash, flash * 2, flash * 2);
          }
        });
      });

      // Holographic Target Reticles & Frameless Labels
      ctx.globalCompositeOperation = 'source-over';
      companyNodes.forEach((cn, idx) => {
        const np = project3D(cn.x, cn.y, cn.z, 0.22);
        const dofAlpha = Math.max(0.55, Math.min(1.0, (280 - Math.abs(np.z)) / 300));
        const r1 = 7 * np.scale, r2 = 14 * np.scale, r3 = 21 * np.scale;
        ctx.strokeStyle = `rgba(200, 218, 235, ${(0.28 * dofAlpha).toFixed(2)})`;
        ctx.lineWidth = 0.85;
        ctx.beginPath(); ctx.arc(np.px, np.py, r1, 0, Math.PI * 2); ctx.stroke();

        ctx.strokeStyle = `rgba(${rgbCyn}, ${(0.22 * dofAlpha).toFixed(2)})`;
        ctx.beginPath(); ctx.arc(np.px, np.py, r2, 0, Math.PI * 2); ctx.stroke();

        const rotArc = tick * 0.45 * (idx % 2 === 0 ? 1 : -1) + idx;
        ctx.strokeStyle = `rgba(${rgbAcc}, ${(0.42 * dofAlpha).toFixed(2)})`;
        ctx.lineWidth = 1.1;
        ctx.beginPath(); ctx.arc(np.px, np.py, r3, rotArc, rotArc + Math.PI * 0.65); ctx.stroke();

        ctx.globalCompositeOperation = 'lighter';
        ctx.drawImage(packetDot, np.px - 8, np.py - 8, 16, 16);
        ctx.globalCompositeOperation = 'source-over';

        ctx.font = '700 11.5px "SF Pro Display", "Inter", -apple-system, sans-serif';
        const wTitle = ctx.measureText(cn.title).width;
        ctx.font = '500 11px "SF Pro Text", "Inter", -apple-system, sans-serif';
        const wMetric = ctx.measureText(' - ' + cn.metric).width;
        const totalW = wTitle + wMetric;

        const lx = Math.max(12, Math.min(width - totalW - 10, np.px + 12));
        const ly = Math.max(44, Math.min(height - 52, np.py + cn.labelDy));

        ctx.strokeStyle = `rgba(210, 225, 240, ${(0.38 * dofAlpha).toFixed(2)})`;
        ctx.lineWidth = 0.85;
        ctx.beginPath();
        ctx.moveTo(np.px, np.py);
        ctx.lineTo(lx - 4, ly + 4);
        ctx.lineTo(lx + totalW + 4, ly + 4);
        ctx.stroke();

        ctx.shadowColor = 'rgba(0, 0, 0, 0.95)';
        ctx.shadowBlur = 8;
        ctx.font = '700 11.5px "SF Pro Display", "Inter", -apple-system, sans-serif';
        ctx.fillStyle = `rgba(255, 255, 255, ${dofAlpha.toFixed(2)})`;
        ctx.fillText(cn.title, lx, ly);

        ctx.font = '500 11px "SF Pro Text", "Inter", -apple-system, sans-serif';
        ctx.fillStyle = `rgba(205, 215, 228, ${(dofAlpha * 0.88).toFixed(2)})`;
        ctx.fillText(' - ' + cn.metric, lx + wTitle, ly);
        ctx.shadowBlur = 0;
      });

      requestAnimationFrame(render);
    }
    requestAnimationFrame(render);
  }

  window.initBrainNetwork = initBrainNetwork;
})();
