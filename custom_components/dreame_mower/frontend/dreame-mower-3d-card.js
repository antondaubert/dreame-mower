/*
 * Dreame Mower 3D map card.
 *
 * Shows the LiDAR point cloud the mower recorded for a map. The card asks the
 * integration for the mower's maps (WebSocket `dreame_mower/point_clouds`),
 * fetches the clouds from its authenticated endpoint, and follows the active
 * map (the mower's `current_map_id`) unless another map is picked.
 *
 *   type: custom:dreame-mower-3d-card
 *   entity: lawn_mower.my_mower
 *   height: 450px        # optional, when the dashboard does not size the card
 *   point_size: 0.25     # optional, in metres
 *   invert_pitch: false  # optional, default of the "Invert ↑↓" box
 *
 * The integration serves this file and adds it to the dashboard resources;
 * three.js is only loaded once a card is shown.
 */

const THREE_URL = new URL("./three-0.160.0.module.min.js", import.meta.url).href;
let threePromise = null;
const loadThree = () => (threePromise ??= import(THREE_URL));

// Parsed point clouds by endpoint, kept while the page lives so switching views
// or maps does not parse them again. The ETag tells whether the file changed.
const parsedClouds = new Map();

const HELP = [
  ["Drag", "orbit around the point under the cursor"],
  ["Ctrl / Shift / right drag", "move"],
  ["Wheel / pinch", "zoom to the cursor"],
  ["W S", "forward, back"],
  ["↑ ↓", "pitch"],
  ["← →", "yaw"],
  ["Q E", "roll"],
  ["A D", "strafe"],
  ["R F", "up, down"],
  ["H", "level the horizon"],
  ["Shift", "faster"],
  ["", "Keys by position: W A S D is Z Q S D on AZERTY"],
];
const STORAGE_INVERT = "dreame-mower-3d-card.invert-pitch";

/** Parse an ASCII or binary PCD file into positions and optional 8-bit colours. */
function parsePcd(buffer) {
  const head = new TextDecoder("latin1").decode(new Uint8Array(buffer, 0, Math.min(buffer.byteLength, 4096)));
  const dataLine = /^DATA (\w+)\r?\n/m.exec(head);
  if (!dataLine) throw new Error("not a PCD file");
  const fields = {};
  for (const line of head.slice(0, dataLine.index).split(/\r?\n/)) {
    const [key, ...values] = line.trim().split(/\s+/);
    if (key && !key.startsWith("#")) fields[key] = values;
  }
  const names = fields.FIELDS || [];
  const sizes = (fields.SIZE || []).map(Number);
  const types = fields.TYPE || [];
  const counts = (fields.COUNT || names.map(() => "1")).map(Number);
  const total = Number((fields.POINTS || fields.WIDTH || [0])[0]);
  const [ix, iy, iz, ic] = ["x", "y", "z", "rgb"].map((n) => names.indexOf(n));
  if (ix < 0 || iy < 0 || iz < 0) throw new Error("the file has no x y z fields");

  const positions = new Float32Array(total * 3);
  const colors = ic >= 0 ? new Uint8Array(total * 3) : null;
  let n = 0;
  const put = (x, y, z, rgb) => {
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return;
    positions.set([x, y, z], n * 3);
    if (colors) colors.set([(rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255], n * 3);
    n++;
  };

  const mode = dataLine[1];
  const start = dataLine.index + dataLine[0].length;
  if (mode === "binary") {
    const offsets = [];
    let stride = 0;
    names.forEach((_, i) => { offsets.push(stride); stride += sizes[i] * counts[i]; });
    if (start + stride * total > buffer.byteLength) throw new Error("the file is truncated");
    const view = new DataView(buffer, start);
    const read = (row, i) => (types[i] === "F" && sizes[i] === 8 ? view.getFloat64(row + offsets[i], true) : view.getFloat32(row + offsets[i], true));
    for (let p = 0; p < total; p++) {
      const row = p * stride;
      put(read(row, ix), read(row, iy), read(row, iz), ic >= 0 ? view.getUint32(row + offsets[ic], true) : 0);
    }
  } else if (mode === "ascii") {
    const asUint = new Uint32Array(1), asFloat = new Float32Array(asUint.buffer);
    const lines = new TextDecoder("latin1").decode(new Uint8Array(buffer, start)).split(/\r?\n/);
    for (const line of lines.slice(0, total)) {
      const v = line.trim().split(/\s+/);
      let rgb = 0;
      if (ic >= 0) {
        if (types[ic] === "F") { asFloat[0] = Number(v[ic]); rgb = asUint[0]; } else rgb = Number(v[ic]);
      }
      put(Number(v[ix]), Number(v[iy]), Number(v[iz]), rgb);
    }
  } else {
    throw new Error(`PCD "${mode}" data is not supported`);
  }
  return { positions: positions.subarray(0, n * 3), colors: colors && colors.subarray(0, n * 3), count: n };
}

/** Centre, ground height and extent from percentiles, so a few stray points do not skew them. */
function bounds(positions, count) {
  const step = Math.max(1, Math.floor(count / 20000)), xs = [], ys = [], zs = [];
  for (let i = 0; i < count; i += step) { xs.push(positions[i * 3]); ys.push(positions[i * 3 + 1]); zs.push(positions[i * 3 + 2]); }
  const q = (a, p) => a.sort((u, v) => u - v)[Math.floor(p * (a.length - 1))];
  const x0 = q(xs, 0.02), x1 = q(xs, 0.98), y0 = q(ys, 0.02), y1 = q(ys, 0.98);
  return { cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, ground: q(zs, 0.1), size: Math.max(x1 - x0, y1 - y0, 1) };
}

/** The 3D scene and its free camera: orbit around the picked point, grab-to-move, zoom to the cursor, flight keys. */
class Viewer {
  constructor(THREE, container, options) {
    this.T = THREE;
    this.options = options;
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.outputColorSpace = THREE.LinearSRGBColorSpace;  // the file's colours as they are
    this.canvas = this.renderer.domElement;
    this.canvas.tabIndex = 0;
    container.appendChild(this.canvas);
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x111111);
    this.camera = new THREE.PerspectiveCamera(50, 1, 0.3, 3000);
    this.camera.up.set(0, 0, 1);  // the point clouds have z up
    this.Z = new THREE.Vector3(0, 0, 1);
    this.X = new THREE.Vector3(1, 0, 0);
    this.Y = new THREE.Vector3(0, 1, 0);
    this.raycaster = new THREE.Raycaster();
    this.points = null;
    this.home = null;
    this.keys = new Set();
    this.pointers = new Map();
    this.gesture = null;
    this.dirty = true;
    this.clock = new THREE.Clock();
    this.listen();
    this.resizer = new ResizeObserver(() => this.resize());
    this.resizer.observe(container);
    this.renderer.setAnimationLoop(() => this.frame());
  }

  dispose() {
    this.renderer.setAnimationLoop(null);
    this.resizer.disconnect();
    if (this.points) this.points.geometry.dispose();
    this.renderer.dispose();
    this.renderer.forceContextLoss();
    this.canvas.remove();
  }

  resize() {
    const { clientWidth: w, clientHeight: h } = this.canvas.parentElement;
    if (!w || !h) return;
    this.renderer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.dirty = true;
  }

  show(cloud) {
    const T = this.T;
    if (this.points) { this.scene.remove(this.points); this.points.geometry.dispose(); }
    const geometry = new T.BufferGeometry();
    geometry.setAttribute("position", new T.BufferAttribute(cloud.positions, 3));
    if (cloud.colors) geometry.setAttribute("color", new T.BufferAttribute(cloud.colors, 3, true));
    const material = new T.PointsMaterial({ size: this.options.pointSize, sizeAttenuation: true, vertexColors: !!cloud.colors, color: cloud.colors ? 0xffffff : 0x66bb6a });
    this.points = new T.Points(geometry, material);
    this.scene.add(this.points);
    this.home = bounds(cloud.positions, cloud.count);
    this.recentre();
  }

  scalePoints(factor) {
    if (!this.points) return;
    this.points.material.size *= factor;
    this.dirty = true;
  }

  recentre() {
    if (!this.home) return;
    const { cx, cy, ground, size } = this.home;
    this.camera.position.set(cx, cy - size * 0.75, ground + size * 0.55);
    this.camera.lookAt(cx, cy, ground);
    this.dirty = true;
  }

  dir() { return this.camera.getWorldDirection(new this.T.Vector3()); }
  local(axis) { return axis.clone().applyQuaternion(this.camera.quaternion); }

  levelHorizon() {  // keeps the heading and the slope, drops the roll
    const d = this.dir();
    if (Math.abs(d.z) < 0.999) this.camera.lookAt(this.camera.position.clone().add(d));
    this.dirty = true;
  }

  ray(x, y) {
    const r = this.canvas.getBoundingClientRect();
    this.raycaster.setFromCamera(new this.T.Vector2(((x - r.left) / r.width) * 2 - 1, -((y - r.top) / r.height) * 2 + 1), this.camera);
    return this.raycaster.ray;
  }

  onPlane(x, y, z) {
    const hit = this.ray(x, y).intersectPlane(new this.T.Plane(this.Z, -z), new this.T.Vector3());
    return hit && hit.distanceTo(this.camera.position) < 5000 ? hit : null;
  }

  /** The point of the cloud under the cursor, else the ground under it. */
  pick(x, y) {
    this.ray(x, y);
    if (this.points) {
      this.raycaster.params.Points.threshold = Math.max(0.2, this.camera.position.z - this.home.ground) * 0.01;
      const hit = this.raycaster.intersectObject(this.points)[0];
      if (hit) return hit.point;
    }
    return this.onPlane(x, y, this.home.ground) ?? this.raycaster.ray.at(this.home.size * 0.5, new this.T.Vector3());
  }

  orbit(pivot, dx, dy) {
    // One rotation for both the position (around the pivot) and the orientation,
    // so the pivot stays where it is on screen. Only refuses to pass the vertical.
    const T = this.T;
    const qYaw = new T.Quaternion().setFromAxisAngle(this.Z, -dx * 0.005);
    const right = this.local(this.X).applyQuaternion(qYaw);
    const q = new T.Quaternion().setFromAxisAngle(right, -dy * 0.005).multiply(qYaw);
    if (Math.abs(this.dir().applyQuaternion(q).z) > 0.9998) q.copy(qYaw);
    this.camera.position.sub(pivot).applyQuaternion(q).add(pivot);
    this.camera.quaternion.premultiply(q);
    this.dirty = true;
  }

  grab(anchor, x, y) {  // the grabbed ground point stays under the cursor
    const hit = this.onPlane(x, y, anchor.z);
    if (hit) { this.camera.position.add(anchor.clone().sub(hit)); this.dirty = true; }
  }

  zoom(x, y, factor) {
    const target = this.pick(x, y), offset = this.camera.position.clone().sub(target);
    if (factor < 1 && offset.length() * factor < 1) return;
    this.camera.position.copy(target).add(offset.multiplyScalar(factor));
    this.dirty = true;
  }

  listen() {
    const c = this.canvas;
    const middle = () => {
      const [a, b] = [...this.pointers.values()];
      return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, d: Math.hypot(a.x - b.x, a.y - b.y) };
    };
    c.addEventListener("contextmenu", (e) => e.preventDefault());
    c.addEventListener("pointerdown", (e) => {
      if (!this.home) return;
      c.focus();
      c.setPointerCapture(e.pointerId);
      this.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (this.pointers.size === 2) {
        const m = middle();
        this.gesture = { mode: "pinch", anchor: this.pick(m.x, m.y), d: m.d };
      } else if (this.pointers.size === 1) {
        const move = e.button === 1 || e.button === 2 || e.ctrlKey || e.shiftKey || e.metaKey;
        const p = this.pick(e.clientX, e.clientY);
        this.gesture = move ? { mode: "grab", anchor: p } : { mode: "orbit", pivot: p };
      }
    });
    c.addEventListener("pointermove", (e) => {
      const prev = this.pointers.get(e.pointerId);
      if (!prev || !this.gesture) return;
      const dx = e.clientX - prev.x, dy = e.clientY - prev.y;
      this.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      const g = this.gesture;
      if (g.mode === "orbit") this.orbit(g.pivot, dx, dy);
      else if (g.mode === "grab") this.grab(g.anchor, e.clientX, e.clientY);
      else if (g.mode === "pinch" && this.pointers.size === 2) {
        const m = middle();
        if (m.d > 0 && g.d > 0) this.zoom(m.x, m.y, g.d / m.d);
        this.grab(g.anchor, m.x, m.y);
        g.d = m.d;
      }
    });
    const release = (e) => {
      this.pointers.delete(e.pointerId);
      this.gesture = null;
      if (this.pointers.size === 1) {  // from two fingers to one: carry on orbiting without a jump
        const [p] = this.pointers.values();
        this.gesture = { mode: "orbit", pivot: this.pick(p.x, p.y) };
      }
    };
    c.addEventListener("pointerup", release);
    c.addEventListener("pointercancel", release);
    c.addEventListener("wheel", (e) => {
      e.preventDefault();
      if (this.home) this.zoom(e.clientX, e.clientY, Math.exp(e.deltaY * (e.ctrlKey ? 0.01 : 0.0015)));
    }, { passive: false });

    // Physical key codes, so W A S D sit in the same place on any keyboard layout
    // (Z Q S D on a French one). Keys stop here: Home Assistant has its own shortcuts.
    const FLIGHT = new Set(["KeyW", "KeyA", "KeyS", "KeyD", "KeyQ", "KeyE", "KeyR", "KeyF", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "PageUp", "PageDown"]);
    c.addEventListener("keydown", (e) => {
      if (e.key === "Tab" || e.key === "Escape") return;
      e.stopPropagation();
      if (FLIGHT.has(e.code)) { this.keys.add(e.code); e.preventDefault(); }
      if (e.key === "Shift") this.keys.add("Shift");
      if (e.code === "KeyH") this.levelHorizon();
    });
    c.addEventListener("keyup", (e) => {
      e.stopPropagation();
      this.keys.delete(e.code);
      if (e.key === "Shift") this.keys.delete("Shift");
    });
    c.addEventListener("blur", () => this.keys.clear());
  }

  fly(dt) {
    if (!this.home || !this.keys.size) return;
    const k = (code) => (this.keys.has(code) ? 1 : 0);
    const cam = this.camera;
    const height = Math.max(0, cam.position.z - this.home.ground);
    const v = Math.min(Math.max(height * 0.8, 4), 80) * (this.keys.has("Shift") ? 3 : 1) * dt;
    // Moves along the camera's own axes, roll included; pitch and roll turn around
    // them, yaw around the world's vertical so ← → always turn level.
    cam.position.addScaledVector(this.dir(), (k("KeyW") - k("KeyS")) * v);
    cam.position.addScaledVector(this.local(this.X), (k("KeyD") - k("KeyA")) * v);
    cam.position.addScaledVector(this.local(this.Y), (k("KeyR") + k("PageUp") - k("KeyF") - k("PageDown")) * v);
    cam.rotateOnWorldAxis(this.Z, (k("ArrowLeft") - k("ArrowRight")) * 1.2 * dt);
    cam.rotateX((k("ArrowUp") - k("ArrowDown")) * (this.options.invertPitch ? -0.9 : 0.9) * dt);
    cam.rotateZ((k("KeyQ") - k("KeyE")) * 1.2 * dt);
    this.dirty = true;
  }

  frame() {
    this.fly(Math.min(this.clock.getDelta(), 0.1));
    if (!this.dirty) return;
    this.dirty = false;
    this.renderer.render(this.scene, this.camera);
  }
}

const STYLE = `
  :host { display: block; height: 100%; }
  ha-card { height: 100%; min-height: var(--dm3d-height, 400px); overflow: hidden; position: relative; background: #111; }
  .stage { position: absolute; inset: 0; }
  .stage canvas { display: block; outline: none; touch-action: none; }
  .bar { position: absolute; top: 8px; left: 8px; right: 8px; display: flex; gap: 6px; flex-wrap: wrap; align-items: center; z-index: 1; pointer-events: none; }
  .bar > * { pointer-events: auto; }
  button, label { background: rgba(40, 40, 40, .85); color: #ddd; border: 1px solid #444; border-radius: 6px; padding: 5px 9px; font: 13px var(--ha-font-family-body, system-ui), sans-serif; cursor: pointer; }
  button.on { background: var(--primary-color, #2e7d32); border-color: transparent; color: var(--text-primary-color, #fff); }
  label { display: inline-flex; gap: 5px; align-items: center; }
  label input { margin: 0; }
  .spacer { flex: 1; pointer-events: none; }
  .status { position: absolute; left: 8px; bottom: 8px; color: #ccc; font-size: 12px; opacity: .8; pointer-events: none; }
  .help { position: absolute; right: 8px; bottom: 8px; background: rgba(20, 20, 20, .9); color: #ddd; border: 1px solid #444; border-radius: 6px; padding: 8px 10px; font-size: 12px; display: grid; grid-template-columns: auto auto; gap: 2px 12px; }
  .help[hidden] { display: none; }
  .help b { font-weight: 600; white-space: nowrap; }
`;

const CARD_TYPE = "dreame-mower-3d-card";
const DOMAIN = "dreame_mower";

const isDreameMower = (hass, entityId) =>
  typeof entityId === "string" && entityId.startsWith("lawn_mower.") && hass.entities?.[entityId]?.platform === DOMAIN;

const FORM_LABELS = {
  entity: "Mower",
  height: "Height",
  point_size: "Point size (m)",
  invert_pitch: "Invert the ↑ ↓ keys",
};
const FORM_HELPERS = {
  height: "Any CSS height, such as 450px or 70vh; ignored where the dashboard sizes the card",
  invert_pitch: "Default for this card; each browser can still change it with the Invert ↑↓ box",
};

class DreameMower3dCard extends HTMLElement {
  static getConfigForm() {
    return {
      schema: [
        { name: "entity", required: true, selector: { entity: { filter: { domain: "lawn_mower", integration: DOMAIN } } } },
        {
          type: "grid",
          name: "",
          schema: [
            { name: "height", selector: { text: {} } },
            { name: "point_size", selector: { number: { min: 0.05, max: 2, step: 0.05, mode: "box" } } },
          ],
        },
        { name: "invert_pitch", selector: { boolean: {} } },
      ],
      computeLabel: (schema) => FORM_LABELS[schema.name],
      computeHelper: (schema) => FORM_HELPERS[schema.name],
    };
  }

  static getStubConfig(hass) {
    return { entity: Object.keys(hass.states).find((id) => isDreameMower(hass, id)) || "" };
  }

  static getEntitySuggestion(hass, entityId) {
    return isDreameMower(hass, entityId) ? { config: { type: `custom:${CARD_TYPE}`, entity: entityId } } : null;
  }

  setConfig(config) {
    if (!config || !config.entity) throw new Error("Choose a Dreame mower");
    if (config.entity !== this._config?.entity) { this._info = null; this._watchState = undefined; }
    this._config = config;
    let stored = null;
    try { stored = localStorage.getItem(STORAGE_INVERT); } catch (e) { /* storage may be blocked */ }
    this._invertPitch = stored === null ? !!config.invert_pitch : stored === "1";
    if (this.shadowRoot) this._applyConfig();
    if (this._viewer) this._viewer.options.pointSize = Number(config.point_size) || 0.25;
  }

  set hass(hass) {
    this._hass = hass;
    this._sync();
  }

  getCardSize() { return 8; }
  getGridOptions() { return { columns: "full", rows: 8, min_rows: 4, min_columns: 6 }; }

  connectedCallback() {
    if (!this.shadowRoot) this._render();
    this._start();
  }

  disconnectedCallback() {
    if (this._viewer) { this._viewer.dispose(); this._viewer = null; }
    this._shown = null;
  }

  _render() {
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `<style>${STYLE}</style>
      <ha-card>
        <div class="stage"></div>
        <div class="bar">
          <span class="maps"></span>
          <button class="smaller" title="Smaller points">Points −</button>
          <button class="bigger" title="Bigger points">Points +</button>
          <button class="recentre">Recentre</button>
          <label title="Invert the ↑ ↓ keys"><input type="checkbox" class="invert"> Invert ↑↓</label>
          <span class="spacer"></span>
          <button class="toggle-help" title="Controls">?</button>
          <button class="fullscreen" title="Full screen">⛶</button>
        </div>
        <div class="status"></div>
        <div class="help" hidden>${HELP.map(([k, v]) => `<b>${k}</b><span>${v}</span>`).join("")}</div>
      </ha-card>`;
    const $ = (s) => root.querySelector(s);
    this._stage = $(".stage");
    this._status = $(".status");
    this._mapsBar = $(".maps");
    this._invertBox = $(".invert");
    $(".smaller").onclick = () => this._viewer?.scalePoints(1 / 1.4);
    $(".bigger").onclick = () => this._viewer?.scalePoints(1.4);
    $(".recentre").onclick = () => this._viewer?.recentre();
    $(".toggle-help").onclick = () => { const h = $(".help"); h.hidden = !h.hidden; };
    $(".fullscreen").onclick = () => {
      const card = $("ha-card");
      if (document.fullscreenElement) document.exitFullscreen(); else card.requestFullscreen?.();
    };
    this._invertBox.onchange = () => {
      this._invertPitch = this._invertBox.checked;
      try { localStorage.setItem(STORAGE_INVERT, this._invertPitch ? "1" : "0"); } catch (e) { /* storage may be blocked */ }
      if (this._viewer) this._viewer.options.invertPitch = this._invertPitch;
    };
    this._applyConfig();
  }

  _applyConfig() {
    const c = this._config || {};
    this.style.setProperty("--dm3d-height", c.height || "400px");
    if (this._invertBox) this._invertBox.checked = this._invertPitch;
    if (this._viewer) this._viewer.options.invertPitch = this._invertPitch;
  }

  async _start() {
    if (this._viewer || this._starting) return;
    this._starting = true;
    try {
      const THREE = await loadThree();
      if (!this.isConnected) return;
      this._viewer = new Viewer(THREE, this._stage, { pointSize: Number(this._config?.point_size) || 0.25, invertPitch: this._invertPitch });
      this._sync();
    } catch (err) {
      this._setStatus(`Could not start the 3D view: ${err.message}`);
    } finally {
      this._starting = false;
    }
  }

  /** Ask the integration for the maps again whenever the mower's active map changes. */
  _sync() {
    if (!this.shadowRoot || !this._hass || !this._config) return;
    const mower = this._hass.states[this._config.entity];
    if (!mower) return this._setStatus(`Entity not found: ${this._config.entity}`);
    const mapId = mower.attributes.current_map_id ?? null;
    if (!this._info || mapId !== this._mapId) {
      this._mapId = mapId;
      this._fetchMaps();
      return;
    }
    this._showWanted();
  }

  async _fetchMaps() {
    if (this._fetching) { this._refetch = true; return; }
    this._fetching = true;
    try {
      const info = await this._hass.callWS({ type: "dreame_mower/point_clouds", entity_id: this._config.entity });
      if (info.active_index !== this._info?.active_index) this._picked = null;
      this._info = info;
      this._mapId = this._hass.states[this._config.entity]?.attributes.current_map_id ?? null;
      this._showWanted();
    } catch (err) {
      this._setStatus(`Could not list the 3D maps: ${err.message || err.code || err}`);
    } finally {
      this._fetching = false;
      if (this._refetch) { this._refetch = false; this._fetchMaps(); }
    }
  }

  /** Show the picked map, else the active one, and redraw the map buttons. */
  _showWanted() {
    const maps = this._info?.maps || [];
    if (!maps.length) return this._setStatus("The mower has no maps yet");
    const wanted = maps.find((m) => m.index === this._picked) || maps.find((m) => m.index === this._info.active_index) || maps[0];
    const key = maps.map((m) => `${m.index}:${m.name}`).join("|") + `#${wanted.index}`;
    if (key !== this._barKey) {
      this._barKey = key;
      this._mapsBar.replaceChildren(...(maps.length > 1 ? maps.map((m) => {
        const b = document.createElement("button");
        b.textContent = m.name;
        b.classList.toggle("on", m.index === wanted.index);
        b.onclick = () => { this._picked = m.index; this._showWanted(); };
        return b;
      }) : []));
    }
    if (this._viewer && this._shown !== wanted.url) this._load(wanted);
  }

  async _load(map) {
    this._shown = map.url;
    this._setStatus(`Loading ${map.name}…`);
    try {
      const response = await this._hass.fetchWithAuth(map.url);
      if (response.status === 404) throw new Error(`no 3D map is stored for ${map.name}`);
      if (!response.ok) throw new Error(`the server answered ${response.status}`);
      const etag = response.headers.get("ETag");
      let cached = parsedClouds.get(map.url);
      if (!cached || !etag || cached.etag !== etag) {
        cached = { etag, cloud: parsePcd(await response.arrayBuffer()) };
        parsedClouds.set(map.url, cached);
      }
      if (this._shown !== map.url || !this._viewer) return;  // another map was picked meanwhile
      this._viewer.show(cached.cloud);
      this._setStatus(`${map.name} · ${cached.cloud.count.toLocaleString()} points`);
    } catch (err) {
      if (this._shown === map.url) this._setStatus(`Could not load the 3D map: ${err.message}`);
    }
  }

  _setStatus(text) {
    if (this._status) this._status.textContent = text;
  }
}

if (!customElements.get(CARD_TYPE)) customElements.define(CARD_TYPE, DreameMower3dCard);
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === CARD_TYPE)) {
  window.customCards.push({
    type: CARD_TYPE,
    name: "Dreame Mower 3D map",
    description: "The LiDAR point cloud of the mower's map, to orbit and fly through.",
    preview: false,
  });
}
