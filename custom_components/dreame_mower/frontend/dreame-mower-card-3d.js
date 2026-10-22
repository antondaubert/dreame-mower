/*
 * The 3D view of the map card: the LiDAR point cloud the mower keeps for the
 * map the card shows.
 *
 * A section of dreame-mower-card (see the comment above SECTION_TYPES in
 * dreame-mower-card.js), in a module of its own that the integration loads on
 * every page. Its button sits under the map's zoom buttons when the map has a
 * stored cloud, and swaps the map for the cloud; closing it brings the map
 * back. The section asks the integration which maps have a cloud (WebSocket
 * `dreame_mower/point_clouds`) and fetches the cloud from its authenticated
 * endpoint once the view opens. three.js is only imported then, and the
 * view's animation loop and WebGL context only live while it is open.
 */

(() => {
  const DOMAIN = "dreame_mower";
  const SECTION_ID = "3d-map";
  // Served by the integration next to this module.
  const THREE_URL = `/${DOMAIN}/three-0.160.0.module.min.js`;
  let threePromise = null;
  const loadThree = () => (threePromise ??= import(THREE_URL));

  // The size of a point, in metres, before the view's buttons change it.
  const POINT_SIZE = 0.25;
  const POINT_STEP = 1.4;

  // How long to wait before asking again for a list without a cloud for the
  // map the card shows, in ms.
  const RELIST_MS = 60000;

  // Parsed point clouds by endpoint, kept while the page lives so opening the
  // view again does not parse them again. The ETag tells whether the file changed.
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
    ["I", "invert ↑ ↓"],
    ["Shift", "faster"],
    ["", "Keys by position: W A S D is Z Q S D on AZERTY"],
  ];

  // Whether ↑ ↓ pitch the other way, as this browser last chose.
  const STORAGE_INVERT = "dreame-mower-card-3d.invert-pitch";
  function storedInvert() {
    try {
      return localStorage.getItem(STORAGE_INVERT) === "1";
    } catch (err) {
      return false;  // storage may be blocked
    }
  }
  function storeInvert(invert) {
    try {
      localStorage.setItem(STORAGE_INVERT, invert ? "1" : "0");
    } catch (err) {
      // storage may be blocked
    }
  }

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
    constructor(THREE, container) {
      this.T = THREE;
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
      this.pointSize = POINT_SIZE;
      this.invertPitch = false;
      this.onInvert = null;  // the I key asks the section to invert ↑ ↓
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
      const material = new T.PointsMaterial({ size: this.pointSize, sizeAttenuation: true, vertexColors: !!cloud.colors, color: cloud.colors ? 0xffffff : 0x66bb6a });
      this.points = new T.Points(geometry, material);
      this.scene.add(this.points);
      this.home = bounds(cloud.positions, cloud.count);
      this.recentre();
    }

    scalePoints(factor) {
      this.pointSize *= factor;
      if (!this.points) return;
      this.points.material.size = this.pointSize;
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
        if (e.code === "KeyI" && !e.repeat && this.onInvert) this.onInvert();
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
      cam.rotateX((k("ArrowUp") - k("ArrowDown")) * (this.invertPitch ? -0.9 : 0.9) * dt);
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

  // The view takes the map's place and size; the card's mapbtns and mapbtn
  // styles apply to its buttons, since it is shown inside the card.
  const STYLE = `
.pc3d {
  position: relative;
  width: 100%;
  min-height: 220px;
  max-height: max(220px, calc(100vh - 470px));
  aspect-ratio: 1 / 1;
  overflow: hidden;
  background: #111;
}
.pc3d:fullscreen { height: 100% !important; max-height: none; aspect-ratio: auto; }
.pc3d .stage { position: absolute; inset: 0; }
.pc3d .stage canvas { display: block; outline: none; touch-action: none; }
.pc3d .status { position: absolute; left: 8px; bottom: 8px; color: #ccc; font-size: 12px; opacity: .8; pointer-events: none; }
.pc3d .help { position: absolute; left: 8px; top: 8px; background: rgba(20, 20, 20, .9); color: #ddd; border: 1px solid #444; border-radius: 6px; padding: 8px 10px; font-size: 12px; display: grid; grid-template-columns: auto auto; gap: 2px 12px; }
.pc3d .help[hidden] { display: none; }
.pc3d .help b { font-weight: 600; white-space: nowrap; }
.pc3d .help label { grid-column: 1 / -1; display: flex; gap: 6px; align-items: center; margin-top: 4px; cursor: pointer; }
.pc3d .help label input { margin: 0; }
  `;

  const button = (action, icon, label) =>
    `<button type="button" class="mapbtn" data-pc3d="${action}" title="${label}" aria-label="${label}"><ha-icon icon="${icon}"></ha-icon></button>`;

  /** The section: its button on the map, and the view it shows in the map's place while open. */
  class PointCloudSection {
    constructor(host) {
      this.host = host;
      this.info = null;  // what the integration lists: { maps: [{ id, index, name, url, has_cloud }] }
      this.mapId = undefined;
      this.listing = null;
      this.listedAt = 0;
      this.open = false;
      this.el = null;
      this.viewer = null;
      this.shown = null;
    }

    // The card connects its sections on every change of state; the list is
    // asked for once per time the card is shown, then as update() sees fit.
    connect() { if (!this.listedAt) this.list(); }
    resubscribe() { this.list(); }
    disconnect() { this.listedAt = 0; this.close(); }
    reset() { this.info = null; this.mapId = undefined; this.listedAt = 0; this.close(); this.list(); }
    leave() { this.close(); }

    // The view follows the map the card shows, which is the mower's active map.
    // While that map has no cloud in the list, the list is asked for again once
    // in a while: it may have failed (the mower offline), come before the
    // mower's maps were read, or the mower may store a cloud later.
    // A card that is not shown asks nothing; connect() lists once it is again.
    update() {
      if (!this.host.connected) return;
      const mapId = this.currentMapId();
      if (mapId !== this.mapId) {
        this.mapId = mapId;
        this.list();
      } else if (mapId !== null && !this.map() && Date.now() - this.listedAt >= RELIST_MS) {
        this.list();
      }
    }

    currentMapId() {
      const state = this.host.hass && this.host.entityId ? this.host.hass.states[this.host.entityId] : null;
      return state ? state.attributes.current_map_id ?? null : null;
    }

    /** The listed map the card shows, if it has a stored cloud. */
    map() {
      const maps = (this.info && this.info.maps) || [];
      const shown = maps.find((m) => m.id === this.mapId);
      return shown && shown.has_cloud ? shown : null;
    }

    async list() {
      const { hass, entityId } = this.host;
      if (!hass || !entityId) return;
      this.mapId = this.currentMapId();
      this.listedAt = Date.now();
      const listing = (this.listing = hass.callWS({ type: `${DOMAIN}/point_clouds`, entity_id: entityId }));
      try {
        const info = await listing;
        if (listing !== this.listing) return;  // a newer list was asked for
        this.info = info;
      } catch (err) {
        if (listing !== this.listing) return;
        this.info = null;
      }
      if (this.open && (!this.map() || this.map().url !== this.shown)) {
        if (this.map()) this.load(this.map());
        else this.close();
      }
      this.host.refreshMow();
    }

    mapButtons() {
      return this.map() ? button("open", "mdi:cube-scan", "3D map") : "";
    }

    cover() {
      return this.open ? this.el : null;
    }

    handleEvent(e) {
      if (e.type !== "click" || !e.target.closest('[data-pc3d="open"]')) return;
      // The view takes the height the map has, so the card keeps its size.
      const shown = e.target.closest(".map");
      this.show(shown ? shown.clientHeight : 0);
    }

    show(height = 0) {
      const map = this.map();
      if (!map) return;
      if (!this.el) this.build();
      this.el.style.height = height ? `${height}px` : "";
      this.el.style.aspectRatio = height ? "auto" : "";
      this.open = true;
      this.host.refreshMow();
      this.start(map);
    }

    build() {
      const el = (this.el = document.createElement("div"));
      el.className = "pc3d";
      el.innerHTML =
        `<style>${STYLE}</style><div class="stage"></div>` +
        '<div class="mapbtns">' +
        button("close", "mdi:close", "Back to the map") +
        button("recentre", "mdi:image-filter-center-focus", "Recentre") +
        button("bigger", "mdi:plus-circle-outline", "Bigger points") +
        button("smaller", "mdi:minus-circle-outline", "Smaller points") +
        button("help", "mdi:help-circle-outline", "Controls") +
        button("fullscreen", "mdi:fullscreen", "Full screen") +
        "</div>" +
        `<div class="status"></div><div class="help" hidden>${HELP.map(([k, v]) => `<b>${k}</b><span>${v}</span>`).join("")}` +
        '<label><input type="checkbox" data-pc3d="invert"> Invert ↑ ↓</label></div>';
      el.querySelector('[data-pc3d="invert"]').checked = storedInvert();
      el.addEventListener("change", (e) => {
        if (e.target.dataset.pc3d === "invert") this.setInvert(e.target.checked);
      });
      el.addEventListener("click", (e) => {
        const action = e.target.closest("[data-pc3d]")?.dataset.pc3d;
        if (action === "close") this.close();
        else if (action === "recentre") this.viewer?.recentre();
        else if (action === "bigger") this.viewer?.scalePoints(POINT_STEP);
        else if (action === "smaller") this.viewer?.scalePoints(1 / POINT_STEP);
        else if (action === "help") { const help = el.querySelector(".help"); help.hidden = !help.hidden; }
        else if (action === "fullscreen") {
          if (document.fullscreenElement) document.exitFullscreen();
          else el.requestFullscreen?.();
        }
      });
    }

    async start(map) {
      this.setStatus("Loading the 3D view…");
      try {
        const THREE = await loadThree();
        if (!this.open || this.viewer) return;
        this.viewer = new Viewer(THREE, this.el.querySelector(".stage"));
        this.viewer.invertPitch = storedInvert();
        this.viewer.onInvert = () => this.setInvert(!this.viewer.invertPitch);
        this.load(this.map() || map);
      } catch (err) {
        if (this.open) this.setStatus(`Could not start the 3D view: ${err.message || err}`);
      }
    }

    /** Pitch the other way with ↑ ↓ or not, and remember it in this browser. */
    setInvert(invert) {
      storeInvert(invert);
      if (this.viewer) this.viewer.invertPitch = invert;
      const box = this.el && this.el.querySelector('[data-pc3d="invert"]');
      if (box) box.checked = invert;
    }

    close() {
      if (this.viewer) { this.viewer.dispose(); this.viewer = null; }
      this.shown = null;
      if (document.fullscreenElement && document.fullscreenElement === this.el) document.exitFullscreen();
      if (!this.open) return;
      this.open = false;
      this.host.refreshMow();
    }

    async load(map) {
      if (!this.viewer) return;
      this.shown = map.url;
      this.setStatus(`Loading ${map.name}…`);
      try {
        const response = await this.host.hass.fetchWithAuth(map.url);
        if (response.status === 404) throw new Error(`no 3D map is stored for ${map.name}`);
        if (!response.ok) throw new Error(`the server answered ${response.status}`);
        const etag = response.headers.get("ETag");
        let cached = parsedClouds.get(map.url);
        if (!cached || !etag || cached.etag !== etag) {
          cached = { etag, cloud: parsePcd(await response.arrayBuffer()) };
          parsedClouds.set(map.url, cached);
        }
        if (this.shown !== map.url || !this.viewer) return;  // closed, or another map meanwhile
        this.viewer.show(cached.cloud);
        this.setStatus(`${map.name} · ${cached.cloud.count.toLocaleString()} points`);
      } catch (err) {
        if (this.shown === map.url) this.setStatus(`Could not load the 3D map: ${err.message}`);
      }
    }

    setStatus(text) {
      const status = this.el && this.el.querySelector(".status");
      if (status) status.textContent = text;
    }
  }

  // The integration loads this module before the frontend has put its own custom
  // element registry in place of window.customElements, and the map card is
  // defined in that one: wait for the frontend's root element, then for the card.
  customElements
    .whenDefined("home-assistant")
    .then(() => window.customElements.whenDefined("dreame-mower-card"))
    .then(() =>
      window.customElements
        .get("dreame-mower-card")
        .registerSection({ id: SECTION_ID, create: (host) => new PointCloudSection(host) }),
    );
})();
