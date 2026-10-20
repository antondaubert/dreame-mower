/*
 * Dreame Mower Card: an interactive map for the dreame_mower integration.
 *
 * Served by the integration itself; no build step. The map arrives as
 * vector geometry over the dreame_mower/map/subscribe websocket command and
 * is drawn as SVG in map units (millimetres, y up on the map, y down on
 * screen). Strokes and stripes are real sizes, so they scale with the zoom;
 * labels and markers keep their size on screen.
 */

// === Constants and palettes ===

const CARD_TYPE = "dreame-mower-card";
const EDITOR_TYPE = "dreame-mower-card-editor";
const DOMAIN = "dreame_mower";
const SUBSCRIBE_TYPE = `${DOMAIN}/map/subscribe`;

// Delays before subscribing again after the feed closed or failed; the last
// one repeats.
const RESUBSCRIBE_DELAYS = [2000, 5000, 5000, 10000, 30000];
const PAN_THRESHOLD_PX = 6;
const DOUBLE_TAP_MS = 300;
const DOUBLE_TAP_PX = 25;
const TOAST_MS = 5000;
// Share of the view the map fills when it is fitted.
const FIT_SHARE = 0.85;
// Real sizes in map units (mm).
const STRIPE_WIDTH = 500;
const OUTLINE_WIDTH = 40;
const TRAIL_WIDTH = 400;
const MOWER_LENGTH = 880;
const MOWER_WIDTH = 560;
const STATION_LENGTH = 1100;
const STATION_WIDTH = 700;
// The mower and its station are drawn at their real size, and the mower never
// shorter than this on screen.
const MOWER_SCALE = 1;
const MOWER_MIN_PX = 20;

// Lawn colours by zone id, starting at zone 1; the outline is a shade darker.
const ZONE_COLORS = [
  "#CCF3DE", "#FEE7CD", "#CAEFFC", "#E0E9FF", "#FCCACA", "#FFF4C7", "#CAE1FC", "#FFCEBE",
  "#F0FFCA", "#C4FFE1", "#FCCAEA", "#C0CCFF", "#CAFCFC", "#EBCAFC", "#DEFCCA", "#FCCAD5",
];

const PALETTES = {
  light: {
    background: "#f4f4f4",
    surface: "#ffffff",
    text: "#404040",
    zoneName: "#6b6b6b",
    muted: "#8a8a8a",
    stripe: "#ffffff",
    lawnShade: 0,
    pathOuter: "#A6A6A6",
    pathInner: "#E2E2E2",
    noGo: "#EE3C2F",
    ignoreObstacles: "#008b8b",
    spot: "#70966E",
    trail: "rgba(255,255,255,.6)",
    working: "#70966E",
    brand: "#AB8C5E",
    obstacle: "#87B2FF",
    mowerBody: "#cfcfcf",
    mowerTop: "#3a3a3a",
    mowerEdge: "#8c8c8c",
    station: "#707378",
    stationBody: "#484a4e",
    edge: "#A0D69D",
  },
  dark: {
    background: "#1c1c1e",
    surface: "#2c2c2e",
    text: "#e0e0e0",
    zoneName: "#c8c8c8",
    muted: "#9a9a9a",
    stripe: "rgba(255,255,255,.07)",
    lawnShade: 0.62,
    pathOuter: "#5a5a5a",
    pathInner: "#3a3a3a",
    noGo: "#EE3C2F",
    ignoreObstacles: "#2bb5b5",
    spot: "#8fb88c",
    trail: "rgba(255,255,255,.35)",
    working: "#8fb88c",
    brand: "#c9a877",
    obstacle: "#87B2FF",
    mowerBody: "#bdbdbd",
    mowerTop: "#2e2e2e",
    mowerEdge: "#777777",
    station: "#606368",
    stationBody: "#3c3e42",
    edge: "#6f9f6c",
  },
};

// === CSS ===

const CSS = `
:host { display: block; }
ha-card {
  /* The card's chrome follows Home Assistant's theme; only the map keeps
     its own palette. */
  --mower-text: var(--primary-text-color, #212121);
  --mower-muted: var(--secondary-text-color, #727272);
  --mower-background: var(--ha-card-background, var(--card-background-color, #fff));
  --mower-divider: var(--divider-color, rgba(0,0,0,.12));
  --mower-surface: color-mix(in srgb, var(--mower-text) 6%, var(--mower-background));
  --mower-brand: var(--primary-color, #03a9f4);
  --mower-error: var(--error-color, #db4437);
  position: relative;
  overflow: hidden;
  color: var(--mower-text);
  background: var(--mower-background);
  font-family: var(--paper-font-body1_-_font-family, inherit);
}
button { font: inherit; color: inherit; }
.tabs { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border-bottom: 1px solid var(--mower-divider); }
.tabs button {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 9px 4px 7px;
  border: none;
  border-bottom: 2px solid transparent;
  background: none;
  color: var(--mower-muted);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: .2px;
  cursor: pointer;
  --mdc-icon-size: 22px;
}
.tabs button.on { color: var(--mower-brand); border-bottom-color: var(--mower-brand); }
.status { display: flex; align-items: center; gap: 4px; padding: 10px 6px 8px 16px; }
.status .txt { flex: 1 1 auto; min-width: 0; }
.status .caption { font-size: 12px; line-height: 16px; color: var(--mower-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.status .state { font-size: 16px; font-weight: 500; line-height: 20px; }
.status .sub { display: flex; align-items: center; gap: 4px; font-size: 13px; line-height: 18px; color: var(--mower-muted); --mdc-icon-size: 16px; }
.status .sub.err { color: var(--mower-error); }
.iconbtn {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: none;
  color: var(--mower-text);
  cursor: pointer;
  --mdc-icon-size: 24px;
}
.iconbtn:disabled { opacity: .3; cursor: default; }
.map {
  position: relative;
  width: 100%;
  min-height: 220px;
  /* The whole card fits on a phone screen: dragging on the map moves the map,
     so the page could not be scrolled past it. */
  max-height: max(220px, calc(100vh - 470px));
  aspect-ratio: 1 / 1;
  overflow: hidden;
  outline: none;
  touch-action: none;
  background: var(--mower-map-background);
}
.map svg.main {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  display: block;
  user-select: none;
  -webkit-user-select: none;
}
.mapbtns { position: absolute; right: 8px; top: 8px; display: flex; flex-direction: column; gap: 4px; z-index: 1; }
.mapbtn, .mapchip {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 1px solid var(--mower-divider);
  background: var(--mower-background);
  color: var(--mower-text);
  opacity: .94;
  cursor: pointer;
}
.mapbtn { width: 32px; height: 32px; border-radius: 50%; --mdc-icon-size: 18px; }
.mapbtns .secbtns, .mapbtns [data-section] { display: contents; }
.mapchip {
  position: absolute;
  left: 8px;
  top: 8px;
  z-index: 1;
  gap: 6px;
  max-width: calc(100% - 64px);
  height: 32px;
  padding: 0 8px 0 10px;
  border-radius: 16px;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  --mdc-icon-size: 16px;
}
.mapchip .name { overflow: hidden; text-overflow: ellipsis; }
.mapchip .m, .mapchip ha-icon { color: var(--mower-muted); font-weight: 400; }
.mapchip:disabled { cursor: default; opacity: .9; }
.mapnote {
  position: absolute;
  left: 50%;
  bottom: 10px;
  transform: translateX(-50%);
  z-index: 1;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: calc(100% - 32px);
  padding: 6px 12px;
  border: 1px solid var(--mower-divider);
  border-radius: 16px;
  background: color-mix(in srgb, var(--mower-background) 92%, transparent);
  font-size: 12px;
  pointer-events: none;
}
.mapnote .spin {
  flex: 0 0 auto;
  width: 14px;
  height: 14px;
  border: 2px solid var(--mower-divider);
  border-top-color: var(--mower-brand);
  border-radius: 50%;
  animation: mower-spin 0.9s linear infinite;
}
@keyframes mower-spin { to { transform: rotate(360deg); } }
.msg {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 16px;
  color: var(--mower-muted);
  pointer-events: none;
}
.errline {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 10px 12px 0;
  padding: 6px 6px 6px 12px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--mower-error) 12%, var(--mower-background));
  color: var(--mower-error);
  font-size: 13px;
  line-height: 18px;
  --mdc-icon-size: 20px;
}
.errline span { flex: 1 1 auto; }
.flat { flex: 0 0 auto; padding: 6px 10px; border: none; border-radius: 18px; background: none; color: var(--mower-brand); font-weight: 500; cursor: pointer; }
.flat:disabled { opacity: .5; cursor: default; }
.panel { display: flex; flex-direction: column; gap: 10px; padding: 10px 12px 12px; }
.panel .controls { display: flex; flex-direction: column; gap: 10px; }
.panel .controls:empty, .panel .strip:empty { display: none; }
.strip { display: grid; grid-template-columns: repeat(var(--modes, 4), minmax(0, 1fr)); border: 1px solid var(--mower-divider); border-radius: 18px; overflow: hidden; }
.strip button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-height: 36px;
  padding: 7px 4px;
  border: none;
  background: none;
  font-size: 13px;
  cursor: pointer;
  --mdc-icon-size: 17px;
}
.strip button.on { background: var(--mower-brand); color: var(--text-primary-color, #fff); }
.strip button:disabled { color: var(--mower-muted); cursor: default; }
.strip button.on:disabled { color: var(--text-primary-color, #fff); opacity: .6; }
.glyph { width: 17px; height: 17px; flex: 0 0 auto; }
.hint { font-size: 13px; line-height: 18px; color: var(--mower-muted); }
.hint b { color: var(--mower-text); font-weight: 500; }
.pill {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  min-width: 0;
  min-height: 40px;
  box-sizing: border-box;
  padding: 8px 10px 8px 12px;
  border: 1px solid var(--mower-divider);
  border-radius: 20px;
  background: none;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  cursor: pointer;
  --mdc-icon-size: 16px;
}
.pill .v { display: inline-flex; align-items: center; gap: 3px; }
.pill .v .glyph, .pill ha-icon { width: 16px; height: 16px; color: var(--mower-muted); }
.pill .dot { color: var(--mower-muted); opacity: .6; }
.pill .later { margin-left: 6px; color: var(--mower-muted); overflow: hidden; text-overflow: ellipsis; }
.pill .chev { margin-left: auto; }
.pill:disabled { color: var(--mower-muted); cursor: default; }
.primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  min-height: 44px;
  padding: 10px 18px;
  border: none;
  border-radius: 22px;
  background: var(--mower-brand);
  color: var(--text-primary-color, #fff);
  font-size: 15px;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  --mdc-icon-size: 20px;
}
.primary small { font-size: 12px; font-weight: 400; opacity: .9; }
.primary:disabled { opacity: .45; cursor: default; }
.progress { height: 4px; border-radius: 2px; background: var(--mower-divider); overflow: hidden; }
.progress > div { height: 100%; background: var(--mower-working); }
.figs { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; font-size: 13px; color: var(--mower-muted); }
.figs b { color: var(--mower-text); font-weight: 500; }
.figs .zone { margin-left: auto; }
.bigrow { display: flex; gap: 10px; }
.bigrow > * { flex: 1 1 0; min-width: 0; }
.big {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 46px;
  padding: 0 10px;
  border: 1px solid var(--mower-divider);
  border-radius: 12px;
  background: var(--mower-background);
  color: var(--mower-text);
  font-size: 15px;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  --mdc-icon-size: 22px;
}
.big ha-icon { color: var(--mower-brand); }
.big.stop ha-icon { color: var(--mower-error); }
.big.pause ha-icon { color: #f9a825; }
.big:disabled { color: var(--mower-muted); cursor: default; }
.big:disabled ha-icon { color: var(--mower-muted); }
/* A bar along the bottom of the card, over the row of buttons there while
   it shows; taps go through to them. */
.toast {
  pointer-events: none;
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 12px;
  box-sizing: border-box;
  min-height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 8px 14px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  background: var(--mower-text);
  color: var(--mower-background);
  font-size: 0.9em;
  z-index: 6;
}
.toast.error { background: var(--mower-error); color: #fff; }
/* The mowing settings cover the card when opened from the Mow tab; opened
   from the Settings tab they are one of its pages. The views of the History,
   Schedules and Settings tabs sit below the tabs. */
.settings {
  position: absolute;
  inset: 0;
  z-index: 3;
  display: flex;
  flex-direction: column;
  background: var(--mower-background);
}
.settings.inline { position: static; z-index: auto; }
.view { display: flex; flex-direction: column; }
.view .sbody { padding: 0 0 12px; }
.view .shead:empty { display: none; }
.subhead, .view .shead, .settings .shead {
  display: flex;
  align-items: center;
  gap: 4px;
  min-height: 52px;
  box-sizing: border-box;
  padding: 6px 8px 6px 4px;
  border-bottom: 1px solid var(--mower-divider);
  font-size: 16px;
  font-weight: 500;
}
.subhead .iconbtn, .view .shead .iconbtn, .settings .shead .iconbtn { width: 36px; height: 36px; }
.subhead .title, .view .shead .title, .settings .shead .title { flex: 0 1 auto; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.subhead .muted, .view .shead .muted, .settings .shead .muted {
  flex: 1 1 auto;
  min-width: 0;
  padding: 0 8px 0 6px;
  color: var(--mower-muted);
  font-size: 13px;
  font-weight: 400;
  text-align: right;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.subhead .muted.left { text-align: left; }
.settings .sbody { flex: 1 1 auto; overflow-y: auto; padding: 12px 12px 4px; display: flex; flex-direction: column; gap: 14px; }
.settings.inline .sbody { overflow: visible; }
/* Lists of rows: a group title, then rows with an icon tile, a title, a
   grey line of what is set, and a control or a chevron at the right. */
.group { padding: 12px 16px 4px; font-size: 12px; font-weight: 500; letter-spacing: .4px; text-transform: uppercase; color: var(--mower-muted); }
.group.sep { margin-top: 4px; padding-top: 14px; border-top: 1px solid var(--mower-divider); }
.list { display: flex; flex-direction: column; }
.row {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  min-height: 52px;
  box-sizing: border-box;
  padding: 9px 12px 9px 16px;
  border: none;
  background: none;
  color: var(--mower-text);
  font: inherit;
  text-align: left;
  --mdc-icon-size: 20px;
}
.row.wrap { flex-wrap: wrap; row-gap: 8px; }
.row.short { min-height: 44px; }
button.row { cursor: pointer; }
button.row:disabled { opacity: .45; cursor: default; }
.row + .row { border-top: 1px solid color-mix(in srgb, var(--mower-divider) 50%, transparent); }
.row .ricon {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--mower-brand) 12%, transparent);
  color: var(--mower-brand);
}
.row .ricon .glyph { width: 20px; height: 20px; }
.row .ricon.g { background: color-mix(in srgb, #43a047 14%, transparent); color: #2e7d32; }
.row .ricon.o { background: color-mix(in srgb, #ef6c00 13%, transparent); color: #ef6c00; }
.row .ricon.p { background: color-mix(in srgb, #8e24aa 12%, transparent); color: #8e24aa; }
.row .ricon.n { background: color-mix(in srgb, var(--mower-text) 7%, transparent); color: var(--mower-muted); }
.row .rt { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; }
.row .rt .t { font-size: 14px; font-weight: 500; line-height: 18px; }
.row .rt .d { font-size: 12px; line-height: 16px; color: var(--mower-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row .rt .d.multi { white-space: normal; }
.row .chev { flex: 0 0 auto; color: var(--mower-muted); }
.row .val { flex: 0 1 auto; min-width: 0; color: var(--mower-muted); font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row > .flat { margin-right: -6px; }
.row .res { flex: 0 0 auto; --mdc-icon-size: 24px; }
.row .res.complete { color: #43a047; }
.row .res.incomplete { color: #f9a825; }
.row .res.stopped { color: var(--mower-error); }
.row .cam { flex: 0 0 auto; display: inline-flex; align-items: center; gap: 2px; font-size: 12px; color: #4a7fd6; --mdc-icon-size: 15px; }
.row .in, .settings .in {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 55%;
  box-sizing: border-box;
  padding: 5px 8px;
  border: 1px solid var(--mower-divider);
  border-radius: 6px;
  background: var(--mower-background);
  color: var(--mower-text);
  font: inherit;
  font-size: 14px;
  line-height: 18px;
  white-space: nowrap;
}
.row .in input { min-width: 0; padding: 0; border: none; background: none; color: inherit; font: inherit; }
.row .in input[type="number"] { width: 4em; text-align: right; }
.row input[type="range"] { flex: 1 1 140px; min-width: 0; margin: 0; accent-color: var(--mower-brand); }
.row ha-entity-picker { flex: 0 1 55%; min-width: 0; }
/* What wraps below its title still sits at the right. */
.row.wrap > :last-child:not(.rt) { margin-left: auto; }
.row.wrap > ha-entity-picker { flex: 0 1 320px; }
.row .chips { justify-content: flex-end; }
.meter { display: block; height: 5px; margin-top: 6px; border-radius: 3px; background: color-mix(in srgb, var(--mower-text) 10%, transparent); overflow: hidden; }
.meter i { display: block; height: 100%; }
.meter .good { background: #43a047; }
.meter .soon { background: #f9a825; }
.meter .now { background: var(--mower-error); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 32px;
  box-sizing: border-box;
  padding: 4px 10px;
  border: 1px solid var(--mower-divider);
  border-radius: 16px;
  background: none;
  color: var(--mower-text);
  font: inherit;
  font-size: 13px;
  white-space: nowrap;
  cursor: pointer;
  --mdc-icon-size: 16px;
}
.chip .glyph { width: 16px; height: 16px; }
.chip.on { background: var(--mower-brand); border-color: var(--mower-brand); color: var(--text-primary-color, #fff); }
.chip.danger { color: var(--mower-error); }
.chip:disabled { opacity: .45; cursor: default; }
.callout {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin: 8px 12px 0;
  padding: 10px 12px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--mower-brand) 8%, var(--mower-background));
  font-size: 13px;
  line-height: 18px;
  --mdc-icon-size: 20px;
}
.callout > ha-icon { flex: 0 0 auto; color: var(--mower-brand); }
.callout > div { flex: 1 1 auto; min-width: 0; }
.callout.mid { align-items: center; }
.callout.warn { background: color-mix(in srgb, #f9a825 14%, var(--mower-background)); }
.callout.warn > ha-icon { color: #f9a825; }
.callout.err { background: color-mix(in srgb, var(--mower-error) 12%, var(--mower-background)); }
.callout.err > ha-icon { color: var(--mower-error); }
.callout b { font-weight: 500; }
.callout .muted { color: var(--mower-muted); }
.save { display: flex; align-items: center; justify-content: flex-end; gap: 8px; padding: 10px 12px 12px; }
.save .primary { width: auto; min-height: 40px; }
.settings .save { padding: 8px 12px 12px; border-top: 1px solid var(--mower-divider); }
.settings.inline .save { border-top: none; }
.flat.danger { color: var(--mower-error); }
.view .hint, .settings .hint { padding: 4px 16px 10px; font-size: 12.5px; }
.settings .sbody .hint { padding: 0; }
.view .note { padding: 18px 16px; }
.seg { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); border: 1px solid var(--mower-divider); border-radius: 18px; overflow: hidden; }
.seg button {
  min-height: 34px;
  padding: 6px 4px;
  border: none;
  background: none;
  color: var(--mower-text);
  font: inherit;
  font-size: 13px;
  white-space: nowrap;
  cursor: pointer;
}
.seg button + button { border-left: 1px solid var(--mower-divider); }
.seg button.on { background: var(--mower-brand); color: var(--text-primary-color, #fff); }
.seg button:disabled { opacity: .5; cursor: default; }
.row .seg { flex: 0 0 auto; width: 176px; }
.sfield { display: flex; flex-direction: column; gap: 6px; }
.sfield.off { opacity: .45; pointer-events: none; }
.sfield .lab { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--mower-muted); --mdc-icon-size: 15px; }
.sfield .lab .glyph { width: 15px; height: 15px; }
.sfield .lab b { margin-left: auto; color: var(--mower-text); font-weight: 500; font-size: 14px; }
.sfield .range { display: flex; align-items: center; gap: 10px; font-size: 12.5px; color: var(--mower-muted); }
.sfield .range input { flex: 1 1 auto; min-width: 0; margin: 0; accent-color: var(--mower-brand); }
.settings .group { padding: 4px 0 0; display: flex; align-items: center; gap: 4px; }
.settings .group .glyph { width: 15px; height: 15px; }
.settings .list { margin: -6px -12px 0; }
.settings .sfield select.in { max-width: none; align-self: flex-start; }
.row.off { opacity: .45; pointer-events: none; }
.preview { display: block; width: 100%; height: 110px; border-radius: 10px; background: var(--mower-map-background); }
.switch {
  position: relative;
  flex: 0 0 auto;
  width: 40px;
  height: 22px;
  padding: 0;
  border: none;
  border-radius: 11px;
  background: color-mix(in srgb, var(--mower-text) 28%, transparent);
  cursor: pointer;
}
.switch::after {
  content: "";
  position: absolute;
  left: 2px;
  top: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 2px rgba(0,0,0,.3);
  transition: transform .15s;
}
.switch.on { background: var(--mower-brand); }
.switch:disabled { opacity: .45; cursor: default; }
.switch.on::after { transform: translateX(18px); }
.totals { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); margin: 10px 12px 0; padding: 10px 6px; border-radius: 10px; background: var(--mower-surface); text-align: center; }
.totals b { display: block; font-size: 20px; font-weight: 500; }
.totals small { font-size: 12px; color: var(--mower-muted); }
.worklog .filter { padding: 10px 12px 4px; }
/* A long log scrolls within the tab, so the card stays its size. */
.worklog .loglist { max-height: min(60vh, 560px); overflow-y: auto; }
.logmapwrap { position: relative; }
.logmap {
  display: block;
  width: 100%;
  min-height: 240px;
  height: min(55vh, 420px);
  background: var(--mower-map-background);
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
}
.edithead .flat { display: inline-flex; align-items: center; gap: 2px; padding-right: 4px; --mdc-icon-size: 18px; }
.editpanel { display: flex; flex-direction: column; gap: 10px; padding: 10px 12px 12px; }
.editpanel .tools { display: flex; gap: 6px; overflow-x: auto; scrollbar-width: none; margin: 0 -12px; padding: 0 12px; }
.editpanel .tools::-webkit-scrollbar { display: none; }
.editpanel .tools .chip { flex: 0 0 auto; }
.editpanel .callout { margin: 0; flex-wrap: wrap; row-gap: 4px; }
.editpanel .callout input[type="text"] { flex: 1 1 auto; min-width: 0; padding: 5px 8px; border: 1px solid var(--mower-divider); border-radius: 6px; background: var(--mower-background); color: inherit; font: inherit; }
.editpanel .callout .facing { flex: 1 1 100%; display: flex; align-items: center; gap: 8px; }
.editpanel .callout .facing input[type="range"] { flex: 1 1 auto; min-width: 0; accent-color: var(--mower-brand); }
.editpanel .callout .facing b { min-width: 3.2em; text-align: right; }
.editpanel .callout .acts { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 2px; }
.editpanel .callout .flat { padding: 6px 8px; }
.editpanel .warn { font-size: 12.5px; color: #BF6E12; }
.editpanel .save { padding: 0; }
.maplist .cards { display: flex; flex-direction: column; gap: 10px; padding: 12px; }
.maplist .mapcard { padding: 12px; border: 1px solid var(--mower-divider); border-radius: 12px; }
.maplist .mapcard.empty { display: flex; align-items: center; gap: 12px; border-style: dashed; }
.maplist .mapcard .top { display: flex; align-items: center; gap: 12px; }
.maplist .mapcard svg { flex: 0 0 auto; width: 80px; height: 62px; }
.maplist .mapcard .name { flex: 1 1 auto; min-width: 0; display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 500; }
.maplist .mapcard.empty .name { color: var(--mower-muted); }
.maplist .mapcard .info { flex: 1 1 auto; min-width: 0; }
.maplist .mapcard .info .hint { padding: 0; }
.maplist .inuse { padding: 1px 6px; border-radius: 5px; font-size: 11.5px; font-weight: 500; color: #2e7d32; background: color-mix(in srgb, #43a047 15%, transparent); }
.maplist .ops { margin-top: 10px; }
.maplist .ops input { flex: 1 1 140px; min-width: 0; padding: 5px 8px; border: 1px solid var(--mower-divider); border-radius: 6px; background: var(--mower-background); color: inherit; font: inherit; }
.maplist .hint { padding: 0; }
.maplist .hint.warn { color: #BF6E12; }
/* The bottom sheets: an obstacle's photo, the questions before a start and
   the map picker. */
.scrim { position: absolute; inset: 0; z-index: 4; background: rgba(0,0,0,.28); }
.sheet {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 5;
  box-sizing: border-box;
  max-height: 85%;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 8px 16px 16px;
  border-radius: 16px 16px 0 0;
  background: var(--mower-background);
  box-shadow: 0 -4px 16px rgba(0,0,0,.18);
}
.sheet .grip { flex: 0 0 auto; width: 36px; height: 4px; margin: 0 auto -4px; border-radius: 2px; background: var(--mower-divider); }
.sheet .phead { display: flex; align-items: center; gap: 8px; }
.sheet .phead > span { flex: 1 1 auto; min-width: 0; font-size: 16px; font-weight: 500; }
.sheet .phead small { color: var(--mower-muted); font-size: 13px; font-weight: 400; }
.sheet .phead .iconbtn { width: 32px; height: 32px; --mdc-icon-size: 20px; }
.sheet p { margin: 0; font-size: 13px; line-height: 18px; color: var(--mower-muted); }
.sheet .frame { position: relative; flex: 0 0 auto; border-radius: 10px; overflow: hidden; background: #000; aspect-ratio: 16 / 9; }
.sheet .frame img, .sheet .frame svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.sheet .wait { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; padding: 18px 12px;
  border-radius: 10px; background: var(--mower-surface); color: var(--mower-muted); font-size: 13px; text-align: center; aspect-ratio: 16 / 9; }
.sheet .wait button { margin-top: 6px; }
.choice .pactions { display: flex; flex-direction: column; gap: 10px; }
.choice .cpreview:empty { display: none; }
.choice .cpreview svg.logmap { min-height: 0; height: min(32vh, 220px); touch-action: auto; border: 1px solid var(--mower-divider); }
.choice .cpreview .note { padding: 8px; font-size: 12.5px; }
.choice .cnote { display: block; font-size: 12px; color: var(--mower-muted); }
.picker .maprow { display: flex; align-items: center; gap: 14px; min-height: 64px; padding: 4px 0; }
.picker .maprow + .maprow { border-top: 1px solid var(--mower-divider); }
.picker .maprow svg { flex: 0 0 auto; width: 72px; height: 56px; }
.picker .maprow span { flex: 1 1 auto; min-width: 0; font-size: 14px; font-weight: 500; }
.picker .maprow small { display: block; font-size: 12px; font-weight: 400; color: var(--mower-muted); }
.picker .maprow > ha-icon { color: var(--mower-brand); padding: 0 10px; }
[hidden] { display: none !important; }
`;

// === Helpers: text and formatting ===

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ESCAPES[ch]);
}

// "returning_to_charge" -> "Returning to charge"
function humanize(value) {
  if (value === null || value === undefined || value === "") return "";
  const text = String(value).replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function num(value) {
  return Math.round(value * 10) / 10;
}

function errorMessage(err) {
  if (!err) return "Unknown error";
  if (typeof err === "string") return err;
  if (err.message) return err.message;
  if (err.error && err.error.message) return err.error.message;
  if (err.code) return String(err.code);
  return "Unknown error";
}

function safeUnsubscribe(unsub) {
  try {
    const result = unsub();
    if (result && typeof result.catch === "function") result.catch(() => {});
  } catch (err) {
    // The subscription is already gone.
  }
}

// === Helpers: live state ===

// The code the mower sets while rain keeps it home.
const RAIN_CODE = 56;

// What a code says as it comes up.
const CODE_ALERTS = {
  48: "Mowing task complete",
  49: "Unable to reach some zones",
  53: "Scheduled mowing task started",
  54: "Low battery. Returning to the station",
  55: "Low battery. The scheduled task is cancelled",
  56: "Water is detected on the LiDAR. Rain protection is activated; returning to the station",
  57: "Rain protection is activated. The scheduled task is cancelled",
  58: "Rain protection is activated. The scheduled task is cancelled",
  60: "Temperature is too low. Frost protection is activated; the scheduled task is cancelled",
  61: "Do Not Disturb is on. Returning to the station",
  62: "Do Not Disturb is on. The scheduled task is cancelled",
  70: "The mower resumes the unfinished task",
  71: "Idle for too long. Returning to the station",
  72: "Paused for too long. Returning to the station",
  74: "Patrol complete",
};

// What the mower is busy with that keeps it from moving on, or null.
function mowerWait(mower) {
  if (!mower.available) return null;
  if (mower.location === "relocating") {
    return mower.docking === "in_station" ? "Leaving the station and finding its position…" : "Repositioning…";
  }
  if (mower.leaving_station) return "Leaving the station…";
  if (mower.docking === "docking_in_base") return "Driving into the station…";
  return null;
}

// === Helpers: work log ===

const MODE_LABELS = { all_area: "All-area", edge: "Edge", zone: "Zone", spot: "Spot", other: "Task" };
// The kind of a running task, as the status line names it.
const TASK_KINDS = { all_area: "all-area", edge: "edge", zone: "zone", spot: "spot", patrol: "patrol" };
const RESULT_LABELS = { complete: "Task complete", stopped: "Task stopped", incomplete: "Task incomplete" };
const RESULT_ICONS = { complete: "mdi:check-circle-outline", stopped: "mdi:stop-circle-outline", incomplete: "mdi:alert-circle-outline" };
const START_LABELS = { app: "In the app", schedule: "By a schedule", control_panel: "On the mower" };
const EFFICIENCY_LABELS = { standard: "Standard", efficient: "Efficient", rush: "Rush" };

function logTitle(entry) {
  const label = MODE_LABELS[entry.mode] || "Task";
  return entry.scheduled ? `Scheduled ${label.toLowerCase()}` : label;
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function formatTime(seconds) {
  const d = new Date(seconds * 1000);
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

// Minutes since midnight as "09:30".
function formatClock(minutes) {
  return `${pad2(Math.floor(minutes / 60))}:${pad2(minutes % 60)}`;
}

const WEEKDAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// A day as "Thu 16 Oct", with its year when it is not this one.
function formatDayOf(d) {
  const year = d.getFullYear() === new Date().getFullYear() ? "" : ` ${d.getFullYear()}`;
  return `${WEEKDAY_NAMES[d.getDay()]} ${d.getDate()} ${MONTH_NAMES[d.getMonth()]}${year}`;
}

// A unix time as "Thu 16 Oct, 09:12", in the viewer's time zone.
function formatDay(seconds) {
  if (!seconds) return "";
  return `${formatDayOf(new Date(seconds * 1000))}, ${formatTime(seconds)}`;
}

// Whether a task of the work log stopped within the day one of `points`
// names: the mower says when that day ended, and otherwise only its date.
function stoppedOnDayOf(entry, points) {
  const day = (seconds) => {
    const d = new Date(seconds * 1000);
    return `${d.getFullYear()}.${pad2(d.getMonth() + 1)}.${pad2(d.getDate())}`;
  };
  const stopped = entry.start + (entry.duration || 0) * 60;
  return points.some((point) =>
    // A day may run 23 or 25 hours where the clocks change.
    point.day_end ? stopped < point.day_end + 120 && stopped >= point.day_end - 90000 : day(stopped) === point.date || day(entry.start) === point.date,
  );
}

// Whether a task of the work log is an all-area or zone task left unfinished.
function unfinishedTask(entry) {
  return ["all_area", "zone"].includes(entry.mode) && ["stopped", "incomplete"].includes(entry.result);
}

function formatMinutes(minutes) {
  if (minutes === null || minutes === undefined) return "–";
  return minutes >= 60 ? `${Math.floor(minutes / 60)} h ${minutes % 60} min` : `${minutes} min`;
}

// === Helpers: schedules ===

const WEEK_DAYS = { monday: "Mon", tuesday: "Tue", wednesday: "Wed", thursday: "Thu", friday: "Fri", saturday: "Sat", sunday: "Sun" };
const TASK_TYPES = { all_area: "all-area", zone: "zones", edge: "edges", patrol: "patrol" };

// A schedule's tasks in a line: "Mon, Thu 10:00 all-area · Sat 09:30 zones".
// Tasks starting at the same time with the same kind share their days.
function scheduleSummary(tasks) {
  if (!Array.isArray(tasks) || !tasks.length) return "No tasks";
  const order = Object.keys(WEEK_DAYS);
  const groups = new Map();
  for (const task of tasks) {
    const minutes = Number(task.start_time) || 0;
    const key = `${minutes}|${task.type}`;
    if (!groups.has(key)) groups.set(key, { minutes, type: task.type, days: [] });
    groups.get(key).days.push(task.week_day);
  }
  return [...groups.values()]
    .sort((a, b) => a.minutes - b.minutes)
    .map((group) => {
      const days = [...new Set(group.days)].sort((a, b) => order.indexOf(a) - order.indexOf(b));
      const named = days.length === 7 ? "Daily" : days.map((day) => WEEK_DAYS[day] || day).join(", ");
      return `${named} ${formatClock(group.minutes)} ${TASK_TYPES[group.type] || group.type || ""}`.trim();
    })
    .join(" · ");
}

// === Helpers: coordinate transform ===

/*
 * Map units (y up) <-> SVG user units (y down, rotated), over the box
 * [x1, y1, x2, y2] the view is fitted to:
 *   X = x - x1, Y = y2 - y
 * then a clockwise turn in steps of 90 degrees:
 *    90: (X, Y) -> (H - Y, X)    size (H, W)
 *   180: (X, Y) -> (W - X, H - Y) size (W, H)
 *   270: (X, Y) -> (Y, W - X)    size (H, W)
 * fromMap is the exact inverse of toMap.
 */
function makeTransform(box, rotation) {
  const [x1, y1, x2, y2] = box;
  const W = Math.max(x2 - x1, 1);
  const H = Math.max(y2 - y1, 1);
  const rot = (((Math.round(rotation / 90) * 90) % 360) + 360) % 360;
  const swap = rot === 90 || rot === 270;
  return {
    rotation: rot,
    width: swap ? H : W,
    height: swap ? W : H,
    toMap(x, y) {
      const X = x - x1;
      const Y = y2 - y;
      switch (rot) {
        case 90:
          return [H - Y, X];
        case 180:
          return [W - X, H - Y];
        case 270:
          return [Y, W - X];
        default:
          return [X, Y];
      }
    },
    fromMap(u, v) {
      let X;
      let Y;
      switch (rot) {
        case 90:
          X = v;
          Y = H - u;
          break;
        case 180:
          X = W - u;
          Y = H - v;
          break;
        case 270:
          X = W - v;
          Y = u;
          break;
        default:
          X = u;
          Y = v;
      }
      return [X + x1, y2 - Y];
    },
  };
}

// === Helpers: geometry ===

// A flat [x, y, x, y, ...] list as pairs.
function pairs(flat) {
  const out = [];
  for (let i = 0; i + 1 < flat.length; i += 2) out.push([flat[i], flat[i + 1]]);
  return out;
}

function pointInPolygon(x, y, points) {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const [xi, yi] = points[i];
    const [xj, yj] = points[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

// The centre of mass of a polygon, or the mean of its corners if it has no area.
function polygonCentroid(points) {
  let area = 0;
  let cx = 0;
  let cy = 0;
  for (let i = 0; i < points.length; i++) {
    const [x0, y0] = points[i];
    const [x1, y1] = points[(i + 1) % points.length];
    const cross = x0 * y1 - x1 * y0;
    area += cross;
    cx += (x0 + x1) * cross;
    cy += (y0 + y1) * cross;
  }
  if (Math.abs(area) < 1e-9) {
    const n = points.length || 1;
    return [points.reduce((s, p) => s + p[0], 0) / n, points.reduce((s, p) => s + p[1], 0) / n];
  }
  return [cx / (3 * area), cy / (3 * area)];
}

// The box [x1, y1, x2, y2] around a list of points, or null.
function boxOf(points) {
  if (!points.length) return null;
  let [x1, y1] = points[0];
  let [x2, y2] = points[0];
  for (const [x, y] of points) {
    if (x < x1) x1 = x;
    if (x > x2) x2 = x;
    if (y < y1) y1 = y;
    if (y > y2) y2 = y;
  }
  return [x1, y1, x2, y2];
}

// === Helpers: colours ===

function hexRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function rgbHex(rgb) {
  return `#${rgb.map((c) => Math.max(0, Math.min(255, Math.round(c))).toString(16).padStart(2, "0")).join("")}`;
}

// The lawn colour of a zone and its outline, mixed towards the background
// by `shade` (0 keeps the colour).
function zoneColors(id, pal) {
  const base = hexRgb(ZONE_COLORS[(((id - 1) % ZONE_COLORS.length) + ZONE_COLORS.length) % ZONE_COLORS.length]);
  const bg = hexRgb(pal.background);
  const fill = base.map((c, i) => c + (bg[i] - c) * pal.lawnShade);
  return { fill: rgbHex(fill), outline: rgbHex(fill.map((c) => c - 10)) };
}

function batteryChargingIcon(level) {
  if (level === null || level === undefined) return "mdi:battery-charging";
  const step = Math.round(Math.max(0, Math.min(100, level)) / 10) * 10;
  return step <= 0 ? "mdi:battery-charging-outline" : `mdi:battery-charging-${step}`;
}

function batteryIcon(level) {
  if (level === null || level === undefined) return "mdi:battery-unknown";
  const step = Math.round(Math.max(0, Math.min(100, level)) / 10) * 10;
  if (step >= 100) return "mdi:battery";
  if (step <= 0) return "mdi:battery-outline";
  return `mdi:battery-${step}`;
}

// Distance from (x, y) to the segment from a to b, in map units.
function distanceToSegment(x, y, a, b) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len2 = dx * dx + dy * dy;
  const t = len2 ? Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / len2)) : 0;
  return Math.hypot(x - (a[0] + t * dx), y - (a[1] + t * dy));
}

// === Helpers: SVG snippets ===

function svgPoints(tf, points) {
  return points.map(([x, y]) => tf.toMap(x, y).map(num).join(",")).join(" ");
}

function svgPolygon(tf, points, attrs) {
  return `<polygon points="${svgPoints(tf, points)}" ${attrs}/>`;
}

function svgPolyline(tf, points, attrs) {
  return `<polyline points="${svgPoints(tf, points)}" fill="none" ${attrs}/>`;
}

// A trail of [x, y] points with null at its breaks, as one path.
function trailPath(tf, points) {
  let d = "";
  let pen = false;
  for (const point of points) {
    if (!point) {
      pen = false;
      continue;
    }
    const [X, Y] = tf.toMap(point[0], point[1]);
    d += `${pen ? "L" : "M"}${num(X)} ${num(Y)}`;
    pen = true;
  }
  return d;
}

// A zone's name centred on (X, Y); px is the size of one screen pixel in SVG
// units.
function svgZoneLabel(X, Y, name, px, pal) {
  if (!name) return "";
  return (
    `<text x="${num(X)}" y="${num(Y)}" font-size="${num(16 * px)}" fill="${pal.zoneName}" ` +
    `text-anchor="middle" dominant-baseline="central" pointer-events="none">${esc(name)}</text>`
  );
}

// The round toggle that picks a zone, spot or edge: grey with a white ring,
// or in the brand colour with a tick once picked.
function svgToggle(X, Y, px, on, pal) {
  const r = 11 * px;
  let out =
    `<circle cx="${num(X)}" cy="${num(Y)}" r="${num(r)}" fill="${on ? pal.brand : "rgba(128,128,128,.75)"}" ` +
    `stroke="#fff" stroke-width="${num(2 * px)}" pointer-events="none"/>`;
  if (on) {
    out +=
      `<path d="M${num(X - r * 0.45)} ${num(Y)}L${num(X - r * 0.1)} ${num(Y + r * 0.35)}L${num(X + r * 0.5)} ${num(Y - r * 0.35)}" ` +
      `fill="none" stroke="#fff" stroke-width="${num(2 * px)}" stroke-linecap="round" stroke-linejoin="round" pointer-events="none"/>`;
  }
  return out;
}

// The station in fractions of its length (along, the hood at +0.5) and width
// (across): a plate with cut corners, the ramp narrowing towards the entry, and
// the hood whose front edge bows out in the middle.
const STATION_PLATE = [[-0.5, -0.46], [-0.47, -0.5], [0.46, -0.5], [0.5, -0.45], [0.5, 0.45], [0.46, 0.5], [-0.47, 0.5], [-0.5, 0.46]];
const STATION_RAMP = [[-0.38, -0.09], [0.24, -0.17], [0.24, 0.17], [-0.38, 0.09]];
const STATION_HOOD = [
  [0.5, -0.34],
  [0.5, 0.34],
  [0.3, 0.42],
  ...[0.75, 0.5, 0.25, 0, -0.25, -0.5, -0.75].map((t) => [0.3 - 0.08 * (1 - t * t), 0.42 * t]),
  [0.3, -0.42],
];
// Where a docked mower stands on the station: its centre, in station lengths
// ahead of the station's centre, so that its front is under the hood.
const DOCKED_AT = 0.04;

// The charging station seen from above, (X, Y) its centre, its hood towards
// +X before it is turned by `angle` (clockwise on screen): a plate with a ramp
// down its middle and a rail on each side; the hood over its far end carries
// the light. A docked mower stands on the plate, its front under the hood,
// where the charging contacts are.
function svgStation(X, Y, scale, angle, light, pal, docked = false, look = "rwd") {
  const L = STATION_LENGTH * scale;
  const W = STATION_WIDTH * scale;
  const shape = (outline, attrs) => `<polygon points="${localPoints(L, W, outline)}" ${attrs}/>`;
  const edge = `stroke="${pal.mowerEdge}" stroke-width="${num(L * 0.006)}" stroke-linejoin="round"`;
  const rail = (side) => shape([[-0.12, side * 0.37], [0.12, side * 0.37], [0.12, side * 0.4], [-0.12, side * 0.4]], `fill="${pal.stationBody}"`);
  return (
    `<g transform="translate(${num(X)} ${num(Y)}) rotate(${num(angle)})" pointer-events="none">` +
    shape(STATION_PLATE, `fill="${pal.station}" ${edge}`) +
    shape(STATION_RAMP, `fill="${pal.stationBody}"`) +
    rail(-1) +
    rail(1) +
    (docked ? `<g transform="translate(${num(L * DOCKED_AT)} 0)" data-look="${look}">${mowerBody(scale, pal, look)}</g>` : "") +
    shape(STATION_HOOD, `fill="${pal.stationBody}" ${edge}`) +
    `<rect x="${num(L * (0.27 - 0.0125))}" y="${num(-W * 0.09)}" width="${num(L * 0.025)}" height="${num(W * 0.18)}" rx="${num(L * 0.0125)}" fill="${light}"/>` +
    `</g>`
  );
}

// The body of the mower seen from above, in fractions of its length (along,
// front at +0.5) and width (across): wide wings at the back, narrowing to a
// round front.
const MOWER_OUTLINE = (() => {
  const points = [[-0.42, -0.3]];
  const quad = (c, e, n = 8) => {
    const p = points[points.length - 1];
    for (let i = 1; i <= n; i++) {
      const t = i / n;
      points.push([0, 1].map((k) => (1 - t) ** 2 * p[k] + 2 * (1 - t) * t * c[k] + t * t * e[k]));
    }
  };
  const cubic = (c1, c2, e, n = 16) => {
    const p = points[points.length - 1];
    for (let i = 1; i <= n; i++) {
      const t = i / n;
      points.push([0, 1].map((k) => (1 - t) ** 3 * p[k] + 3 * (1 - t) ** 2 * t * c1[k] + 3 * (1 - t) * t * t * c2[k] + t ** 3 * e[k]));
    }
  };
  quad([-0.36, -0.3], [-0.34, -0.5]);
  points.push([0.05, -0.46]);
  cubic([0.35, -0.44], [0.5, -0.3], [0.5, 0]);
  cubic([0.5, 0.3], [0.35, 0.44], [0.05, 0.46]);
  points.push([-0.34, 0.5]);
  quad([-0.36, 0.3], [-0.42, 0.3]);
  return points;
})();

// Model families drawn with all-wheel drive (four wheel pods and a front
// bumper) instead of the two-wheel body; the status says which model the
// mower is. The A3 AWD Pro comes in sizes that share its body (the 3500 is
// dreame.mower.g2541e), told apart by the last letter of the model.
const AWD_MODEL_FAMILIES = ["dreame.mower.g2541"];

function mowerLook(model) {
  return AWD_MODEL_FAMILIES.some((family) => String(model || "").startsWith(family)) ? "awd" : "rwd";
}

// The all-wheel drive body seen from above, in the same fractions as
// MOWER_OUTLINE: a square back, straight sides, and shoulders that close in
// towards the front.
const AWD_OUTLINE = (() => {
  const points = [[-0.44, -0.3]];
  const quad = (c, e, n = 8) => {
    const p = points[points.length - 1];
    for (let i = 1; i <= n; i++) {
      const t = i / n;
      points.push([0, 1].map((k) => (1 - t) ** 2 * p[k] + 2 * (1 - t) * t * c[k] + t * t * e[k]));
    }
  };
  quad([-0.44, -0.38], [-0.36, -0.38]);
  points.push([0.22, -0.38]);
  quad([0.4, -0.38], [0.44, -0.2]);
  points.push([0.44, 0.2]);
  quad([0.4, 0.38], [0.22, 0.38]);
  points.push([-0.36, 0.38]);
  quad([-0.44, 0.38], [-0.44, 0.3]);
  return points;
})();

// `outline` in fractions of a shape `L` long and `W` wide, as SVG points.
function localPoints(L, W, outline) {
  return outline.map(([u, v]) => `${num(u * L)},${num(v * W)}`).join(" ");
}

// The mower seen from above in local coordinates, its front towards +X: the
// rear wheels and the back show behind a light body carrying the red stop
// button, the dark lid with the light in front of it, and the camera at the
// front.
function mowerBody(scale, pal, look = "rwd") {
  if (look === "awd") return mowerBodyAwd(scale, pal);
  const L = MOWER_LENGTH * scale;
  const W = MOWER_WIDTH * scale;
  return (
    `<rect x="${num(-L / 2)}" y="${num(-W * 0.48)}" width="${num(L * 0.3)}" height="${num(W * 0.96)}" rx="${num(W * 0.1)}" fill="#2b2b2b"/>` +
    `<polygon points="${localPoints(L, W, MOWER_OUTLINE)}" fill="${pal.mowerBody}" stroke="${pal.mowerEdge}" stroke-width="${num(L * 0.01)}" stroke-linejoin="round"/>` +
    `<path d="M0 ${num(-W * 0.24)}H${num(L * 0.1)}Q${num(L * 0.2)} ${num(-W * 0.24)} ${num(L * 0.2)} 0Q${num(L * 0.2)} ${num(W * 0.24)} ${num(L * 0.1)} ${num(W * 0.24)}H0" ` +
    `fill="none" stroke="#52C3FF" stroke-width="${num(W * 0.035)}" stroke-linecap="round"/>` +
    `<rect x="${num(-L * 0.18)}" y="${num(-W * 0.23)}" width="${num(L * 0.32)}" height="${num(W * 0.46)}" rx="${num(W * 0.08)}" fill="${pal.mowerTop}"/>` +
    `<rect x="${num(-L * 0.31)}" y="${num(-W * 0.22)}" width="${num(L * 0.12)}" height="${num(W * 0.44)}" rx="${num(W * 0.04)}" fill="#E8433E"/>` +
    `<circle cx="${num(L * 0.36)}" r="${num(W * 0.06)}" fill="#2f2f2f" stroke="#d0d0d0" stroke-width="${num(W * 0.02)}"/>`
  );
}

// The all-wheel drive mower (A3 AWD Pro) seen from above, its front towards
// +X: a wheel pod at each corner standing out of the body, the black bumper
// across the front with the twin cameras behind it, and on the light body the
// dark lid with the LiDAR dome at its centre and the red strip behind it.
function mowerBodyAwd(scale, pal) {
  const L = MOWER_LENGTH * scale;
  const W = MOWER_WIDTH * scale;
  const rect = (u0, u1, v0, v1, attrs) =>
    `<rect x="${num(u0 * L)}" y="${num(v0 * W)}" width="${num((u1 - u0) * L)}" height="${num((v1 - v0) * W)}" ${attrs}/>`;
  const wheel = (u0, side) => {
    const [v0, v1] = side < 0 ? [-0.52, -0.33] : [0.33, 0.52];
    let tread = "";
    for (let i = 1; i < 5; i++) {
      const u = u0 + (0.26 * i) / 5;
      tread += `<line x1="${num(u * L)}" y1="${num(v0 * W)}" x2="${num(u * L)}" y2="${num(v1 * W)}" stroke="#3d3d3d" stroke-width="${num(L * 0.012)}"/>`;
    }
    return rect(u0, u0 + 0.26, v0, v1, `rx="${num(W * 0.05)}" fill="#1f1f1f"`) + tread;
  };
  return (
    wheel(0.18, -1) + wheel(0.18, 1) + wheel(-0.46, -1) + wheel(-0.46, 1) +
    `<polygon points="${localPoints(L, W, AWD_OUTLINE)}" fill="${pal.mowerBody}" stroke="${pal.mowerEdge}" stroke-width="${num(L * 0.01)}" stroke-linejoin="round"/>` +
    rect(0.32, 0.45, -0.2, 0.2, `rx="${num(W * 0.04)}" fill="#2b2b2b"`) +
    `<circle cx="${num(L * 0.41)}" cy="${num(-W * 0.08)}" r="${num(W * 0.03)}" fill="#111" stroke="#8c8c8c" stroke-width="${num(W * 0.01)}"/>` +
    `<circle cx="${num(L * 0.41)}" cy="${num(W * 0.08)}" r="${num(W * 0.03)}" fill="#111" stroke="#8c8c8c" stroke-width="${num(W * 0.01)}"/>` +
    rect(0.45, 0.53, -0.52, 0.52, `rx="${num(L * 0.02)}" fill="#222"`) +
    rect(0.47, 0.51, 0.3, 0.42, `fill="#E8433E"`) +
    rect(-0.24, 0.26, -0.22, 0.22, `rx="${num(W * 0.08)}" fill="${pal.mowerTop}"`) +
    rect(-0.31, -0.26, -0.17, 0.17, `rx="${num(W * 0.02)}" fill="#E8433E"`) +
    `<circle cx="${num(L * 0.02)}" r="${num(W * 0.085)}" fill="#1a1a1a" stroke="#6a6a6a" stroke-width="${num(W * 0.015)}"/>` +
    `<circle cx="${num(L * 0.02)}" r="${num(W * 0.03)}" fill="#444"/>`
  );
}

// The mower out on the lawn, (X, Y) its centre, turned by `angle`
// (clockwise on screen); a red mark ahead of it shows where it heads.
function svgMower(X, Y, scale, angle, pal, look = "rwd") {
  const L = MOWER_LENGTH * scale;
  const W = MOWER_WIDTH * scale;
  const tip = L * 0.5 + W * 0.32;
  return (
    `<g transform="translate(${num(X)} ${num(Y)}) rotate(${num(angle)})" pointer-events="none" data-look="${look}">` +
    mowerBody(scale, pal, look) +
    `<path d="M${num(tip)} 0L${num(L * 0.5 + W * 0.1)} ${num(-W * 0.14)}V${num(W * 0.14)}Z" fill="#EE3C2F"/>` +
    `</g>`
  );
}

// What the camera recognised an obstacle as, by its type: the name, and the
// pictogram on its pin, drawn in white within -1..1.
const AI_OBSTACLE_KINDS = {
  0: { label: "Person", glyph: '<circle cx=".2" cy="-.7" r=".22" fill="#fff" stroke="none"/><path d="M.1-.4L-.1.2L-.45.75M-.1.2L.25.4L.35.8M-.4-.05L-.05-.3L.35.05"/>' },
  1: { label: "Cat", glyph: "paw" },
  2: { label: "Dog", glyph: "paw" },
  3: { label: "Hedgehog", glyph: '<path d="M-.8.45Q-.7-.45.2-.4Q.6-.35.8.3L.85.45Z M-.5-.1L-.65-.4M-.15-.35L-.2-.7M.25-.38L.35-.72M.55-.15L.8-.4"/>' },
  4: { label: "Hose", glyph: '<path d="M-.8.5C-.4-.6.1.9.45-.2C.6-.6.8-.5.8-.5"/>' },
  5: { label: "Sprinkler", glyph: '<path d="M0-.75C.45-.15.4.4 0 .4C-.4.4-.45-.15 0-.75Z M-.35.8H.35"/>' },
  6: { label: "Dog waste", glyph: '<path d="M-.7.65H.7Q.75.2.35.15Q.5-.25.1-.3Q.25-.75-.1-.75Q0-.4-.35-.3Q-.6-.2-.4.15Q-.8.25-.7.65Z"/>' },
  7: { label: "Ball", glyph: '<circle r=".72"/><path d="M-.55-.45C-.1-.2-.1.2-.55.45M.55-.45C.1-.2.1.2.55.45"/>' },
};
const PAW_GLYPH =
  '<g fill="#fff" stroke="none"><ellipse cy=".35" rx=".42" ry=".34"/><circle cx="-.55" cy="-.1" r=".17"/>' +
  '<circle cx="-.22" cy="-.48" r=".18"/><circle cx=".22" cy="-.48" r=".18"/><circle cx=".55" cy="-.1" r=".17"/></g>';
const OTHER_GLYPH = '<circle cx="-.45" r=".13" fill="#fff" stroke="none"/><circle r=".13" fill="#fff" stroke="none"/><circle cx=".45" r=".13" fill="#fff" stroke="none"/>';
// The cone of an obstacle the mower ran into or saw with its LiDAR.
const CONE_GLYPH = '<path d="M-.35-1H.35L.75.55H-.75Z M-1 .8H1"/>';

// What tells an obstacle apart: for one the camera recognised its photo, or
// where it is and what; for one the mower ran into its id.
function obstacleKey(obstacle) {
  if (obstacle.kind !== "ai") return `obstacle:${obstacle.id}`;
  return obstacle.image || `${obstacle.x},${obstacle.y},${obstacle.type}`;
}

// A no-go rectangle around an obstacle, [x0, y0, x1, y1] in mm: its outline
// with some room around it, at least as large as the mower takes one.
function obstacleNoGoRect(obstacle) {
  const box = obstacle.bounds || (obstacle.polygon && boxOf(pairs(obstacle.polygon))) || [obstacle.x, obstacle.y, obstacle.x, obstacle.y];
  const [min, max] = EDIT_LIMITS.rectangle;
  const side = (lo, hi) => {
    const centre = (lo + hi) / 2;
    const half = Math.min(max, Math.max(min, hi - lo + 2 * OBSTACLE_NO_GO_MARGIN_MM)) / 2;
    return [Math.round(centre - half), Math.round(centre + half)];
  };
  const [x0, x1] = side(box[0], box[2]);
  const [y0, y1] = side(box[1], box[3]);
  return [x0, y0, x1, y1];
}

function aiObstacleKind(type) {
  return AI_OBSTACLE_KINDS[type] || { label: "Obstacle", glyph: OTHER_GLYPH };
}

// A map pin over (X, Y) marking an obstacle: a cone for one the mower ran
// into or saw, and what it is for one the camera recognised. A pin with a
// `key` opens the obstacle's sheet when tapped.
function svgObstaclePin(X, Y, px, pal, obstacle = null, key = null) {
  const r = 10 * px;
  const cy = Y - 18 * px;
  const scale = 5.5 * px;
  let glyph = CONE_GLYPH;
  if (obstacle && obstacle.kind === "ai") {
    glyph = aiObstacleKind(obstacle.type).glyph;
    if (glyph === "paw") glyph = PAW_GLYPH;
  }
  const open = key === null ? 'pointer-events="none"' : `data-obstacle="${esc(key)}" pointer-events="all" style="cursor:pointer"`;
  return (
    `<g ${open}>` +
    `<path d="M${num(X)} ${num(Y)}L${num(X - r * 0.6)} ${num(cy + r * 0.75)}A${num(r)} ${num(r)} 0 1 1 ${num(X + r * 0.6)} ${num(cy + r * 0.75)}Z" ` +
    `fill="${pal.obstacle}" stroke="#fff" stroke-width="${num(2 * px)}"/>` +
    `<g transform="translate(${num(X)} ${num(cy)}) scale(${num(scale)})" fill="none" stroke="#fff" stroke-width=".3" ` +
    `stroke-linejoin="round" stroke-linecap="round">${glyph}</g></g>`
  );
}

// === Helpers: map editor ===

// The four corners of a rectangle [x0, y0, x1, y1].
function rectPoints(r) {
  return [[r[0], r[1]], [r[2], r[1]], [r[2], r[3]], [r[0], r[3]]];
}

// Which way a maintenance point faces: an arrowhead off its pin. The heading
// counts degrees from the map's x axis, turning towards its y axis.
function svgFacing(tf, point, heading, color, px) {
  const [X, Y] = tf.toMap(point[0], point[1]);
  const radians = (heading * Math.PI) / 180;
  const [AX, AY] = tf.toMap(point[0] + Math.cos(radians) * 1000, point[1] + Math.sin(radians) * 1000);
  const length = Math.hypot(AX - X, AY - Y) || 1;
  const [ux, uy] = [(AX - X) / length, (AY - Y) / length];
  const tip = 19 * px;
  const base = 10 * px;
  const half = 6 * px;
  const at = (along, across) => `${num(X + ux * along - uy * across)} ${num(Y + uy * along + ux * across)}`;
  return `<path d="M${at(tip, 0)}L${at(base, half)}L${at(base, -half)}Z" fill="${color}" stroke="#fff" stroke-width="${num(1.5 * px)}" stroke-linejoin="round"/>`;
}

// The size of a shape: width × height, length or width across; "" for
// one without a size of its own.
function editSizeText(item) {
  const m = (mm) => `${(mm / 1000).toFixed(1)} m`;
  if (item.shape === "rectangle") return `${m(Math.abs(item.rect[2] - item.rect[0]))} × ${m(Math.abs(item.rect[3] - item.rect[1]))}`;
  if (item.shape === "line") return m(Math.hypot(item.line[2] - item.line[0], item.line[3] - item.line[1]));
  if (item.shape === "circle") return `⌀ ${m(2 * item.circle[2])}`;
  return "";
}

// The part of an item that changes when it is edited.
function editGeometry(item) {
  if (item.shape === "rectangle") return { rect: item.rect };
  if (item.shape === "line") return { line: item.line };
  if (item.shape === "circle") return { circle: item.circle };
  if (item.shape === "point") return { point: item.point };
  return {};
}

function editShapeKey(item) {
  const round = (values) => (values || []).map((v) => Math.round(v));
  const g = editGeometry(item);
  // A maintenance point also changes when it is turned.
  if (item.shape === "point" && item.heading !== null && item.heading !== undefined) g.heading = [item.heading];
  return JSON.stringify(Object.fromEntries(Object.entries(g).map(([k, v]) => [k, round(v)])));
}

function editSize(item) {
  if (item.shape === "rectangle") return Math.min(Math.abs(item.rect[2] - item.rect[0]), Math.abs(item.rect[3] - item.rect[1]));
  if (item.shape === "line") return Math.hypot(item.line[2] - item.line[0], item.line[3] - item.line[1]);
  if (item.shape === "circle") return 2 * item.circle[2];
  if (item.shape === "point") return 0;
  const box = boxOf(pairs(item.polygon || []));
  return box ? Math.min(box[2] - box[0], box[3] - box[1]) : 0;
}

function editNormalise(item) {
  if (item.shape === "rectangle") {
    const [x0, y0, x1, y1] = item.rect;
    item.rect = [Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1)].map((v) => Math.round(v));
  }
  if (item.line) item.line = item.line.map((v) => Math.round(v));
  if (item.circle) item.circle = item.circle.map((v) => Math.round(v));
  if (item.point) item.point = item.point.map((v) => Math.round(v));
}

// Whether a point lies on an item, `tol` around it.
function editHit(item, p, tol) {
  if (item.shape === "point") return Math.hypot(item.point[0] - p[0], item.point[1] - p[1]) <= 2 * tol;
  if (item.shape === "line") return distanceToSegment(p[0], p[1], item.line.slice(0, 2), item.line.slice(2)) <= tol;
  if (item.shape === "circle") return Math.hypot(item.circle[0] - p[0], item.circle[1] - p[1]) <= item.circle[2] + tol;
  const points = item.shape === "rectangle" ? rectPoints(item.rect) : pairs(item.polygon || []);
  return points.length >= 3 && pointInPolygon(p[0], p[1], points);
}

// The handles of an item: corners, ends, or the edge of a circle.
function editHandles(item) {
  if (item.shape === "rectangle") return rectPoints(item.rect).map((at, i) => ({ id: `c${i}`, at }));
  if (item.shape === "line") return [{ id: "e0", at: item.line.slice(0, 2) }, { id: "e1", at: item.line.slice(2) }];
  if (item.shape === "circle") return [{ id: "r", at: [item.circle[0] + item.circle[2], item.circle[1]] }];
  return [];
}

function editMoved(from, dx, dy) {
  if (from.rect) return { rect: [from.rect[0] + dx, from.rect[1] + dy, from.rect[2] + dx, from.rect[3] + dy] };
  if (from.line) return { line: [from.line[0] + dx, from.line[1] + dy, from.line[2] + dx, from.line[3] + dy] };
  if (from.circle) return { circle: [from.circle[0] + dx, from.circle[1] + dy, from.circle[2]] };
  if (from.point) return { point: [from.point[0] + dx, from.point[1] + dy] };
  return {};
}

// A handle dragged to p: the opposite corner of a rectangle stays put, and
// held on one axis (Shift) only the side the drag follows most changes.
// Sizes stay within what the mower takes.
function editHandleMoved(from, handle, p, oneAxis, limits) {
  if (from.rect) {
    const corners = rectPoints(from.rect);
    const index = Number(handle.slice(1));
    const fixed = corners[(index + 2) % 4];
    const grabbed = corners[index];
    const side = (axis) => limitSide(fixed[axis], p[axis], limits, Math.sign(grabbed[axis] - fixed[axis]) || 1);
    if (oneAxis) {
      // Only the side the drag follows most changes; the other stays as it was.
      const alongX = Math.abs(p[0] - grabbed[0]) >= Math.abs(p[1] - grabbed[1]);
      return { rect: alongX ? [fixed[0], fixed[1], side(0), grabbed[1]] : [fixed[0], fixed[1], grabbed[0], side(1)] };
    }
    return { rect: [fixed[0], fixed[1], side(0), side(1)] };
  }
  if (from.line) {
    const fixed = handle === "e0" ? from.line.slice(2) : from.line.slice(0, 2);
    let to = oneAxis ? straighten(fixed, p) : p;
    const length = Math.hypot(to[0] - fixed[0], to[1] - fixed[1]) || 1;
    const f = clampSize(length, limits) / length;
    to = [fixed[0] + (to[0] - fixed[0]) * f, fixed[1] + (to[1] - fixed[1]) * f];
    return { line: handle === "e0" ? [to[0], to[1], fixed[0], fixed[1]] : [fixed[0], fixed[1], to[0], to[1]] };
  }
  if (from.circle) {
    const radius = Math.hypot(p[0] - from.circle[0], p[1] - from.circle[1]);
    return { circle: [from.circle[0], from.circle[1], clampSize(2 * radius, limits) / 2] };
  }
  return {};
}

// The smallest and largest size the mower takes for an item.
function editLimits(item) {
  if (item.shape === "line") return EDIT_LIMITS.line;
  if (item.shape === "circle") return EDIT_LIMITS.circle;
  return item.kind === "spot" ? EDIT_LIMITS.spot : EDIT_LIMITS.rectangle;
}

const clampSize = (size, [min, max]) => Math.max(min, Math.min(max, size));

// A side from `from` towards `to`, as long as the mower takes it.
function limitSide(from, to, limits, fallback = 1) {
  const sign = Math.sign(to - from) || fallback;
  return from + sign * clampSize(Math.abs(to - from), limits);
}

// A rectangle from a fixed corner towards p, each side within the limits.
function editLimitRect(fixed, p, limits) {
  return [fixed[0], fixed[1], limitSide(fixed[0], p[0], limits), limitSide(fixed[1], p[1], limits)];
}

// A line from a fixed end towards p, its length within the limits.
function editLimitLine(fixed, p, limits) {
  const length = Math.hypot(p[0] - fixed[0], p[1] - fixed[1]);
  if (!length) return [fixed[0], fixed[1], fixed[0] + limits[0], fixed[1]];
  const f = clampSize(length, limits) / length;
  return [fixed[0], fixed[1], fixed[0] + (p[0] - fixed[0]) * f, fixed[1] + (p[1] - fixed[1]) * f];
}

// p kept on the horizontal or vertical through `from`, whichever is closer.
function straighten(from, p) {
  return Math.abs(p[0] - from[0]) >= Math.abs(p[1] - from[1]) ? [p[0], from[1]] : [from[0], p[1]];
}

// p moved so the rectangle from `from` to it is a square.
function squared(from, p) {
  const size = Math.max(Math.abs(p[0] - from[0]), Math.abs(p[1] - from[1]));
  return [from[0] + Math.sign(p[0] - from[0] || 1) * size, from[1] + Math.sign(p[1] - from[1] || 1) * size];
}

// The action and data that put an item on the map as it is drawn.
function editServiceCall(item) {
  const existing = item.id !== null;
  const round = (values) => values.map((v) => Math.round(v));
  if (item.kind === "no_go") {
    const data = { shape: item.shape };
    if (item.shape === "rectangle") data.points = [round(item.rect.slice(0, 2)), round(item.rect.slice(2))];
    if (item.shape === "line") data.points = [round(item.line.slice(0, 2)), round(item.line.slice(2))];
    if (item.shape === "circle") {
      data.points = [round(item.circle.slice(0, 2))];
      data.radius = Math.round(item.circle[2]);
    }
    if (existing) data.zone_id = item.id;
    return ["set_no_go_zone", data];
  }
  if (item.kind === "maintenance") {
    const data = { x: Math.round(item.point[0]), y: Math.round(item.point[1]) };
    if (item.heading !== null && item.heading !== undefined) data.heading = Math.round(item.heading) % 360;
    if (existing) data.point_id = item.id;
    return ["set_maintenance_point", data];
  }
  const data = { rect: round(item.rect) };
  if (existing) data.area_id = item.id;
  return [item.kind === "spot" ? "set_spot_area" : "set_ignore_obstacle_area", data];
}

// === Helpers: pan and zoom of a small map ===

// Rescales what a zoomable picture marks with data-keep around its anchor, as
// the view is zoomed by `zoom` against the whole picture: a pin keeps its size
// on screen, a station its real size but no less than its least one on screen.
function keepScreenSize(svg, zoom) {
  for (const group of svg.querySelectorAll("[data-keep]")) {
    const x = Number(group.dataset.x);
    const y = Number(group.dataset.y);
    let factor = zoom;
    if (group.dataset.keep === "station") {
      const scale = Number(group.dataset.scale);
      factor = Math.max(MOWER_SCALE, Number(group.dataset.least) * zoom) / scale;
    }
    group.setAttribute("transform", `translate(${num(x)} ${num(y)}) scale(${factor.toFixed(4)}) translate(${num(-x)} ${num(-y)})`);
  }
}

// Lets an SVG be dragged, pinched or wheeled to move and zoom its view, and
// fits it again on a double tap; `onTap` hears of every single tap.
class PanZoom {
  // `onView` hears how far the view is zoomed against the whole picture (1:
  // not zoomed, below 1: zoomed in) each time it changes.
  constructor(svg, onTap = null, onView = null) {
    this.svg = svg;
    this.onTap = onTap;
    this.onView = onView;
    const [x, y, w, h] = svg.getAttribute("viewBox").split(" ").map(Number);
    this.home = { x, y, w, h };
    this.vb = { ...this.home };
    this.pointers = new Map();
    this.start = null;
    this.lastTap = 0;
    svg.addEventListener("pointerdown", (e) => this._down(e));
    svg.addEventListener("pointermove", (e) => this._move(e));
    svg.addEventListener("pointerup", (e) => this._up(e));
    svg.addEventListener("pointercancel", (e) => this._up(e));
    svg.addEventListener("wheel", (e) => this._wheel(e), { passive: false });
  }

  // SVG units per screen pixel, and where the view starts on screen.
  _metrics() {
    const rect = this.svg.getBoundingClientRect();
    const unit = Math.max(this.vb.w / rect.width, this.vb.h / rect.height);
    return {
      rect,
      unit,
      left: rect.left + (rect.width - this.vb.w / unit) / 2,
      top: rect.top + (rect.height - this.vb.h / unit) / 2,
    };
  }

  _apply() {
    const vb = this.vb;
    this.svg.setAttribute("viewBox", `${num(vb.x)} ${num(vb.y)} ${num(vb.w)} ${num(vb.h)}`);
    if (this.onView) this.onView(vb.w / this.home.w);
  }

  // Zooms by `factor` keeping the point under (cx, cy) on screen in place.
  _zoom(factor, cx, cy) {
    const m = this._metrics();
    const w = Math.max(this.home.w / 20, Math.min(this.home.w * 2, this.vb.w / factor));
    const scale = w / this.vb.w;
    const px = this.vb.x + (cx - m.left) * m.unit;
    const py = this.vb.y + (cy - m.top) * m.unit;
    this.vb = { x: px - (px - this.vb.x) * scale, y: py - (py - this.vb.y) * scale, w, h: this.vb.h * scale };
    this._apply();
  }

  _down(e) {
    this.svg.setPointerCapture(e.pointerId);
    this.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    this.start = this._gesture();
  }

  // What the fingers do now: one moves the view, two zoom it.
  _gesture() {
    const points = [...this.pointers.values()];
    if (!points.length) return null;
    const cx = points.reduce((sum, p) => sum + p.x, 0) / points.length;
    const cy = points.reduce((sum, p) => sum + p.y, 0) / points.length;
    const spread = points.length > 1 ? Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y) : 0;
    return { cx, cy, spread, vb: { ...this.vb }, unit: this._metrics().unit, count: points.length, moved: false };
  }

  _move(e) {
    if (!this.pointers.has(e.pointerId) || !this.start) return;
    this.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const now = this._gesture();
    const start = this.start;
    if (Math.hypot(now.cx - start.cx, now.cy - start.cy) > 4 || now.count > 1) start.moved = true;
    this.vb = { ...start.vb, x: start.vb.x - (now.cx - start.cx) * start.unit, y: start.vb.y - (now.cy - start.cy) * start.unit };
    this._apply();
    if (now.count > 1 && start.spread) this._zoom(now.spread / start.spread, now.cx, now.cy);
  }

  _up(e) {
    if (!this.pointers.has(e.pointerId)) return;
    const start = this.start;
    this.pointers.delete(e.pointerId);
    this.start = this._gesture();
    // The finger left after a pinch only ends it.
    if (this.start && start && (start.moved || start.count > 1)) this.start.moved = true;
    if (start && !start.moved && start.count === 1) {
      if (this.onTap) this.onTap(e);
      const now = Date.now();
      if (now - this.lastTap < DOUBLE_TAP_MS) {
        this.vb = { ...this.home };
        this._apply();
        this.lastTap = 0;
      } else {
        this.lastTap = now;
      }
    }
  }

  _wheel(e) {
    e.preventDefault();
    this._zoom(Math.exp(-e.deltaY * 0.002), e.clientX, e.clientY);
  }

  // Zooms by `factor` about the middle of the view.
  zoomBy(factor) {
    const rect = this.svg.getBoundingClientRect();
    this._zoom(factor, rect.left + rect.width / 2, rect.top + rect.height / 2);
  }

  // Shows the whole picture again.
  fit() {
    this.vb = { ...this.home };
    this._apply();
  }
}

// === Card element ===

let instanceCounter = 0;

// What the main button mows: the whole map, or the edges, zones or spots
// picked on it.
const MODES = [
  { id: "all", label: "All", icon: "mdi:select-all" },
  { id: "edges", label: "Edges", glyph: "edges", kind: "edges", noun: "edges", one: "edge" },
  { id: "zones", label: "Zones", icon: "mdi:floor-plan", kind: "zones", noun: "zones", one: "zone" },
  { id: "spots", label: "Spots", icon: "mdi:crosshairs-gps", kind: "spots", noun: "spot areas", one: "spot" },
];

// The card's tabs.
const TABS = [
  { id: "mow", label: "Mow", icon: "mdi:robot-mower-outline" },
  { id: "history", label: "History", icon: "mdi:history" },
  { id: "schedules", label: "Schedules", icon: "mdi:calendar-month-outline" },
  { id: "settings", label: "Settings", icon: "mdi:cog-outline" },
];

/*
 * Sections other modules add to the card with
 * DreameMowerCard.registerSection({ id, create(host) }): to the Schedules
 * tab, above the mower's schedules, and to the Mow tab's map.
 * create() gets what the card shares with a section (see _sectionHost) and
 * returns an object with any of:
 *   connect(), disconnect(), resubscribe(), dropped(), reset()
 *       follow the card's feed: subscribe, stop, the websocket reconnected,
 *       the socket went away, the card shows another mower
 *   render()     "" | html above the schedules | { head, body }, a page of
 *                its own filling the tab
 *   rendered()   after the tab's markup is in place
 *   handleEvent(e)  click, change, input and value-changed in the tab
 *   back()       the tab was tapped again
 *   leave()      the tab is left; false keeps it open
 *   beforeDrive(action)  "start", "recharge", "maintenance" or "continue"
 *                (an error cleared) is about to make the mower drive; may
 *                wait (a gate opening on its way) and returns false, or a
 *                promise of false, to call it off; throwing calls it off too
 *   mapLayer(view)  SVG drawn over the map; view holds px (map units per
 *                screen pixel), pal (the colours), docked and station
 *                ({ x, y, angle, length } on the map, or null)
 *   mapButtons()  html of buttons under the map's zoom buttons on the Mow
 *                tab; their clicks go to the section's handleEvent(e)
 *   cover()      an element shown in place of the map on the Mow tab, or
 *                null for the map; the section keeps it, so what it holds
 *                (a player, say) survives the card's redraws
 *   update()     Home Assistant's state changed
 */
const SECTION_TYPES = [];
// Cards on the page, to set up sections registered after them.
const LIVE_CARDS = new Set();

// How far one tap on the map's + or − button zooms.
const ZOOM_STEP = 1.5;

// Line icons the icon font lacks: an edge around a lawn, a cutting height, a
// mowing direction and edges mowed after a task.
const glyph = (paths) =>
  `<svg class="glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
const GLYPHS = {
  edges: glyph('<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><rect x="8" y="8" width="8" height="8" rx="1.5" stroke-dasharray="2 2"/>'),
  height: glyph('<path d="M12 4v16M8.5 7.5L12 4l3.5 3.5M8.5 16.5L12 20l3.5-3.5M4 20h16"/>'),
  angle: glyph('<path d="M4 20L20 4M4 14L10 20M4 8L16 20M4 20h16"/>'),
  border: glyph('<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 12h3M17 12h3M12 4v3M12 17v3" stroke-dasharray="1.5 1.5"/>'),
};

// How close to an edge a tap has to land to pick it, in screen pixels.
const EDGE_HIT_PX = 18;

// The consumables, what their reset button says and what it asks.
const CONSUMABLES = {
  blade: { label: "Blades", icon: "mdi:saw-blade", done: "Replaced", confirm: "Have the blades been replaced?" },
  brush: { label: "Station cleaning brush", icon: "mdi:brush", done: "Replaced", confirm: "Has the station's cleaning brush been replaced?" },
  robot: { label: "Mower maintenance", icon: "mdi:wrench-outline", done: "Done", confirm: "Has the mower been serviced?" },
};

// The map editor's button: a pin over a folded map.
const EDIT_MAP_ICON =
  '<svg class="glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M12 2.6a4.4 4.4 0 0 0-4.4 4.4c0 3.1 4.4 7.2 4.4 7.2s4.4-4.1 4.4-7.2A4.4 4.4 0 0 0 12 2.6z"/><circle cx="12" cy="7" r="1.5"/>' +
  '<path d="M7.6 12.4H5.2L2.6 21.4h18.8l-2.6-9h-2.4"/><path d="M3.9 16.9l5.6 1.9 5-3.2 5.6 2.1"/><path d="M9.5 18.8l-.9 2.6M14.5 15.6l1.1 5.8"/></svg>';

// The tools of the map editor: what a drag on the map draws. All of them
// change the map only; the mower stays where it is.
const EDIT_TOOLS = [
  { id: "no_go", label: "No-go", icon: "mdi:cancel", kind: "no_go", shape: "rectangle", hint: "Drag on the map to draw a no-go zone." },
  { id: "no_go_line", label: "Line", icon: "mdi:vector-line", kind: "no_go", shape: "line", hint: "Drag on the map to draw a line the mower does not cross." },
  { id: "no_go_circle", label: "Circle", icon: "mdi:circle-outline", kind: "no_go", shape: "circle", hint: "Drag from the centre to draw a round no-go zone." },
  { id: "ignore", label: "Ignore", icon: "mdi:shield-off-outline", kind: "ignore", shape: "rectangle", hint: "Drag to draw an area where the mower drives over low obstacles, relying on its bumper." },
  { id: "spot", label: "Spot", icon: "mdi:selection", kind: "spot", shape: "rectangle", hint: "Drag to draw a spot area; it has to lie within one zone." },
  { id: "maintenance", label: "Point", icon: "mdi:wrench-outline", kind: "maintenance", shape: "point", hint: "Tap the map to place a maintenance point." },
  { id: "zones", label: "Zones", icon: "mdi:vector-polygon", hint: "Tap a zone to rename or split it, or two neighbouring zones to merge them." },
];
// Map item kinds as the map actions name them.
const EDIT_KIND_NAMES = { no_go: "no_go_zone", ignore: "ignore_obstacle_area", spot: "spot_area", maintenance: "maintenance_point" };
const EDIT_KIND_LABELS = { no_go: "No-go zone", ignore: "Ignore-obstacles area", spot: "Spot area", maintenance: "Maintenance point" };
// A drag shorter than this (mm) is a slip, not a shape.
const EDIT_MIN_MM = 200;
// The sizes the mower takes, in mm: each side of a rectangle, the length of
// a line, the width of a circle.
const EDIT_LIMITS = {
  rectangle: [1000, 20000],
  spot: [1000, 10000],
  line: [1000, 200000],
  circle: [1000, 20000],
};
// The room a no-go zone made from an obstacle leaves around it, in mm.
const OBSTACLE_NO_GO_MARGIN_MM = 300;
// How close to a handle or a line a press has to land, in screen pixels.
const EDIT_HIT_PX = 14;

class DreameMowerCard extends HTMLElement {
  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (id) => id.startsWith("lawn_mower.") && hass.states[id].attributes.device_class === DOMAIN,
    );
    return { entity: entity || Object.keys(hass.states).find((id) => id.startsWith("lawn_mower.")) || "lawn_mower." };
  }

  static async getConfigElement() {
    await loadEntityPicker();
    return document.createElement(EDITOR_TYPE);
  }

  // Adds a section to every card, those already on the page included.
  static registerSection(type) {
    if (!type || typeof type.id !== "string" || typeof type.create !== "function") return;
    if (SECTION_TYPES.some((t) => t.id === type.id)) return;
    SECTION_TYPES.push(type);
    for (const card of LIVE_CARDS) {
      card._syncSections();
      card._ensureSubscribed();
      card._invalidate("schedules");
    }
  }

  constructor() {
    super();
    this._uid = ++instanceCounter;
    this._config = null;
    this._hass = null;
    this._stateObj = null;
    this._geometry = null;
    this._status = null;
    this._trail = [];
    this._tf = null;
    this._tfKey = null;
    this._shapes = { edges: [], zones: [], spots: [] };
    this._fit = null;
    this._vb = null;
    this._viewTouched = false;
    this._mode = "all";
    this._selected = { edges: new Set(), zones: new Set(), spots: new Set() };
    this._tab = "mow";
    this._picker = false;
    this._busy = false;
    this._settings = null;
    this._log = null;
    this._photo = null;
    this._edit = null;
    this._mapList = null;
    this._maint = null;
    this._sections = [];
    this._syncSections();
    // Subscription
    this._sub = null;
    this._retry = 0;
    this._retryTimer = null;
    this._connection = null;
    this._feedError = null;
    // Rendering
    this._dirty = new Set();
    this._raf = null;
    this._html = {};
    // Pointers
    this._pointers = new Map();
    this._gesture = null;
    this._lastTap = null;
    this._toastTimer = null;
    this._onReady = () => this._resubscribeNow();
    // The socket went away: its subscription ids mean nothing on the next
    // socket, so the old subscription is dropped without unsubscribing.
    this._onDisconnected = () => {
      this._sub = null;
      this._eachSection("dropped");
    };
  }

  // --- Configuration ---

  setConfig(config) {
    if (!config || typeof config.entity !== "string" || !config.entity.startsWith("lawn_mower.")) {
      throw new Error("Set 'entity' to the lawn mower entity of the Dreame Mower integration");
    }
    const previous = this._config;
    this._config = { show_header: true, show_controls: true, show_trail: true, theme: "auto", ...config };
    this._renderedTheme = this._theme();
    if (previous && previous.entity !== config.entity) {
      this._unsubscribe();
      this._clearRetry();
      this._retry = 0;
      this._geometry = null;
      this._status = null;
      this._trail = [];
      this._tf = null;
      this._tfKey = null;
      this._viewTouched = false;
      this._clearSelection();
      this._log = null;
      this._photo = null;
      this._edit = null;
      this._mapList = null;
      this._picker = false;
      this._tab = "mow";
      this._maint = null;
      this._eachSection("reset");
    }
    this._ensureSubscribed();
    this._invalidate("all");
  }

  getCardSize() {
    return 12;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  set hass(hass) {
    this._hass = hass;
    const theme = this._config ? this._theme() : null;
    if (theme !== this._renderedTheme) {
      this._renderedTheme = theme;
      this._invalidate("all");
    }
    const stateObj = this._config ? hass.states[this._config.entity] : undefined;
    if (stateObj !== this._stateObj) {
      this._stateObj = stateObj;
      this._invalidate("header", "toolbar", "actions", "dyn", "picker", "photo");
    }
    // The settings and the schedules show other entities of the mower, which
    // change on their own.
    if (this._maint) this._invalidate("maint");
    if (this._tab === "schedules") this._invalidate("schedules");
    this._eachSection("update");
    this._ensureSubscribed();
  }

  // --- Lifecycle ---

  connectedCallback() {
    LIVE_CARDS.add(this);
    this._syncSections();
    this._ensureDom();
    if (this._resizeObserver) this._resizeObserver.observe(this._el.map);
    this._ensureSubscribed();
    this._invalidate("all");
  }

  disconnectedCallback() {
    this._unsubscribe();
    this._clearRetry();
    this._eachSection("disconnect");
    LIVE_CARDS.delete(this);
    this._unbindConnection();
    if (this._raf !== null) {
      cancelAnimationFrame(this._raf);
      this._raf = null;
    }
    if (this._resizeObserver) this._resizeObserver.disconnect();
    this._pointers.clear();
    this._gesture = null;
  }

  // --- Subscription ---

  _ensureSubscribed() {
    if (!this.isConnected || !this._config || !this._hass || !this._hass.connection) return;
    this._bindConnection(this._hass.connection);
    this._eachSection("connect");
    if (this._sub || this._retryTimer) return;
    this._subscribe();
  }

  _bindConnection(connection) {
    if (this._connection === connection) return;
    this._unbindConnection();
    this._connection = connection;
    if (connection.addEventListener) {
      connection.addEventListener("ready", this._onReady);
      connection.addEventListener("disconnected", this._onDisconnected);
    }
  }

  _unbindConnection() {
    if (this._connection && this._connection.removeEventListener) {
      this._connection.removeEventListener("ready", this._onReady);
      this._connection.removeEventListener("disconnected", this._onDisconnected);
    }
    this._connection = null;
  }

  _subscribe() {
    const connection = this._hass.connection;
    const sub = { unsub: null };
    this._sub = sub;
    // The first status of a subscription is what is, not what changed.
    this._announceFrom = null;
    const current = () => this._sub === sub;
    connection
      .subscribeMessage(
        (event) => {
          if (current()) this._onFeedEvent(event);
        },
        { type: SUBSCRIBE_TYPE, entity_id: this._config.entity },
        { resubscribe: false },
      )
      .then((unsub) => {
        if (!current()) {
          safeUnsubscribe(unsub);
          return;
        }
        sub.unsub = unsub;
        this._retry = 0;
        if (this._feedError) {
          this._feedError = null;
          this._invalidate("msg");
        }
      })
      .catch((err) => {
        if (!current()) return;
        this._sub = null;
        this._feedError = errorMessage(err);
        this._invalidate("msg");
        this._scheduleResubscribe();
      });
  }

  _unsubscribe() {
    const sub = this._sub;
    this._sub = null;
    if (sub && sub.unsub) safeUnsubscribe(sub.unsub);
  }

  _clearRetry() {
    if (this._retryTimer !== null) {
      clearTimeout(this._retryTimer);
      this._retryTimer = null;
    }
  }

  // Subscribe again after a delay, once the mower entity is available.
  _scheduleResubscribe() {
    this._clearRetry();
    const delay = RESUBSCRIBE_DELAYS[Math.min(this._retry, RESUBSCRIBE_DELAYS.length - 1)];
    this._retry += 1;
    this._retryTimer = setTimeout(() => {
      this._retryTimer = null;
      if (!this.isConnected || !this._hass || !this._config || this._sub) return;
      const stateObj = this._hass.states[this._config.entity];
      if (!stateObj || stateObj.state === "unavailable") {
        this._scheduleResubscribe();
        return;
      }
      this._subscribe();
    }, delay);
  }

  // The websocket reconnected: the old subscription died with the old socket.
  // It is dropped, not unsubscribed: the connection reuses subscription ids
  // after a reconnect, so unsubscribing the old id could end another
  // subscription.
  _resubscribeNow() {
    if (!this.isConnected || !this._config || !this._hass) return;
    this._sub = null;
    this._clearRetry();
    this._retry = 0;
    this._subscribe();
    this._eachSection("resubscribe");
  }

  _onFeedEvent(event) {
    if (!event || typeof event !== "object") return;
    switch (event.type) {
      case "geometry":
        if (this._geometry && this._geometry.map_id !== event.map_id) this._clearSelection();
        this._geometry = event;
        this._buildShapes();
        this._updateTransform();
        this._invalidate("header", "toolbar", "base", "trail", "dyn", "msg", "picker", "actions", "settings", "maps", "maint");
        break;
      case "path":
        this._trail = this._trail.slice(0, event.keep || 0).concat(event.points || []);
        this._invalidate("trail");
        break;
      case "status": {
        const previous = this._status;
        this._status = event;
        this._announce(this._announceFrom, event.state);
        this._announceFrom = event.state;
        const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
        if (!previous || previous.rotation !== event.rotation || !same(previous.dock, event.dock)) this._updateTransform();
        if (
          !previous ||
          !same(previous.zones, event.zones) ||
          previous.current_zone !== event.current_zone ||
          this._working(previous) !== this._working(event)
        ) {
          this._invalidate("base", "trail");
        }
        this._invalidate("header", "toolbar", "dyn", "msg", "picker", "actions", "settings", "maps", "maint");
        break;
      }
      case "closed":
        // The integration unloaded the mower; follow it once it is back.
        this._unsubscribe();
        this._scheduleResubscribe();
        break;
      default:
        break;
    }
  }

  // --- Map state ---

  _hasMap() {
    return Boolean(this._geometry && this._geometry.map_id !== null && this._tf);
  }

  // Whether a mowing session runs: the lawn then shows what is mowed
  // instead of its stripes.
  _working(status = this._status) {
    return Boolean(status && status.state && status.state.session_active);
  }

  // Zones and spot areas as point lists, for drawing and hit tests.
  _buildShapes() {
    const g = this._geometry || {};
    const shape = (item) => {
      const points = pairs(item.polygon || []);
      return { id: item.id, name: item.name, points, center: points.length ? polygonCentroid(points) : null };
    };
    const zones = (g.zones || []).map(shape).filter((s) => s.points.length >= 3);
    const zoneName = (id) => (zones.find((zone) => zone.id === id) || {}).name || `Zone ${id}`;
    // An edge is a zone's outline (index 0) or the outline of a shape cut
    // into the lawn (index 128 and up); it is picked by its [zone, index] pair.
    // A zone's outline is drawn along the zone itself: the edge the mower
    // keeps for it is a coarser copy of the same line.
    const edges = (g.contours || [])
      .map((contour) => {
        const [zoneId, index] = contour.id;
        const zone = index === 0 ? zones.find((z) => z.id === zoneId) : null;
        const points = zone ? zone.points : pairs(contour.points || []);
        const name = index === 0 ? `${zoneName(zoneId)} edge` : `${zoneName(zoneId)} shape ${index - 127}`;
        return { id: `${zoneId},${index}`, contour: contour.id, name, points };
      })
      .filter((edge) => edge.points.length >= 2);
    this._shapes = {
      edges,
      zones,
      spots: (g.spots || []).map(shape).filter((s) => s.points.length >= 3),
    };
    for (const kind of ["edges", "zones", "spots"]) {
      const ids = new Set(this._shapes[kind].map((s) => s.id));
      for (const id of [...this._selected[kind]]) if (!ids.has(id)) this._selected[kind].delete(id);
    }
    if (!this._modes().some((mode) => mode.id === this._mode)) this._mode = "all";
  }

  _modes() {
    return MODES.filter((mode) => !mode.kind || this._shapes[mode.kind].length);
  }

  _modeKind() {
    const mode = MODES.find((m) => m.id === this._mode);
    return mode ? mode.kind || null : null;
  }

  // Edge and spot mowing leave the lawns themselves alone, so they fade.
  _faded() {
    const kind = this._modeKind();
    return kind === "edges" || kind === "spots";
  }

  // The box the view fits, the map filling FIT_SHARE of it: the map's areas
  // and the station.
  _mapBox() {
    const g = this._geometry;
    const points = [];
    if (g && g.bounds) points.push([g.bounds[0], g.bounds[1]], [g.bounds[2], g.bounds[3]]);
    const dock = this._status && this._status.dock;
    if (dock) points.push([dock.x, dock.y]);
    const box = boxOf(points);
    if (!box) return null;
    const w = Math.max(box[2] - box[0], 1000);
    const h = Math.max(box[3] - box[1], 1000);
    const mx = (w / FIT_SHARE - (box[2] - box[0])) / 2;
    const my = (h / FIT_SHARE - (box[3] - box[1])) / 2;
    return [box[0] - mx, box[1] - my, box[2] + mx, box[3] + my];
  }

  _updateTransform() {
    const box = this._geometry && this._geometry.map_id !== null ? this._mapBox() : null;
    if (!box) {
      this._tf = null;
      this._tfKey = null;
      this._invalidate("base", "trail", "dyn", "aspect");
      return;
    }
    const rotation = this._status ? this._status.rotation || 0 : 0;
    const key = `${this._geometry.map_id}|${rotation}`;
    this._tf = makeTransform(box, rotation);
    if (key !== this._tfKey) {
      // Another map or rotation: the old view no longer applies.
      this._viewTouched = false;
      this._tfKey = key;
    }
    this._fit = { x: 0, y: 0, w: this._tf.width, h: this._tf.height };
    if (!this._viewTouched || !this._vb) this._vb = { ...this._fit };
    this._invalidate("base", "trail", "dyn", "view", "aspect");
  }

  // "light" or "dark": forced by the config, or following Home Assistant's
  // dark mode (the browser's preference when the frontend does not say).
  _theme() {
    const wanted = this._config && this._config.theme;
    if (wanted === "light" || wanted === "dark") return wanted;
    const darkMode = this._hass && this._hass.themes ? this._hass.themes.darkMode : undefined;
    if (typeof darkMode === "boolean") return darkMode ? "dark" : "light";
    const media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
    return media && media.matches ? "dark" : "light";
  }

  _palette() {
    return PALETTES[this._theme()];
  }

  // The mower's state: the entity's activity plus what the feed reports.
  _mower() {
    const stateObj = this._stateObj;
    const feed = (this._status && this._status.state) || {};
    const activity = stateObj ? stateObj.state : "unavailable";
    return {
      ...feed,
      activity,
      available: activity !== "unavailable" && feed.available !== false,
    };
  }

  // Whether the mower stands in its station, as the feed reports it or else
  // by the entity's activity.
  _docked() {
    const status = this._status || {};
    return Boolean(status.docked) || this._mower().activity === "docked";
  }

  _zoneSetting(id) {
    const zones = (this._status && this._status.zones) || [];
    return zones.find((zone) => zone.id === id) || null;
  }

  _clearSelection() {
    for (const selected of Object.values(this._selected)) selected.clear();
  }

  // --- DOM ---

  _ensureDom() {
    if (this._root) return;
    this._root = this.attachShadow({ mode: "open" });
    this._root.innerHTML = `
      <style>${CSS}</style>
      <ha-card>
        <nav class="tabs" aria-label="Card tabs"></nav>
        <div class="status">
          <div class="txt"><div class="caption" hidden></div><div class="state"></div><div class="sub"></div><div class="sub err" hidden></div></div>
          <button type="button" class="iconbtn" data-action="recharge"></button>
          <button type="button" class="iconbtn" data-action="find" title="Find my robot: the mower calls out" aria-label="Find my robot"><ha-icon icon="mdi:map-marker-radius"></ha-icon></button>
        </div>
        <div class="edithead subhead" hidden>
          <button type="button" class="iconbtn" data-edithead="back" title="Back to the settings" aria-label="Back to the settings"><ha-icon icon="mdi:chevron-left"></ha-icon></button>
          <span class="title">Map editor</span><span class="muted left"></span>
          <button type="button" class="flat maps" data-edithead="maps"><ha-icon icon="mdi:layers-outline"></ha-icon>Maps<ha-icon icon="mdi:chevron-right"></ha-icon></button>
        </div>
        <div class="map" tabindex="0">
          <svg class="main" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
            <defs></defs>
            <g class="base"></g>
            <g class="trail"></g>
            <g class="dyn"></g>
          </svg>
          <div class="msg" hidden></div>
          <button type="button" class="mapchip" hidden></button>
          <div class="mapbtns" hidden>
            <button type="button" class="mapbtn" data-zoom="in" title="Zoom in" aria-label="Zoom in"><ha-icon icon="mdi:plus"></ha-icon></button>
            <button type="button" class="mapbtn" data-zoom="out" title="Zoom out" aria-label="Zoom out"><ha-icon icon="mdi:minus"></ha-icon></button>
            <button type="button" class="mapbtn" data-zoom="fit" title="Fit the map" aria-label="Fit the map"><ha-icon icon="mdi:fit-to-screen-outline"></ha-icon></button>
            <span class="secbtns"></span>
          </div>
          <div class="mapnote" hidden><span class="spin"></span><span class="text"></span></div>
        </div>
        <div class="cover" hidden></div>
        <div class="errline" hidden></div>
        <div class="panel"><div class="strip" role="group" aria-label="What to mow"></div><div class="hint" hidden></div><div class="controls"></div></div>
        <div class="editpanel" hidden></div>
        <div class="view worklog" hidden><div class="shead"></div><div class="sbody"></div></div>
        <div class="view schedules" hidden><div class="shead"></div><div class="sbody"></div></div>
        <div class="view maint" hidden><div class="shead"></div><div class="sbody"></div></div>
        <div class="view maplist" hidden><div class="shead"></div><div class="sbody"></div></div>
        <div class="settings" hidden><div class="shead"></div><div class="sbody"></div><div class="sfoot save"></div></div>
        <div class="scrim" hidden></div>
        <div class="sheet photo" hidden></div>
        <div class="sheet picker" hidden></div>
        <div class="sheet choice" hidden></div>
        <div class="toast" hidden></div>
      </ha-card>`;
    const $ = (sel) => this._root.querySelector(sel);
    this._el = {
      card: $("ha-card"),
      tabs: $(".tabs"),
      status: $(".status"),
      caption: $(".status .caption"),
      state: $(".status .state"),
      sub: $(".status .sub:not(.err)"),
      subError: $(".status .sub.err"),
      home: $(".status [data-action='recharge']"),
      find: $(".status [data-action='find']"),
      edithead: $(".edithead"),
      map: $(".map"),
      svg: $("svg.main"),
      defs: $("svg.main defs"),
      base: $("g.base"),
      trail: $("g.trail"),
      dyn: $("g.dyn"),
      msg: $(".msg"),
      chip: $(".mapchip"),
      mapbtns: $(".mapbtns"),
      secbtns: $(".mapbtns .secbtns"),
      cover: $(".cover"),
      note: $(".mapnote"),
      error: $(".errline"),
      panel: $(".panel"),
      strip: $(".panel .strip"),
      hint: $(".panel .hint"),
      controls: $(".panel .controls"),
      editpanel: $(".editpanel"),
      toast: $(".toast"),
      settings: $(".settings"),
      shead: $(".settings .shead"),
      sbody: $(".settings .sbody"),
      sfoot: $(".settings .sfoot"),
      maint: $(".maint"),
      khead: $(".maint .shead"),
      kbody: $(".maint .sbody"),
      maps: $(".maplist"),
      mhead: $(".maplist .shead"),
      mbody: $(".maplist .sbody"),
      log: $(".worklog"),
      lhead: $(".worklog .shead"),
      lbody: $(".worklog .sbody"),
      schedules: $(".schedules"),
      schedhead: $(".schedules .shead"),
      schedbody: $(".schedules .sbody"),
      scrim: $(".scrim"),
      photo: $(".photo"),
      picker: $(".picker"),
      choice: $(".choice"),
    };
    const svg = this._el.svg;
    svg.addEventListener("pointerdown", (e) => this._onPointerDown(e));
    svg.addEventListener("pointermove", (e) => this._onPointerMove(e));
    svg.addEventListener("pointerup", (e) => this._onPointerUp(e, false));
    svg.addEventListener("pointercancel", (e) => this._onPointerUp(e, true));
    svg.addEventListener("wheel", (e) => this._onWheel(e), { passive: false });
    svg.addEventListener("contextmenu", (e) => e.preventDefault());
    this._el.tabs.addEventListener("click", (e) => {
      const button = e.target.closest("[data-tab]");
      if (button) this._setTab(button.dataset.tab);
    });
    this._el.status.addEventListener("click", (e) => this._onActionClick(e));
    this._el.panel.addEventListener("click", (e) => {
      const mode = e.target.closest("[data-mode]");
      if (mode && !mode.disabled) this._setMode(mode.dataset.mode);
      else this._onActionClick(e);
    });
    this._el.chip.addEventListener("click", () => {
      if (this._el.chip.disabled) return;
      this._picker = !this._picker;
      this._invalidate("picker");
    });
    this._el.picker.addEventListener("click", (e) => this._onPickerClick(e));
    this._el.mapbtns.addEventListener("click", (e) => {
      // A section's button goes to that section.
      const own = e.target.closest("[data-section]");
      if (own) {
        const entry = this._sections.find((s) => s.id === own.dataset.section);
        if (entry) this._sectionCall(entry.section, "handleEvent", e);
        return;
      }
      const button = e.target.closest("[data-zoom]");
      if (!button || !this._vb) return;
      if (button.dataset.zoom === "fit") {
        this._fitView();
        return;
      }
      const vb = this._vb;
      this._zoomAbout([vb.x + vb.w / 2, vb.y + vb.h / 2], button.dataset.zoom === "in" ? 1 / ZOOM_STEP : ZOOM_STEP);
    });
    // A tap beside a sheet closes it.
    this._el.scrim.addEventListener("click", () => {
      if (this._chosen) this._chosen(null);
      else if (this._picker) this._picker = false;
      else this._photo = null;
      this._invalidate("picker", "photo");
    });
    this._el.editpanel.addEventListener("click", (e) => this._onEditPanelClick(e));
    // Turning a maintenance point: the map follows the slider, the panel once it is let go.
    this._el.editpanel.addEventListener("input", (e) => {
      const selected = this._editSelected();
      if (!e.target.matches("[data-point-heading]") || !selected || selected.kind !== "maintenance") return;
      this._turning = true;
      selected.heading = Number(e.target.value);
      const label = this._el.editpanel.querySelector("[data-heading-label]");
      if (label) label.textContent = `${selected.heading}°`;
      this._invalidate("dyn");
    });
    // The turn ends when the slider is let go or left, whether or not its value changed.
    const turned = (e) => {
      if (!e.target.matches || !e.target.matches("[data-point-heading]") || !this._turning) return;
      this._turning = false;
      this._invalidate("actions");
    };
    for (const type of ["change", "pointerup", "pointercancel", "focusout"]) this._el.editpanel.addEventListener(type, turned);
    this._el.error.addEventListener("click", (e) => {
      const button = e.target.closest("[data-clear-error]");
      if (!button || this._busy) return;
      // Cleared, the mower goes on with its task or drives home.
      this._beforeDrive("continue").then((ready) => ready && this._call(DOMAIN, "clear_error", {}, { success: "Error cleared" }));
    });
    this._el.edithead.addEventListener("click", (e) => {
      const button = e.target.closest("button");
      if (!button || button.disabled) return;
      if (button.dataset.edithead === "back") this._closeEditor();
      if (button.dataset.edithead === "maps") this._openMapList();
    });
    this._el.settings.addEventListener("click", (e) => this._onSettingsClick(e));
    this._el.log.addEventListener("click", (e) => this._onWorkLogClick(e));
    for (const type of ["click", "change", "input", "value-changed"]) {
      this._el.schedules.addEventListener(type, (e) => this._onSchedulesEvent(e));
    }
    this._el.maint.addEventListener("click", (e) => this._onMaintenanceClick(e));
    this._el.maint.addEventListener("change", (e) => this._onMaintenanceChange(e));
    this._el.maint.addEventListener("focusout", (e) => this._onMaintenanceLeave(e));
    this._el.maps.addEventListener("click", (e) => this._onMapListClick(e));
    this._el.photo.addEventListener("click", (e) => this._onPhotoClick(e));
    this._el.settings.addEventListener("input", (e) => this._onSettingsInput(e, false));
    this._el.settings.addEventListener("change", (e) => this._onSettingsInput(e, true));
    if (window.ResizeObserver) {
      // Label and marker sizes depend on the on-screen size of the map.
      this._resizeObserver = new ResizeObserver(() => this._invalidate("dyn"));
    }
  }

  // --- Rendering ---

  _invalidate(...parts) {
    for (const part of parts) {
      if (part === "all") {
        for (const p of ["theme", "header", "toolbar", "aspect", "view", "base", "trail", "dyn", "msg", "picker", "actions", "settings", "log", "photo", "maps", "maint", "schedules"]) {
          this._dirty.add(p);
        }
      } else {
        this._dirty.add(part);
      }
    }
    if (this._raf === null && this.isConnected) {
      this._raf = requestAnimationFrame(() => {
        this._raf = null;
        this._render();
      });
    }
  }

  _render() {
    if (!this._config) return;
    this._ensureDom();
    const dirty = this._dirty;
    this._dirty = new Set();
    if (dirty.has("theme")) this._renderTheme();
    if (dirty.has("header")) this._renderHeader();
    if (dirty.has("toolbar")) this._renderToolbar();
    if (dirty.has("aspect")) this._renderAspect();
    if (dirty.has("view")) this._renderView();
    if (dirty.has("base")) this._renderBase();
    if (dirty.has("trail")) this._renderTrail();
    if (dirty.has("dyn")) this._renderDyn();
    if (dirty.has("msg")) this._renderMsg();
    if (dirty.has("picker")) this._renderPicker();
    if (dirty.has("actions")) {
      this._renderActions();
      this._renderEditPanel();
    }
    if (dirty.has("settings")) this._renderSettings();
    if (dirty.has("log")) this._renderWorkLog();
    if (dirty.has("photo")) this._renderPhoto();
    if (dirty.has("maps")) this._renderMapList();
    if (dirty.has("maint")) this._renderMaintenance();
    if (dirty.has("schedules")) this._renderSchedules();
    // Which tab shows, and what of the card belongs to it; cheap enough to
    // follow every change.
    this._renderTabs();
  }

  _setHtml(key, el, html) {
    if (this._html[key] === html) return;
    this._html[key] = html;
    el.innerHTML = html;
  }

  // The map keeps its own palette; the rest of the card follows Home
  // Assistant's theme through its CSS variables.
  _renderTheme() {
    const pal = this._palette();
    const style = this._el.card.style;
    style.setProperty("--mower-map-background", pal.background);
    style.setProperty("--mower-working", pal.working);
  }

  // --- Tabs ---

  // Shows the open tab: Mow with the map and its controls, History with the
  // work log, Schedules with the schedules, Settings with the mower's settings,
  // where the map editor and the list of maps open too.
  _renderTabs() {
    const tab = this._tab;
    const tabs = TABS.map(
      (t) =>
        `<button type="button" class="${t.id === tab ? "on" : ""}" data-tab="${t.id}" aria-pressed="${t.id === tab}">` +
        `<ha-icon icon="${t.icon}"></ha-icon>${esc(t.label)}</button>`,
    ).join("");
    this._setHtml("tabs", this._el.tabs, tabs);
    const mow = tab === "mow";
    const settings = tab === "settings";
    const editing = settings && Boolean(this._edit) && !this._mapList;
    const el = this._el;
    el.status.hidden = !mow || this._config.show_header === false;
    // A section may show something of its own in the map's place.
    let cover = null;
    const buttons = [];
    if (mow) {
      for (const { id, section } of this._sections) {
        const own = this._sectionCall(section, "cover");
        if (!cover && own && own.nodeType === 1) cover = own;
        const html = this._sectionCall(section, "mapButtons");
        if (html) buttons.push(`<span data-section="${esc(id)}">${html}</span>`);
      }
    }
    this._setHtml("secbtns", el.secbtns, buttons.join(""));
    if (cover && (el.cover.firstChild !== cover || el.cover.childNodes.length !== 1)) el.cover.replaceChildren(cover);
    else if (!cover && el.cover.firstChild) el.cover.replaceChildren();
    el.cover.hidden = !cover;
    el.map.hidden = !(mow || editing) || Boolean(cover);
    el.error.hidden = !mow || !this._mower().error;
    // Without the controls the panel only shows the progress of a running task.
    el.panel.hidden = !mow || (this._config.show_controls === false && !this._mower().session_active);
    el.edithead.hidden = !editing;
    el.editpanel.hidden = !editing;
    el.log.hidden = tab !== "history";
    el.schedules.hidden = tab !== "schedules";
    // The mowing settings opened from the Settings tab are one of its pages.
    const inline = Boolean(this._settings && this._settings.inline);
    el.settings.classList.toggle("inline", inline);
    el.maint.hidden = !settings || Boolean(this._edit) || Boolean(this._mapList) || inline;
    el.maps.hidden = !settings || !this._mapList;
    el.chip.hidden = !mow || !this._hasMap();
    el.mapbtns.hidden = !this._hasMap();
    el.scrim.hidden = !(this._chosen || this._picker || this._photo);
  }

  // Opens a tab. Leaving the Settings tab leaves the map editor, after
  // asking when it holds unsaved changes.
  _setTab(tab) {
    if (!TABS.some((t) => t.id === tab)) return;
    if (tab === this._tab) {
      // Tapping History again leads back from a task to the list.
      if (tab === "history" && this._log && this._log.detail) {
        this._log.detail = null;
        this._invalidate("log");
      }
      // Tapping Settings again leads back from one of its pages to the list.
      if (tab === "settings" && this._settings && this._settings.inline) {
        if (!Object.keys(this._settings.draft).length || window.confirm("Leave without saving the changes?")) this._closeSettings();
      } else if (tab === "settings" && this._maint && this._maint.page && !this._edit && !this._mapList) {
        this._settingsPage(null);
      }
      if (tab === "schedules") this._eachSection("back");
      return;
    }
    if (this._edit && !this._closeEditor()) return;
    if (this._settings && this._settings.inline) {
      if (Object.keys(this._settings.draft).length && !window.confirm("Leave the mowing settings without saving the changes?")) return;
      this._settings = null;
      this._invalidate("settings");
    }
    for (const { section } of this._sections) if (this._sectionCall(section, "leave") === false) return;
    this._tab = tab;
    this._mapList = null;
    this._picker = false;
    this._maint = tab === "settings" ? { page: null } : null;
    if (tab === "history") {
      this._openWorkLog();
    } else {
      this._log = null;
      this._logPanZoom = null;
    }
    this._invalidate("header", "toolbar", "actions", "picker", "maint", "maps", "log", "schedules", "dyn");
  }

  // The state, the battery with what the mower is about, its error, and the
  // buttons that send it home and have it call out.
  _renderHeader() {
    const mower = this._mower();
    const title = this._config.title;
    this._el.caption.hidden = !title;
    this._el.caption.textContent = title || "";
    this._el.state.textContent = mower.available ? mower.text || humanize(mower.status || mower.activity) : "Unavailable";
    const sub = [];
    if (mower.battery !== null && mower.battery !== undefined) {
      const charging = mower.charging === "charging";
      const icon = charging ? batteryChargingIcon(mower.battery) : batteryIcon(mower.battery);
      sub.push(`<ha-icon icon="${icon}"${charging ? ' style="color:#43a047"' : ""}></ha-icon>${esc(mower.battery)} %`);
    }
    const where = this._whereText(mower);
    if (where) sub.push(esc(where));
    this._setHtml("sub", this._el.sub, sub.join(" · "));
    this._el.sub.hidden = !sub.length;
    this._el.subError.hidden = !mower.error;
    this._el.subError.textContent = mower.error || "";
    // On its way home the mower can be stopped where it is; otherwise it can
    // be sent home, unless it stands in its station. During a task the task
    // is kept, to continue after charging.
    const off = !mower.available || this._busy;
    const controls = this._config.show_controls !== false;
    const home = this._el.home;
    const returning = mower.activity === "returning";
    home.hidden = !controls;
    home.dataset.action = returning ? "stop-returning" : "recharge";
    const homeTitle = returning ? "End Returning: stop where it is" : "Recharge: send the mower to its station";
    home.title = homeTitle;
    home.setAttribute("aria-label", homeTitle);
    this._setHtml("home", home, `<ha-icon icon="${returning ? "mdi:home-remove-outline" : "mdi:home-import-outline"}"></ha-icon>`);
    home.disabled = off || (!returning && this._docked());
    this._el.find.hidden = !controls;
    this._el.find.disabled = off;
    // What the mower does that keeps it from moving on: finding where it
    // is, leaving or finding its station.
    const wait = mowerWait(mower);
    this._el.note.hidden = !wait;
    if (wait) this._el.note.querySelector(".text").textContent = wait;
    this._setHtml(
      "error",
      this._el.error,
      mower.error
        ? `<ha-icon icon="mdi:alert-circle-outline"></ha-icon><span>${esc(mower.error)}</span>` +
            `<button type="button" class="flat" data-clear-error ${this._busy ? "disabled" : ""}>Clear and continue</button>`
        : "",
    );
  }

  // Where the mower is or what it is about, in a few words.
  _whereText(mower) {
    if (!mower.available) return "";
    if (mower.activity === "returning") return "returning";
    if (this._docked()) return "on the station";
    if (mower.session_active) {
      // "zone task in Lawn": what kind of task runs, and where.
      const current = this._status ? this._status.current_zone : null;
      const zone = this._shapes.zones.find((z) => z.id === current);
      const kind = TASK_KINDS[mower.task_mode];
      return `${kind ? `${kind} task` : "task"}${zone ? ` in ${zone.name}` : mower.activity === "mowing" ? "" : " paused"}`;
    }
    return "";
  }

  // What to mow, and what is picked for it on the map.
  _renderToolbar() {
    this._el.edithead.querySelector(".maps").disabled = this._busy;
    const mower = this._mower();
    const modes = this._modes();
    const session = Boolean(mower.session_active);
    // Without a map, or while a task runs, there is nothing to choose.
    const strip =
      modes.length > 1 && !session
        ? modes
            .map(
              (mode) =>
                `<button type="button" class="${mode.id === this._mode ? "on" : ""}" data-mode="${mode.id}" aria-pressed="${mode.id === this._mode}" ` +
                `${this._busy || !mower.available ? "disabled" : ""}>${mode.glyph ? GLYPHS[mode.glyph] : `<ha-icon icon="${mode.icon}"></ha-icon>`}${esc(mode.label)}</button>`,
            )
            .join("")
        : "";
    this._el.strip.style.setProperty("--modes", String(modes.length));
    this._setHtml("strip", this._el.strip, strip);
    const kind = this._modeKind();
    let hint = "";
    if (!session && strip) {
      if (!kind) {
        hint = "Mows the whole map. Pick Edges, Zones or Spots to mow only what you tap on the map.";
      } else {
        const picked = this._shapes[kind].filter((shape) => this._selected[kind].has(shape.id));
        const noun = MODES.find((mode) => mode.kind === kind).noun;
        if (picked.length) {
          const area = (shape) => {
            const zone = kind === "zones" ? ((this._geometry && this._geometry.zones) || []).find((z) => z.id === shape.id) : null;
            return zone && zone.area ? ` · ${num(zone.area)} m²` : "";
          };
          hint =
            picked.map((shape) => `<b>${esc(shape.name)}</b>${esc(area(shape))}`).join(", ") +
            esc(`. Tap more ${noun} to add them; tap one again to drop it.`);
        } else {
          hint = esc(`Tap ${noun} on the map to pick them; tap one again to drop it.`);
        }
      }
      if (!kind) hint = esc(hint);
    }
    this._setHtml("hint", this._el.hint, hint);
    this._el.hint.hidden = !hint;
  }

  _renderAspect() {
    const fit = this._fit;
    const ratio = this._tf && fit ? Math.max(0.75, Math.min(1.6, fit.w / fit.h)) : 1;
    this._el.map.style.aspectRatio = `${num(ratio)} / 1`;
  }

  _renderView() {
    const vb = this._vb;
    if (vb) this._el.svg.setAttribute("viewBox", `${num(vb.x)} ${num(vb.y)} ${num(vb.w)} ${num(vb.h)}`);
  }

  // Size of one screen pixel in SVG units.
  _px() {
    const vb = this._vb;
    const svg = this._el && this._el.svg;
    if (!vb || !svg) return 1;
    const cw = svg.clientWidth;
    const ch = svg.clientHeight;
    if (!cw || !ch) return vb.w / 400;
    return Math.max(vb.w / cw, vb.h / ch);
  }

  // Paths between the zones, the lawns with their stripes, no-go areas,
  // areas where obstacles are ignored and, when spots are picked, spot areas.
  _renderBase() {
    if (!this._hasMap()) {
      this._setHtml("defs", this._el.defs, "");
      this._setHtml("base", this._el.base, "");
      return;
    }
    const tf = this._tf;
    const pal = this._palette();
    const g = this._geometry;
    const working = this._working();
    const faded = this._faded();
    const defs = [];
    const parts = [];
    for (const path of g.paths || []) {
      const points = pairs(path.points || []);
      if (points.length < 2) continue;
      const line = (stroke, width, extra = "") =>
        svgPolyline(tf, points, `stroke="${stroke}" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round" ${extra}`);
      parts.push(line(pal.pathOuter, 590), line(pal.pathInner, 550), line(pal.pathOuter, 25, 'stroke-dasharray="200 200"'));
    }
    for (const zone of this._shapes.zones) {
      const colors = zoneColors(zone.id, pal);
      const setting = this._zoneSetting(zone.id);
      const angle = setting ? setting.stripe_angle : null;
      let fill = faded ? pal.background : colors.fill;
      if (!working && !faded && angle !== null && angle !== undefined) {
        // Stripes along the mowing direction, turned with the map.
        const id = `stripes-${this._uid}-${zone.id}`;
        const period = 2 * STRIPE_WIDTH;
        defs.push(
          `<pattern id="${id}" patternUnits="userSpaceOnUse" width="${period}" height="${period}" ` +
            `patternTransform="rotate(${num(tf.rotation - angle)})">` +
            `<rect width="${period}" height="${period}" fill="${colors.fill}"/>` +
            `<rect width="${period}" height="${STRIPE_WIDTH}" fill="${pal.stripe}"/></pattern>`,
        );
        fill = `url(#${id})`;
      }
      // In edge mode the edges layer draws the outlines.
      const outline = this._modeKind() === "edges" ? 'stroke="none"' : `stroke="${colors.outline}" stroke-width="${OUTLINE_WIDTH}" stroke-linejoin="round"`;
      parts.push(svgPolygon(tf, zone.points, `fill="${fill}" ${outline}`));
    }
    // While the map is edited, its items are drawn from the working copy.
    for (const area of this._edit ? [] : g.no_go || []) {
      const points = pairs(area.polygon || []);
      if (area.shape === "line" && area.line) {
        parts.push(svgPolyline(tf, [area.line.slice(0, 2), area.line.slice(2)], `stroke="${pal.noGo}" stroke-width="${2 * OUTLINE_WIDTH}" stroke-linecap="round"`));
      } else if (points.length >= 3) {
        parts.push(
          svgPolygon(tf, points, `fill="${pal.noGo}" fill-opacity=".15" stroke="${pal.noGo}" stroke-width="${OUTLINE_WIDTH}"`),
        );
      }
    }
    for (const area of this._edit ? [] : g.ignore_obstacles || []) {
      const points = pairs(area.polygon || []);
      if (points.length >= 3) {
        parts.push(
          svgPolygon(
            tf,
            points,
            `fill="${pal.ignoreObstacles}" fill-opacity=".15" stroke="${pal.ignoreObstacles}" stroke-width="${OUTLINE_WIDTH}"`,
          ),
        );
      }
    }
    if (this._modeKind() === "spots" && !this._edit) {
      for (const spot of this._shapes.spots) {
        parts.push(
          svgPolygon(tf, spot.points, `fill="${pal.spot}" fill-opacity=".15" stroke="${pal.spot}" stroke-width="${OUTLINE_WIDTH}"`),
        );
      }
    }
    // The zone being mowed is outlined in dashes; the mowed trail lies over it.
    const current = working && this._status ? this._status.current_zone : null;
    const zone = current === null || current === undefined ? null : this._shapes.zones.find((z) => z.id === current);
    if (zone) {
      parts.push(
        svgPolygon(tf, zone.points, `fill="none" stroke="${pal.working}" stroke-width="${OUTLINE_WIDTH}" stroke-dasharray="300 130" pointer-events="none"`),
      );
    }
    // The mowed trail is only shown within the lawns.
    defs.push(
      `<clipPath id="lawn-${this._uid}">${this._shapes.zones.map((z) => svgPolygon(tf, z.points, "")).join("")}</clipPath>`,
    );
    this._setHtml("defs", this._el.defs, defs.join(""));
    this._setHtml("base", this._el.base, parts.join(""));
  }

  // What the running session has mowed so far.
  _renderTrail() {
    if (!this._hasMap() || this._config.show_trail === false || !this._working() || !this._trail.length) {
      this._setHtml("trail", this._el.trail, "");
      return;
    }
    const d = trailPath(this._tf, this._trail);
    this._setHtml(
      "trail",
      this._el.trail,
      d
        ? `<path d="${d}" fill="none" stroke="${this._palette().trail}" stroke-width="${TRAIL_WIDTH}" ` +
            `stroke-linejoin="round" stroke-linecap="round" clip-path="url(#lawn-${this._uid})" pointer-events="none"/>`
        : "",
    );
  }

  // The zone being mowed, the picked zones, labels, recognised obstacles,
  // the station and the mower.
  _renderDyn() {
    if (!this._hasMap()) {
      this._el.dyn.innerHTML = "";
      return;
    }
    const tf = this._tf;
    const pal = this._palette();
    const px = this._px();
    const status = this._status || {};
    const working = this._working();
    const parts = [];

    if (this._edit) {
      if (this._editSync()) this._invalidate("actions");
      parts.push(this._editOverlay(tf, pal, px));
    }
    const kind = this._edit ? null : this._modeKind();
    if (kind === "edges" && !working) {
      // Every edge as a line, the picked ones in the brand colour and wider.
      for (const edge of this._shapes.edges) {
        const on = this._selected.edges.has(edge.id);
        parts.push(
          svgPolyline(
            tf,
            edge.points.concat([edge.points[0]]),
            `stroke="${on ? pal.brand : pal.edge}" stroke-width="${on ? 2 * OUTLINE_WIDTH : OUTLINE_WIDTH}" ` +
              `stroke-linejoin="round" pointer-events="none"`,
          ),
        );
      }
    }
    for (const zone of this._shapes.zones) {
      if (!zone.center) continue;
      const [X, Y] = tf.toMap(zone.center[0], zone.center[1]);
      parts.push(svgZoneLabel(X, Y, zone.name, px, pal));
    }
    if (kind === "spots") {
      for (const spot of this._shapes.spots) {
        if (!spot.center) continue;
        const [X, Y] = tf.toMap(spot.center[0], spot.center[1]);
        parts.push(svgZoneLabel(X, Y, spot.name, px, pal));
      }
    }

    // The toggles that pick what to mow: on each zone or spot, or on the
    // first point of each edge.
    if (kind && !working) {
      for (const shape of this._shapes[kind]) {
        const at = kind === "edges" ? shape.points[0] : shape.center;
        if (!at) continue;
        const [X, Y] = tf.toMap(at[0], at[1]);
        parts.push(svgToggle(X, Y, px, this._selected[kind].has(shape.id), pal));
      }
    }

    // Obstacles the mower ran into show their outline; those of the plain
    // kind (type 0) and the ones its camera recognised get a pin.
    for (const obstacle of status.obstacles || []) {
      if (obstacle.polygon && !working) {
        const points = pairs(obstacle.polygon);
        if (points.length >= 3) {
          parts.push(svgPolygon(tf, points, `fill="${pal.obstacle}" stroke="${pal.obstacle}" stroke-width="${OUTLINE_WIDTH}" pointer-events="none"`));
        }
      }
    }
    for (const obstacle of status.obstacles || []) {
      if (obstacle.kind === "obstacle" && obstacle.type !== 0) continue;
      const [X, Y] = tf.toMap(obstacle.x, obstacle.y);
      parts.push(svgObstaclePin(X, Y, px, pal, obstacle, obstacleKey(obstacle)));
    }

    // The station, and the mower on it while it is docked.
    const scale = Math.max(MOWER_SCALE, (MOWER_MIN_PX * px) / MOWER_LENGTH);
    const screenAngle = (angle) => -(angle || 0) + tf.rotation;
    const dock = status.dock;
    const docked = this._docked();
    const look = mowerLook(status.model);
    let station = null;
    if (dock) {
      const [X, Y] = tf.toMap(dock.x, dock.y);
      station = { x: X, y: Y, angle: screenAngle(dock.angle), length: STATION_LENGTH * scale };
      parts.push(svgStation(X, Y, scale, station.angle, docked ? "#52FF8C" : "#52C3FF", pal, docked, look));
    }
    if (!(docked && dock) && status.mower) {
      const [X, Y] = tf.toMap(status.mower.x, status.mower.y);
      parts.push(svgMower(X, Y, scale, screenAngle(status.mower.heading), pal, look));
    }
    // What the sections draw over it.
    if (!this._edit) {
      const view = { px, pal, docked, station };
      for (const { section } of this._sections) {
        const layer = this._sectionCall(section, "mapLayer", view);
        if (typeof layer === "string") parts.push(layer);
      }
    }
    this._el.dyn.innerHTML = parts.join("");
  }

  _renderMsg() {
    const msg = this._el.msg;
    let text = "";
    if (this._feedError) text = `Map unavailable: ${this._feedError}`;
    else if (!this._geometry) text = "Loading map…";
    else if (!this._hasMap()) text = "No map yet";
    msg.hidden = !text;
    msg.textContent = text;
  }

  // The map chip names the map in use; tapped, it opens the picker with
  // every map of the mower, where another one is put to use.
  _renderPicker() {
    const g = this._geometry;
    const mower = this._mower();
    const session = Boolean(mower.session_active);
    const switchable = this._config.show_controls !== false && !session;
    if (!switchable) this._picker = false;
    const chip = this._el.chip;
    if (g && g.map_id !== null && g.map_id !== undefined) {
      const name = g.name || `Map ${g.map_id}`;
      const area = g.total_area ? `${num(g.total_area)} m²` : "";
      this._setHtml(
        "chip",
        chip,
        `<span class="name">${esc(name)}</span>${area ? `<span class="m">${esc(area)}</span>` : ""}` +
          (switchable ? `<ha-icon icon="${this._picker ? "mdi:chevron-up" : "mdi:chevron-down"}"></ha-icon>` : ""),
      );
      chip.disabled = !switchable;
      const label = `Map ${name}${area ? `, ${area}` : ""}${switchable ? "; choose another map" : ""}`;
      chip.title = label;
      chip.setAttribute("aria-label", label);
    }
    const el = this._el.picker;
    el.hidden = !this._picker;
    if (!this._picker) {
      this._setHtml("picker", el, "");
      return;
    }
    const off = !mower.available || this._busy || session ? "disabled" : "";
    const maps = (this._status && this._status.maps) || [];
    const rows = maps
      .map((map) => {
        const name = map.name || `Map ${map.id}`;
        const drawn = this._drawnMap(map.id);
        const count = drawn ? (drawn.zones || []).length : null;
        const facts = [`${num(map.area || 0)} m²`];
        if (count !== null) facts.push(`${count} zone${count === 1 ? "" : "s"}`);
        if (map.selected) facts.push("in use");
        return (
          `<div class="maprow">${this._mapOutline(map.id)}<span>${esc(name)}<small>${esc(facts.join(" · "))}</small></span>` +
          (map.selected
            ? `<ha-icon icon="mdi:check" title="In use"></ha-icon>`
            : `<button type="button" class="flat" data-use="${map.id}" ${off}>Use</button>`) +
          `</div>`
        );
      })
      .join("");
    this._setHtml(
      "picker",
      el,
      `<div class="grip"></div>` +
        `<div class="phead"><span>Maps</span><button type="button" class="iconbtn" data-close title="Close" aria-label="Close"><ha-icon icon="mdi:close"></ha-icon></button></div>` +
        `<div>${rows || `<div class="note">No maps yet</div>`}</div>` +
        `<p>Switching takes a moment and only works while no task runs. Renaming, backups and deleting are in Settings › Maps.</p>`,
    );
  }

  async _onPickerClick(e) {
    const button = e.target.closest("button");
    if (!button || button.disabled) return;
    if ("close" in button.dataset) {
      this._picker = false;
      this._invalidate("picker");
      return;
    }
    if (button.dataset.use) {
      const mapId = Number(button.dataset.use);
      const map = ((this._status && this._status.maps) || []).find((m) => m.id === mapId);
      const name = map ? map.name || `Map ${map.id}` : `Map ${mapId}`;
      if (await this._call(DOMAIN, "select_map", { map_id: mapId }, { success: `Switching to ${name}…` })) {
        this._picker = false;
        this._invalidate("picker");
      }
    }
  }

  // The zones and bounds of a map the card knows the outline of: the active
  // one or another; undefined for a map it does not know.
  _drawnMap(id) {
    const g = this._geometry || {};
    return g.map_id === id ? g : (g.other_maps || []).find((other) => other.map_id === id);
  }

  // A small outline of a map's zones, or an empty frame when the card does
  // not know it.
  _mapOutline(id) {
    const outline = this._drawnMap(id);
    if (!outline || !outline.bounds) return `<svg viewBox="0 0 1 1"></svg>`;
    const pal = this._palette();
    const tf = makeTransform(outline.bounds, (this._status && this._status.rotation) || 0);
    const zones = (outline.zones || [])
      .map((zone) => {
        const colors = zoneColors(zone.id, pal);
        return svgPolygon(tf, pairs(zone.polygon || []), `fill="${colors.fill}" stroke="${colors.outline}" stroke-width="${num(tf.width / 50)}"`);
      })
      .join("");
    return `<svg viewBox="0 0 ${num(tf.width)} ${num(tf.height)}" preserveAspectRatio="xMidYMid meet">${zones}</svg>`;
  }

  // --- Picking zones ---

  _setMode(mode) {
    if (mode === this._mode) return;
    this._mode = mode;
    this._invalidate("toolbar", "base", "dyn", "picker", "actions");
  }

  // A tap on the map picks or drops the edge, zone or spot under it.
  _tap(x, y) {
    const kind = this._modeKind();
    if (!kind || this._working()) return;
    let hit = null;
    if (kind === "edges") {
      // The nearest edge, if the tap is close enough to it.
      let best = (EDGE_HIT_PX * this._px());
      for (const edge of this._shapes.edges) {
        const points = edge.points.concat([edge.points[0]]);
        for (let i = 1; i < points.length; i++) {
          const d = distanceToSegment(x, y, points[i - 1], points[i]);
          if (d < best) {
            best = d;
            hit = edge;
          }
        }
      }
      if (hit) this._toggle(kind, hit.id);
      return;
    }
    // Smaller shapes lie on top of larger ones, so the smallest hit wins.
    let hitArea = Infinity;
    for (const shape of this._shapes[kind]) {
      if (!pointInPolygon(x, y, shape.points)) continue;
      const box = boxOf(shape.points);
      const area = (box[2] - box[0]) * (box[3] - box[1]);
      if (area < hitArea) {
        hit = shape;
        hitArea = area;
      }
    }
    if (hit) this._toggle(kind, hit.id);
  }

  _toggle(kind, id) {
    const selected = this._selected[kind];
    if (selected.has(id)) selected.delete(id);
    else selected.add(id);
    this._invalidate("toolbar", "dyn", "actions");
  }

  // --- Pan and zoom ---

  _clientToSvg(clientX, clientY) {
    const svg = this._el.svg;
    const ctm = svg.getScreenCTM();
    if (!ctm) return null;
    const pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const p = pt.matrixTransform(ctm.inverse());
    return [p.x, p.y];
  }

  // Pointer position in map units.
  _clientToMap(clientX, clientY) {
    const p = this._clientToSvg(clientX, clientY);
    if (!p || !this._tf) return null;
    return this._tf.fromMap(p[0], p[1]);
  }

  _zoomLimits() {
    const fit = this._fit || this._vb;
    return { min: fit.w / 20, max: fit.w * 3 };
  }

  // Scale the view by f about the SVG point p, which stays put on screen.
  _zoomAbout(p, f) {
    const vb = this._vb;
    if (!vb) return;
    const limits = this._zoomLimits();
    const w = Math.min(limits.max, Math.max(limits.min, vb.w * f));
    const k = w / vb.w;
    if (Math.abs(k - 1) < 1e-6) return;
    this._vb = { x: p[0] - (p[0] - vb.x) * k, y: p[1] - (p[1] - vb.y) * k, w, h: vb.h * k };
    this._viewTouched = true;
    this._invalidate("view", "dyn");
  }

  _fitView() {
    if (!this._fit) return;
    this._vb = { ...this._fit };
    this._viewTouched = false;
    this._invalidate("view", "dyn");
  }

  _onWheel(e) {
    if (!this._vb || !this._hasMap()) return;
    e.preventDefault();
    const p = this._clientToSvg(e.clientX, e.clientY);
    if (!p) return;
    const delta = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaMode === 2 ? e.deltaY * 400 : e.deltaY;
    this._zoomAbout(p, Math.exp(Math.max(-100, Math.min(100, delta)) * 0.0025));
  }

  _onPointerDown(e) {
    if (!this._hasMap() || !this._vb) return;
    if (e.pointerType === "mouse" && e.button > 2) return;
    try {
      this._el.svg.setPointerCapture(e.pointerId);
    } catch (err) {
      // The pointer may already be gone.
    }
    this._pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (this._pointers.size === 2) {
      // A second finger zooms; what the first one was drawing is dropped.
      if (this._gesture && this._gesture.type === "edit") this._editRelease(this._gesture, true);
      this._startPinch();
      return;
    }
    if (this._pointers.size > 2) return;
    const primary = e.pointerType !== "mouse" || e.button === 0;
    if (primary && this._pointers.size === 1 && this._edit) {
      const p = this._clientToMap(e.clientX, e.clientY);
      const op = p && this._editPress(p);
      if (op) {
        this._gesture = { type: "edit", id: e.pointerId, op, start: p, sx: e.clientX, sy: e.clientY };
        return;
      }
    }
    this._gesture = {
      type: primary ? "pending" : "pan",
      id: e.pointerId,
      sx: e.clientX,
      sy: e.clientY,
      vb: { ...this._vb },
      px: this._px(),
    };
  }

  _startPinch() {
    const [a, b] = [...this._pointers.values()];
    const mid = [(a.x + b.x) / 2, (a.y + b.y) / 2];
    this._gesture = {
      type: "pinch",
      dist: Math.hypot(a.x - b.x, a.y - b.y) || 1,
      mid,
      anchor: this._clientToSvg(mid[0], mid[1]),
      vb: { ...this._vb },
      px: this._px(),
    };
  }

  _onPointerMove(e) {
    const ptr = this._pointers.get(e.pointerId);
    if (!ptr) return;
    ptr.x = e.clientX;
    ptr.y = e.clientY;
    const g = this._gesture;
    if (!g) return;
    if (g.type === "pinch") {
      if (this._pointers.size < 2 || !g.anchor) return;
      const [a, b] = [...this._pointers.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y) || 1;
      const limits = this._zoomLimits();
      const w = Math.min(limits.max, Math.max(limits.min, (g.vb.w * g.dist) / dist));
      const f = w / g.vb.w;
      const mid = [(a.x + b.x) / 2, (a.y + b.y) / 2];
      const step = g.px * f;
      this._vb = {
        x: g.anchor[0] - (g.anchor[0] - g.vb.x) * f - (mid[0] - g.mid[0]) * step,
        y: g.anchor[1] - (g.anchor[1] - g.vb.y) * f - (mid[1] - g.mid[1]) * step,
        w,
        h: g.vb.h * f,
      };
      this._viewTouched = true;
      this._invalidate("view", "dyn");
      return;
    }
    if (e.pointerId !== g.id) return;
    if (g.type === "edit") {
      const p = this._clientToMap(e.clientX, e.clientY);
      if (p) this._editDrag(g, p, e);
      return;
    }
    const dx = e.clientX - g.sx;
    const dy = e.clientY - g.sy;
    if (g.type === "pending" && Math.hypot(dx, dy) >= PAN_THRESHOLD_PX) g.type = "pan";
    if (g.type === "pan") {
      this._vb = { x: g.vb.x - dx * g.px, y: g.vb.y - dy * g.px, w: g.vb.w, h: g.vb.h };
      this._viewTouched = true;
      this._invalidate("view");
    }
  }

  _onPointerUp(e, cancelled) {
    if (!this._pointers.has(e.pointerId)) return;
    this._pointers.delete(e.pointerId);
    const g = this._gesture;
    if (!g) return;
    if (g.type === "pinch") {
      if (this._pointers.size === 1) {
        // Keep panning with the finger that stays.
        const [id, ptr] = [...this._pointers.entries()][0];
        this._gesture = { type: "pan", id, sx: ptr.x, sy: ptr.y, vb: { ...this._vb }, px: this._px() };
      } else if (this._pointers.size === 0) {
        this._gesture = null;
      }
      return;
    }
    if (e.pointerId !== g.id) return;
    this._gesture = null;
    if (g.type === "edit") {
      if (g.op.kind === "pending" && !cancelled) {
        // Pressed and let go without drawing: a tap.
        const p = this._clientToMap(e.clientX, e.clientY);
        if (p) this._editTap(p);
        return;
      }
      this._editRelease(g, cancelled);
      return;
    }
    if (g.type !== "pending" || cancelled) return;
    // A tap.
    const now = Date.now();
    const last = this._lastTap;
    if (last && now - last.t < DOUBLE_TAP_MS && Math.hypot(e.clientX - last.x, e.clientY - last.y) < DOUBLE_TAP_PX) {
      // The second tap of a double tap only fits the view; the first one
      // already picked a zone.
      this._lastTap = null;
      this._fitView();
      return;
    }
    this._lastTap = { t: now, x: e.clientX, y: e.clientY };
    if (this._edit) {
      const at = this._clientToMap(e.clientX, e.clientY);
      if (at) this._editTap(at);
      return;
    }
    const under = this._root.elementFromPoint(e.clientX, e.clientY);
    const pin = under && under.closest ? under.closest("[data-obstacle]") : null;
    if (pin) {
      this._lastTap = null;
      this._openObstacle(pin.dataset.obstacle);
      return;
    }
    const p = this._clientToMap(e.clientX, e.clientY);
    if (p && this._edit) this._editTap(p);
    else if (p) this._tap(p[0], p[1]);
  }

  // --- Map list ---

  // The mower's maps, with what can be done to each here. Renaming changes
  // the map only; the rest needs the mower not to mow or return. Nothing
  // here makes it drive.
  _renderMapList() {
    const list = this._mapList;
    if (!list) return;
    const maps = (this._status && this._status.maps) || [];
    // A map brought back from its backup comes without its name: it is named first.
    if (list.unnamedAmong) {
      const restored = maps.find((map) => !list.unnamedAmong.includes(map.id));
      if (restored) list.renaming = restored.id;
      // A map that shows up much later is no longer what was just restored.
      if (restored || Date.now() - list.restoredAt > 60000) list.unnamedAmong = null;
    }
    const blocked = this._editBlocked();
    const busy = this._busy;
    const off = blocked || busy ? "disabled" : "";
    const chip = (op, icon, label, attrs = "", cls = "") =>
      `<button type="button" class="chip ${cls}" data-op="${op}" ${attrs}><ha-icon icon="${icon}"></ha-icon>${esc(label)}</button>`;
    const cards = maps
      .map((map) => {
        const name = map.name || `Map ${map.id}`;
        const id = `data-map="${map.id}"`;
        let ops;
        if (list.renaming === map.id) {
          ops =
            `<input type="text" maxlength="24" value="${esc(name)}" data-map-name aria-label="Map name">` +
            `<button type="button" class="chip on" ${id} data-op="rename-save" ${off}>Save</button>` +
            `<button type="button" class="chip" data-op="rename-cancel">Cancel</button>`;
        } else if (map.selected) {
          ops =
            chip("rename", "mdi:pencil-outline", "Rename", `${id} ${off}`) +
            chip("backup", "mdi:content-save-outline", "Back up", `${id} ${off}`) +
            chip("restore", "mdi:backup-restore", "Restore", `${id} ${map.has_backup ? off : "disabled"} title="${map.has_backup ? "" : "The mower holds no backup of this map"}"`) +
            chip("delete", "mdi:delete-outline", "Delete", `${id} ${off}`, "danger");
        } else {
          ops =
            chip("use", "mdi:swap-horizontal", "Use this map", `${id} ${off}`, "on") +
            chip("rename", "mdi:pencil-outline", "Rename", `${id} ${off}`) +
            chip("delete", "mdi:delete-outline", "Delete", `${id} ${off}`, "danger");
        }
        const drawn = this._drawnMap(map.id);
        const zones = drawn ? (drawn.zones || []).length : null;
        const summary = [
          `${num(map.area || 0)} m²`,
          zones !== null ? `${zones} zone${zones === 1 ? "" : "s"}` : "",
          map.has_backup ? "backed up" : "",
        ].filter(Boolean);
        return (
          `<div class="mapcard"><div class="top">${this._mapOutline(map.id)}<div class="info"><div class="name">${esc(name)}` +
          `${map.selected ? '<span class="inuse">In use</span>' : ""}</div><div class="hint">${esc(summary.join(" · "))}</div></div></div>` +
          `<div class="chips ops">${ops}</div></div>`
        );
      })
      .join("");
    // A deleted map keeps its backup in its empty slot, from where it comes back.
    const deleted = ((this._status && this._status.deleted_maps) || [])
      .map(
        (slot) =>
          `<div class="mapcard empty"><div class="info"><div class="name">Empty slot</div>` +
          `<div class="hint">${esc(`Slot ${slot} holds the backup of a deleted map`)}</div></div>` +
          `<button type="button" class="chip" data-slot="${esc(slot)}" data-op="restore-deleted" ${off}><ha-icon icon="mdi:backup-restore"></ha-icon>Restore</button></div>`,
      )
      .join("");
    const slots = maps.length + ((this._status && this._status.deleted_maps) || []).length;
    this._setHtml(
      "mhead",
      this._el.mhead,
      `<button type="button" class="iconbtn" data-op="close" title="Back" aria-label="Back"><ha-icon icon="mdi:chevron-left"></ha-icon></button>` +
        `<span class="title">Maps</span><span class="muted">${esc(`${maps.length} map${maps.length === 1 ? "" : "s"}${slots > maps.length ? `, ${slots - maps.length} empty slot${slots - maps.length === 1 ? "" : "s"}` : ""}`)}</span>`,
    );
    const html =
      `<div class="cards">` +
      cards +
      deleted +
      (blocked ? `<div class="hint warn">${esc(blocked)}</div>` : "") +
      `<div class="hint">None of these makes the mower drive, but switching, restoring and deleting only work while it does not mow or return. ` +
      `Deleting asks twice. A restored map comes back without its name and schedules, and asks for a name. A new map is only made in the app, as the mower drives its boundary.</div></div>`;
    // The name field keeps what is being typed into it.
    const field = this._el.mbody.querySelector("[data-map-name]");
    if (field && field === this._root.activeElement && list.renaming !== null) return;
    this._setHtml("mbody", this._el.mbody, html);
  }

  // Unsaved changes in the editor go when the map changes under them.
  _dropEditsFirst() {
    if (!this._edit || !this._editChanges().length) return true;
    if (!window.confirm("Drop the unsaved changes in the editor?")) return false;
    this._editSync(true);
    return true;
  }

  async _onMapListClick(event) {
    const button = event.target.closest("button");
    const list = this._mapList;
    if (!button || button.disabled || !list) return;
    const mapId = Number(button.dataset.map);
    const map = ((this._status && this._status.maps) || []).find((m) => m.id === mapId);
    const name = map ? map.name || `Map ${map.id}` : "";
    switch (button.dataset.op) {
      case "close":
        this._mapList = null;
        break;
      case "rename":
        list.renaming = mapId;
        break;
      case "rename-cancel":
        list.renaming = null;
        break;
      case "rename-save": {
        const field = this._el.mbody.querySelector("[data-map-name]");
        const value = field ? field.value.trim() : "";
        if (value && (await this._call(DOMAIN, "rename_map", { map_id: mapId, name: value }, { success: "Map renamed" }))) {
          list.renaming = null;
        }
        break;
      }
      case "use":
        if (!this._dropEditsFirst()) return;
        await this._call(DOMAIN, "select_map", { map_id: mapId }, { success: `Switching to ${name}…` });
        break;
      case "backup":
        if (!window.confirm(`Back ${name} up? Its earlier backup is replaced.`)) return;
        await this._call(DOMAIN, "backup_map", {}, { success: "Map backed up" });
        break;
      case "restore":
        if (!this._dropEditsFirst()) return;
        if (!window.confirm(`Put ${name} back as its backup has it? Changes since, schedules and mowing settings may be lost.`)) return;
        if (await this._call(DOMAIN, "restore_map", {}, { success: "Map restored" })) this._editSync(true);
        break;
      case "restore-deleted": {
        const slot = Number(button.dataset.slot);
        if (
          !window.confirm(`Bring the deleted map of slot ${slot} back from its backup? It comes back without its name and schedules, and with the default mowing settings.`)
        )
          return;
        const before = ((this._status && this._status.maps) || []).map((m) => m.id);
        if (await this._call(DOMAIN, "restore_map", { slot }, { success: "Map restored; give it its name again" })) {
          list.unnamedAmong = before;
          list.restoredAt = Date.now();
        }
        break;
      }
      case "delete":
        if (!this._dropEditsFirst()) return;
        if (
          !window.confirm(
            `Delete ${name} with all its zones and settings? ` +
              (map && map.has_backup
                ? "It can be brought back from its backup, without its name, schedules and mowing settings."
                : "It has no backup: a new map has to be mapped in the app, driving the mower."),
          )
        )
          return;
        if (!window.confirm(`Really delete ${name}?`)) return;
        if (await this._call(DOMAIN, "delete_map", { map_id: mapId }, { success: "Map deleted" })) this._editSync(true);
        break;
      default:
        return;
    }
    this._invalidate("maps");
  }

  // --- Settings tab ---

  _openMapList() {
    this._mapList = { renaming: null, unnamedAmong: null };
    this._invalidate("maps");
  }

  // Opens a page of the Settings tab, or its list with null.
  _settingsPage(page) {
    this._maint = { page };
    this._invalidate("maint");
  }

  // The entity of this mower's device in `domain` with the translation key
  // `key` (any, when null), or null when the mower has none.
  _deviceEntity(domain, key) {
    const entities = (this._hass && this._hass.entities) || {};
    if (!this._entityIndex || this._entityIndex.of !== entities || this._entityIndex.entity !== this._config.entity) {
      // Built once for each registry the card is handed.
      const index = new Map();
      const all = new Map();
      const own = entities[this._config.entity];
      if (own && own.device_id) {
        for (const entry of Object.values(entities)) {
          if (entry.device_id !== own.device_id || entry.platform !== DOMAIN) continue;
          const entryDomain = entry.entity_id.split(".")[0];
          if (!index.has(`${entryDomain}:`)) index.set(`${entryDomain}:`, entry.entity_id);
          if (entry.translation_key) {
            const key = `${entryDomain}:${entry.translation_key}`;
            index.set(key, entry.entity_id);
            all.set(key, [...(all.get(key) || []), entry.entity_id]);
          }
        }
      }
      this._entityIndex = { of: entities, entity: this._config.entity, index, all };
    }
    return this._entityIndex.index.get(`${domain}:${key === null ? "" : key}`) || null;
  }

  // Every entity of this mower's device in `domain` with the translation key
  // `key`, in the order of their ids.
  _deviceEntities(domain, key) {
    this._deviceEntity(domain, key);
    return [...(this._entityIndex.all.get(`${domain}:${key}`) || [])].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  }

  // What the rows of the Settings tab are built from: the entities and the
  // feed's settings, and controls that write them.
  _settingsKit() {
    const hass = this._hass;
    const off = this._busy || !this._mower().available;
    const status = this._status || {};
    const state = (id) => (id && hass.states[id]) || null;
    const usable = (st) => st && st.state !== "unavailable";
    const shown = (st) => (st && usable(st) && st.state !== "unknown" ? st.state : "");
    const text = (title, desc) =>
      `<span class="rt"><span class="t">${esc(title)}</span>${desc ? `<span class="d">${esc(desc)}</span>` : ""}</span>`;
    const tile = (icon, tone = "") => `<span class="ricon ${tone}">${icon.startsWith("<") ? icon : `<ha-icon icon="${icon}"></ha-icon>`}</span>`;
    const row = (title, desc, control, lead = "") => `<div class="row">${lead}${text(title, desc)}${control}</div>`;
    const link = (page, title, desc, lead = "", enabled = true) =>
      `<button type="button" class="row" data-page="${esc(page)}" ${enabled ? "" : "disabled"}>${lead}${text(title, desc)}` +
      `<ha-icon class="chev" icon="mdi:chevron-right"></ha-icon></button>`;
    const sw = (on, attrs, label, disabled) =>
      `<button type="button" class="switch ${on ? "on" : ""}" role="switch" aria-checked="${on}" aria-label="${esc(label)}" ${attrs} ${disabled ? "disabled" : ""}></button>`;
    // A switch entity of the mower by its translation key, or null.
    const entitySwitch = (key) => {
      const id = this._deviceEntity("switch", key);
      const st = state(id);
      if (!st) return null;
      const on = st.state === "on";
      const known = on || st.state === "off";
      return { id, on, known, control: (label) => sw(on, `data-toggle="${esc(id)}"`, label, off || !known) };
    };
    const actionSwitch = (on, label, service, field = "enabled") =>
      sw(Boolean(on), `data-service="${esc(service)}" data-field="${esc(field)}" data-on="${on ? 1 : 0}"`, label, off);
    const options = (choices, current) =>
      (choices.some(([value]) => value === current) ? "" : `<option value="" disabled selected>–</option>`) +
      choices.map(([value, label]) => `<option value="${esc(value)}" ${value === current ? "selected" : ""}>${esc(label)}</option>`).join("");
    // A select entity of the mower by its translation key, or null.
    const entitySelect = (key) => {
      const id = this._deviceEntity("select", key);
      const st = state(id);
      if (!st) return null;
      const choices = (st.attributes.options || []).map((option) => [option, option]);
      return {
        id,
        value: shown(st),
        control: (label) =>
          `<select class="in" aria-label="${esc(label)}" data-select="${esc(id)}" ${off || !usable(st) ? "disabled" : ""}>${options(choices, st.state)}</select>`,
      };
    };
    const actionSelect = (label, service, field, choices, current) =>
      `<select class="in" aria-label="${esc(label)}" data-service="${esc(service)}" data-field="${esc(field)}" ${off ? "disabled" : ""}>${options(choices, current)}</select>`;
    const timeEntity = (key, label) => {
      const id = this._deviceEntity("time", key);
      const st = state(id);
      if (!st) return "";
      return row(
        label,
        "",
        `<input class="in" type="time" aria-label="${esc(label)}" value="${esc(shown(st).slice(0, 5))}" data-time="${esc(id)}" ${off || !usable(st) ? "disabled" : ""}>`,
      );
    };
    // The From and Until rows of a time window changed through an action.
    const windowRows = (setting, label, service) => [
      row("From", "", `<input class="in" type="time" aria-label="${esc(label)} from" value="${formatClock(Math.min(setting.start, 1439))}" data-window="${esc(service)}" data-part="start" ${off ? "disabled" : ""}>`),
      row("Until", "", `<input class="in" type="time" aria-label="${esc(label)} until" value="${formatClock(Math.min(setting.end, 1439))}" data-window="${esc(service)}" data-part="end" ${off ? "disabled" : ""}>`),
    ];
    return { hass, off, status, state, usable, shown, text, tile, row, link, sw, entitySwitch, actionSwitch, entitySelect, actionSelect, timeEntity, windowRows };
  }

  // What each page of the Settings tab holds: its title, the summary its row
  // in the list shows, and its rows. A page the mower does not offer is left
  // out.
  _settingsPages() {
    const k = this._settingsKit();
    const { status, state, shown, row, entitySwitch, actionSwitch, entitySelect, actionSelect, timeEntity, windowRows } = k;
    const pages = {};
    const window = (setting) => `${formatClock(Math.min(setting.start, 1439))} – ${formatClock(Math.min(setting.end, 1439))}`;

    const rain = entitySwitch("rain_protection");
    if (rain) {
      const delay = entitySelect("rain_delay");
      const resumes = state(this._deviceEntity("sensor", "rain_protection_end"));
      const at = resumes && shown(resumes) ? new Date(resumes.state) : null;
      const rows = [row("Rain protection", "Back to the station when it rains, and mowing waits", rain.control("Rain protection"))];
      if (delay && rain.on) rows.push(row("After rain", "How long mowing waits once the rain stopped", delay.control("After rain")));
      if (at && !Number.isNaN(at.getTime())) rows.push(row("Mowing resumes", "", `<span class="val">${esc(formatDay(at.getTime() / 1000))}</span>`));
      const wait = delay && delay.value ? (/^\d+ h$/.test(delay.value) ? `waits ${delay.value} after rain` : delay.value) : "";
      pages.rain = {
        title: "Rain protection",
        icon: "mdi:weather-rainy",
        summary: rain.on ? ["On", wait].filter(Boolean).join(" · ") : rain.known ? "Off" : "",
        rows,
      };
    }

    const charging = entitySwitch("charging_period");
    if (charging) {
      const from = shown(state(this._deviceEntity("time", "charging_period_start"))).slice(0, 5);
      const until = shown(state(this._deviceEntity("time", "charging_period_end"))).slice(0, 5);
      const rows = [row("Charging period", "Charge fully only within these hours", charging.control("Charging period"))];
      if (charging.on) rows.push(timeEntity("charging_period_start", "From"), timeEntity("charging_period_end", "Until"));
      pages.charging = {
        title: "Charging period",
        icon: "mdi:clock-outline",
        summary: charging.on ? (from && until ? `${from} – ${until}` : "On") : charging.known ? "Off" : "",
        rows,
      };
    }

    const dnd = status.do_not_disturb;
    const slow = status.low_speed_at_night;
    if (dnd || slow) {
      const rows = [];
      const parts = [];
      if (dnd) {
        rows.push(row("Do Not Disturb", "No task starts; a running one pauses and the mower goes home", actionSwitch(dnd.enabled, "Do Not Disturb", "set_do_not_disturb")));
        if (dnd.enabled) rows.push(...windowRows(dnd, "Do Not Disturb", "set_do_not_disturb"));
        parts.push(dnd.enabled ? window(dnd) : "Off");
      }
      if (slow) {
        rows.push(
          `<div class="group sep">Low speed at night</div>`,
          row("Low speed at night", "The mower drives slowly in this window", actionSwitch(slow.enabled, "Low speed at night", "set_low_speed_at_night")),
        );
        if (slow.enabled) rows.push(...windowRows(slow, "Low speed at night", "set_low_speed_at_night"));
        parts.push(`low speed at night ${slow.enabled ? window(slow) : "off"}`);
      }
      pages.dnd = { title: dnd ? "Do Not Disturb" : "Low speed at night", icon: "mdi:weather-night", summary: parts.join(" · "), rows };
    }

    const stopPoint = status.stop_point_setting;
    if (stopPoint) {
      const rows = [
        row("Start from the stop point", "A new task can go on where an unfinished one stopped", actionSwitch(stopPoint.enabled, "Start from the stop point", "set_start_from_stop_point")),
      ];
      if (stopPoint.enabled) {
        const choices = [1, 2, 3, 4, 5, 6, 7];
        const days =
          (choices.includes(stopPoint.days) ? "" : `<option value="" disabled selected>–</option>`) +
          choices.map((day) => `<option value="${day}" ${day === stopPoint.days ? "selected" : ""}>${day} day${day > 1 ? "s" : ""}</option>`).join("");
        rows.push(row("Keep a stop point", "How long an unfinished task can be continued", `<select class="in" aria-label="Keep a stop point" data-days ${k.off ? "disabled" : ""}>${days}</select>`));
      }
      const kept = stopPoint.days ? ` · a stop point is kept for ${stopPoint.days} day${stopPoint.days > 1 ? "s" : ""}` : "";
      pages.stop_point = { title: "Start from the stop point", icon: "mdi:debug-step-over", summary: stopPoint.enabled ? `On${kept}` : "Off", rows };
    }

    const light = status.light;
    if (light) {
      const scenes = [["standby", "In standby"], ["working", "While working"], ["charging", "While charging"], ["error", "On errors"]];
      const rows = [row("Light only in a period", "Otherwise the lights follow the states below all day", actionSwitch(light.custom_period, "Light only in a period", "set_light", "custom_period"))];
      if (light.custom_period) rows.push(...windowRows(light, "Light period", "set_light"));
      rows.push(`<div class="group sep">Light on</div>`);
      for (const [scene, label] of scenes) rows.push(row(label, "", actionSwitch(light[scene], `Light ${label.toLowerCase()}`, "set_light", scene)));
      const on = scenes.filter(([scene]) => light[scene]).map(([, label]) => label.toLowerCase());
      pages.lights = {
        title: "Lights",
        icon: "mdi:lightbulb-outline",
        tone: "o",
        summary: `${light.custom_period ? window(light) : "All day"} · ${on.length ? on.join(", ") : "always off"}`,
        rows,
      };
    }

    const theft = [
      ["lift_alarm", "Lift alarm", "Sounds when the mower is lifted", "lift alarm"],
      ["off_map_alarm", "Off-map alarm", "Sounds when the mower is carried off the map", "off-map alarm"],
      ["location_reporting", "Real-time location", "Reports where the mower is", "location"],
      ["anti_theft_pin_check", "PIN before power-off", "Asks for the PIN before the mower is switched off", "PIN"],
    ]
      .map(([key, title, desc, short]) => ({ toggle: entitySwitch(key), title, desc, short }))
      .filter((item) => item.toggle);
    if (theft.length) {
      pages.anti_theft = {
        title: "Anti-theft",
        icon: "mdi:shield-outline",
        tone: "o",
        summary: humanize(theft.filter((item) => item.toggle.known).map((item) => `${item.short} ${item.toggle.on ? "on" : "off"}`).join(" · ")),
        rows: theft.map((item) => row(item.title, item.desc, item.toggle.control(item.title))),
      };
    }

    const presence = status.human_presence;
    if (presence) {
      const rows = [row("Human presence alert", "Tells when the camera sees a person", actionSwitch(presence.enabled, "Human presence alert", "set_human_presence_alert"))];
      if (presence.enabled) {
        rows.push(row("Sensitivity", "", actionSelect("Sensitivity", "set_human_presence_alert", "sensitivity", [["low", "Low"], ["medium", "Medium"], ["high", "High"]], presence.sensitivity)));
        rows.push(`<div class="group sep">Watch</div>`);
        for (const [mode, label] of [["standby", "In standby"], ["mowing", "While mowing"], ["returning", "While returning"], ["patrolling", "While patrolling"]]) {
          rows.push(row(label, "", actionSwitch(presence[mode], `Watch ${label.toLowerCase()}`, "set_human_presence_alert", mode)));
        }
        rows.push(
          `<div class="group sep">Then</div>`,
          row("Speak and notify", "The mower speaks and a notification goes out", actionSwitch(presence.voice, "Speak and notify", "set_human_presence_alert", "voice")),
          row("Take a photo", "A photo of the person goes to the app's album", actionSwitch(presence.photo, "Take a photo", "set_human_presence_alert", "photo")),
        );
        if (presence.interval !== null && presence.interval !== undefined) {
          rows.push(row("Alert at most every", "", actionSelect("Alert at most every", "set_human_presence_alert", "interval", [[3, "3 min"], [10, "10 min"], [20, "20 min"]], presence.interval)));
        }
      }
      const parts = presence.enabled
        ? ["On", presence.photo ? "photo" : "", presence.interval ? `at most every ${presence.interval} min` : ""].filter(Boolean)
        : ["Off"];
      pages.presence = { title: "Human presence alert", icon: "mdi:account-alert-outline", tone: "o", summary: parts.join(" · "), rows };
    }

    const voice = status.robot_voice;
    if (voice) {
      const rows = [];
      const parts = [];
      if (voice.language) {
        rows.push(row("Voice language", "Changed in the app", `<span class="val">${esc(voice.language)}</span>`));
        parts.push(voice.language);
      }
      if (voice.volume !== null && voice.volume !== undefined) {
        rows.push(
          `<div class="row wrap">${k.text("Volume", `${voice.volume} %`)}` +
            `<input type="range" min="0" max="100" step="5" value="${esc(voice.volume)}" aria-label="Robot volume" data-service="set_robot_voice" data-field="volume" ${k.off ? "disabled" : ""}></div>`,
        );
        parts.push(`volume ${voice.volume} %`);
      }
      if (voice.prompts) {
        const prompts = [["regular", "Regular notifications"], ["work_status", "Work status prompts"], ["special_status", "Special status prompts"], ["error_status", "Error prompts"]];
        rows.push(`<div class="group sep">Prompts</div>`);
        for (const [kind, label] of prompts) rows.push(row(label, "", actionSwitch(voice.prompts[kind], label, "set_robot_voice", kind)));
        parts.push(`${prompts.filter(([kind]) => voice.prompts[kind]).length} of ${prompts.length} prompts`);
      }
      pages.voice = { title: "Robot voice", icon: "mdi:account-voice", tone: "n", summary: parts.join(" · "), rows };
    }
    return pages;
  }

  // The Settings tab: its groups of rows, or one of its pages.
  _renderMaintenance() {
    if (!this._maint) return;
    // A control in use is not replaced; the page catches up once it is left.
    const active = this._root.activeElement;
    if (active && this._el.maint.contains(active) && /^(INPUT|SELECT)$/.test(active.tagName)) return;
    const pages = this._settingsPages();
    const page = this._maint.page;
    const head = (title) =>
      `<button type="button" class="iconbtn" data-page="" title="Back to the settings" aria-label="Back to the settings"><ha-icon icon="mdi:chevron-left"></ha-icon></button>` +
      `<span class="title">${esc(title)}</span>`;
    let html;
    if (page === "maintenance") {
      this._setHtml("khead", this._el.khead, head("Maintenance"));
      html = this._maintenancePage();
    } else if (page && pages[page]) {
      this._setHtml("khead", this._el.khead, head(pages[page].title));
      html = `<div class="list">${pages[page].rows.filter(Boolean).join("")}</div>`;
    } else {
      if (page) this._maint.page = null;
      this._setHtml("khead", this._el.khead, "");
      html = this._settingsList(pages);
    }
    this._setHtml("kbody", this._el.kbody, html);
  }

  // The list of the Settings tab: Map, Mowing, Functions, Security, General.
  _settingsList(pages) {
    const k = this._settingsKit();
    const { status, tile, row, link, entitySwitch, entitySelect, state } = k;
    const group = (title, rows, first = false) => {
      const shown = rows.filter(Boolean);
      return shown.length ? `<div class="group${first ? "" : " sep"}">${esc(title)}</div><div class="list">${shown.join("")}</div>` : "";
    };
    const page = (id) => (pages[id] ? link(id, pages[id].title, pages[id].summary, tile(pages[id].icon, pages[id].tone || "")) : "");

    // Map
    const maps = status.maps || [];
    const used = maps.find((map) => map.selected);
    const others = maps.filter((map) => !map.selected).map((map) => map.name || `Map ${map.id}`);
    const empty = (status.deleted_maps || []).length;
    const mapSummary = [
      used ? `${used.name || `Map ${used.id}`} in use` : "",
      ...others,
      empty ? `${empty} empty slot${empty > 1 ? "s" : ""} with a backup` : "",
    ]
      .filter(Boolean)
      .join(" · ");
    const mapRows = [
      link("edit", "Map editor", "No-go zones, ignore areas, spot areas, maintenance points, zones", tile(EDIT_MAP_ICON), this._hasMap()),
      link("maps", "Maps", mapSummary || "Rename, back up, restore, use or delete a map", tile("mdi:layers-outline")),
    ];

    // Mowing
    const mowing = [];
    if (this._settingsFeed()) mowing.push(link("mowing", "Mowing settings", this._mowingSummary(), tile(GLYPHS.height, "g")));
    const points = ((this._geometry && this._geometry.maintenance_points) || []).length;
    const wear = (status.consumables || [])
      .filter((item) => item.item !== "robot")
      .map((item) => `${{ blade: "blades", brush: "brush" }[item.item] || item.item} ${Math.floor(Math.max(0, Math.min(100, item.health)))} %`);
    mowing.push(
      link(
        "maintenance",
        "Maintenance",
        [`${points || "No"} maintenance point${points === 1 ? "" : "s"}`, ...wear].join(" · "),
        tile("mdi:wrench-outline", "g"),
      ),
    );

    // Functions: switches in their row, everything else on a page.
    const inline = (key, icon, title, desc) => {
      const toggle = entitySwitch(key);
      return toggle ? row(title, desc, toggle.control(title), tile(icon)) : "";
    };
    const navigation = entitySelect("navigation_path");
    const functions = [
      page("rain"),
      page("charging"),
      inline("frost_protection", "mdi:snowflake", "Frost protection", "Back to the station at 6 °C or below"),
      inline("path_obstacle_avoidance", "mdi:routes", "Pathway obstacle avoidance", "Steers around obstacles on the paths between zones"),
      navigation ? row("Navigation path", "The direct way, or a varying one that spares the lawn", navigation.control("Navigation path"), tile("mdi:map-marker-path")) : "",
      inline("auto_recharge_standby", "mdi:home-lightning-bolt-outline", "Auto recharge", "Back to the station after an hour paused or idle outside it"),
      inline("ai_obstacle_photos", "mdi:camera-outline", "Obstacle photos", "Tap an obstacle on the map to see its photo"),
      page("dnd"),
      page("stop_point"),
    ];

    // Security
    const childLock = entitySwitch("child_lock");
    const security = [
      page("lights"),
      page("anti_theft"),
      page("presence"),
      childLock ? row("Child lock", "The control panel locks after five idle minutes", childLock.control("Child lock"), tile("mdi:lock-outline", "o")) : "",
    ];

    // General
    const general = [
      row(
        "Find my robot",
        "The mower calls out so you can find it by its sound",
        `<button type="button" class="flat" data-find ${k.off ? "disabled" : ""}>Call</button>`,
        tile("mdi:bell-ring-outline", "n"),
      ),
      page("voice"),
      status.time_zone ? row("Time zone", "", `<span class="val">${esc(status.time_zone)}</span>`, tile("mdi:earth", "n")) : "",
    ];
    const update = state(this._deviceEntity("update", null));
    const link_module = status.link_module;
    if (update || link_module) {
      const installed = update ? update.attributes.installed_version : null;
      const latest = update ? update.attributes.latest_version : null;
      const value = !update ? "" : update.state === "on" && latest ? `${latest} available` : update.state === "off" ? "Up to date" : "";
      const module = link_module
        ? `link module${link_module.plan_valid === false ? ", data plan expired" : link_module.plan_valid ? ", data plan valid" : ""}`
        : "";
      general.push(row("Firmware", [installed, module].filter(Boolean).join(" · "), value ? `<span class="val">${esc(value)}</span>` : "", tile("mdi:chip", "n")));
    }
    return (
      group("Map", mapRows, true) +
      group("Mowing", mowing) +
      group("Functions", functions) +
      group("Security", security) +
      group("General", general)
    );
  }

  // The mowing settings in a line: height, efficiency, direction, edges.
  _mowingSummary() {
    const feed = this._settingsFeed();
    const values = (feed && feed.areas && feed.areas["0"]) || {};
    const each = { crisscross: "+45° each session", chequerboard: "+90° each session" }[values.mowing_direction_mode];
    const parts = [
      feed && feed.mode === "per_zone" ? "Per zone" : "",
      values.cutting_height !== undefined && values.cutting_height !== null ? `${values.cutting_height} cm` : "",
      values.efficiency ? (EFFICIENCY_LABELS[values.efficiency] || humanize(values.efficiency)).toLowerCase() : "",
      values.mowing_direction !== undefined && values.mowing_direction !== null ? `${values.mowing_direction}°${each ? `, ${each}` : ""}` : "",
      values.edge_mowing_auto ? "edges after" : "",
    ];
    return parts.filter(Boolean).join(" · ") || "Height, direction, edges and obstacles";
  }

  // The maintenance points to send the mower to, and how worn the blades,
  // the station brush and the mower's own maintenance are.
  _maintenancePage() {
    const status = this._status || {};
    const mower = this._mower();
    const busy = this._busy || !mower.available ? "disabled" : "";
    const points = (this._geometry && this._geometry.maintenance_points) || [];
    const pointRows = points.length
      ? `<div class="list">${points
          .map(
            (point) =>
              `<div class="row"><span class="ricon g"><ha-icon icon="mdi:map-marker-outline"></ha-icon></span>` +
              `<span class="rt"><span class="t">Point ${esc(point.id)}</span>` +
              (point.heading !== null && point.heading !== undefined ? `<span class="d">Faces ${esc(Math.round(point.heading))}°</span>` : "") +
              `</span><button type="button" class="flat" data-go="${esc(point.id)}" ${busy || mower.session_active ? "disabled" : ""}>Go there</button></div>`,
          )
          .join("")}</div>`
      : `<div class="note">This map has no maintenance point. Place one in the map editor.</div>`;
    const consumables = status.consumables;
    const consumableRows = consumables
      ? `<div class="list">${consumables.map((item) => this._consumableRow(item, busy)).join("")}</div>`
      : `<div class="note">Not read from the mower yet.</div>`;
    return (
      `<div class="group">Maintenance point</div>${pointRows}` +
      `<div class="hint">The mower drives to the point and waits there for cleaning or servicing. Keep its way clear. Points are placed in Settings › Map editor.</div>` +
      `<div class="group sep">Consumables</div>${consumableRows}` +
      (consumables ? `<div class="hint">Each button starts the count over after asking. The bar turns amber from 60 % down and red from 20 % down.</div>` : "")
    );
  }

  _consumableRow(item, busy) {
    const info = CONSUMABLES[item.item] || { label: item.item, done: "Replaced", icon: "mdi:wrench-outline" };
    const health = Math.max(0, Math.min(100, item.health));
    const level = health > 60 ? "good" : health > 20 ? "soon" : "now";
    const left =
      item.item === "robot"
        ? `needs maintenance in ${Math.round(item.remaining_hours)} h`
        : `${item.remaining_hours} h left of ${item.total_hours} h`;
    return (
      `<div class="row"><span class="ricon o"><ha-icon icon="${info.icon}"></ha-icon></span>` +
      `<span class="rt"><span class="t">${esc(info.label)}</span><span class="d">${esc(`${Math.floor(health)} % · ${left}`)}</span>` +
      `<span class="meter"><i class="${level}" style="width:${health}%"></i></span></span>` +
      `<button type="button" class="flat" data-reset="${esc(item.item)}" ${busy}>${esc(info.done)}</button></div>`
    );
  }

  async _onMaintenanceClick(e) {
    const button = e.target.closest("button");
    if (!button || button.disabled) return;
    if ("page" in button.dataset) {
      const page = button.dataset.page;
      if (page === "edit") this._openEditor();
      else if (page === "maps") this._openMapList();
      else if (page === "mowing") this._openSettings(null, { inline: true });
      else this._settingsPage(page || null);
      return;
    }
    if (button.dataset.toggle) {
      const on = button.classList.contains("on");
      await this._call("switch", on ? "turn_off" : "turn_on", { entity_id: button.dataset.toggle }, { target: false });
      return;
    }
    if (button.dataset.service) {
      const value = button.dataset.on !== "1";
      const field = button.dataset.field || "enabled";
      if (button.dataset.service === "set_start_from_stop_point" && field === "enabled" && !value) {
        if (!window.confirm("Switch off starting from the stop point? The stop points the mower holds are cleared.")) return;
      }
      await this._call(DOMAIN, button.dataset.service, { [field]: value });
      return;
    }
    if ("find" in button.dataset) {
      await this._call(DOMAIN, "find_robot", {}, { success: "Calling the mower; listen for its sound" });
      return;
    }
    if (button.dataset.go) {
      const id = Number(button.dataset.go);
      if (!window.confirm(`Send the mower to maintenance point ${id}? It drives there and waits.`)) return;
      if (!(await this._beforeDrive("maintenance"))) return;
      await this._call(DOMAIN, "go_to_maintenance_point", { point_id: id }, { success: "On its way to the maintenance point" });
      return;
    }
    if (button.dataset.reset) {
      const info = CONSUMABLES[button.dataset.reset];
      if (!window.confirm(`${info.confirm} Its count starts over.`)) return;
      await this._call(DOMAIN, "reset_consumable", { item: button.dataset.reset }, { success: "Count started over" });
    }
  }

  async _onMaintenanceChange(e) {
    const target = e.target;
    if (target.dataset.service && target.dataset.field && target.value !== "") {
      const numeric = target.type === "range" || /^\d+$/.test(target.value);
      await this._call(DOMAIN, target.dataset.service, { [target.dataset.field]: numeric ? Number(target.value) : target.value });
      return;
    }
    if ("days" in target.dataset && target.value) {
      await this._call(DOMAIN, "set_start_from_stop_point", { days: Number(target.value) });
      return;
    }
    if (target.dataset.select && target.value) {
      await this._call("select", "select_option", { entity_id: target.dataset.select, option: target.value }, { target: false });
    }
  }

  // A time is written once its field is left, not at every digit typed.
  async _onMaintenanceLeave(e) {
    const target = e.target;
    if (target.dataset && target.dataset.window) {
      const setting = (this._status || {})[{ set_do_not_disturb: "do_not_disturb", set_low_speed_at_night: "low_speed_at_night", set_light: "light" }[target.dataset.window]];
      const stored = setting ? setting[target.dataset.part] : null;
      // A period may end at 24:00, which the field shows as 23:59.
      const minutes = stored === null || stored === undefined ? null : Math.min(stored, 1439);
      const current = minutes === null ? "" : formatClock(minutes);
      if (target.value && target.value !== current) {
        await this._call(DOMAIN, target.dataset.window, { [target.dataset.part]: `${target.value}:00` });
        return;
      }
      this._invalidate("maint");
      return;
    }
    if (target.dataset && target.dataset.time) {
      const stateObj = this._hass.states[target.dataset.time];
      const current = stateObj ? String(stateObj.state).slice(0, 5) : "";
      if (target.value && target.value !== current) {
        await this._call("time", "set_value", { entity_id: target.dataset.time, time: `${target.value}:00` }, { target: false });
        return;
      }
    }
    if (target.dataset && (target.dataset.time || target.dataset.select || target.dataset.service || "days" in target.dataset)) this._invalidate("maint");
  }

  // --- Schedules ---

  // The Schedules tab: the sections other modules add, then the mower's own
  // schedules. A section may fill the tab with a page of its own instead.
  _renderSchedules() {
    if (this._tab !== "schedules" || !this._hass) return;
    // A control in use is not replaced; the tab catches up once it is left.
    const active = this._root.activeElement;
    if (active && this._el.schedules.contains(active) && /^(INPUT|SELECT|HA-ENTITY-PICKER)$/.test(active.tagName)) return;
    const parts = [];
    let page = null;
    for (const { section } of this._sections) {
      const out = this._sectionCall(section, "render") || "";
      if (out && typeof out === "object") {
        page = out;
        break;
      }
      if (out) parts.push(out);
    }
    if (page) {
      this._setHtml("schedhead", this._el.schedhead, page.head || "");
      this._setHtml("schedbody", this._el.schedbody, page.body || "");
    } else {
      this._setHtml("schedhead", this._el.schedhead, "");
      this._setHtml("schedbody", this._el.schedbody, parts.join("") + this._schedules(parts.length > 0));
    }
    for (const { section } of this._sections) this._sectionCall(section, "rendered");
  }

  // The schedules of the map in use, each with its tasks and its switch.
  _schedules(below) {
    const hass = this._hass;
    const off = this._busy || !this._mower().available;
    const rows = this._deviceEntities("switch", "schedule")
      .map((id) => hass.states[id])
      .filter(Boolean)
      .map((st) => {
        const on = st.state === "on";
        const known = on || st.state === "off";
        const name = st.attributes.schedule_name || st.attributes.friendly_name || st.entity_id;
        const summary = st.state === "unavailable" ? "Not on the map in use" : scheduleSummary(st.attributes.tasks);
        return (
          `<div class="row"><span class="ricon o"><ha-icon icon="mdi:calendar-month-outline"></ha-icon></span>` +
          `<span class="rt"><span class="t">${esc(name)}</span><span class="d">${esc(summary)}</span></span>` +
          `<button type="button" class="switch ${on ? "on" : ""}" role="switch" aria-checked="${on}" aria-label="${esc(name)}" data-schedule="${esc(st.entity_id)}" ${off || !known ? "disabled" : ""}></button></div>`
        );
      })
      .join("");
    const used = ((this._status && this._status.maps) || []).find((map) => map.selected);
    return (
      `<div class="group${below ? " sep" : ""}">Robot schedules${used ? ` · ${esc(used.name || `Map ${used.id}`)}` : ""}</div>` +
      (rows ? `<div class="list">${rows}</div>` : `<div class="note">The mower has no schedules.</div>`) +
      `<div class="hint">The mower runs one of its own schedules at a time: switching one on switches the other off. Their tasks are set up in the app.</div>`
    );
  }


  // A schedule's switch is the card's own; everything else in the tab goes
  // to the sections.
  async _onSchedulesEvent(e) {
    const button = e.type === "click" && e.target.closest ? e.target.closest("button[data-schedule]") : null;
    if (button) {
      if (button.disabled) return;
      const on = button.classList.contains("on");
      await this._call("switch", on ? "turn_off" : "turn_on", { entity_id: button.dataset.schedule }, { target: false });
      return;
    }
    for (const { section } of this._sections) this._sectionCall(section, "handleEvent", e);
  }

  // --- Sections ---

  // Sets up the sections registered since, for this card. A section that
  // fails to set up is left out.
  _syncSections() {
    for (const type of SECTION_TYPES) {
      if (this._sections.some((s) => s.id === type.id)) continue;
      let section = null;
      try {
        section = type.create(this._sectionHost());
      } catch (err) {
        console.error(`Dreame Mower Card: section ${type.id} failed to set up`, err);
      }
      this._sections.push({ id: type.id, section: section || {} });
    }
  }

  // Calls a section's method, if it has one; what goes wrong there stays
  // there, so the card keeps working without it.
  _sectionCall(section, method, ...args) {
    if (typeof section[method] !== "function") return undefined;
    try {
      return section[method](...args);
    } catch (err) {
      console.error(`Dreame Mower Card: a section's ${method} failed`, err);
      return undefined;
    }
  }

  _eachSection(method) {
    for (const { section } of this._sections) this._sectionCall(section, method);
  }

  // What a section gets to see of the card and do with it.
  _sectionHost() {
    const card = this;
    return {
      get hass() {
        return card._hass;
      },
      get entityId() {
        return card._config ? card._config.entity : null;
      },
      get busy() {
        return card._busy;
      },
      get connected() {
        return card.isConnected;
      },
      get body() {
        return card._el ? card._el.schedbody : null;
      },
      mower: () => card._mower(),
      settingsFeed: () => card._settingsFeed(),
      toast: (text, error = false) => card._toast(text, error),
      refresh: () => card._invalidate("schedules"),
      redrawMap: () => card._invalidate("dyn"),
      // The Mow tab's map buttons and cover, with the map's overlays, which
      // follow once the map shows again.
      refreshMow: () => card._invalidate("toolbar", "dyn"),
      docked: () => card._docked(),
      entity: (domain, key) => (card._config ? card._deviceEntity(domain, key) : null),
    };
  }

  // Lets the sections get ready for `action`, which makes the mower drive:
  // true when it can go ahead, false when one of them called it off (a
  // section that fails calls it off too, since the way may not be clear).
  async _beforeDrive(action) {
    const ready = this._sections.filter(({ section }) => typeof section.beforeDrive === "function");
    if (!ready.length) return true;
    this._busy = true;
    this._invalidate("header", "toolbar", "actions", "settings", "maps", "photo", "maint", "picker", "schedules");
    try {
      for (const { section } of ready) {
        if ((await section.beforeDrive(action)) === false) return false;
      }
      return true;
    } catch (err) {
      console.error("Dreame Mower Card: a section's beforeDrive failed", err);
      this._toast(errorMessage(err), true);
      return false;
    } finally {
      this._busy = false;
      this._invalidate("header", "toolbar", "actions", "settings", "maps", "photo", "maint", "picker", "schedules");
    }
  }

  // --- Map editor ---

  // Edits the current map: what is drawn on it, never what the mower has to
  // drive. Changes collect in a working copy and go out on Save.
  _openEditor() {
    if (!this._hasMap()) return;
    this._settings = null;
    this._log = null;
    this._logPanZoom = null;
    this._picker = false;
    this._mapList = null;
    // The editor works on the map inside the Settings tab; leaving it
    // returns to the tab it was opened from.
    this._editFrom = this._tab;
    this._tab = "settings";
    if (!this._maint) this._maint = { page: null };
    this._edit = { tool: null, items: [], deleted: [], selected: null, zones: [], split: false, splitLine: null, mapId: null, next: 1 };
    this._turning = false;
    this._editSync(true);
    this._invalidate("toolbar", "header", "base", "dyn", "actions", "settings", "log", "picker", "maint");
  }

  // Leaves the map editor, after asking when it holds unsaved changes;
  // true once it is left.
  _closeEditor() {
    if (this._editChanges().length && !window.confirm("Leave the map editor without saving the changes?")) return false;
    this._edit = null;
    this._turning = false;
    this._mapList = null;
    if (this._editFrom === "mow") this._tab = "mow";
    this._editFrom = null;
    this._invalidate("toolbar", "header", "base", "dyn", "actions", "picker", "maps", "maint");
    return true;
  }

  // The working copy follows the map while nothing in it changed. Returns
  // true when it took the map's items over again.
  _editSync(force = false) {
    const e = this._edit;
    const g = this._geometry;
    if (!e || !g) return false;
    if (!force && e.mapId === g.map_id && e.geometry === g) return false;
    if (!force && e.mapId === g.map_id && this._editChanges().length) return false;
    if (e.mapId !== null && e.mapId !== g.map_id) {
      e.zones = [];
      if (this._editChanges().length) this._toast("The mower switched maps; the unsaved changes were dropped", true);
    }
    e.mapId = g.map_id;
    e.geometry = g;
    e.deleted = [];
    const keys = new Set();
    const items = [];
    const add = (kind, item) => {
      const key = `${kind}:${item.id}`;
      keys.add(key);
      items.push({ ...item, kind, key, orig: editShapeKey(item) });
    };
    for (const area of g.no_go || []) {
      add("no_go", { id: area.id, shape: area.shape || "polygon", rect: area.rect, line: area.line, circle: area.circle, polygon: area.polygon });
    }
    for (const area of g.ignore_obstacles || []) add("ignore", { id: area.id, shape: area.shape || "polygon", rect: area.rect, polygon: area.polygon });
    for (const spot of g.spots || []) add("spot", { id: spot.id, shape: spot.shape || "polygon", rect: spot.rect, polygon: spot.polygon });
    for (const point of g.maintenance_points || []) {
      add("maintenance", { id: point.id, shape: "point", point: [point.x, point.y], heading: point.heading ?? null });
    }
    e.items = items;
    // What was selected stays so while the map still has it.
    if (e.selected && !keys.has(e.selected)) e.selected = null;
    return true;
  }

  // What Save sends: new and changed items, and the deleted ones.
  _editChanges() {
    const e = this._edit;
    if (!e) return [];
    const changes = [];
    for (const item of e.items) {
      if (item.id === null) changes.push({ op: "set", item });
      else if (item.shape !== "polygon" && editShapeKey(item) !== item.orig) changes.push({ op: "set", item });
    }
    for (const item of e.deleted) changes.push({ op: "delete", item });
    return changes;
  }

  _editTool() {
    return EDIT_TOOLS.find((tool) => tool.id === (this._edit && this._edit.tool)) || null;
  }

  _editSelected() {
    const e = this._edit;
    return e && e.selected ? e.items.find((item) => item.key === e.selected) || null : null;
  }

  // A press on the map: grab a handle or the selected item, or get ready to
  // draw. Returns what the drag does, or null to let it pan.
  _editPress(p) {
    const e = this._edit;
    if (this._busy) return null;
    const tol = EDIT_HIT_PX * this._px();
    const selected = this._editSelected();
    if (selected && selected.shape !== "polygon") {
      // Grabbed where it was pressed: a handle keeps its offset to the finger.
      const from = JSON.stringify(editGeometry(selected));
      const handle = editHandles(selected).find((h) => Math.hypot(h.at[0] - p[0], h.at[1] - p[1]) <= tol);
      if (handle) {
        const offset = [handle.at[0] - p[0], handle.at[1] - p[1]];
        return { kind: "pending", then: { kind: "handle", item: selected, handle: handle.id, from, offset } };
      }
      if (editHit(selected, p, tol)) return { kind: "pending", then: { kind: "move", item: selected, from } };
    }
    const tool = this._editTool();
    if (!tool || this._editBlocked()) return null;
    if (tool.id === "zones" && !(e.split && e.zones.length === 1)) return null;
    if (tool.shape === "point") return null;
    // Drawing starts once the finger moves; a press let go before is a tap.
    return { kind: "pending", tool };
  }

  _editDrag(g, p, event) {
    const e = this._edit;
    const op = g.op;
    const shift = Boolean(event && event.shiftKey);
    if (op.kind === "pending") {
      if (Math.hypot(event.clientX - g.sx, event.clientY - g.sy) < PAN_THRESHOLD_PX) return;
      const tool = op.tool;
      if (op.then) {
        g.op = op.then;
      } else if (tool.id === "zones") {
        e.splitLine = [g.start[0], g.start[1], g.start[0], g.start[1]];
        g.op = { kind: "split" };
      } else {
        const item = { kind: tool.kind, id: null, key: `new:${e.next++}`, shape: tool.shape, orig: null };
        if (tool.shape === "rectangle") item.rect = [g.start[0], g.start[1], g.start[0], g.start[1]];
        if (tool.shape === "line") item.line = [g.start[0], g.start[1], g.start[0], g.start[1]];
        if (tool.shape === "circle") item.circle = [g.start[0], g.start[1], 0];
        e.items.push(item);
        e.selected = item.key;
        g.op = { kind: "draw", item };
      }
    }
    const current = g.op;
    if (current.kind === "split") {
      const end = shift ? straighten(g.start, p) : p;
      e.splitLine = [g.start[0], g.start[1], end[0], end[1]];
    } else if (current.kind === "draw") {
      const item = current.item;
      if (item.rect) item.rect = editLimitRect(g.start, shift ? squared(g.start, p) : p, editLimits(item));
      if (item.line) item.line = editLimitLine(g.start, shift ? straighten(g.start, p) : p, editLimits(item));
      if (item.circle) item.circle = [g.start[0], g.start[1], clampSize(2 * Math.hypot(p[0] - g.start[0], p[1] - g.start[1]), editLimits(item)) / 2];
    } else {
      const from = JSON.parse(current.from);
      if (current.kind === "move") {
        let [dx, dy] = [p[0] - g.start[0], p[1] - g.start[1]];
        // Held on one axis: the shape moves straight across or along.
        if (shift) Math.abs(dx) >= Math.abs(dy) ? (dy = 0) : (dx = 0);
        Object.assign(current.item, editMoved(from, dx, dy));
      } else {
        const at = [p[0] + current.offset[0], p[1] + current.offset[1]];
        Object.assign(current.item, editHandleMoved(from, current.handle, at, shift, editLimits(current.item)));
      }
    }
    this._invalidate("dyn");
  }

  _editRelease(g, cancelled) {
    const e = this._edit;
    const op = g.op;
    if (op.kind === "split") {
      const line = e.splitLine;
      e.splitLine = null;
      if (!cancelled && Math.hypot(line[2] - line[0], line[3] - line[1]) >= EDIT_MIN_MM) this._splitZone(e.zones[0], line);
    } else if (op.kind === "draw") {
      if (cancelled) {
        e.items = e.items.filter((item) => item !== op.item);
        e.selected = null;
      } else {
        editNormalise(op.item);
      }
    } else if (op.kind !== "pending") {
      if (cancelled) Object.assign(op.item, JSON.parse(op.from));
      else editNormalise(op.item);
    }
    this._invalidate("dyn", "actions");
  }

  // A tap selects what lies under it, or places a maintenance point.
  _editTap(p) {
    const e = this._edit;
    if (!e || this._busy) return;
    const tool = this._editTool();
    const tol = EDIT_HIT_PX * this._px();
    if (tool && tool.id === "zones") {
      const zone = this._shapes.zones.find((z) => pointInPolygon(p[0], p[1], z.points));
      if (!zone) e.zones = [];
      else if (e.zones.includes(zone.id)) e.zones = e.zones.filter((id) => id !== zone.id);
      else e.zones = [...e.zones.slice(-1), zone.id];
      e.split = false;
      this._invalidate("dyn", "actions");
      return;
    }
    // Points first, then the smaller areas over the larger ones.
    const hits = e.items.filter((item) => editHit(item, p, tol)).sort((a, b) => editSize(a) - editSize(b));
    if (hits.length) {
      e.selected = hits[0].key;
    } else if (tool && tool.shape === "point" && !this._editBlocked()) {
      const item = { kind: "maintenance", id: null, key: `new:${e.next++}`, shape: "point", point: [p[0], p[1]], heading: 0, orig: null };
      e.items.push(item);
      e.selected = item.key;
    } else {
      e.selected = null;
    }
    this._invalidate("dyn", "actions");
  }

  // Why the map cannot be changed now, or null.
  _editBlocked() {
    const mower = this._mower();
    if (!mower.available) return "The mower is offline.";
    if (mower.session_active || mower.activity === "returning") return "The map can be changed once the mower no longer mows or returns.";
    return null;
  }

  _editOverlay(tf, pal, px) {
    const e = this._edit;
    const out = [];
    const colors = { no_go: pal.noGo, ignore: pal.ignoreObstacles, spot: pal.spot, maintenance: pal.brand };
    for (const item of e.items) {
      const color = colors[item.kind];
      const selected = item.key === e.selected;
      const outline = selected ? `stroke-dasharray="${num(6 * px)} ${num(4 * px)}"` : "";
      const width = num((selected ? 2.5 : 1.6) * px);
      if (item.shape === "point") {
        const [X, Y] = tf.toMap(item.point[0], item.point[1]);
        if (item.heading !== null && item.heading !== undefined) out.push(svgFacing(tf, item.point, item.heading, color, px));
        out.push(
          `<circle cx="${num(X)}" cy="${num(Y)}" r="${num(9 * px)}" fill="${color}" stroke="#fff" stroke-width="${num(2 * px)}" ${outline}/>` +
            `<path transform="translate(${num(X)} ${num(Y)}) scale(${num(px)})" d="M-3.5 3.5L2 -2M1 -4.5a2.6 2.6 0 1 0 3.5 3.5" fill="none" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/>`,
        );
      } else if (item.shape === "line") {
        out.push(svgPolyline(tf, [item.line.slice(0, 2), item.line.slice(2)], `stroke="${color}" stroke-width="${num(Math.max(2 * OUTLINE_WIDTH, 4 * px))}" stroke-linecap="round" ${outline}`));
      } else if (item.shape === "circle") {
        const [X, Y] = tf.toMap(item.circle[0], item.circle[1]);
        out.push(`<circle cx="${num(X)}" cy="${num(Y)}" r="${num(item.circle[2])}" fill="${color}" fill-opacity=".15" stroke="${color}" stroke-width="${width}" ${outline}/>`);
      } else {
        const points = item.shape === "rectangle" ? rectPoints(item.rect) : pairs(item.polygon || []);
        if (points.length >= 3) out.push(svgPolygon(tf, points, `fill="${color}" fill-opacity=".15" stroke="${color}" stroke-width="${width}" ${outline}`));
      }
      if (selected && item.shape !== "polygon" && item.shape !== "point") out.push(this._editSizeLabel(item, tf, pal, px));
      if (selected && item.shape !== "polygon") {
        for (const handle of editHandles(item)) {
          const [X, Y] = tf.toMap(handle.at[0], handle.at[1]);
          out.push(`<circle cx="${num(X)}" cy="${num(Y)}" r="${num(7 * px)}" fill="#fff" stroke="${pal.brand}" stroke-width="${num(2 * px)}"/>`);
        }
      }
    }
    for (const id of e.zones) {
      const zone = this._shapes.zones.find((z) => z.id === id);
      if (zone) out.push(svgPolygon(tf, zone.points, `fill="none" stroke="${pal.brand}" stroke-width="${num(3 * px)}" stroke-dasharray="${num(8 * px)} ${num(5 * px)}"`));
    }
    if (e.splitLine) {
      out.push(svgPolyline(tf, [e.splitLine.slice(0, 2), e.splitLine.slice(2)], `stroke="${pal.brand}" stroke-width="${num(3 * px)}" stroke-linecap="round"`));
    }
    return `<g pointer-events="none">${out.join("")}</g>`;
  }

  // The size of a shape beside it: width × height, length or width across.
  _editSizeLabel(item, tf, pal, px) {
    const text = editSizeText(item);
    let at;
    if (item.shape === "rectangle") {
      const [x0, y0, x1, y1] = item.rect;
      at = [(x0 + x1) / 2, (y0 + y1) / 2];
    } else if (item.shape === "line") {
      at = [(item.line[0] + item.line[2]) / 2, (item.line[1] + item.line[3]) / 2];
    } else {
      at = item.circle.slice(0, 2);
    }
    const [X, Y] = tf.toMap(at[0], at[1]);
    const fs = 11 * px;
    const w = text.length * fs * 0.6 + 10 * px;
    const h = 18 * px;
    return (
      `<rect x="${num(X - w / 2)}" y="${num(Y - h / 2)}" width="${num(w)}" height="${num(h)}" rx="${num(h / 2)}" fill="${pal.surface}" fill-opacity=".9"/>` +
      `<text x="${num(X)}" y="${num(Y)}" font-size="${num(fs)}" fill="${pal.text}" text-anchor="middle" dominant-baseline="central">${esc(text)}</text>`
    );
  }

  _renderEditPanel() {
    const el = this._el.editpanel;
    const e = this._edit;
    el.hidden = !e;
    if (!e) {
      this._setHtml("editpanel", el, "");
      return;
    }
    this._editSync();
    const blocked = this._editBlocked();
    const tool = this._editTool();
    const changes = this._editChanges();
    const busy = this._busy;
    const chip = (id, icon, label, title) =>
      `<button type="button" class="chip ${(e.tool || "") === id ? "on" : ""}" data-tool="${id}" title="${esc(title)}" aria-pressed="${(e.tool || "") === id}" ${busy ? "disabled" : ""}>` +
      `<ha-icon icon="${icon}"></ha-icon>${esc(label)}</button>`;
    const tools =
      chip("", "mdi:cursor-default-outline", "Select", "Tap something on the map to change it") +
      EDIT_TOOLS.map((t) => chip(t.id, t.icon, t.label, t.hint)).join("");
    const flat = (op, label, cls = "", off = busy) => `<button type="button" class="flat ${cls}" data-edit="${op}" ${off ? "disabled" : ""}>${esc(label)}</button>`;
    let context = "";
    const selected = this._editSelected();
    if (tool && tool.id === "zones") {
      const names = e.zones.map((id) => (this._shapes.zones.find((z) => z.id === id) || {}).name || `Zone ${id}`);
      if (e.zones.length === 1) {
        context =
          `<div><input type="text" maxlength="24" value="${esc(names[0])}" data-zone-name aria-label="Zone name">` +
          (e.split ? `<br><span class="muted">Drag across the zone where it is to be split.</span>` : "") +
          `</div><div class="acts">${flat("rename", "Rename", "", blocked || busy)}${flat("split", e.split ? "Cancel split" : "Split", "", blocked || busy)}</div>`;
      } else if (e.zones.length === 2) {
        context = `<div><b>${esc(names.join(" + "))}</b><br><span class="muted">Neighbouring zones become one.</span></div>${flat("merge", "Merge", "", blocked || busy)}`;
      } else {
        context = `<div>${esc(tool.hint)}</div>`;
      }
    } else if (selected) {
      const label = EDIT_KIND_LABELS[selected.kind];
      const size = editSizeText(selected);
      const note =
        selected.shape === "polygon"
          ? "This shape can only be deleted here"
          : selected.kind === "maintenance"
            ? "Drag to move it"
            : `Drag it or its handles · Shift keeps it ${selected.shape === "line" ? "straight" : "square"}`;
      let facing = "";
      if (selected.kind === "maintenance") {
        // Which way the mower faces there; it keeps what the map says until turned.
        const heading = selected.heading ?? null;
        const mower = this._status && this._status.mower;
        facing =
          `<div class="facing"><span>Faces</span>` +
          `<input type="range" min="0" max="355" step="5" value="${heading === null ? 0 : Math.round(heading / 5) * 5 % 360}" data-point-heading aria-label="Which way the mower faces there">` +
          `<b data-heading-label>${heading === null ? "not known" : `${Math.round(heading)}°`}</b>` +
          (mower && mower.heading !== null && mower.heading !== undefined
            ? `<button type="button" class="flat" data-edit="heading-mower" ${busy ? "disabled" : ""} title="Face the way the mower faces now">Like the mower</button>`
            : "") +
          `</div>`;
      }
      context =
        `<div><b>${esc(label)}</b>${selected.id === null ? " (new)" : ""}${size ? ` · ${esc(size)}` : ""}<br><span class="muted">${esc(note)}</span></div>` +
        flat("delete", "Delete", "danger") +
        facing;
    } else {
      context =
        `<div>${esc(tool ? tool.hint : "Pick what to draw, or tap something on the map to change it.")}` +
        (tool && tool.shape !== "point" ? `<br><span class="muted">Shift keeps it square or straight.</span>` : "") +
        `</div>`;
    }
    const count = changes.length;
    const html =
      `<div class="tools" role="group" aria-label="Editor tools">${tools}</div>` +
      `<div class="callout mid">${context}</div>` +
      (blocked ? `<div class="warn">${esc(blocked)}</div>` : "") +
      `<div class="hint">Changes stay here until <b>Save</b>; none of them makes the mower drive. The mower takes them only while it is not mowing or returning. ` +
      `A new zone, a path or a new map is only made in the app, as the mower drives the boundary.</div>` +
      `<div class="save">${flat("discard", "Discard", "", !count || busy)}` +
      `<button type="button" class="primary" data-edit="save" ${count && !busy && !blocked ? "" : "disabled"}>${count ? `Save ${count} change${count === 1 ? "" : "s"}` : "Save"}</button></div>`;
    const unsaved = this._el.edithead.querySelector(".muted");
    if (unsaved) unsaved.textContent = count ? `${count} unsaved change${count === 1 ? "" : "s"}` : "";
    // The name field keeps what is being typed into it.
    const field = el.querySelector("[data-zone-name]");
    if (field && field === this._root.activeElement && this._html.editpanel && html.includes("data-zone-name")) return;
    // A slider being turned is not replaced under the finger.
    const slider = el.querySelector("[data-point-heading]");
    if (slider && this._turning) return;
    const focused = slider !== null && slider === this._root.activeElement;
    this._setHtml("editpanel", el, html);
    if (focused) {
      const again = el.querySelector("[data-point-heading]");
      if (again) again.focus();
    }
  }

  async _onEditPanelClick(event) {
    const button = event.target.closest("button");
    const e = this._edit;
    if (!button || button.disabled || !e) return;
    if ("tool" in button.dataset) {
      const tool = button.dataset.tool || null;
      e.tool = e.tool === tool ? null : tool;
      e.zones = [];
      e.split = false;
      e.selected = null;
      this._invalidate("dyn", "actions");
      return;
    }
    switch (button.dataset.edit) {
      case "discard":
        this._editSync(true);
        break;
      case "delete": {
        const item = this._editSelected();
        if (!item) break;
        e.items = e.items.filter((other) => other !== item);
        if (item.id !== null) e.deleted.push(item);
        e.selected = null;
        break;
      }
      case "heading-mower": {
        const selected = this._editSelected();
        const mower = this._status && this._status.mower;
        if (selected && selected.kind === "maintenance" && mower && mower.heading !== null && mower.heading !== undefined) {
          selected.heading = Math.round(mower.heading) % 360;
          this._invalidate("dyn", "actions");
        }
        return;
      }
      case "save":
        await this._saveEdits();
        break;
      case "rename": {
        const field = this._el.editpanel.querySelector("[data-zone-name]");
        const name = field ? field.value.trim() : "";
        if (name) await this._call(DOMAIN, "rename_zone", { zone_id: e.zones[0], name }, { success: "Zone renamed" });
        break;
      }
      case "split":
        e.split = !e.split;
        break;
      case "merge": {
        if (!window.confirm("Merge the two zones into one? Their schedules may need to be set up again.")) return;
        if (await this._call(DOMAIN, "merge_zones", { zone_ids: e.zones }, { success: "Zones merged" })) e.zones = [];
        break;
      }
      default:
        return;
    }
    this._invalidate("dyn", "actions");
  }

  async _splitZone(zoneId, line) {
    const e = this._edit;
    if (!window.confirm("Split the zone along this line? The schedules that name it are dropped.")) {
      this._invalidate("dyn");
      return;
    }
    const ok = await this._call(DOMAIN, "split_zone", { zone_id: zoneId, line: line.map((v) => Math.round(v)) }, { success: "Zone split" });
    if (ok && this._edit === e) {
      e.zones = [];
      e.split = false;
    }
    this._invalidate("dyn", "actions");
  }

  // Sends the changes one by one; what failed stays in the working copy.
  async _saveEdits() {
    const e = this._edit;
    const changes = this._editChanges();
    let done = 0;
    for (const change of changes) {
      if (this._edit !== e) return;
      const item = change.item;
      let ok;
      if (change.op === "delete") {
        ok = await this._call(DOMAIN, "delete_map_item", { kind: EDIT_KIND_NAMES[item.kind], item_id: item.id });
        if (ok) e.deleted = e.deleted.filter((other) => other !== item);
      } else {
        const [service, data] = editServiceCall(item);
        const answer = await this._call(DOMAIN, service, data, { response: true });
        ok = Boolean(answer);
        if (ok) {
          if (item.id === null && (answer.id === null || answer.id === undefined)) {
            // Without its number the item cannot be told apart; the map's
            // next copy brings it back.
            e.items = e.items.filter((other) => other !== item);
            if (e.selected === item.key) e.selected = null;
            e.geometry = null;
          } else {
            // The mower numbers a new item; the copy keeps it by that number.
            if (item.id === null) {
              const key = `${item.kind}:${answer.id}`;
              if (e.selected === item.key) e.selected = key;
              item.id = answer.id;
              item.key = key;
            }
            item.orig = editShapeKey(item);
          }
        }
      }
      if (!ok) break;
      done += 1;
    }
    if (done === changes.length) this._toast(done === 1 ? "Change saved" : `${done} changes saved`);
    this._invalidate("dyn", "actions");
  }

  // --- Mowing settings ---

  // The settings the feed reports for the active map, or null before any.
  _settingsFeed() {
    return (this._status && this._status.settings) || null;
  }

  _perZone() {
    const feed = this._settingsFeed();
    return Boolean(feed && feed.mode === "per_zone");
  }

  // Opens the settings page: of `zoneId` while the map follows its per-zone
  // settings, of the whole map otherwise.
  // Opened from the Settings tab (`inline`) they are a page of it, otherwise
  // they cover the card.
  _openSettings(zoneId, { inline = false } = {}) {
    if (!this._settingsFeed()) return;
    const zones = this._shapes.zones;
    let zone = null;
    if (this._perZone()) zone = zones.some((z) => z.id === zoneId) ? zoneId : zones.length ? zones[0].id : null;
    this._settings = { zone, draft: {}, inline };
    this._picker = false;
    this._invalidate("settings", "picker", "maint");
  }

  _closeSettings() {
    this._settings = null;
    this._invalidate("settings", "maint");
  }

  // The zone the page changes, while the map follows its per-zone settings.
  _settingsZone() {
    if (!this._settings || !this._perZone()) return null;
    if (this._settings.zone === null && this._shapes.zones.length) this._settings.zone = this._shapes.zones[0].id;
    return this._settings.zone;
  }

  // The values the page starts from: the zone's own record, or the map-wide
  // one for the map and for a zone that keeps none of its own yet.
  _settingsBase() {
    const feed = this._settingsFeed();
    if (!feed) return {};
    const areas = feed.areas || {};
    const own = this._settingsZone() !== null ? areas[String(this._settingsZone())] : null;
    return own || areas["0"] || {};
  }

  _settingValue(key) {
    const draft = this._settings.draft;
    return key in draft ? draft[key] : this._settingsBase()[key];
  }

  _setSetting(key, value) {
    const draft = this._settings.draft;
    const base = this._settingsBase();
    if (JSON.stringify(base[key]) === JSON.stringify(value)) delete draft[key];
    else draft[key] = value;
    // Avoiding obstacles along the edges needs something that recognises
    // them: switching it on brings the LiDAR along, and it goes off with the
    // last way of recognising obstacles.
    const lidar = this._settingValue("lidar_obstacle_recognition");
    const ai = this._settingValue("ai_obstacle_recognition") || [];
    if (key === "edge_obstacle_avoidance" && value && lidar === false && !ai.length) {
      this._setSetting("lidar_obstacle_recognition", true);
    } else if (key !== "edge_obstacle_avoidance" && lidar === false && !ai.length && this._settingValue("edge_obstacle_avoidance")) {
      this._setSetting("edge_obstacle_avoidance", false);
    }
  }

  _renderSettings() {
    const el = this._el.settings;
    const feed = this._settingsFeed();
    if (!this._settings || !feed) {
      el.hidden = true;
      this._settings = feed ? this._settings : null;
      return;
    }
    el.hidden = false;
    const base = this._settingsBase();
    const has = (key) => key in base;
    const value = (key) => this._settingValue(key);
    const perZone = this._perZone();
    const field = (label, control, { hint = "", off = false, glyph = "", out = "" } = {}) =>
      `<div class="sfield${off ? " off" : ""}"><div class="lab">${glyph ? GLYPHS[glyph] : ""}${esc(label)}${out}</div>${control}` +
      `${hint ? `<div class="hint">${esc(hint)}</div>` : ""}</div>`;
    const row = (label, control, { hint = "", off = false, cls = "" } = {}) =>
      `<div class="row short${off ? " off" : ""}${cls ? ` ${cls}` : ""}"><span class="rt"><span class="t">${esc(label)}</span>` +
      `${hint ? `<span class="d">${esc(hint)}</span>` : ""}</span>${control}</div>`;
    const seg = (key, options) =>
      `<div class="seg">${options
        .map(([option, label]) => `<button type="button" class="${value(key) === option ? "on" : ""}" data-set="${key}" data-value="${esc(option)}"${typeof option === "number" ? " data-number" : ""}>${esc(label)}</button>`)
        .join("")}</div>`;
    const toggle = (key, label, hint, opts = {}) =>
      has(key)
        ? row(
            label,
            `<button type="button" class="switch${value(key) ? " on" : ""}" data-toggle="${key}" role="switch" aria-checked="${value(key) ? "true" : "false"}" aria-label="${esc(label)}"></button>`,
            { hint, ...opts },
          )
        : "";
    const slider = (key, label, min, max, step, unit, glyph) =>
      field(
        label,
        `<div class="range"><span>${esc(`${min}${unit.trim() === "°" ? "°" : ""}`)}</span>` +
          `<input type="range" min="${min}" max="${max}" step="${step}" value="${esc(value(key))}" data-range="${key}" data-unit="${unit}" aria-label="${esc(label)}">` +
          `<span>${esc(`${max}${unit.trim() === "°" ? "°" : ""}`)}</span></div>`,
        { glyph, out: `<b data-out="${key}">${esc(value(key))}${unit}</b>` },
      );
    const group = (title, glyph, rows) => (rows ? `<div class="group">${glyph}${esc(title)}</div><div class="list">${rows}</div>` : "");

    const zones = this._shapes.zones;
    const parts = [
      `<div class="seg" role="group" aria-label="One set of settings for the map, or one per zone">` +
        `<button type="button" class="${perZone ? "" : "on"}" data-mode="map_wide">Whole map</button>` +
        `<button type="button" class="${perZone ? "on" : ""}" data-mode="per_zone">Per zone</button></div>`,
      perZone
        ? field(
            "Settings of the zone",
            `<select class="in zone" aria-label="Zone">${zones
              .map((zone) => `<option value="${zone.id}" ${zone.id === this._settingsZone() ? "selected" : ""}>${esc(zone.name || `Zone ${zone.id}`)}</option>`)
              .join("")}</select>`,
          )
        : "",
      has("cutting_height") ? slider("cutting_height", "Cutting height", 3, feed.height_max || 7, 0.5, " cm", "height") : "",
      has("efficiency")
        ? field("Efficiency", seg("efficiency", [["standard", "Standard"], ["efficient", "Efficient"]]), {
            hint: value("efficiency") === "efficient" ? "Efficient is faster and takes less care around obstacles." : "",
          })
        : "",
      has("turning_method")
        ? field("Turning", seg("turning_method", [["efficient", "Efficient"], ["lawn_care", "Lawn care"]]), {
            hint: value("turning_method") === "lawn_care" ? "Wider turns that spare the lawn." : "",
          })
        : "",
      has("mowing_direction")
        ? field(
            "Mowing direction",
            this._directionPreview(value("mowing_direction")) +
              `<div class="range"><span>0°</span><input type="range" min="0" max="179" step="1" value="${esc(value("mowing_direction"))}" data-range="mowing_direction" data-unit="°" aria-label="Mowing direction"><span>179°</span></div>`,
            { glyph: "angle", out: `<b data-out="mowing_direction">${esc(value("mowing_direction"))}°</b>` },
          )
        : "",
      has("mowing_direction_mode")
        ? field("Each session", seg("mowing_direction_mode", [["fixed", "Same"], ["crisscross", "+45°"], ["chequerboard", "+90°"]]), {
            hint: "Applies once the current cycle is complete.",
          })
        : "",
    ];
    const edges = [
      toggle("edge_mowing_auto", "Mow edges after a task", "After all-area and zone mowing"),
      toggle("edge_mowing_safe", "Safe edge mowing", "Keeps a buffer from the boundary"),
      toggle("edge_blade_offset", "EdgeMaster", "Blade shifted to the side, two laps"),
    ].join("");
    const lidar = value("lidar_obstacle_recognition");
    const ai = value("ai_obstacle_recognition") || [];
    const detects = lidar !== false || ai.length > 0;
    const kinds = [["humans", "Humans"], ["animals", "Animals"], ["objects", "Objects"]];
    const obstacles = [
      toggle("lidar_obstacle_recognition", "LiDAR recognition", "Off lets the mower clear tall grass"),
      has("ai_obstacle_recognition")
        ? row(
            "AI recognition",
            `<div class="chips">${kinds
              .map(([kind, label]) => `<button type="button" class="chip ${ai.includes(kind) ? "on" : ""}" data-ai="${kind}" aria-pressed="${ai.includes(kind)}">${label}</button>`)
              .join("")}</div>`,
            { cls: "wrap" },
          )
        : "",
      toggle("edge_obstacle_avoidance", "Avoid on edges", "May leave grass uncut along the edges"),
      has("obstacle_height")
        ? row("Height above", seg("obstacle_height", [5, 10, 15, 20].map((cm) => [cm, `${cm}`])), { off: lidar === false, hint: "cm" })
        : "",
      has("obstacle_distance")
        ? row("Distance", seg("obstacle_distance", [10, 15, 20].map((cm) => [cm, `${cm}`])), {
            off: !detects,
            hint: value("obstacle_distance") === 10 ? "cm; shorter may scrape obstacles" : "cm",
          })
        : "",
    ].join("");

    const maps = (this._status && this._status.maps) || [];
    const used = maps.find((map) => map.selected);
    this._setHtml(
      "shead",
      this._el.shead,
      `<button type="button" class="iconbtn" data-close title="Back" aria-label="Back"><ha-icon icon="mdi:chevron-left"></ha-icon></button>` +
        `<span class="title">Mowing settings</span><span class="muted">${esc(used ? used.name || `Map ${used.id}` : "")}</span>`,
    );
    // The picker keeps its element across renders unless the zones change.
    const picker = this._el.sbody.querySelector("select.zone");
    if (picker) picker.value = String(this._settingsZone());
    this._setHtml(
      "sbody",
      this._el.sbody,
      parts.join("") +
        group("Edges", GLYPHS.border, edges) +
        group("Obstacles", '<ha-icon icon="mdi:eye-outline" style="--mdc-icon-size:15px"></ha-icon>', obstacles),
    );
    const changed = Object.keys(this._settings.draft).length > 0;
    const off = !changed || this._busy ? "disabled" : "";
    this._setHtml(
      "sfoot",
      this._el.sfoot,
      `<button type="button" class="flat" data-discard ${off}>Discard</button><button type="button" class="primary" data-save ${off}>Save</button>`,
    );
  }

  // The lawns the settings apply to, striped along the direction being set,
  // as the map shows them; the other zones stay plain.
  _directionPreview(direction) {
    const tf = this._tf;
    const zones = this._shapes.zones;
    if (!tf || !zones.length) return "";
    const pal = this._palette();
    const zone = this._settingsZone();
    const edited = zones.filter((z) => zone === null || z.id === zone);
    if (!edited.length) return "";
    let box = null;
    for (const z of edited) {
      for (const [x, y] of z.points) {
        const [X, Y] = tf.toMap(x, y);
        box = box ? [Math.min(box[0], X), Math.min(box[1], Y), Math.max(box[2], X), Math.max(box[3], Y)] : [X, Y, X, Y];
      }
    }
    const pad = Math.max(box[2] - box[0], box[3] - box[1]) * 0.06;
    const id = `direction-${this._uid}`;
    const period = 2 * STRIPE_WIDTH;
    const lawns = zones
      .map((z) => {
        const colors = zoneColors(z.id, pal);
        const mine = edited.includes(z);
        const outline = `stroke="${colors.outline}" stroke-width="${OUTLINE_WIDTH}" stroke-linejoin="round"`;
        return (
          svgPolygon(tf, z.points, `fill="${mine ? colors.fill : pal.background}" ${outline}`) +
          (mine ? svgPolygon(tf, z.points, `fill="url(#${id})"`) : "")
        );
      })
      .join("");
    return (
      `<svg class="preview" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet" ` +
      `viewBox="${num(box[0] - pad)} ${num(box[1] - pad)} ${num(box[2] - box[0] + 2 * pad)} ${num(box[3] - box[1] + 2 * pad)}">` +
      `<defs><pattern id="${id}" patternUnits="userSpaceOnUse" width="${period}" height="${period}" ` +
      `patternTransform="${this._stripeTransform(direction)}">` +
      `<rect width="${period}" height="${STRIPE_WIDTH}" fill="${pal.stripe}"/></pattern></defs>${lawns}</svg>`
    );
  }

  // The stripes of a mowing direction, turned as the map is.
  _stripeTransform(direction) {
    const stripe = (180 - (Number(direction) % 180)) % 180;
    return `rotate(${num(this._tf.rotation - stripe)})`;
  }

  async _onSettingsClick(e) {
    const target = e.target.closest("button");
    if (!target || target.disabled || !this._settings) return;
    const data = target.dataset;
    if ("close" in data) {
      if (Object.keys(this._settings.draft).length && !window.confirm("Leave without saving the changes?")) return;
      this._closeSettings();
    } else if ("discard" in data) {
      this._settings.draft = {};
    } else if ("save" in data) {
      await this._saveSettings();
    } else if (data.mode) {
      await this._setSettingsMode(data.mode);
    } else if (data.toggle) {
      this._setSetting(data.toggle, !this._settingValue(data.toggle));
    } else if (data.set) {
      this._setSetting(data.set, "number" in data ? Number(data.value) : data.value);
    } else if (data.ai) {
      const kinds = new Set(this._settingValue("ai_obstacle_recognition") || []);
      if (kinds.has(data.ai)) kinds.delete(data.ai);
      else kinds.add(data.ai);
      this._setSetting("ai_obstacle_recognition", ["humans", "animals", "objects"].filter((kind) => kinds.has(kind)));
    }
    this._invalidate("settings");
  }

  // A slider shows its value while it moves, and takes it once let go.
  _onSettingsInput(e, done) {
    const picker = e.target.closest("select.zone");
    if (picker && done && this._settings) {
      const zone = Number(picker.value);
      if (Object.keys(this._settings.draft).length && !window.confirm("Switch zones without saving the changes?")) {
        picker.value = String(this._settings.zone);
        return;
      }
      this._settings = { zone, draft: {}, inline: this._settings.inline };
      this._invalidate("settings");
      return;
    }
    const input = e.target.closest("input[data-range]");
    if (!input || !this._settings) return;
    const key = input.dataset.range;
    const out = this._el.settings.querySelector(`[data-out="${key}"]`);
    if (out) out.textContent = `${input.value}${input.dataset.unit || ""}`;
    const stripes = key === "mowing_direction" ? this._el.settings.querySelector("svg.preview pattern") : null;
    if (stripes) stripes.setAttribute("patternTransform", this._stripeTransform(input.value));
    if (!done) return;
    this._setSetting(key, Number(input.value));
    this._invalidate("settings");
  }

  // Writes what was changed in one go, as the page shows it.
  async _saveSettings() {
    const draft = this._settings.draft;
    const fields = { edge_mowing_auto: "automatic_edge_mowing", edge_mowing_safe: "safe_edge_mowing" };
    const data = {};
    for (const [key, value] of Object.entries(draft)) data[fields[key] || key] = value;
    const zone = this._settingsZone();
    if (zone !== null) data.zone_id = zone;
    if (!Object.keys(draft).length) return;
    const ok = await this._call(DOMAIN, "set_mowing_settings", data, { success: "Settings saved" });
    if (ok && this._settings) {
      this._settings.draft = {};
      this._invalidate("settings");
    }
  }

  // Switches the map between one set of settings and a set per zone.
  async _setSettingsMode(mode) {
    if ((mode === "per_zone") === this._perZone()) return;
    const question =
      mode === "per_zone"
        ? "Give each zone its own settings? Zones without any start from the map's settings."
        : "Use one set of settings for the whole map? The zones keep theirs for later.";
    if (!window.confirm(question)) return;
    const ok = await this._call(DOMAIN, "set_mowing_preference_mode", { mode }, { success: "Settings mode changed" });
    if (ok && this._settings) {
      const zones = this._shapes.zones;
      this._settings = { zone: mode === "per_zone" && zones.length ? zones[0].id : null, draft: {}, inline: this._settings.inline };
    }
  }

  // --- Work log ---

  async _openWorkLog() {
    if (!this._hass || !this._config) return;
    this._log = { loading: true, error: null, totals: null, entries: [], filter: "all", detail: null };
    this._invalidate("log");
    const log = this._log;
    try {
      const result = await this._hass.callWS({ type: `${DOMAIN}/work_log`, entity_id: this._config.entity });
      if (this._log !== log) return;
      log.totals = result.totals;
      log.entries = result.entries || [];
    } catch (err) {
      if (this._log !== log) return;
      log.error = errorMessage(err);
    }
    log.loading = false;
    this._invalidate("log");
  }

  async _openWorkLogEntry(entry) {
    const log = this._log;
    if (!log) return;
    const detail = { entry, loading: true, error: null, data: null };
    log.detail = detail;
    this._invalidate("log");
    if (!entry.file) {
      detail.loading = false;
      detail.error = "This task left no details";
      this._invalidate("log");
      return;
    }
    try {
      detail.data = await this._hass.callWS({ type: `${DOMAIN}/work_log/details`, entity_id: this._config.entity, file: entry.file });
    } catch (err) {
      detail.error = errorMessage(err);
    }
    detail.loading = false;
    if (this._log === log && log.detail === detail) this._invalidate("log");
  }

  _onWorkLogClick(e) {
    const target = e.target.closest("button");
    if (!target || !this._log) return;
    const data = target.dataset;
    if ("close" in data) {
      if (this._log.detail) this._log.detail = null;
      else this._log = null;
    } else if (data.filter) {
      this._log.filter = data.filter;
    } else if (data.entry) {
      const entry = this._log.entries.find((item) => String(item.start) === data.entry);
      if (entry) this._openWorkLogEntry(entry);
      return;
    } else if (data.logzoom) {
      const panZoom = this._logPanZoom;
      if (!panZoom) return;
      if (data.logzoom === "fit") panZoom.fit();
      else panZoom.zoomBy(data.logzoom === "in" ? ZOOM_STEP : 1 / ZOOM_STEP);
      return;
    } else if (data.photo) {
      const detail = this._log.detail;
      if (detail && detail.data) this._openObstacle(data.photo, detail.data.obstacles);
      return;
    }
    this._invalidate("log");
  }

  _renderWorkLog() {
    const log = this._log;
    if (!log) {
      this._setHtml("lhead", this._el.lhead, "");
      this._setHtml("lbody", this._el.lbody, "");
      return;
    }
    if (log.detail) {
      const entry = log.detail.entry;
      this._setHtml(
        "lhead",
        this._el.lhead,
        `<button type="button" class="iconbtn" data-close title="Back to the list" aria-label="Back to the list"><ha-icon icon="mdi:chevron-left"></ha-icon></button>` +
          `<span class="title">${esc(`${logTitle(entry)} mowing`)}</span><span class="muted">${esc(formatDay(entry.start))}</span>`,
      );
      this._setHtml("lbody", this._el.lbody, this._workLogDetail(log.detail));
      const map = this._el.lbody.querySelector("svg.logmap");
      if (map && (!this._logPanZoom || this._logPanZoom.svg !== map)) {
        // A tap on a recognised obstacle opens its photo.
        this._logPanZoom = new PanZoom(
          map,
          (e) => {
            const under = this._root.elementFromPoint(e.clientX, e.clientY);
            const pin = under && under.closest ? under.closest("[data-obstacle]") : null;
            const detail = this._log && this._log.detail;
            if (pin && detail && detail.data) this._openObstacle(pin.dataset.obstacle, detail.data.obstacles);
          },
          (zoom) => keepScreenSize(map, zoom),
        );
      }
      return;
    }
    this._logPanZoom = null;
    // The list is the tab itself; only a task has a way back to it.
    this._setHtml("lhead", this._el.lhead, "");
    if (log.loading || log.error) {
      this._setHtml("lbody", this._el.lbody, `<div class="note">${esc(log.error || "Loading…")}</div>`);
      return;
    }
    const totals = log.totals
      ? `<div class="totals"><div><b>${esc(num(log.totals.area))}</b><small>m² mowed</small></div>` +
        `<div><b>${esc(formatMinutes(log.totals.time))}</b><small>mowing</small></div>` +
        `<div><b>${esc(log.totals.count)}</b><small>tasks</small></div></div>`
      : "";
    const filters = [["all", "All"], ["complete", "Complete"], ["stopped", "Stopped"], ["incomplete", "Incomplete"]];
    const filter =
      `<div class="chips filter" role="group" aria-label="Which tasks">` +
      filters
        .map(([id, label]) => `<button type="button" class="chip ${log.filter === id ? "on" : ""}" data-filter="${id}" aria-pressed="${log.filter === id}">${label}</button>`)
        .join("") +
      `</div>`;
    const entries = log.entries.filter((entry) => log.filter === "all" || entry.result === log.filter);
    const rows = entries
      .map((entry) => {
        const result = RESULT_ICONS[entry.result] ? entry.result : "incomplete";
        const facts = [formatDay(entry.start), entry.area !== null && entry.area !== undefined ? `${entry.area} m²` : "", formatMinutes(entry.duration)];
        return (
          `<button type="button" class="row" data-entry="${esc(entry.start)}">` +
          `<ha-icon class="res ${result}" icon="${RESULT_ICONS[result]}"></ha-icon>` +
          `<span class="rt"><span class="t">${esc(`${logTitle(entry)} · ${result}`)}</span><span class="d">${esc(facts.filter(Boolean).join(" · "))}</span></span>` +
          (entry.photos ? `<span class="cam" title="Obstacles photographed"><ha-icon icon="mdi:camera"></ha-icon>${esc(entry.photos)}</span>` : "") +
          `<ha-icon class="chev" icon="mdi:chevron-right"></ha-icon></button>`
        );
      })
      .join("");
    this._setHtml(
      "lbody",
      this._el.lbody,
      totals + filter + (rows ? `<div class="list loglist">${rows}</div>` : `<div class="note">No tasks</div>`),
    );
  }

  // One task: its map with the lanes it mowed, where it stopped, and what
  // there is to know about it.
  _workLogDetail(detail) {
    if (detail.loading || detail.error) return `<div class="note">${esc(detail.error || "Loading…")}</div>`;
    const data = detail.data;
    const map = this._workLogMap(data);
    const zoom = (op, icon, label) =>
      `<button type="button" class="mapbtn" data-logzoom="${op}" title="${label}" aria-label="${label}"><ha-icon icon="${icon}"></ha-icon></button>`;
    const parts = [];
    if (map) {
      parts.push(
        `<div class="logmapwrap">${map}<div class="mapbtns">` +
          zoom("in", "mdi:plus", "Zoom in") +
          zoom("out", "mdi:minus", "Zoom out") +
          zoom("fit", "mdi:fit-to-screen-outline", "Fit the map") +
          `</div></div>`,
      );
    }
    // A task that did not finish: where it stopped, when the mower still
    // holds that place.
    if (data.result === "stopped" || data.result === "incomplete") {
      const names = new Map(((this._geometry && this._geometry.zones) || []).map((zone) => [zone.id, zone.name]));
      const points = this._resumableStopPoints(detail.entry);
      const head = `<b>${esc(RESULT_LABELS[data.result])}</b>`;
      if (points.length) {
        const where = points.map((point) => `${point.progress.toFixed(2)} % in ${names.get(point.zone_id) || `Zone ${point.zone_id}`}`).join(", ");
        parts.push(
          `<div class="callout warn"><ha-icon icon="mdi:debug-step-over"></ha-icon><div>${head}${esc(`${data.result === "stopped" ? "" : " · stopped"} at ${where}`)}` +
            `<br><span class="muted">The next start can go on from here.</span></div></div>`,
        );
      } else {
        const mowed = data.area !== null && data.area !== undefined ? ` · ${data.area}${data.map_area ? ` of ${data.map_area}` : ""} m² mowed` : "";
        parts.push(`<div class="callout warn"><ha-icon icon="mdi:alert-circle-outline"></ha-icon><div>${head}${esc(mowed)}</div></div>`);
      }
    }
    const fact = (title, value) => (value ? `<div class="row short"><span class="rt"><span class="t">${esc(title)}</span></span><span class="val">${esc(value)}</span></div>` : "");
    const mowed = [
      data.area !== null && data.area !== undefined ? `${data.area}${data.map_area ? ` of ${data.map_area}` : ""} m²` : "",
      data.duration !== null && data.duration !== undefined ? formatMinutes(data.duration) : "",
    ].filter(Boolean);
    const height = [data.height ? `${data.height} cm` : "", data.per_zone ? "per-zone settings" : (EFFICIENCY_LABELS[data.efficiency] || "").toLowerCase()].filter(Boolean);
    const rows = [
      fact("Mowed", mowed.join(" · ")),
      fact("Cutting height", height.join(" · ")),
      fact("Started", START_LABELS[data.start_mode] || ""),
      fact("Ended", data.end ? formatDay(data.end) : ""),
    ];
    // The obstacles it met; a pin on the map, or this row, opens a photo.
    const obstacles = (data.obstacles || []).filter((obstacle) => !(obstacle.kind === "obstacle" && obstacle.type !== 0));
    if (obstacles.length) {
      const recognised = obstacles.filter((obstacle) => obstacle.kind === "ai");
      const kinds = [...new Set(recognised.map((obstacle) => aiObstacleKind(obstacle.type).label.toLowerCase()))];
      const photos = recognised.filter((obstacle) => obstacle.image).length;
      const desc = [kinds.length ? humanize(kinds.join(", ")) : `${obstacles.length} met`, recognised.length ? "tap a pin for its photo" : ""].filter(Boolean).join(" · ");
      const first = recognised[0];
      rows.push(
        (first ? `<button type="button" class="row short" data-photo="${esc(obstacleKey(first))}">` : `<div class="row short">`) +
          `<span class="rt"><span class="t">Obstacles</span><span class="d">${esc(desc)}</span></span>` +
          (photos ? `<span class="cam"><ha-icon icon="mdi:camera"></ha-icon>${photos}</span>` : `<span class="val">${obstacles.length}</span>`) +
          (first ? `<ha-icon class="chev" icon="mdi:chevron-right"></ha-icon></button>` : `</div>`),
      );
    }
    for (const fault of data.faults || []) {
      rows.push(`<div class="row short"><span class="rt"><span class="t">${esc(fault.description)}</span><span class="d">${esc(formatDay(fault.time))}</span></span></div>`);
    }
    parts.push(`<div class="list">${rows.filter(Boolean).join("")}</div>`);
    return parts.join("");
  }

  // The stop points an unfinished task left, while the mower still holds
  // them: only for the newest unfinished all-area or zone task of their day.
  _resumableStopPoints(entry) {
    const points = ((this._status && this._status.stop_points) || []).filter((point) => point.progress > 0 && point.progress < 100);
    if (!points.length || !this._log) return [];
    const newest = this._log.entries.find((item) => unfinishedTask(item) && stoppedOnDayOf(item, points));
    return newest && newest.start === entry.start ? points.filter((point) => stoppedOnDayOf(entry, [point])) : [];
  }

  // The map of a task: its lawns, coloured where they were finished, the
  // lanes mowed, the obstacles met and the station.
  _workLogMap(data, { stoppedHere = false } = {}) {
    const g = data.geometry;
    if (!g || !g.bounds) return "";
    const pal = this._palette();
    const rotation = (this._status && this._status.rotation) || 0;
    const box = [...g.bounds];
    if (data.dock) {
      box[0] = Math.min(box[0], data.dock.x - 800);
      box[1] = Math.min(box[1], data.dock.y - 800);
      box[2] = Math.max(box[2], data.dock.x + 800);
      box[3] = Math.max(box[3], data.dock.y + 800);
    }
    const tf = makeTransform(box, rotation);
    const px = Math.max(tf.width, tf.height) / 360;
    const pad = 12 * px;
    const results = new Map((data.zones || []).map((zone) => [zone.id, zone.result]));
    const parts = [];
    for (const zone of g.zones || []) {
      const points = pairs(zone.polygon || []);
      if (points.length < 3) continue;
      const colors = zoneColors(zone.id, pal);
      // Shown before a new start, every zone is lawn to be mowed.
      const done = stoppedHere || ["finished", "edges"].includes(results.get(zone.id));
      parts.push(svgPolygon(tf, points, `fill="${done || !results.size ? colors.fill : pal.background}" stroke="${colors.outline}" stroke-width="${OUTLINE_WIDTH}" stroke-linejoin="round"`));
    }
    for (const area of g.no_go || []) {
      const points = pairs(area.polygon || []);
      if (points.length >= 3) parts.push(svgPolygon(tf, points, `fill="${pal.noGo}" fill-opacity=".15" stroke="${pal.noGo}" stroke-width="${OUTLINE_WIDTH}"`));
    }
    for (const track of data.tracks || []) {
      parts.push(`<path d="${trailPath(tf, track)}" fill="none" stroke="${pal.pathOuter}" stroke-width="${num(Math.max(40, 1.2 * px))}" stroke-linecap="round" stroke-linejoin="round"/>`);
    }
    // Where the task stopped: the end of the last lane it mowed.
    const lastTrack = stoppedHere ? (data.tracks || []).filter((track) => track.length).pop() : null;
    const stopAt = lastTrack ? lastTrack[lastTrack.length - 1] : null;
    // Pins keep their size on screen as the map is zoomed, and the station
    // its real size, but no smaller than it is shown on the main map.
    for (const obstacle of data.obstacles || []) {
      if (obstacle.kind === "obstacle" && obstacle.type !== 0) continue;
      const [X, Y] = tf.toMap(obstacle.x, obstacle.y);
      parts.push(
        `<g data-keep="pin" data-x="${num(X)}" data-y="${num(Y)}">` +
          svgObstaclePin(X, Y, px, pal, obstacle, obstacle.kind === "ai" ? obstacleKey(obstacle) : null) +
          `</g>`,
      );
    }
    if (stopAt) {
      const [X, Y] = tf.toMap(stopAt[0], stopAt[1]);
      const r = 9 * px;
      parts.push(
        `<circle cx="${num(X)}" cy="${num(Y)}" r="${num(r)}" fill="${pal.brand}" stroke="#fff" stroke-width="${num(2 * px)}"/>` +
          `<path d="M${num(X - r * 0.35)} ${num(Y - r * 0.45)}L${num(X + r * 0.45)} ${num(Y)}L${num(X - r * 0.35)} ${num(Y + r * 0.45)}Z" fill="#fff"/>`,
      );
    }
    if (data.dock) {
      const [X, Y] = tf.toMap(data.dock.x, data.dock.y);
      const least = (MOWER_MIN_PX * px) / MOWER_LENGTH;
      const scale = Math.max(MOWER_SCALE, least);
      parts.push(
        `<g data-keep="station" data-x="${num(X)}" data-y="${num(Y)}" data-scale="${scale}" data-least="${least}">` +
          svgStation(X, Y, scale, -(data.dock.angle || 0) + tf.rotation, "#52C3FF", pal, false) +
          `</g>`,
      );
    }
    return (
      `<svg class="logmap" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet" ` +
      `viewBox="${num(-pad)} ${num(-pad)} ${num(tf.width + 2 * pad)} ${num(tf.height + 2 * pad)}">${parts.join("")}</svg>`
    );
  }

  // --- Live state ---

  // Tells what changed in a way the map does not show: the mower found its
  // position or did not, and the codes it starts to report.
  _announce(before, after) {
    if (!before || !after) return;
    if (before.location === "relocating" && after.location === "located") this._toast("Positioning successful");
    if (before.location !== "locating_failed" && after.location === "locating_failed") {
      this._toast("Positioning failed. Move the mower onto the lawn within the map, or back to its station", true);
    }
    if (!before.codes || !after.codes) return;
    const known = new Set(before.codes);
    for (const code of after.codes) {
      if (!known.has(code) && CODE_ALERTS[code]) this._toast(CODE_ALERTS[code]);
    }
  }

  // --- Photos of recognised obstacles ---

  // An obstacle's sheet: its photo, and on the map what can be done with it.
  // Opened from the work log it only shows what was there.
  _openObstacle(key, obstacles = null) {
    const fromLog = obstacles !== null;
    const list = fromLog ? obstacles : (this._status && this._status.obstacles) || [];
    const obstacle = list.find((item) => (fromLog ? item.kind === "ai" : true) && obstacleKey(item) === key);
    if (!obstacle) return;
    this._photo = { obstacle, fromLog, loading: false, error: null, data: null };
    this._invalidate("photo");
    if (obstacle.kind === "ai" && obstacle.image) this._loadPhoto();
  }

  async _ignoreObstacle() {
    const photo = this._photo;
    if (!photo || this._busy) return;
    if (!window.confirm("Ignore this obstacle? The mower forgets it and its icon goes; this cannot be undone.")) return;
    const done = await this._call(DOMAIN, "ignore_obstacle", { obstacle_id: photo.obstacle.id }, { success: "Obstacle ignored" });
    if (done && this._photo === photo) {
      this._photo = null;
      this._invalidate("photo");
    }
  }

  // Opens the map editor with a no-go zone drawn around the obstacle, to be
  // adjusted and saved like any other.
  _obstacleToNoGo() {
    const photo = this._photo;
    if (!photo) return;
    this._photo = null;
    this._invalidate("photo");
    if (!this._edit) this._openEditor();
    const e = this._edit;
    if (!e) return;
    const item = { kind: "no_go", id: null, key: `new:${e.next++}`, shape: "rectangle", rect: obstacleNoGoRect(photo.obstacle), orig: null };
    e.items.push(item);
    e.tool = null;
    e.selected = item.key;
    this._toast("Adjust the no-go zone if needed, then Save");
    this._invalidate("toolbar", "base", "dyn", "actions");
  }

  async _loadPhoto() {
    const photo = this._photo;
    if (!photo || photo.loading) return;
    photo.loading = true;
    photo.error = null;
    this._invalidate("photo");
    try {
      photo.data = await this._hass.callWS({ type: `${DOMAIN}/obstacle_photo`, entity_id: this._config.entity, image: photo.obstacle.image });
    } catch (err) {
      photo.error = errorMessage(err);
    }
    photo.loading = false;
    if (this._photo === photo) this._invalidate("photo");
  }

  _onPhotoClick(e) {
    const target = e.target.closest("button");
    if (!target || !this._photo) return;
    if ("close" in target.dataset) {
      this._photo = null;
      this._invalidate("photo");
    } else if ("retry" in target.dataset) {
      this._loadPhoto();
    } else if ("ignore" in target.dataset) {
      this._ignoreObstacle();
    } else if ("noGo" in target.dataset) {
      this._obstacleToNoGo();
    }
  }

  _renderPhoto() {
    const el = this._el.photo;
    const photo = this._photo;
    el.hidden = !photo;
    if (!photo) {
      this._setHtml("photo", el, "");
      return;
    }
    const obstacle = photo.obstacle;
    const ai = obstacle.kind === "ai";
    const kind = ai ? aiObstacleKind(obstacle.type) : { label: "Obstacle" };
    let picture;
    if (!ai) {
      picture = "";
    } else if (photo.data) {
      const { width, height, boxes } = photo.data;
      picture =
        `<div class="frame"><img alt="" src="data:image/jpeg;base64,${photo.data.image}">` +
        `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">${(boxes || [])
          .map((box) => `<rect x="${box.x}" y="${box.y}" width="${box.w}" height="${box.h}" fill="none" stroke="#EE3C2F" stroke-width="3"/>`)
          .join("")}</svg></div>`;
    } else if (!obstacle.image) {
      picture = `<div class="wait">The mower took no photo of this obstacle.</div>`;
    } else if (photo.error) {
      picture = `<div class="wait">${esc(photo.error)}<button type="button" class="flat" data-retry>Try again</button></div>`;
    } else {
      picture =
        `<div class="wait"><ha-icon icon="mdi:image-sync-outline"></ha-icon>Loading the photo…` +
        `<span>The mower sends it over its own connection, which can take a minute.</span></div>`;
    }
    this._setHtml(
      "photo",
      el,
      `<div class="grip"></div>` +
        `<div class="phead"><span>${esc(kind.label)} <small>${obstacle.confidence ? `· ${esc(obstacle.confidence)} % sure` : ""}</small></span>` +
        `<button type="button" class="iconbtn" data-close title="Close" aria-label="Close"><ha-icon icon="mdi:close"></ha-icon></button></div>` +
        picture +
        `<p>${
          ai ? "The mower recognised this obstacle with its camera and steers around it." : "The mower ran into this obstacle or saw it, and steers around it."
        }</p>` +
        this._obstacleActions(photo),
    );
  }

  // What can be done with an obstacle on the map: ignore one the camera
  // recognised (not while the mower mows), or put a no-go zone around it.
  _obstacleActions(photo) {
    if (photo.fromLog) return "";
    const busy = this._busy ? "disabled" : "";
    const buttons = [`<button type="button" class="big" data-no-go ${busy}><ha-icon icon="mdi:cancel"></ha-icon>No-go zone</button>`];
    if (photo.obstacle.kind === "ai" && photo.obstacle.ignorable && this._mower().activity !== "mowing") {
      buttons.push(`<button type="button" class="big stop" data-ignore ${busy}><ha-icon icon="mdi:eye-off-outline"></ha-icon>Ignore</button>`);
    }
    return `<div class="bigrow">${buttons.join("")}</div>`;
  }

  // --- Service calls and toasts ---

  // Calls a service; true once it went through, or with `response` what the
  // service answered for this card's mower.
  async _call(domain, service, data = {}, { success, target = true, response = false } = {}) {
    if (!this._hass) return false;
    this._busy = true;
    this._invalidate("header", "toolbar", "actions", "settings", "maps", "photo", "maint", "picker", "schedules");
    try {
      const result = await this._hass.callService(
        domain,
        service,
        data,
        target ? { entity_id: this._config.entity } : undefined,
        false,
        response,
      );
      if (success) this._toast(success);
      if (response) return ((result && result.response) || {})[this._config.entity] || {};
      return true;
    } catch (err) {
      this._toast(errorMessage(err), true);
      return false;
    } finally {
      this._busy = false;
      this._invalidate("header", "toolbar", "actions", "settings", "maps", "photo", "maint", "picker", "schedules");
    }
  }

  _toast(message, isError = false) {
    if (!this._el) return;
    const toast = this._el.toast;
    toast.textContent = message;
    toast.classList.toggle("error", isError);
    toast.hidden = false;
    if (this._toastTimer) clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      toast.hidden = true;
      this._toastTimer = null;
    }, TOAST_MS);
  }

  // --- Actions ---

  // The controls under the map: the settings pill and the button that
  // starts mowing, or while a task runs its progress with Pause or
  // Continue and End.
  _renderActions() {
    const el = this._el.controls;
    const mower = this._mower();
    const off = !mower.available || this._busy;
    const activity = mower.activity;
    const mowing = activity === "mowing";
    const returning = activity === "returning";
    const session = Boolean(mower.session_active);
    const kind = this._modeKind();
    const picked = kind ? this._selected[kind].size : 0;
    const controls = this._config.show_controls !== false;
    const big = (action, icon, label, enabled, cls = "") =>
      `<button type="button" class="big ${cls}" data-action="${action}" ${enabled && !off ? "" : "disabled"}>` +
      `<ha-icon icon="${icon}"></ha-icon>${esc(label)}</button>`;
    const parts = [];
    if (session) {
      const progress = typeof mower.progress === "number" ? Math.max(0, Math.min(100, mower.progress)) : null;
      if (progress !== null) {
        parts.push(
          `<div class="progress" role="progressbar" aria-valuenow="${Math.round(progress)}" aria-valuemin="0" aria-valuemax="100"><div style="width:${num(progress)}%"></div></div>`,
        );
      }
      const figs = [];
      if (progress !== null) figs.push(`<span><b>${esc(progress.toFixed(progress < 10 ? 1 : 0))} %</b></span>`);
      if (typeof mower.mowed_area === "number") {
        const total = typeof mower.total_area === "number" && mower.total_area ? ` of ${num(mower.total_area)} m²` : " m²";
        figs.push(`<span><b>${esc(num(mower.mowed_area))}</b>${esc(total)}</span>`);
      }
      if (typeof mower.session_minutes === "number") {
        const minutes = mower.session_minutes;
        const span = minutes >= 60 ? `${Math.floor(minutes / 60)} h ${minutes % 60}` : `${minutes}`;
        figs.push(`<span><b>${esc(span)}</b> min</span>`);
      }
      const current = this._status ? this._status.current_zone : null;
      const zone = this._shapes.zones.find((z) => z.id === current);
      if (zone) figs.push(`<span class="zone">${esc(zone.name)}</span>`);
      if (figs.length) parts.push(`<div class="figs">${figs.join("")}</div>`);
      if (!controls) {
        this._setHtml("actions", el, parts.join(""));
        return;
      }
      // A running task: hold or continue it, or end it where the mower is.
      // On its way home the mower can be stopped where it is instead.
      parts.push(
        `<div class="bigrow">` +
          (mowing ? big("pause", "mdi:pause", "Pause", true, "pause") : big("start", "mdi:play", "Continue", true)) +
          (returning
            ? big("stop-returning", "mdi:home-remove-outline", "End returning", true, "stop")
            : big("end", "mdi:stop", "End", true, "stop")) +
          `</div>`,
      );
      parts.push(this._settingsPill(true));
    } else if (!controls) {
      this._setHtml("actions", el, "");
      return;
    } else {
      parts.push(this._settingsPill(false));
      // A start that may go on from where an unfinished task stopped asks
      // first; the button says so.
      const stops = !kind || kind === "zones" ? this._pendingStopPoints(kind ? [...this._selected.zones] : null) : [];
      const least = stops.length ? Math.min(...stops.map((point) => point.progress)) : null;
      const mode = MODES.find((m) => m.kind === kind);
      const label = !kind ? "Mow all" : picked ? `Mow ${picked} ${picked === 1 ? mode.one : mode.noun}` : `Mow ${mode.noun}`;
      let note = "";
      if (stops.length) note = `can go on from ${Math.floor(least)} %`;
      else if ((mower.codes || []).includes(RAIN_CODE)) note = "rain protection";
      const enabled = !returning && (!kind || picked > 0);
      parts.push(
        `<button type="button" class="primary" data-action="start" ${enabled && !off ? "" : "disabled"}>` +
          `<ha-icon icon="mdi:play"></ha-icon>${esc(label)}${note ? `<small>· ${esc(note)}</small>` : ""}</button>`,
      );
    }
    if (this._config.show_header === false && this._config.show_controls !== false) {
      // Without the status row, its buttons join the controls.
      const home = returning
        ? big("stop-returning", "mdi:home-remove-outline", "End returning", true)
        : big("recharge", "mdi:home-import-outline", "Recharge", !this._docked());
      parts.push(`<div class="bigrow">${home}${big("find", "mdi:map-marker-radius", "Find my robot", true)}</div>`);
    }
    this._setHtml("actions", el, parts.join(""));
  }

  // A line with the mowing settings the next task uses; it opens them.
  _settingsPill(running) {
    const feed = this._settingsFeed();
    if (!feed) return "";
    const areas = feed.areas || {};
    // With per-zone settings, those of the one zone picked.
    const picked = this._modeKind() === "zones" && this._selected.zones.size === 1 ? [...this._selected.zones][0] : null;
    const zone = feed.mode === "per_zone" && picked !== null ? picked : null;
    const values = (zone !== null && areas[String(zone)]) || areas["0"] || {};
    const items = [];
    if (values.cutting_height !== undefined && values.cutting_height !== null) items.push(`<span class="v">${GLYPHS.height}${esc(values.cutting_height)} cm</span>`);
    if (values.mowing_direction !== undefined && values.mowing_direction !== null) items.push(`<span class="v">${GLYPHS.angle}${esc(values.mowing_direction)}°</span>`);
    if (values.efficiency) items.push(`<span class="v">${esc(EFFICIENCY_LABELS[values.efficiency] || humanize(values.efficiency))}</span>`);
    if (values.edge_mowing_auto && !running) items.push(`<span class="v">${GLYPHS.border}Edges after</span>`);
    if (!items.length) items.push(`<span class="v">Mowing settings</span>`);
    const name = zone !== null ? (this._shapes.zones.find((z) => z.id === zone) || {}).name : null;
    const title = `Mowing settings${name ? ` of ${name}` : ""}${running ? "; set before the next task" : ""}`;
    return (
      `<button type="button" class="pill" data-action="settings" data-zone="${zone === null ? "" : zone}" title="${esc(title)}" aria-label="${esc(title)}" ${running || this._busy ? "disabled" : ""}>` +
      items.join('<span class="dot">·</span>') +
      (running ? `<span class="later">set before the next task</span>` : "") +
      `<ha-icon class="chev" icon="mdi:chevron-right"></ha-icon></button>`
    );
  }

  async _onActionClick(e) {
    const button = e.target.closest("button[data-action]");
    if (!button || button.disabled) return;
    switch (button.dataset.action) {
      case "start":
        await this._start();
        break;
      case "pause":
        await this._call("lawn_mower", "pause");
        break;
      case "end":
        // The task ends where the mower is; it keeps where each zone stopped.
        if (window.confirm("End mowing? The mower stops where it is, and the next task can continue from there.")) {
          await this._call(DOMAIN, "end_task");
        }
        break;
      case "recharge":
        // During a task the task is kept, to continue after charging.
        if (!(await this._beforeDrive("recharge"))) break;
        await this._call(DOMAIN, "recharge");
        break;
      case "stop-returning":
        await this._call(DOMAIN, "stop_returning");
        break;
      case "find":
        await this._call(DOMAIN, "find_robot", {}, { success: "Calling the mower; listen for its sound" });
        break;
      case "settings":
        this._openSettings(button.dataset.zone === "" ? null : Number(button.dataset.zone));
        break;
      default:
        break;
    }
  }

  // Mow the whole map, or what was picked on it; a paused task continues.
  async _start() {
    let mower = this._mower();
    const kind = this._modeKind();
    let picked = kind ? this._shapes[kind].filter((shape) => this._selected[kind].has(shape.id)) : [];
    if (kind && !picked.length && !mower.session_active) return;
    // A new all-area or zone task may go on from where an unfinished one stopped.
    let resume;
    if (!mower.session_active && (!kind || kind === "zones")) {
      resume = await this._askFromStopPoint(kind ? picked.map((zone) => zone.id) : null);
      if (resume === null) return;
      // The question may have stood a while: a task may have started since.
      mower = this._mower();
      if (kind) picked = this._shapes[kind].filter((shape) => this._selected[kind].has(shape.id));
      if (kind && !picked.length && !mower.session_active) return;
    }
    // While it rains the mower stays home; started anyway, it mows.
    const raining = (mower.codes || []).includes(RAIN_CODE);
    if (raining) {
      const choice = await this._choose(
        "Rain protection is active",
        "The mower stays home while it rains. Start mowing anyway? The rain protection is cleared first.",
        [
          { id: "anyway", label: "Clear it and start mowing" },
          { id: "", label: "Not now", plain: true },
        ],
      );
      if (choice !== "anyway") return;
    }
    if (!(await this._beforeDrive("start"))) return;
    // Getting ready may have taken a while: look again.
    mower = this._mower();
    if (kind) picked = this._shapes[kind].filter((shape) => this._selected[kind].has(shape.id));
    if (kind && !picked.length && !mower.session_active) return;
    if (raining &&!(await this._call(DOMAIN, "clear_rain_protection"))) return;
    if (mower.session_active) {
      // Continue the running session, whatever it mows.
      await this._call("lawn_mower", "start_mowing");
      return;
    }
    const fromStopPoint = resume === undefined ? {} : { from_stop_point: resume };
    if (!kind) {
      await this._call(DOMAIN, "start_all_area_mowing", fromStopPoint);
      return;
    }
    let ok;
    if (kind === "edges") {
      ok = await this._call(DOMAIN, "start_edge_mowing", { contour_ids: picked.map((edge) => edge.contour) }, { success: "Edge mowing started" });
    } else if (kind === "spots") {
      ok = await this._call(DOMAIN, "start_spot_mowing", { spot_area_ids: picked.map((spot) => spot.id) }, { success: "Spot mowing started" });
    } else {
      ok = await this._call(
        DOMAIN,
        "start_zone_mowing",
        { zone_ids: picked.map((zone) => zone.id), ...fromStopPoint },
        { success: "Zone mowing started" },
      );
    }
    if (ok) {
      this._selected[kind].clear();
      this._invalidate("toolbar", "dyn", "actions");
    }
  }

  // The stop points a new task over `zoneIds` (or every zone) could go on
  // from; Start asks about them, and says so beforehand.
  _pendingStopPoints(zoneIds) {
    if (!(this._status && this._status.stop_point_start)) return [];
    // With the setting off the mower no longer goes on from a stop point.
    if (this._status.stop_point_setting && !this._status.stop_point_setting.enabled) return [];
    return ((this._status && this._status.stop_points) || []).filter(
      (point) => point.progress > 0 && point.progress < 100 && (!zoneIds || zoneIds.includes(point.zone_id)),
    );
  }

  // When an unfinished task left a stop point in a zone about to be mowed
  // (`zoneIds`, or every zone), asks whether to go on from there: true or
  // false, null when the start is called off, undefined when nothing is left.
  async _askFromStopPoint(zoneIds) {
    const points = this._pendingStopPoints(zoneIds);
    if (!points.length) return undefined;
    const names = new Map(((this._geometry && this._geometry.zones) || []).map((zone) => [zone.id, zone.name]));
    const lines = points
      .map((point) => esc(`${names.get(point.zone_id) || `Zone ${point.zone_id}`}: ${point.progress.toFixed(2)} % mowed on ${point.date}`))
      .join("<br>");
    const asked = this._choose(
      "Start from the stop point?",
      "Only the rest of the unfinished zones is mowed; the other zones are mowed from the beginning.",
      [
        { id: "resume", label: "Start from the stop point" },
        { id: "over", label: "Start from the beginning", plain: true },
      ],
      `<div class="cpreview"><div class="note">Loading what was mowed…</div></div><small class="cnote">${lines}</small>`,
    );
    this._previewStoppedTask(points);
    const choice = await asked;
    return choice === null ? null : choice === "resume";
  }

  // Shows in the open question what the unfinished task mowed and where it
  // stopped, from its record in the work log; leaves the question without a
  // map when there is none.
  async _previewStoppedTask(points) {
    // This question's own preview: a closed or newer question is left alone.
    const el = this._el.choice.querySelector(".cpreview");
    const place = (html) => {
      if (el && el.isConnected) el.innerHTML = html;
    };
    const zoneIds = new Set(points.map((point) => point.zone_id));
    const stoppedThatDay = (entry) => stoppedOnDayOf(entry, points);
    try {
      const list = await this._hass.callWS({ type: `${DOMAIN}/work_log`, entity_id: this._config.entity });
      const candidates = (list.entries || [])
        .filter((entry) => entry.file && unfinishedTask(entry))
        .filter(stoppedThatDay)
        .slice(0, 3);
      for (const entry of candidates) {
        if (!el || !el.isConnected) return;
        const data = await this._hass.callWS({ type: `${DOMAIN}/work_log/details`, entity_id: this._config.entity, file: entry.file });
        // The task has to be one on this map that worked these zones; the
        // stop points may stem from different tasks, so one zone will do.
        const zones = new Set(((data.geometry && data.geometry.zones) || []).map((zone) => zone.id));
        const worked = new Set((data.zones || []).map((zone) => zone.id));
        if (!(data.tracks || []).length || ![...zoneIds].every((id) => zones.has(id))) continue;
        if (worked.size && ![...zoneIds].some((id) => worked.has(id))) continue;
        place(this._workLogMap(data, { stoppedHere: true }) || "");
        return;
      }
    } catch (err) {
      // Without the work log the question stands without a map.
    }
    place("");
  }

  // A sheet with a question and a few answers; resolves with the id of the
  // one picked, or null when it is closed.
  _choose(title, text, options, extra = "") {
    const el = this._el.choice;
    if (this._chosen) this._chosen(null);
    return new Promise((resolve) => {
      const done = (id) => {
        if (this._chosen !== done) return;
        this._chosen = null;
        el.hidden = true;
        el.onclick = null;
        this._invalidate("photo");
        resolve(id);
      };
      this._chosen = done;
      el.innerHTML =
        `<div class="grip"></div>` +
        `<div class="phead"><span>${esc(title)}</span>` +
        `<button type="button" class="iconbtn" data-choice="" title="Close" aria-label="Close"><ha-icon icon="mdi:close"></ha-icon></button></div>` +
        `<p>${esc(text)}</p>` +
        extra +
        `<div class="pactions">${options
          .map((option) => `<button type="button" class="${option.plain ? "big" : "primary"}" data-choice="${esc(option.id)}">${esc(option.label)}</button>`)
          .join("")}</div>`;
      el.onclick = (e) => {
        const button = e.target.closest("[data-choice]");
        if (button) done(button.dataset.choice || null);
      };
      el.hidden = false;
      this._invalidate("photo");
    });
  }


}

// === Card editor ===

// Makes sure the frontend's entity picker is defined; it is loaded lazily
// by the editors of the built-in cards.
async function loadEntityPicker() {
  if (customElements.get("ha-entity-picker") || !window.loadCardHelpers) return;
  try {
    const helpers = await window.loadCardHelpers();
    const card = await helpers.createCardElement({ type: "entities", entities: [] });
    if (card && card.constructor && card.constructor.getConfigElement) await card.constructor.getConfigElement();
  } catch (err) {
    // Fall back to a plain select.
  }
}

class DreameMowerCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._config || !this._hass) return;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.innerHTML = `<style>
        :host { display: block; }
        label { display: flex; flex-direction: column; gap: 4px; color: var(--secondary-text-color); }
        select { font: inherit; padding: 6px; color: var(--primary-text-color); background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 6px; }
      </style><div class="root"></div>`;
    }
    const root = this.shadowRoot.querySelector(".root");
    if (customElements.get("ha-entity-picker")) {
      if (!this._picker) {
        root.innerHTML = "";
        this._picker = document.createElement("ha-entity-picker");
        this._picker.label = "Entity";
        this._picker.includeDomains = ["lawn_mower"];
        this._picker.addEventListener("value-changed", (e) => this._setEntity(e.detail.value));
        root.appendChild(this._picker);
      }
      this._picker.hass = this._hass;
      this._picker.value = this._config.entity || "";
      return;
    }
    const ids = Object.keys(this._hass.states)
      .filter((id) => id.startsWith("lawn_mower."))
      .sort();
    const options = ids
      .map((id) => {
        const name = this._hass.states[id].attributes.friendly_name || id;
        return `<option value="${esc(id)}" ${id === this._config.entity ? "selected" : ""}>${esc(name)} (${esc(id)})</option>`;
      })
      .join("");
    const html = `<label>Entity<select>${this._config.entity && !ids.includes(this._config.entity) ? `<option selected>${esc(this._config.entity)}</option>` : ""}${options}</select></label>`;
    if (this._fallbackHtml !== html) {
      this._fallbackHtml = html;
      root.innerHTML = html;
      root.querySelector("select").addEventListener("change", (e) => this._setEntity(e.target.value));
    }
  }

  _setEntity(entity) {
    if (!entity || entity === this._config.entity) return;
    this._config = { ...this._config, entity };
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true }));
  }
}

// === Registration ===

// The helpers a section of the Schedules tab may use; set before the card is
// defined, which is when sections register.
DreameMowerCard.helpers = Object.freeze({
  DOMAIN,
  RESUBSCRIBE_DELAYS,
  GLYPHS,
  MONTH_NAMES,
  esc,
  humanize,
  num,
  pad2,
  formatTime,
  formatDayOf,
  errorMessage,
  safeUnsubscribe,
  loadEntityPicker,
});

if (!customElements.get(CARD_TYPE)) customElements.define(CARD_TYPE, DreameMowerCard);
if (!customElements.get(EDITOR_TYPE)) customElements.define(EDITOR_TYPE, DreameMowerCardEditor);
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === CARD_TYPE)) {
  window.customCards.push({
    type: CARD_TYPE,
    name: "Dreame Mower Card",
    description: "Live map of a Dreame mower with zone and spot mowing",
    preview: true,
  });
}
