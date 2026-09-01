'use strict';

/*
 * Lightweight in-browser preview of earth-trip-visualizer's globe animation.
 * Ports the projection math documented in the desktop app's CLAUDE.md
 * (core/renderer.py, core/animator.py, utils/geo.py) to JS/Canvas.
 * Watch-only: no video is produced, so there's no ffmpeg/MediaRecorder step
 * and no CORS risk from reading pixels back out of the canvas.
 */

// Internal render resolution (raster projection math runs here). Matches
// the display canvas 1:1 (see index.html) so there's no extra upscale blur
// on top of the globe texture itself.
const RW = 450, RH = 800;
const CX = RW / 2, CY = RH / 2;

const GLOBE_R_NORMAL = 217;  // overview zoom (scaled from desktop's GLOBE_R=520 @ W=1080)
// Desktop switches from Blue Marble to live satellite tiles above globe_r ≈
// 2x GLOBE_R_NORMAL (_TILE_MIN_R in renderer.py); this demo has no tile
// fetch, so its "city" zoom stays inside the range Blue Marble alone still
// renders smoothly, rather than the extreme close-up the real tiles give.
const GLOBE_R_CITY = 380;
const GLOBE_R_TRANSIT = 174; // wide view during the mid-transition zoom-out

const BG_RGB = [15, 15, 26];       // --bg
const ACCENT_RGB = [108, 99, 255]; // --accent

const PHASES = {
  INTRO: 1.2,
  PAUSE_A: 2.0,
  TRANSITION: 4.5,
  PAUSE_B: 2.2,
};

const TRANSPORT_EMOJI = {
  plane: '✈️', train: '🚂', bus: '🚌', car: '🚗', ship: '⛴️',
};

// ── Geometry helpers ────────────────────────────────────────────────────

function toRad(d) { return (d * Math.PI) / 180; }

function cameraBasis(clonRad, clatRad) {
  const sLon = Math.sin(clonRad), cLon = Math.cos(clonRad);
  const sLat = Math.sin(clatRad), cLat = Math.cos(clatRad);
  return {
    ex: [-sLon, cLon, 0],
    ey: [-sLat * cLon, -sLat * sLon, cLat],
    ez: [cLat * cLon, cLat * sLon, sLat],
  };
}

function geoToVec3(latRad, lonRad) {
  return [
    Math.cos(latRad) * Math.cos(lonRad),
    Math.cos(latRad) * Math.sin(lonRad),
    Math.sin(latRad),
  ];
}

function dot3(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }

// geo (deg) -> internal pixel space; visible=false means far hemisphere
function geoToPixel(latDeg, lonDeg, basis, globeR) {
  const p = geoToVec3(toRad(latDeg), toRad(lonDeg));
  const depth = dot3(p, basis.ez);
  return {
    x: CX + dot3(p, basis.ex) * globeR,
    y: CY - dot3(p, basis.ey) * globeR,
    visible: depth >= 0,
  };
}

// Spherical linear interpolation between two (lat, lon) points in degrees.
function slerpPath(latA, lonA, latB, lonB, n) {
  const p0 = geoToVec3(toRad(latA), toRad(lonA));
  const p1 = geoToVec3(toRad(latB), toRad(lonB));
  const cosOmega = Math.max(-1, Math.min(1, dot3(p0, p1)));
  const omega = Math.acos(cosOmega);
  const pts = [];
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1);
    let v;
    if (omega < 1e-6) {
      v = p0;
    } else {
      const a = Math.sin((1 - t) * omega) / Math.sin(omega);
      const b = Math.sin(t * omega) / Math.sin(omega);
      v = [a * p0[0] + b * p1[0], a * p0[1] + b * p1[1], a * p0[2] + b * p1[2]];
    }
    const lat = (Math.asin(Math.max(-1, Math.min(1, v[2]))) * 180) / Math.PI;
    const lon = (Math.atan2(v[1], v[0]) * 180) / Math.PI;
    pts.push([lat, lon]);
  }
  return pts;
}

function lerp(a, b, t) { return a + (b - a) * t; }
function easeInOutCubic(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
function countryCodeToFlagEmoji(cc) {
  if (!cc || cc.length !== 2) return '🏳️';
  const A = 0x1f1e6;
  return String.fromCodePoint(A + cc.toUpperCase().charCodeAt(0) - 65)
       + String.fromCodePoint(A + cc.toUpperCase().charCodeAt(1) - 65);
}

// ── Texture ──────────────────────────────────────────────────────────────

let texData = null, texW = 0, texH = 0;

function loadTexture() {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      // Downsample once onto an offscreen canvas — enough detail for the
      // zoom range this demo uses, much cheaper to sample than the 5400x2700
      // source every frame.
      texW = 2400; texH = 1200;
      const off = document.createElement('canvas');
      off.width = texW; off.height = texH;
      const octx = off.getContext('2d');
      octx.drawImage(img, 0, 0, texW, texH);
      texData = octx.getImageData(0, 0, texW, texH).data;
      resolve();
    };
    img.onerror = () => reject(new Error('Failed to load earth texture'));
    img.src = 'assets/earth_texture.jpg';
  });
}

// ── Globe raster (internal resolution) ──────────────────────────────────

const internalCanvas = document.createElement('canvas');
internalCanvas.width = RW; internalCanvas.height = RH;
const internalCtx = internalCanvas.getContext('2d');
const frameImageData = internalCtx.createImageData(RW, RH);

function renderGlobeRaster(clonRad, clatRad, globeR, fade) {
  const basis = cameraBasis(clonRad, clatRad);
  const data = frameImageData.data;
  let idx = 0;
  for (let y = 0; y < RH; y++) {
    const sy = (CY - y) / globeR;
    for (let x = 0; x < RW; x++, idx += 4) {
      const sx = (x - CX) / globeR;
      const d2 = sx * sx + sy * sy;
      if (d2 > 1) {
        data[idx] = BG_RGB[0]; data[idx + 1] = BG_RGB[1]; data[idx + 2] = BG_RGB[2]; data[idx + 3] = 255;
        continue;
      }
      const sz = Math.sqrt(1 - d2);
      const x3 = sx * basis.ex[0] + sy * basis.ey[0] + sz * basis.ez[0];
      const y3 = sx * basis.ex[1] + sy * basis.ey[1] + sz * basis.ez[1];
      const z3 = sx * basis.ex[2] + sy * basis.ey[2] + sz * basis.ez[2];
      const lat = Math.asin(Math.max(-1, Math.min(1, z3)));
      const lon = Math.atan2(y3, x3);
      let sxi = Math.floor(((lon + Math.PI) / (2 * Math.PI)) * texW) % texW;
      if (sxi < 0) sxi += texW;
      let syi = Math.floor(((Math.PI / 2 - lat) / Math.PI) * texH);
      syi = Math.max(0, Math.min(texH - 1, syi));
      const srcIdx = (syi * texW + sxi) * 4;

      // Soft rim glow near the limb, cheap stand-in for the atmosphere glow.
      const rim = d2 > 0.82 ? (d2 - 0.82) / 0.18 : 0;
      let r = texData[srcIdx], g = texData[srcIdx + 1], b = texData[srcIdx + 2];
      r = r + (ACCENT_RGB[0] - r) * rim * 0.35;
      g = g + (ACCENT_RGB[1] - g) * rim * 0.35;
      b = b + (ACCENT_RGB[2] - b) * rim * 0.35;

      data[idx] = r * fade + BG_RGB[0] * (1 - fade);
      data[idx + 1] = g * fade + BG_RGB[1] * (1 - fade);
      data[idx + 2] = b * fade + BG_RGB[2] * (1 - fade);
      data[idx + 3] = 255;
    }
  }
  internalCtx.putImageData(frameImageData, 0, 0);
}

// ── Overlay drawing (display resolution) ────────────────────────────────

const displayCanvas = document.getElementById('globe');
const ctx = displayCanvas.getContext('2d');
const SCALE = displayCanvas.width / RW;

function drawPin(x, y, label, flag) {
  ctx.save();
  const grad = ctx.createRadialGradient(x, y, 0, x, y, 20);
  grad.addColorStop(0, 'rgba(108,99,255,0.95)');
  grad.addColorStop(1, 'rgba(108,99,255,0)');
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(x, y, 20, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = '#ffffff';
  ctx.beginPath();
  ctx.arc(x, y, 6, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = '#6c63ff';
  ctx.beginPath();
  ctx.arc(x, y, 4, 0, Math.PI * 2);
  ctx.fill();

  // Flag emoji glyphs carry a lot of built-in side padding that
  // measureText() doesn't report, so measuring "flag + label" as one
  // string and centering on that width leaves the pill lopsided (empty
  // gap before the flag). Instead: measure only the label, reserve a
  // fixed icon slot for the flag, and lay both out left-aligned.
  const labelFont = "700 15px 'Segoe UI', system-ui, sans-serif";
  ctx.font = labelFont;
  const labelWidth = ctx.measureText(label).width;
  const flagSlot = 20, gap = 6, padX = 14, pillH = 28;
  const w = flagSlot + gap + labelWidth + padX * 2;
  const left = x - w / 2;
  const midY = y + 16 + pillH / 2;

  ctx.fillStyle = 'rgba(15,15,26,0.9)';
  ctx.strokeStyle = 'rgba(108,99,255,0.5)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(left, y + 16, w, pillH, pillH / 2);
  ctx.fill();
  ctx.stroke();

  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.font = '16px serif';
  ctx.fillText(flag, left + padX, midY);
  ctx.font = labelFont;
  ctx.fillStyle = '#e2e8f0';
  ctx.fillText(label, left + padX + flagSlot + gap, midY);
  ctx.restore();
}

function drawArc(points, progress, basis, globeR) {
  const upTo = Math.max(1, Math.floor(points.length * progress));
  const path = new Path2D();
  let started = false;
  for (let i = 0; i < upTo; i++) {
    const p = geoToPixel(points[i][0], points[i][1], basis, globeR);
    if (!p.visible) { started = false; continue; }
    const x = p.x * SCALE, y = p.y * SCALE;
    if (!started) { path.moveTo(x, y); started = true; } else { path.lineTo(x, y); }
  }
  ctx.save();
  // Soft outer glow pass, then a crisp bright core — makes the arc read
  // clearly against both ocean and land in the underlying texture.
  ctx.strokeStyle = 'rgba(139,133,255,0.35)';
  ctx.lineWidth = 7;
  ctx.setLineDash([]);
  ctx.stroke(path);
  ctx.strokeStyle = '#c7c2ff';
  ctx.lineWidth = 3;
  ctx.setLineDash([6, 6]);
  ctx.stroke(path);
  ctx.restore();
}

function drawTransportIcon(x, y, key) {
  ctx.save();
  ctx.fillStyle = 'rgba(0,0,0,0.4)';
  ctx.beginPath();
  ctx.ellipse(x, y + 8, 18, 8, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.font = '32px serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(TRANSPORT_EMOJI[key] || '✈️', x, y);
  ctx.restore();
}

// ── Animation state machine ─────────────────────────────────────────────

let anim = null; // current animation session token, invalidated on re-click

async function watchPreview() {
  const btn = document.getElementById('watchBtn');
  const status = document.getElementById('status');
  const cityAName = document.getElementById('cityA').value.trim();
  const cityBName = document.getElementById('cityB').value.trim();
  const transportKey = document.getElementById('transport').value;

  if (!cityAName || !cityBName) {
    status.textContent = 'Enter both cities.';
    status.className = 'error';
    return;
  }

  const token = Symbol('anim');
  anim = token;
  btn.disabled = true;
  status.className = '';
  status.textContent = 'Geocoding cities…';

  let cityA, cityB;
  try {
    [cityA, cityB] = await Promise.all([geocode(cityAName), geocode(cityBName)]);
  } catch (err) {
    status.textContent = err.message;
    status.className = 'error';
    btn.disabled = false;
    return;
  }
  if (anim !== token) return;

  status.textContent = `${cityA.flag} ${cityA.label}  →  ${cityB.flag} ${cityB.label}`;
  btn.disabled = false;

  const arcPoints = slerpPath(cityA.lat, cityA.lon, cityB.lat, cityB.lon, 120);
  runLoop(token, cityA, cityB, arcPoints, transportKey);
}

async function geocode(query) {
  const url = `https://nominatim.openstreetmap.org/search?format=jsonv2&addressdetails=1&limit=1&q=${encodeURIComponent(query)}`;
  const res = await fetch(url, { headers: { 'Accept-Language': 'en' } });
  if (!res.ok) throw new Error(`Geocoding failed for "${query}"`);
  const data = await res.json();
  if (!data.length) throw new Error(`Couldn't find "${query}"`);
  const hit = data[0];
  const addr = hit.address || {};
  const cc = addr.country_code;
  // Prefer a real place name from the address breakdown; Nominatim doesn't
  // always tag one as city/town/village (e.g. Tokyo resolves at prefecture
  // level). Only fall back to the raw query when none exist at all — and in
  // that case use it as-is, since it may already read "City, Country" and
  // appending the country again would duplicate it.
  const cityName = addr.city || addr.town || addr.village || addr.municipality
    || addr.city_district || addr.county || addr.state;
  const label = cityName
    ? (addr.country ? `${cityName}, ${addr.country}` : cityName)
    : query;
  return {
    lat: parseFloat(hit.lat),
    lon: parseFloat(hit.lon),
    label,
    flag: countryCodeToFlagEmoji(cc),
  };
}

function runLoop(token, cityA, cityB, arcPoints, transportKey) {
  const total = PHASES.INTRO + PHASES.PAUSE_A + PHASES.TRANSITION + PHASES.PAUSE_B;
  const start = performance.now();

  function frame(now) {
    if (anim !== token) return; // superseded by a new click

    const elapsed = ((now - start) / 1000) % total;
    let clat, clon, globeR, fade = 1, arcProgress = 0, showTip = false, tip = null;

    if (elapsed < PHASES.INTRO) {
      const t = easeInOutCubic(elapsed / PHASES.INTRO);
      clat = cityA.lat; clon = cityA.lon;
      globeR = lerp(GLOBE_R_NORMAL, GLOBE_R_CITY, t);
      fade = Math.min(1, elapsed / (PHASES.INTRO * 0.4));
    } else if (elapsed < PHASES.INTRO + PHASES.PAUSE_A) {
      clat = cityA.lat; clon = cityA.lon; globeR = GLOBE_R_CITY;
    } else if (elapsed < PHASES.INTRO + PHASES.PAUSE_A + PHASES.TRANSITION) {
      const t = (elapsed - PHASES.INTRO - PHASES.PAUSE_A) / PHASES.TRANSITION;
      const tipIdx = Math.min(arcPoints.length - 1, Math.floor(t * arcPoints.length));
      [clat, clon] = arcPoints[tipIdx];
      globeR = GLOBE_R_CITY - (GLOBE_R_CITY - GLOBE_R_TRANSIT) * Math.sin(t * Math.PI);
      arcProgress = t;
      showTip = true;
    } else {
      clat = cityB.lat; clon = cityB.lon; globeR = GLOBE_R_CITY; arcProgress = 1;
    }

    const clonRad = toRad(clon), clatRad = toRad(clat);
    renderGlobeRaster(clonRad, clatRad, globeR, fade);

    ctx.imageSmoothingEnabled = true;
    ctx.clearRect(0, 0, displayCanvas.width, displayCanvas.height);
    ctx.drawImage(internalCanvas, 0, 0, displayCanvas.width, displayCanvas.height);

    const basis = cameraBasis(clonRad, clatRad);
    if (elapsed < PHASES.INTRO + PHASES.PAUSE_A) {
      const p = geoToPixel(cityA.lat, cityA.lon, basis, globeR);
      if (p.visible) drawPin(p.x * SCALE, p.y * SCALE, cityA.label, cityA.flag);
    } else if (elapsed < PHASES.INTRO + PHASES.PAUSE_A + PHASES.TRANSITION) {
      drawArc(arcPoints, arcProgress, basis, globeR);
      if (showTip) {
        const t = (elapsed - PHASES.INTRO - PHASES.PAUSE_A) / PHASES.TRANSITION;
        const tipIdx = Math.min(arcPoints.length - 1, Math.floor(t * arcPoints.length));
        const tp = geoToPixel(arcPoints[tipIdx][0], arcPoints[tipIdx][1], basis, globeR);
        if (tp.visible) drawTransportIcon(tp.x * SCALE, tp.y * SCALE, transportKey);
      }
    } else {
      drawArc(arcPoints, 1, basis, globeR);
      const p = geoToPixel(cityB.lat, cityB.lon, basis, globeR);
      if (p.visible) drawPin(p.x * SCALE, p.y * SCALE, cityB.label, cityB.flag);
    }

    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

// ── Wire up ──────────────────────────────────────────────────────────────

document.getElementById('watchBtn').addEventListener('click', watchPreview);

// "＋ Add Stop" mirrors the desktop app's own button (city_panel.py) to show
// multi-stop routes exist, without building multi-leg support here — it
// only swaps the status line to a note and restores it, never touches
// geocoding or the animation loop.
let addStopNoteTimer = null;
document.getElementById('addStopBtn').addEventListener('click', () => {
  const status = document.getElementById('status');
  const prevText = status.textContent;
  const prevClass = status.className;
  clearTimeout(addStopNoteTimer);
  status.textContent = '🖥️  Multi-stop routes are supported in the desktop app — this preview covers one leg.';
  status.className = '';
  addStopNoteTimer = setTimeout(() => {
    status.textContent = prevText;
    status.className = prevClass;
  }, 2500);
});

loadTexture()
  .then(() => { watchPreview(); })
  .catch((err) => {
    document.getElementById('status').textContent = err.message;
    document.getElementById('status').className = 'error';
  });
