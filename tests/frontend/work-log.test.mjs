import assert from "node:assert/strict";
import { test } from "node:test";

import { $, $$, DOCKED, GEOMETRY, MOWER, click, fakeHass, load, mount, openTab, plain, sendFeed, settle, subscribed } from "./harness.mjs";

// --- The work log ---

const WORK_LOG = "dreame_mower/work_log/subscribe";
const TASK = { start: 1791540000, duration: 39, area: 68.4, mode: "all_area", result: "complete", scheduled: true, file: "ali_dreame/task.json", photos: 0 };
const OLDER = { ...TASK, start: 1791450000, file: "ali_dreame/older.json" };

async function sendWorkLog(window, hass, event) {
  const [subscription] = subscribed(hass, WORK_LOG);
  subscription.callback(event);
  await settle(window);
}

test("the work log shows the kept tasks while the cloud is read", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass();
  const card = await mount(window, hass);
  await openTab(window, card, "history");
  const body = () => $(card, ".view.worklog .sbody");

  assert.deepEqual(plain(subscribed(hass, WORK_LOG).map((s) => s.message)), [{ type: WORK_LOG, entity_id: MOWER }]);
  assert.equal(body().textContent, "Loading…");

  await sendWorkLog(window, hass, { totals: null, entries: [OLDER], refreshing: true, error: null });
  assert.equal($$(card, ".loglist .row").length, 1);
  assert.equal($(card, ".lognote").textContent, "Updating…");

  await sendWorkLog(window, hass, { totals: { area: 100, time: 80, count: 2, start: 1 }, entries: [TASK, OLDER], refreshing: false, error: null });
  assert.equal($$(card, ".loglist .row").length, 2);
  assert.equal($(card, ".lognote"), null);

  // A failed read keeps the tasks and says so.
  await sendWorkLog(window, hass, { totals: null, entries: [TASK], refreshing: false, error: "The work log is not available right now" });
  assert.equal($$(card, ".loglist .row").length, 1);
  assert.match($(card, ".lognote").textContent, /not available right now; showing the kept tasks/);

  await openTab(window, card, "mow");
  assert.deepEqual(subscribed(hass, WORK_LOG), []);
});

test("an empty work log that cannot be read says why", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass();
  const card = await mount(window, hass);
  await openTab(window, card, "history");

  await sendWorkLog(window, hass, { totals: null, entries: [], refreshing: false, error: "The work log is not available right now" });

  assert.equal($(card, ".view.worklog .sbody").textContent, "The work log is not available right now");
});

test("the work log follows the socket coming back", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass();
  const card = await mount(window, hass);
  await openTab(window, card, "history");
  await sendWorkLog(window, hass, { totals: null, entries: [TASK], refreshing: false, error: null });

  hass.fire("disconnected");
  hass.fire("ready");
  await settle(window);

  assert.equal(subscribed(hass, WORK_LOG).length, 1);
  assert.equal($$(card, ".loglist .row").length, 1);
});

test("a task opened again is shown without asking for its details again", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass({ ws: (m) => (m.type === "dreame_mower/work_log/details" ? { result: "complete", area: 68.4, map_area: 75, duration: 39, obstacles: [], faults: [] } : {}) });
  const card = await mount(window, hass);
  await openTab(window, card, "history");
  await sendWorkLog(window, hass, { totals: null, entries: [TASK], refreshing: false, error: null });

  for (let i = 0; i < 2; i++) {
    await click(window, $(card, `.loglist [data-entry="${TASK.start}"]`));
    assert.match($(card, ".view.worklog .sbody").textContent, /68\.4 of 75 m²/);
    await click(window, $(card, ".view.worklog [data-close]"));
  }

  assert.equal(hass.calls.filter((m) => m.type === "dreame_mower/work_log/details").length, 1);
});

test("the work log is followed again once a reloaded mower is back", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass();
  const card = await mount(window, hass);
  await openTab(window, card, "history");
  await sendWorkLog(window, hass, { totals: null, entries: [TASK], refreshing: false, error: null });
  const [first] = subscribed(hass, WORK_LOG);

  await sendWorkLog(window, hass, { type: "closed" });
  assert.equal(first.active, false);
  assert.deepEqual(subscribed(hass, WORK_LOG), []);
  // What was shown stays meanwhile.
  assert.equal($$(card, ".loglist .row").length, 1);

  await new Promise((resolve) => setTimeout(resolve, 2100));
  await settle(window);
  assert.equal(subscribed(hass, WORK_LOG).length, 1);
});

test("the question about the stop point shows what the unfinished task mowed", async () => {
  const window = load("dreame-mower-card.js");
  const start = Date.UTC(2026, 9, 12, 10) / 1000;
  const stopped = { ...TASK, start, mode: "zone", result: "stopped", file: "ali_dreame/stopped.json" };
  const hass = fakeHass({
    ws: (m) => {
      if (m.type === "dreame_mower/work_log") return { totals: null, entries: [stopped] };
      if (m.type === "dreame_mower/work_log/details")
        return { geometry: { bounds: [0, 0, 10000, 8000], zones: [{ id: 4, polygon: [0, 0, 5000, 0, 5000, 5000] }] }, zones: [{ id: 4, result: "unfinished" }], tracks: [[[100, 100], [900, 900]]], obstacles: [] };
      return {};
    },
  });
  const card = await mount(window, hass);
  const day = new Date(start * 1000);
  const date = `${day.getFullYear()}.${String(day.getMonth() + 1).padStart(2, "0")}.${String(day.getDate()).padStart(2, "0")}`;
  await sendFeed(window, hass, GEOMETRY, { ...DOCKED, stop_point_start: true, stop_points: [{ zone_id: 4, progress: 30.21, date }] });

  card._askFromStopPoint([4]);
  await settle(window);

  assert.deepEqual(
    hass.calls.map((m) => m.type),
    ["dreame_mower/work_log", "dreame_mower/work_log/details"],
  );
  assert.ok($(card, ".cpreview svg"));
});

test("a task's obstacle photos show as a gallery that opens them one by one", async () => {
  const window = load("dreame-mower-card.js");
  const ai = (image, type = 99) => ({ kind: "ai", type, x: 100, y: 100, image });
  const details = {
    result: "complete",
    obstacles: [ai("1.1_0"), ai("1.2_0", 4), ai("1.3_0"), { kind: "ai", type: 99, x: 5, y: 5, image: null }, { kind: "obstacle", type: 0, id: 7, x: 1, y: 1 }],
    faults: [],
  };
  const hass = fakeHass({
    ws: (m) => {
      if (m.type === "dreame_mower/work_log/details") return details;
      if (m.type === "dreame_mower/obstacle_photo") {
        if (m.image === "1.2_0") throw new Error("The mower did not send the photo; its connection may be weak");
        return { image: "AAAA", width: 1280, height: 720, boxes: [] };
      }
      return {};
    },
  });
  const card = await mount(window, hass);
  await openTab(window, card, "history");
  await sendWorkLog(window, hass, { totals: null, entries: [TASK], refreshing: false, error: null });
  await click(window, $(card, `.loglist [data-entry="${TASK.start}"]`));
  await settle(window);

  const tiles = $$(card, ".gallery button");
  assert.deepEqual(
    tiles.map((tile) => tile.dataset.photo),
    ["1.1_0", "1.2_0", "1.3_0"],
  );
  assert.deepEqual(
    hass.calls.filter((m) => m.type === "dreame_mower/obstacle_photo").map((m) => m.image),
    ["1.1_0", "1.2_0", "1.3_0"],
  );
  assert.ok(tiles[0].querySelector("img"));
  assert.equal(tiles[1].querySelector("ha-icon").getAttribute("icon"), "mdi:image-off-outline");
  assert.ok(tiles[2].querySelector("img"));

  await click(window, tiles[2]);
  assert.match($(card, ".photo .pnav").textContent, /3 \/ 3/);
  assert.ok($(card, ".photo .frame img"));
  await click(window, $(card, '.photo [data-step="1"]'));
  assert.match($(card, ".photo .pnav").textContent, /1 \/ 3/);
  // Photos shown before are not asked for again.
  assert.equal(hass.calls.filter((m) => m.type === "dreame_mower/obstacle_photo").length, 3);
});

// A task with recognised obstacles; `photo` answers for each image.
async function openTaskWithPhotos(window, { photo = () => ({ image: "AAAA", width: 1280, height: 720, boxes: [] }), extra = [] } = {}) {
  const ai = (image, type = 99) => ({ kind: "ai", type, x: 100, y: 100, image });
  const details = {
    result: "complete",
    geometry: { bounds: [0, 0, 10000, 8000], zones: [] },
    obstacles: [ai("1.1_0"), ai("1.2_0", 4), ai("1.3_0"), ...extra],
    faults: [],
  };
  const hass = fakeHass({
    ws: (m) => {
      if (m.type === "dreame_mower/work_log/details") return details;
      if (m.type === "dreame_mower/obstacle_photo") return photo(m.image);
      return {};
    },
  });
  const card = await mount(window, hass);
  await openTab(window, card, "history");
  await sendWorkLog(window, hass, { totals: null, entries: [TASK], refreshing: false, error: null });
  await click(window, $(card, `.loglist [data-entry="${TASK.start}"]`));
  await settle(window);
  return { card, hass };
}

async function swipe(window, element, dx, dy = 0) {
  const at = (type, x, y) => element.dispatchEvent(new window.MouseEvent(type, { bubbles: true, composed: true, clientX: x, clientY: y }));
  at("pointerdown", 200, 200);
  at("pointerup", 200 + dx, 200 + dy);
  await settle(window);
}

test("photos arriving leave the task's map as it was zoomed", async () => {
  const window = load("dreame-mower-card.js");
  let release;
  const late = new Promise((resolve) => (release = resolve));
  const { card, hass } = await openTaskWithPhotos(window, { photo: (image) => (image === "1.3_0" ? late.then(() => ({ image: "AAAA", width: 1, height: 1, boxes: [] })) : { image: "AAAA", width: 1, height: 1, boxes: [] }) });
  const map = $(card, "svg.logmap");
  assert.ok(map);

  release();
  await settle(window);

  assert.equal($$(card, ".gallery img").length, 3);
  assert.equal($(card, "svg.logmap"), map);
  // Nor does a later update of the work log.
  await sendWorkLog(window, hass, { totals: null, entries: [TASK], refreshing: false, error: null });
  assert.equal($(card, "svg.logmap"), map);
});

test("a swipe that ended beside the sheet does not steer the next tap", async () => {
  const window = load("dreame-mower-card.js");
  const { card } = await openTaskWithPhotos(window);
  await click(window, $$(card, ".gallery button")[0]);
  const at = (element, type, x) => element.dispatchEvent(new window.MouseEvent(type, { bubbles: true, composed: true, clientX: x, clientY: 200 }));

  // Pressed on the photo, let go over the dimmed card.
  at($(card, ".photo .frame img"), "pointerdown", 300);
  at($(card, ".scrim"), "pointerup", 100);
  const next = $(card, '.photo [data-step="1"]');
  at(next, "pointerdown", 500);
  at(next, "pointerup", 500);
  await click(window, next);

  assert.equal($(card, ".photo .pnav").textContent, "2 / 3");
});

test("a photo the gallery could not get shows in it once the sheet got it", async () => {
  const window = load("dreame-mower-card.js");
  let tries = 0;
  const { card } = await openTaskWithPhotos(window, {
    photo: (image) => {
      if (image === "1.2_0" && tries++ === 0) throw new Error("The mower did not send the photo; its connection may be weak");
      return { image: "AAAA", width: 1, height: 1, boxes: [] };
    },
  });
  const tile = () => $$(card, ".gallery button")[1];
  assert.equal(tile().querySelector("ha-icon").getAttribute("icon"), "mdi:image-off-outline");

  // Opening it asks the mower again.
  await click(window, tile());

  assert.ok(tile().querySelector("img"));
  assert.ok($(card, ".photo .frame img"));
});

test("a swipe over the photo steps through the task's photos", async () => {
  const window = load("dreame-mower-card.js");
  const { card } = await openTaskWithPhotos(window);
  await click(window, $$(card, ".gallery button")[0]);
  const count = () => $(card, ".photo .pnav").textContent;

  await swipe(window, $(card, ".photo .frame img"), -80);
  assert.equal(count(), "2 / 3");
  await swipe(window, $(card, ".photo .frame img"), 80);
  assert.equal(count(), "1 / 3");
  // Too short, or rather up and down, is no swipe.
  await swipe(window, $(card, ".photo .frame img"), -20);
  await swipe(window, $(card, ".photo .frame img"), -60, 90);
  assert.equal(count(), "1 / 3");
});

test("an obstacle without a photo opens without stepping", async () => {
  const window = load("dreame-mower-card.js");
  const { card } = await openTaskWithPhotos(window, { extra: [{ kind: "ai", type: 99, x: 5, y: 5, image: null }] });

  card._openObstacle("5,5,99", card._log.detail.data.obstacles);
  await settle(window);

  assert.equal($(card, ".photo .pnav"), null);
  assert.match($(card, ".photo").textContent, /took no photo/);
});

test("the gallery stops fetching once its task is closed", async () => {
  const window = load("dreame-mower-card.js");
  let release;
  const first = new Promise((resolve) => (release = resolve));
  const { card, hass } = await openTaskWithPhotos(window, { photo: (image) => (image === "1.1_0" ? first : { image: "AAAA", width: 1, height: 1, boxes: [] }) });

  await click(window, $(card, ".view.worklog [data-close]"));
  release({ image: "AAAA", width: 1, height: 1, boxes: [] });
  await settle(window);

  assert.deepEqual(
    hass.calls.filter((m) => m.type === "dreame_mower/obstacle_photo").map((m) => m.image),
    ["1.1_0"],
  );
});

test("photos are kept as blobs and let go when the card follows another mower", async () => {
  const window = load("dreame-mower-card.js");
  const made = [];
  const revoked = [];
  window.URL.createObjectURL = () => {
    made.push(`blob:${made.length}`);
    return made.at(-1);
  };
  window.URL.revokeObjectURL = (url) => revoked.push(url);
  const { card } = await openTaskWithPhotos(window);

  assert.deepEqual(made, ["blob:0", "blob:1", "blob:2"]);
  assert.deepEqual($$(card, ".gallery img").map((img) => img.getAttribute("src")), made);
  assert.equal(card._photos.get("1.1_0").image, undefined);

  card.setConfig({ entity: "lawn_mower.other" });
  assert.deepEqual(revoked, made);
});

test("the photo sheet sits at the bottom of the window over the card", async () => {
  const window = load("dreame-mower-card.js");
  // A card 600 px wide at 200 px from the left; a fixed sheet lands at the
  // bottom of the window.
  window.HTMLElement.prototype.getBoundingClientRect = function () {
    if (this.tagName === "HA-CARD") return { left: 200, width: 600, top: 0, bottom: 500 };
    const fixed = this.classList.contains("pinned");
    return { left: fixed ? parseFloat(this.style.left) : 200, width: 600, top: 0, bottom: fixed ? window.innerHeight : 500 };
  };
  const { card } = await openTaskWithPhotos(window);

  await click(window, $$(card, ".gallery button")[0]);
  const sheet = $(card, ".sheet.photo");
  assert.ok(sheet.classList.contains("pinned"));
  assert.equal(sheet.style.left, "200px");
  assert.equal(sheet.style.width, "600px");
  assert.ok($(card, ".scrim").classList.contains("pinned"));

  await click(window, $(card, ".photo [data-close]"));
  assert.ok(!$(card, ".scrim").classList.contains("pinned"));
});

test("the photo sheet stays at the bottom of the card where the page holds fixed elements", async () => {
  const window = load("dreame-mower-card.js");
  // jsdom lays nothing out: the pinned sheet does not land where it should.
  const { card } = await openTaskWithPhotos(window);

  await click(window, $$(card, ".gallery button")[0]);

  assert.ok(!$(card, ".sheet.photo").classList.contains("pinned"));
  assert.equal($(card, ".sheet.photo").style.left, "");
});

test("each task shows its battery use per m², coloured by how it compares", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass();
  const card = await mount(window, hass);
  await openTab(window, card, "history");
  const battery = (values) => ({ used: 37, per_sqm: 0.54, source: "recorded", ...values });
  await sendWorkLog(window, hass, {
    totals: null,
    entries: [
      { ...TASK, start: 5, battery: battery({ used: 102, per_sqm: 1.49, usual: 0.54, rating: "very_high" }) },
      { ...TASK, start: 4, battery: battery({ per_sqm: 0.62, usual: 0.54, rating: "high" }) },
      { ...TASK, start: 3, battery: battery({ usual: 0.54, rating: "normal", source: "statistics" }) },
      { ...TASK, start: 2, battery: battery({}) },
      { ...TASK, start: 1, area: 3.6, battery: battery({ per_sqm: 1.37 }) },
      { ...TASK, start: 0, battery: null },
    ],
    refreshing: false,
    error: null,
  });

  const pills = $$(card, ".loglist .row").map((row) => row.querySelector(".bat"));
  assert.deepEqual(
    pills.map((pill) => pill && [pill.className, pill.textContent]),
    [
      ["bat very_high", "1.49 %/m²"],
      ["bat high", "0.62 %/m²"],
      ["bat normal", "~0.54 %/m²"],
      ["bat ", "0.54 %/m²"],
      null,
      null,
    ],
  );
  assert.equal(pills[0].getAttribute("title"), "Battery 102 % · much more than usual (0.54 %/m², +176 %)");
  assert.equal(pills[3].getAttribute("title"), "Battery 37 %");
});

test("the list of tasks reaches down to the bottom of the window", async () => {
  const window = load("dreame-mower-card.js");
  let top = 100;
  window.HTMLElement.prototype.getBoundingClientRect = function () {
    return { left: 0, width: 400, top: this.classList.contains("loglist") ? top : 0, bottom: 0 };
  };
  // What is hidden has no layout.
  window.HTMLElement.prototype.getClientRects = function () {
    return this.closest("[hidden]") ? [] : [{}];
  };
  const hass = fakeHass();
  const card = await mount(window, hass);
  const room = () => $(card, ".loglist").style.getPropertyValue("--log-room");

  // The kept log arrives before the tab shows: the list is fitted once it does.
  $(card, '.tabs [data-tab="history"]').dispatchEvent(new window.MouseEvent("click", { bubbles: true, composed: true }));
  subscribed(hass, WORK_LOG)[0].callback({ totals: null, entries: [TASK, OLDER], refreshing: false, error: null });
  await settle(window);
  // jsdom's window is 768 px high: from 100 px down, less the gap below.
  assert.equal(room(), "656px");

  top = 500;
  window.dispatchEvent(new window.Event("resize"));
  assert.equal(room(), "256px");
});

test("a task shows the mowing direction and turning it was mowed with", async () => {
  const window = load("dreame-mower-card.js");
  let details = {};
  const hass = fakeHass({
    ws: (m) => (m.type === "dreame_mower/work_log/details" ? { result: "complete", area: 68.4, obstacles: [], faults: [], ...details } : {}),
  });
  const card = await mount(window, hass);
  await openTab(window, card, "history");
  const record = { mowing_direction: 90, mowing_direction_mode: "crisscross", turning_method: "lawn_care" };
  const zone30 = { ...record, mowing_direction: 30, mowing_direction_mode: "fixed" };
  const facts = async (value) => {
    details = value;
    card._logDetails.clear();
    await sendWorkLog(window, hass, { totals: null, entries: [TASK], refreshing: false, error: null });
    await click(window, $(card, `.loglist [data-entry="${TASK.start}"]`));
    const rows = Object.fromEntries($$(card, ".view.worklog .row.short").map((row) => [row.querySelector(".t").textContent, (row.querySelector(".val") || {}).textContent]));
    await click(window, $(card, ".view.worklog [data-close]"));
    return [rows["Mowing direction"], rows.Turning];
  };

  // Map-wide: the map's record, whatever the zones keep.
  assert.deepEqual(await facts({ per_zone: false, settings: { per_zone: false, areas: { 0: record, 4: zone30 } } }), ["90° · +45° each session", "Lawn care"]);
  // Per zone: what the zones share; a zone without a record follows the map's.
  assert.deepEqual(await facts({ per_zone: true, settings: { per_zone: true, areas: { 0: record, 4: zone30, 5: zone30 } } }), ["30°", "Lawn care"]);
  assert.deepEqual(await facts({ per_zone: true, zones: [{ id: 4 }, { id: 6 }], settings: { per_zone: true, areas: { 0: record, 4: zone30 } } }), ["per zone", "Lawn care"]);
  // Only the zones the task worked count; the task's file says it mowed per zone.
  assert.deepEqual(await facts({ per_zone: true, zones: [{ id: 4 }], settings: { per_zone: null, areas: { 0: record, 4: zone30 } } }), ["30°", "Lawn care"]);
  // A value that cannot be told is left out rather than set against the others.
  assert.deepEqual(await facts({ per_zone: true, settings: { per_zone: true, areas: { 0: record, 4: zone30, 5: { mowing_direction: 30, turning_method: 7 } } } }), ["30°", "Lawn care"]);
  // A task recorded without them shows neither.
  assert.deepEqual(await facts({ settings: null }), [undefined, undefined]);
});

test("a task shows its battery over its time, below its obstacles", async () => {
  const window = load("dreame-mower-card.js");
  let battery = null;
  const hass = fakeHass({
    ws: (m) => (m.type === "dreame_mower/work_log/details" ? { result: "complete", area: 68.4, obstacles: [], faults: [], battery } : {}),
  });
  const card = await mount(window, hass);
  await openTab(window, card, "history");
  const open = async (value, summary = null) => {
    battery = value;
    card._logDetails.clear();
    await sendWorkLog(window, hass, { totals: null, entries: [{ ...TASK, battery: summary }], refreshing: false, error: null });
    await click(window, $(card, `.loglist [data-entry="${TASK.start}"]`));
    const block = $(card, ".view.worklog .battery-course");
    const result = block && { line: block.querySelector(".bhead span").textContent, chart: block.querySelector("svg") };
    await click(window, $(card, ".view.worklog [data-close]"));
    return result;
  };

  // Down, recharged step by step, down again.
  const samples = [[0, 100], [3480, 15], [3600, 40], [5000, 95], [7080, 79]];
  const recorded = await open({ used: 101, per_sqm: 1.477, source: "recorded", samples }, { used: 101, per_sqm: 1.477, usual: 0.54, rating: "very_high" });
  assert.equal(recorded.line, "100 → 15 %, recharged, 95 → 79 % · 101 % used · 1.48 %/m² · usual 0.54 %/m²");
  assert.equal(recorded.chart.querySelectorAll("polyline").length, 1);
  assert.equal(recorded.chart.querySelector("polyline").getAttribute("points").split(" ").length, 5);
  // The recharge is shaded, in one piece.
  assert.equal(recorded.chart.querySelectorAll("rect").length, 1);

  const line = async (levels) => (await open({ used: 0, per_sqm: null, source: "recorded", samples: levels.map((level, i) => [i * 60, level]) })).line;
  // A level that wavers while mowing is no recharge, nor is a dip while charging the end of one.
  assert.equal(await line([100, 80, 81, 80, 40]), "100 → 40 % · 0 % used");
  assert.equal(await line([100, 15, 40, 39, 95, 79]), "100 → 15 %, recharged, 95 → 79 % · 0 % used");
  // Recharges at the start or the end of a task, or only one.
  assert.equal(await line([30, 50, 90, 60]), "recharged, 90 → 60 % · 0 % used");
  assert.equal(await line([100, 50, 80]), "100 → 50 %, recharged · 0 % used");
  assert.equal(await line([20, 40, 60]), "recharged · 0 % used");

  // From hourly statistics: only the line.
  const hourly = await open({ used: 38, per_sqm: 0.556, source: "statistics", samples: null });
  assert.equal(hourly.line, "~38 % used · ~0.56 %/m²");
  assert.equal(hourly.chart, null);

  assert.equal(await open(null), null);
});

test("a task counts the obstacles it met in the viewer's language", async () => {
  const window = load("dreame-mower-card.js");
  let obstacles = [];
  const hass = fakeHass({
    language: "fr",
    ws: (m) => (m.type === "dreame_mower/work_log/details" ? { result: "complete", area: 68.4, obstacles, faults: [] } : {}),
  });
  const card = await mount(window, hass);
  await openTab(window, card, "history");
  const met = async (count) => {
    obstacles = Array.from({ length: count }, (_, i) => ({ kind: "obstacle", type: 0, id: i, x: i, y: i }));
    card._logDetails.clear();
    await sendWorkLog(window, hass, { totals: null, entries: [TASK], refreshing: false, error: null });
    await click(window, $(card, `.loglist [data-entry="${TASK.start}"]`));
    const text = $(card, ".view.worklog .row.short .d").textContent;
    await click(window, $(card, ".view.worklog [data-close]"));
    return text;
  };
  assert.equal(await met(1), "1 rencontré");
  assert.equal(await met(2), "2 rencontrés");
});

test("a task names the obstacles it recognised as a sentence does in the viewer's language", async () => {
  const kinds = async (language) => {
    const window = load("dreame-mower-card.js");
    const obstacles = [1, 2, 6].map((type) => ({ kind: "ai", type, x: type, y: type, image: null }));
    const hass = fakeHass({
      language,
      ws: (m) => (m.type === "dreame_mower/work_log/details" ? { result: "complete", area: 68.4, obstacles, faults: [] } : {}),
    });
    const card = await mount(window, hass);
    await openTab(window, card, "history");
    await sendWorkLog(window, hass, { totals: null, entries: [TASK], refreshing: false, error: null });
    await click(window, $(card, `.loglist [data-entry="${TASK.start}"]`));
    return $(card, ".view.worklog .row.short .d").textContent;
  };
  assert.equal(await kinds("en"), "Cat, dog, dog waste");
  // German nouns keep their capital.
  assert.equal(await kinds("de"), "Katze, Hund, Hundekot");
});

test("a task's area reads with the viewer's decimal mark", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass({ language: "de" });
  const card = await mount(window, hass);
  await openTab(window, card, "history");
  await sendWorkLog(window, hass, { totals: null, entries: [TASK], refreshing: false, error: null });
  assert.match($(card, `.loglist [data-entry="${TASK.start}"]`).textContent, /68,4 m²/);
});

test("a task's details read their area with the viewer's decimal mark", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass({
    language: "de",
    ws: (m) => (m.type === "dreame_mower/work_log/details" ? { result: "complete", area: 68.42, map_area: 75.4, obstacles: [], faults: [] } : {}),
  });
  const card = await mount(window, hass);
  await openTab(window, card, "history");
  await sendWorkLog(window, hass, { totals: null, entries: [TASK], refreshing: false, error: null });
  await click(window, $(card, `.loglist [data-entry="${TASK.start}"]`));
  const text = $(card, ".view.worklog").textContent;
  assert.match(text, /68,4/);
  assert.doesNotMatch(text, /\d\.\d/);
});
