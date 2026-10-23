import assert from "node:assert/strict";
import { test } from "node:test";

import { $, $$, MOWER, click, entry, fakeHass, load, mount, openTab, plain, settle, subscribed } from "./harness.mjs";

const SCHEDULES = {
  states: {
    "switch.a2_schedule_1": {
      entity_id: "switch.a2_schedule_1",
      state: "on",
      attributes: {
        schedule_name: "Weekdays",
        tasks: [
          { week_day: "thursday", start_time: 600, type: "all_area" },
          { week_day: "monday", start_time: 600, type: "all_area" },
          { week_day: "saturday", start_time: 570, type: "zone" },
        ],
      },
    },
    "switch.a2_schedule_2": { entity_id: "switch.a2_schedule_2", state: "unavailable", attributes: { schedule_name: "Holidays" } },
  },
  entities: {
    "switch.a2_schedule_1": entry("switch.a2_schedule_1", "schedule"),
    "switch.a2_schedule_2": entry("switch.a2_schedule_2", "schedule"),
  },
};

// A section that records what the card asks of it.
function recorder(output = "") {
  const section = { calls: [], output, host: null, keepOpen: false };
  const type = {
    id: "recorder",
    create(host) {
      section.host = host;
      const record =
        (name) =>
        (...args) => {
          section.calls.push(name);
          return args[0];
        };
      return {
        connect: record("connect"),
        disconnect: record("disconnect"),
        resubscribe: record("resubscribe"),
        dropped: record("dropped"),
        reset: record("reset"),
        rendered: record("rendered"),
        back: record("back"),
        render: () => section.output,
        handleEvent: (e) => section.calls.push(`${e.type}:${e.target.dataset.mine || ""}`),
        leave: () => {
          section.calls.push("leave");
          return !section.keepOpen;
        },
      };
    },
  };
  return { section, type };
}

test("the card defines itself and shares its helpers", () => {
  const window = load("dreame-mower-card.js");
  const Card = window.customElements.get("dreame-mower-card");
  assert.ok(Card);
  assert.ok(window.customElements.get("dreame-mower-card-editor"));
  assert.ok(window.customCards.some((card) => card.type === "dreame-mower-card"));
  assert.ok(Object.isFrozen(Card.helpers));
  assert.equal(Card.helpers.DOMAIN, "dreame_mower");
  assert.equal(Card.helpers.esc('<a href="x">'), "&lt;a href=&quot;x&quot;&gt;");
  assert.equal(Card.helpers.humanize("returning_to_charge"), "Returning to charge");
});

test("the card asks for an entity of the integration", () => {
  const window = load("dreame-mower-card.js");
  const card = window.document.createElement("dreame-mower-card");
  assert.throws(() => card.setConfig({ entity: "vacuum.x" }), /lawn mower entity/);
});

test("the card subscribes to the map feed of its mower", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass();
  await mount(window, hass);
  assert.deepEqual(
    subscribed(hass, "dreame_mower/map/subscribe").map((s) => s.message.entity_id),
    [MOWER],
  );
});

test("the Schedules tab lists the mower's schedules with their tasks", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass(SCHEDULES);
  const card = await mount(window, hass);
  assert.deepEqual(
    $$(card, ".tabs [data-tab]").map((b) => b.textContent),
    ["Mow", "History", "Schedules", "Settings"],
  );
  assert.ok($(card, ".view.schedules").hidden);

  await openTab(window, card, "schedules");
  assert.ok(!$(card, ".view.schedules").hidden);
  const rows = $$(card, ".view.schedules .row");
  assert.equal(rows.length, 2);
  assert.match(rows[0].textContent, /Weekdays/);
  assert.match(rows[0].textContent, /Sat 09:30 zones · Mon, Thu 10:00 all-area/);
  assert.match(rows[1].textContent, /Not on the map in use/);
  assert.ok(rows[1].querySelector("button.switch").disabled);
  // Without sections the schedules head the tab.
  assert.equal($(card, ".view.schedules .group").className, "group");
});

test("a schedule's switch turns it off", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass(SCHEDULES);
  const card = await mount(window, hass);
  await openTab(window, card, "schedules");
  await click(window, $(card, '[data-schedule="switch.a2_schedule_1"]'));
  assert.deepEqual(plain(hass.services), [{ domain: "switch", service: "turn_off", data: { entity_id: "switch.a2_schedule_1" } }]);
});

test("a section registered after the card shows above the schedules", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass(SCHEDULES);
  const card = await mount(window, hass);
  const { section, type } = recorder('<div class="mine"><button type="button" data-mine="go">Go</button></div>');
  window.customElements.get("dreame-mower-card").registerSection(type);
  await settle(window);
  assert.ok(section.calls.includes("connect"));
  assert.equal(section.host.entityId, MOWER);
  assert.equal(section.host.hass, hass);
  assert.equal(section.host.mower().available, true);

  await openTab(window, card, "schedules");
  const body = $(card, ".view.schedules .sbody");
  assert.equal(body.firstElementChild.className, "mine");
  assert.equal($(card, ".view.schedules .group").className, "group sep");
  assert.ok(section.calls.includes("rendered"));
  assert.equal(section.host.body, body);

  // Its events go to it; a schedule's switch stays the card's.
  section.calls.length = 0;
  await click(window, $(card, '[data-mine="go"]'));
  assert.deepEqual(section.calls.filter((c) => c.startsWith("click")), ["click:go"]);
  await click(window, $(card, '[data-schedule="switch.a2_schedule_1"]'));
  assert.deepEqual(section.calls.filter((c) => c.startsWith("click")), ["click:go"]);
});

test("a section can fill the tab with a page of its own", async () => {
  const window = load("dreame-mower-card.js");
  const { section, type } = recorder({ head: '<span class="title">Page</span>', body: '<div class="page">Inside</div>' });
  window.customElements.get("dreame-mower-card").registerSection(type);
  const card = await mount(window, fakeHass(SCHEDULES));
  await openTab(window, card, "schedules");
  assert.equal($(card, ".view.schedules .shead").textContent, "Page");
  assert.equal($(card, ".view.schedules .sbody").innerHTML, '<div class="page">Inside</div>');

  // Tapping the tab again is for the section; refresh() draws it anew.
  await openTab(window, card, "schedules");
  assert.ok(section.calls.includes("back"));
  section.output = "<p>Back</p>";
  section.host.refresh();
  await settle(window);
  assert.equal($(card, ".view.schedules .shead").textContent, "");
  assert.match($(card, ".view.schedules .sbody").innerHTML, /^<p>Back<\/p><div class="group sep">Robot schedules/);
});

test("a section can keep the tab open", async () => {
  const window = load("dreame-mower-card.js");
  const { section, type } = recorder();
  window.customElements.get("dreame-mower-card").registerSection(type);
  const card = await mount(window, fakeHass());
  await openTab(window, card, "schedules");
  section.keepOpen = true;
  await openTab(window, card, "history");
  assert.ok(!$(card, ".view.schedules").hidden);
  section.keepOpen = false;
  await openTab(window, card, "history");
  assert.ok($(card, ".view.schedules").hidden);
});

test("a section follows the socket going away and coming back", async () => {
  const window = load("dreame-mower-card.js");
  const { section, type } = recorder();
  window.customElements.get("dreame-mower-card").registerSection(type);
  const hass = fakeHass();
  await mount(window, hass);
  hass.fire("disconnected");
  assert.equal(section.calls.at(-1), "dropped");
  hass.fire("ready");
  assert.equal(section.calls.at(-1), "resubscribe");
  // The map feed comes back too.
  assert.equal(subscribed(hass, "dreame_mower/map/subscribe").length, 1);
  assert.equal(hass.subscriptions.length, 2);
});

test("a failing section leaves the card working", async () => {
  const window = load("dreame-mower-card.js");
  window.console.error = () => {};
  const Card = window.customElements.get("dreame-mower-card");
  const fail = () => {
    throw new Error("broken");
  };
  Card.registerSection({ id: "no-start", create: fail });
  Card.registerSection({
    id: "faulty",
    create: () => ({ connect: fail, render: fail, rendered: fail, handleEvent: fail, leave: fail }),
  });
  const hass = fakeHass(SCHEDULES);
  const card = await mount(window, hass);
  assert.equal(subscribed(hass, "dreame_mower/map/subscribe").length, 1);
  await openTab(window, card, "schedules");
  assert.ok(!$(card, ".view.schedules").hidden);
  assert.equal($$(card, ".view.schedules .row").length, 2);
  await click(window, $(card, '[data-schedule="switch.a2_schedule_1"]'));
  assert.equal(hass.services.length, 1);
  await openTab(window, card, "history");
  assert.ok($(card, ".view.schedules").hidden);
});

test("a section follows the card's mower and its place on the page", async () => {
  const window = load("dreame-mower-card.js");
  const { section, type } = recorder();
  const Card = window.customElements.get("dreame-mower-card");
  Card.registerSection(type);
  // The same id again, or something that is no section, changes nothing.
  Card.registerSection({ ...type, create: () => assert.fail("registered twice") });
  Card.registerSection({ id: "broken" });
  const card = await mount(window, fakeHass());
  card.setConfig({ entity: "lawn_mower.other" });
  assert.ok(section.calls.includes("reset"));
  card.remove();
  assert.equal(section.calls.at(-1), "disconnect");
});

// A mower on its station on a map, as the map feed sends it.
const GEOMETRY = { type: "geometry", map_id: 0, bounds: [0, 0, 10000, 8000] };
const DOCKED = {
  type: "status",
  dock: { x: 2000, y: 3000, angle: 0 },
  docked: true,
  state: { available: true, status: "Charging complete", session_active: false },
};

async function sendFeed(window, hass, ...events) {
  const [subscription] = subscribed(hass, "dreame_mower/map/subscribe");
  for (const event of events) subscription.callback(event);
  await settle(window);
}

// A section that answers beforeDrive with what `answer` returns.
function gate(answer) {
  const asked = [];
  return {
    asked,
    type: {
      id: "gate",
      create: () => ({
        beforeDrive: (action) => {
          asked.push(action);
          return answer(action);
        },
      }),
    },
  };
}

test("a section can call off a task before it starts", async () => {
  const window = load("dreame-mower-card.js");
  const { asked, type } = gate(() => false);
  window.customElements.get("dreame-mower-card").registerSection(type);
  const hass = fakeHass();
  const card = await mount(window, hass);
  await sendFeed(window, hass, GEOMETRY, DOCKED);
  await click(window, $(card, '[data-action="start"]'));
  assert.deepEqual(plain(asked), ["start"]);
  assert.deepEqual(hass.services, []);
});

test("a task starts once the sections are ready, and the card waits for them", async () => {
  const window = load("dreame-mower-card.js");
  let release;
  const { asked, type } = gate(() => new Promise((resolve) => (release = resolve)));
  window.customElements.get("dreame-mower-card").registerSection(type);
  const hass = fakeHass();
  const card = await mount(window, hass);
  await sendFeed(window, hass, GEOMETRY, DOCKED);
  await click(window, $(card, '[data-action="start"]'));
  assert.deepEqual(plain(asked), ["start"]);
  assert.deepEqual(hass.services, []);
  // The card is busy while it waits.
  assert.ok($(card, '[data-action="start"]').disabled);
  release(true);
  await settle(window);
  assert.deepEqual(
    plain(hass.services).map((s) => `${s.domain}.${s.service}`),
    ["dreame_mower.start_all_area_mowing"],
  );
});

test("a failing section calls the drive off", async () => {
  const window = load("dreame-mower-card.js");
  window.console.error = () => {};
  const { type } = gate(() => Promise.reject(new Error("no answer")));
  window.customElements.get("dreame-mower-card").registerSection(type);
  const hass = fakeHass();
  const card = await mount(window, hass);
  await sendFeed(window, hass, GEOMETRY, { ...DOCKED, docked: false, state: { ...DOCKED.state, status: "Idle" } });
  hass.states[MOWER] = { ...hass.states[MOWER], state: "paused" };
  card.hass = { ...hass };
  await settle(window);
  await click(window, $(card, '[data-action="recharge"]'));
  assert.deepEqual(hass.services, []);
  assert.match($(card, ".toast").textContent, /no answer/);
});

test("a section draws over the map, next to the station", async () => {
  const window = load("dreame-mower-card.js");
  const views = [];
  window.customElements.get("dreame-mower-card").registerSection({
    id: "layer",
    create: () => ({
      mapLayer: (view) => {
        views.push(view);
        return `<circle class="mine" cx="${view.station ? view.station.x : 0}" cy="0" r="1"/>`;
      },
    }),
  });
  const hass = fakeHass();
  const card = await mount(window, hass);
  await sendFeed(window, hass, GEOMETRY, DOCKED);
  assert.ok($(card, "circle.mine"));
  const view = views.at(-1);
  assert.ok(view.station && view.station.length > 0 && view.px > 0);
  assert.equal(view.docked, true);
});

test("clearing an error asks the sections first, since the mower goes on", async () => {
  const window = load("dreame-mower-card.js");
  let ready = false;
  const { asked, type } = gate(() => ready);
  window.customElements.get("dreame-mower-card").registerSection(type);
  const hass = fakeHass();
  const card = await mount(window, hass);
  await sendFeed(window, hass, GEOMETRY, { ...DOCKED, state: { ...DOCKED.state, error: "Blades stuck" } });
  await click(window, $(card, "[data-clear-error]"));
  assert.deepEqual(plain(asked), ["continue"]);
  assert.deepEqual(hass.services, []);
  ready = true;
  await click(window, $(card, "[data-clear-error]"));
  assert.deepEqual(plain(hass.services).map((s) => s.service), ["clear_error"]);
});

test("a section adds buttons to the map, and their clicks go to it alone", async () => {
  const window = load("dreame-mower-card.js");
  const clicks = [];
  const Card = window.customElements.get("dreame-mower-card");
  Card.registerSection({
    id: "mine",
    create: () => ({
      mapButtons: () => `<button type="button" class="mapbtn" data-mine="1">M</button>`,
      handleEvent: (e) => clicks.push(`mine:${e.type}`),
    }),
  });
  Card.registerSection({ id: "other", create: () => ({ handleEvent: (e) => clicks.push(`other:${e.type}`) }) });
  const hass = fakeHass();
  const card = await mount(window, hass);
  await sendFeed(window, hass, GEOMETRY, DOCKED);
  const button = $(card, '.mapbtns [data-section="mine"] [data-mine]');
  assert.ok(button);
  await click(window, button);
  assert.deepEqual(clicks, ["mine:click"]);
  // Only on the Mow tab.
  await openTab(window, card, "history");
  assert.equal($(card, ".mapbtns [data-mine]"), null);
});

test("a section can show its own element in the map's place, kept across redraws", async () => {
  const window = load("dreame-mower-card.js");
  const element = window.document.createElement("div");
  element.className = "mycover";
  let covered = false;
  let host = null;
  const updates = [];
  window.customElements.get("dreame-mower-card").registerSection({
    id: "cover",
    create: (h) => {
      host = h;
      return { cover: () => (covered ? element : null), update: () => updates.push("update") };
    },
  });
  const hass = fakeHass();
  const card = await mount(window, hass);
  await sendFeed(window, hass, GEOMETRY, DOCKED);
  assert.equal($(card, ".cover").hidden, true);
  assert.equal($(card, ".map").hidden, false);
  covered = true;
  host.refreshMow();
  await settle(window);
  assert.equal($(card, ".cover").hidden, false);
  assert.equal($(card, ".map").hidden, true);
  assert.equal($(card, ".cover").firstChild, element);
  // A change of state reaches the section and leaves its element in place.
  updates.length = 0;
  card.hass = { ...hass, states: { ...hass.states } };
  await settle(window);
  assert.deepEqual(updates, ["update"]);
  assert.equal($(card, ".cover").firstChild, element);
  assert.equal(host.docked(), true);
  covered = false;
  host.refreshMow();
  await settle(window);
  assert.equal($(card, ".cover").hidden, true);
  assert.equal($(card, ".cover").firstChild, null);
  assert.equal($(card, ".map").hidden, false);
});

test("a section finds the mower's entities by their key", async () => {
  const window = load("dreame-mower-card.js");
  let host = null;
  window.customElements.get("dreame-mower-card").registerSection({ id: "find", create: (h) => ((host = h), {}) });
  await mount(window, fakeHass({ entities: { "sensor.a2_blades": entry("sensor.a2_blades", "blade") } }));
  assert.equal(host.entity("sensor", "blade"), "sensor.a2_blades");
  assert.equal(host.entity("sensor", "other"), null);
});

test("tapping the battery level opens the history of the battery sensor", async () => {
  const window = load("dreame-mower-card.js");
  const battery = { entity_id: "sensor.a2_battery", state: "80", attributes: { device_class: "battery" } };
  const hass = fakeHass({ states: { "sensor.a2_battery": battery }, entities: { "sensor.a2_battery": entry("sensor.a2_battery", null) } });
  const card = await mount(window, hass);
  // The page the card goes to, and the event that has Home Assistant show it.
  const pushed = [];
  window.history.pushState = (state, title, url) => pushed.push(url);
  window.addEventListener("location-changed", () => pushed.push("location-changed"));
  await sendFeed(window, hass, GEOMETRY, { ...DOCKED, state: { ...DOCKED.state, battery: 80 } });
  $(card, "[data-action='battery-history']").click();
  await settle(window);
  assert.deepEqual(pushed, ["/history?entity_id=sensor.a2_battery", "location-changed"]);
});

test("the battery level leads to the history only of the mower's own battery sensor", async () => {
  const window = load("dreame-mower-card.js");
  const sensor = (id, deviceClass) => ({ entity_id: id, state: "80", attributes: { device_class: deviceClass } });
  // Another sensor of the mower, another device's battery and another
  // integration's battery on the mower's device.
  const states = {
    "sensor.a2_blades": sensor("sensor.a2_blades", undefined),
    "sensor.phone_battery": sensor("sensor.phone_battery", "battery"),
    "sensor.other_battery": sensor("sensor.other_battery", "battery"),
  };
  const entities = {
    "sensor.a2_blades": entry("sensor.a2_blades", "blade"),
    "sensor.phone_battery": { ...entry("sensor.phone_battery", null), device_id: "device-phone" },
    "sensor.other_battery": { ...entry("sensor.other_battery", null), platform: "other" },
  };
  const hass = fakeHass({ states, entities });
  const card = await mount(window, hass);
  await sendFeed(window, hass, GEOMETRY, { ...DOCKED, state: { ...DOCKED.state, battery: 80, charging: "charging" } });
  assert.match($(card, ".status .sub").textContent, /80 %/);
  assert.equal($(card, "[data-action='battery-history']"), null);
  // The sensor turning up later makes the level tappable, with its look kept.
  card.hass = {
    ...hass,
    states: { ...hass.states, "sensor.a2_battery": sensor("sensor.a2_battery", "battery") },
    entities: { ...hass.entities, "sensor.a2_battery": entry("sensor.a2_battery", null) },
  };
  await settle(window);
  const button = $(card, "[data-action='battery-history']");
  assert.ok(button);
  assert.equal(button.querySelector("ha-icon").getAttribute("icon"), "mdi:battery-charging-80");
  assert.match(button.textContent, /80 %/);
  // And gone again, the level is plain text.
  card.hass = hass;
  await settle(window);
  assert.equal($(card, "[data-action='battery-history']"), null);
});

test("an all-wheel drive mower is drawn as one, other models keep the two-wheel body", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass();
  const card = await mount(window, hass);
  await sendFeed(window, hass, GEOMETRY, { ...DOCKED, model: "dreame.mower.g2541e" });
  assert.equal($(card, "[data-look]").dataset.look, "awd");
  // Another size of the same family shares the body.
  await sendFeed(window, hass, { ...DOCKED, model: "dreame.mower.g2541f" });
  assert.equal($(card, "[data-look]").dataset.look, "awd");
  await sendFeed(window, hass, { ...DOCKED, model: "dreame.mower.p2255" });
  assert.equal($(card, "[data-look]").dataset.look, "rwd");
});

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
