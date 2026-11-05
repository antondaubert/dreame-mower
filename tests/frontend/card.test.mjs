import assert from "node:assert/strict";
import { test } from "node:test";

import { $, $$, DOCKED, GEOMETRY, MOWER, click, entry, fakeHass, load, mount, openTab, plain, sendFeed, settle, subscribed } from "./harness.mjs";

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

test("the palette option recolours the map and clamps the opacities", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass();
  const card = await mount(window, hass, {
    theme: "dark",
    palette: { background: "#102030", noGo: "#ff00ff", zoneFillOpacity: 0.4, stripeOpacity: 7, nonsense: "red", brand: "" },
  });
  const pal = card._palette();
  assert.equal(pal.noGo, "#ff00ff");
  assert.equal(pal.background, "#102030");
  assert.equal(pal.zoneFillOpacity, 0.4);
  assert.equal(pal.stripeOpacity, 1);
  assert.equal(pal.brand, "#c9a877");
  assert.equal("nonsense" in pal, false);
  await sendFeed(window, hass, { ...GEOMETRY, zones: [{ id: 1, points: [0, 0, 5000, 0, 5000, 5000] }] }, DOCKED);
  assert.equal(card._el.card.style.getPropertyValue("--mower-map-background"), "#102030");
});

test("without a palette option the map keeps the built-in colours", async () => {
  const window = load("dreame-mower-card.js");
  const card = await mount(window, fakeHass(), { theme: "light" });
  const pal = card._palette();
  assert.equal(pal.noGo, "#EE3C2F");
  assert.equal(pal.zoneFillOpacity, 0.15);
  assert.equal(pal.trailOpacity, 0.6);
  assert.equal(pal.stripeOpacity, 1);
});

test("the colors option sets the interface variables and drops them again", async () => {
  const window = load("dreame-mower-card.js");
  const card = await mount(window, fakeHass(), {
    theme: "dark",
    colors: { accent: "#00e8ff", success: "var(--x, #00ff88)", text: "not a colour", nonsense: "red" },
  });
  const style = card._el.card.style;
  assert.equal(style.getPropertyValue("--mower-brand"), "#00e8ff");
  assert.equal(style.getPropertyValue("--mower-success"), "var(--x, #00ff88)");
  assert.equal(style.getPropertyValue("--mower-text"), "");
  card.setConfig({ entity: MOWER, theme: "dark" });
  card._render();
  assert.equal(style.getPropertyValue("--mower-brand"), "");
});

test("the editor sets interface colours and drops them again", async () => {
  const window = load("dreame-mower-card.js");
  const editor = window.document.createElement("dreame-mower-card-editor");
  const changes = [];
  editor.addEventListener("config-changed", (e) => changes.push(plain(e.detail.config)));
  editor.setConfig({ entity: MOWER });
  editor.hass = fakeHass();
  window.document.body.appendChild(editor);
  const field = (selector) => editor.shadowRoot.querySelector(selector);

  const accent = field('[data-colors="accent"]');
  accent.value = "#00e8ff";
  accent.dispatchEvent(new window.Event("input", { bubbles: true, composed: true }));
  assert.deepEqual(changes.at(-1), { entity: MOWER, colors: { accent: "#00e8ff" } });
  assert.equal(field('[data-cpicker="accent"]').value, "#00e8ff");

  accent.value = "";
  accent.dispatchEvent(new window.Event("input", { bubbles: true, composed: true }));
  assert.deepEqual(changes.at(-1), { entity: MOWER });
});

test("the settings page and the bottom sheets paint the card background over an opaque base", async () => {
  const window = load("dreame-mower-card.js");
  const card = await mount(window, fakeHass(), {});
  const css = card.shadowRoot.querySelector("style").textContent;
  const block = (rule) => css.slice(css.indexOf(rule), css.indexOf("}", css.indexOf(rule)));
  // The element itself is the opaque base; the card background is a layer
  // under its content, so a plain background and `colors.background` both show.
  for (const rule of [".settings {", ".sheet {"]) {
    assert.match(block(rule), /background: var\(--mower-cover\);/, rule);
    assert.doesNotMatch(block(rule), /background-color/, rule);
  }
  assert.match(block(".settings::before, .sheet::before {"), /z-index: -1;[^}]*background: var\(--mower-background\)/);
  assert.match(block(".settings.inline {"), /background: var\(--mower-background\)/);
  const sheet = block(".sheet {");
  assert.doesNotMatch(sheet, /overflow/);
  assert.match(block(".sheet .sheetbody {"), /overflow-y: auto/);
});

test("every bottom sheet wraps its content in the scrolling body", async () => {
  const window = load("dreame-mower-card.js");
  const card = await mount(window, fakeHass(), {});
  const done = card._choose("Title", "Text", [{ id: "a", label: "A" }]);
  const sheet = card._el.choice;
  assert.equal(sheet.children.length, 1);
  assert.equal(sheet.firstElementChild.classList.contains("sheetbody"), true);
  sheet.querySelector("[data-choice='a']").click();
  assert.equal(await done, "a");
});

test("computed colours in other spaces are converted to sRGB hex", async () => {
  const window = load("dreame-mower-card.js");
  const card = await mount(window, fakeHass(), {});
  const computed = window.getComputedStyle;
  const set = (color) => (window.getComputedStyle = () => ({ color }));
  try {
    set("rgb(1, 2, 3)");
    assert.equal(card._resolveColor("#123456", "#000000"), "#010203");
    // color(srgb ...) is read directly when no canvas can convert it.
    set("color(srgb 1 0.5 0)");
    assert.equal(card._resolveColor("#123456", "#000000"), "#ff8000");
    // oklch() goes through the canvas.
    set("oklch(0.7 0.1 200)");
    const proto = window.HTMLCanvasElement.prototype;
    const getContext = proto.getContext;
    proto.getContext = () => ({ clearRect() {}, fillRect() {}, getImageData: () => ({ data: [12, 34, 56, 255] }) });
    try {
      assert.equal(card._resolveColor("#123456", "#000000"), "#0c2238");
    } finally {
      proto.getContext = getContext;
    }
    // Neither readable: the fallback.
    set("lab(50 20 20)");
    assert.equal(card._resolveColor("#123456", "#abcdef"), "#abcdef");
  } finally {
    window.getComputedStyle = computed;
  }
});

test("the editor's colour pickers show the theme's colour while a field is left empty", async () => {
  const window = load("dreame-mower-card.js");
  const editor = window.document.createElement("dreame-mower-card-editor");
  editor.setConfig({ entity: MOWER });
  editor.hass = fakeHass();
  window.document.body.appendChild(editor);
  const picker = (key) => editor.shadowRoot.querySelector(`[data-cpicker="${key}"]`).value;
  assert.equal(picker("success"), "#43a047");
  assert.equal(editor.shadowRoot.querySelector('[data-colors="success"]').placeholder, "#43a047");
});

test("a palette colour given as a card variable resolves inside the card, after the colors option", async () => {
  const window = load("dreame-mower-card.js");
  const computed = window.getComputedStyle;
  // Stands in for the cascade: the probe sees the accent only inside the card.
  window.getComputedStyle = (el) =>
    el.closest && el.closest("ha-card") ? { color: el.closest("ha-card").style.getPropertyValue("--mower-brand") === "#00e8ff" ? "rgb(0, 232, 255)" : "rgb(1, 1, 1)" } : computed(el);
  try {
    const card = await mount(window, fakeHass(), { theme: "dark", colors: { accent: "#00e8ff" }, palette: { noGo: "var(--mower-brand)" } });
    card._render();
    assert.equal(card._palette().noGo, "#00e8ff");
    // A new accent alone resolves the palette again.
    card.setConfig({ entity: MOWER, theme: "dark", colors: { accent: "#ff0000" }, palette: { noGo: "var(--mower-brand)" } });
    card._render();
    assert.equal(card._palette().noGo, "#010101");
  } finally {
    window.getComputedStyle = computed;
  }
});

test("the dark success text follows the colors option and keeps its own shade otherwise", async () => {
  const window = load("dreame-mower-card.js");
  const plain = await mount(window, fakeHass(), {});
  const css = plain.shadowRoot.querySelector("style").textContent;
  assert.match(css, /--mower-success-ink: #2e7d32;/);
  assert.equal(plain._el.card.style.getPropertyValue("--mower-success-ink"), "");
  const custom = await mount(window, fakeHass(), { colors: { success: "#00ffcc" } });
  assert.equal(custom._el.card.style.getPropertyValue("--mower-success-ink"), "color-mix(in srgb, var(--mower-success) 70%, #000)");
});

test("the editor takes the card background from --ha-card-background when that is a colour", async () => {
  const window = load("dreame-mower-card.js");
  const editor = window.document.createElement("dreame-mower-card-editor");
  const computed = window.getComputedStyle;
  const supports = window.CSS.supports;
  let card = "";
  window.getComputedStyle = () => ({ getPropertyValue: (name) => (name === "--ha-card-background" ? card : "") });
  window.CSS.supports = (property, value) => property === "color" && !value.includes("gradient");
  try {
    card = " #102030";
    assert.equal(editor._uiDefault("background"), "#102030");
    card = "linear-gradient(#000, #fff)";
    assert.equal(editor._uiDefault("background"), "var(--card-background-color, #fff)");
    card = "";
    assert.equal(editor._uiDefault("background"), "var(--card-background-color, #fff)");
  } finally {
    window.getComputedStyle = computed;
    window.CSS.supports = supports;
  }
});

test("the editor refreshes its colour fields when the theme changes, not on every state", async () => {
  const window = load("dreame-mower-card.js");
  const editor = window.document.createElement("dreame-mower-card-editor");
  editor.setConfig({ entity: MOWER });
  const hass = fakeHass();
  editor.hass = hass;
  window.document.body.appendChild(editor);
  let syncs = 0;
  const sync = editor._syncValues.bind(editor);
  editor._syncValues = () => {
    syncs += 1;
    sync();
  };
  editor.hass = { ...hass };
  assert.equal(syncs, 0);
  editor.hass = { ...hass, themes: { darkMode: true, theme: "other" } };
  assert.equal(syncs, 1);
  // Attached again, it shows the colours of the page it is in.
  editor.remove();
  window.document.body.appendChild(editor);
  assert.equal(syncs, 2);
});

// A style as a module would register it.
const NIGHT = {
  id: "night",
  label: "Night",
  base: "dark",
  colors: { accent: "#00e5ff", success: "#00ffcc" },
  palette: { background: "#080814", noGo: "#e0115f", trailOpacity: 0.8 },
  zoneColors: ["#ff2bd6", "#00ffcc"],
  glow: 0.5,
  buttons: "outlined",
  font: "Rajdhani, sans-serif",
};
const registerStyle = (window, style) => window.customElements.get("dreame-mower-card").registerStyle(style);
const ZONE = { ...GEOMETRY, zones: [{ id: 1, polygon: [0, 0, 5000, 0, 5000, 5000] }] };

test("a style sets the map palette under the card's own palette", async () => {
  const window = load("dreame-mower-card.js");
  registerStyle(window, NIGHT);
  const card = await mount(window, fakeHass(), { style: "night", palette: { noGo: "#ff0000" } });
  const pal = card._palette();
  // The dark palette is the base, the style goes over it, the card over the style.
  assert.equal(pal.background, "#080814");
  assert.equal(pal.trailOpacity, 0.8);
  assert.equal(pal.noGo, "#ff0000");
  assert.equal(pal.pathOuter, "#5a5a5a");
  assert.deepEqual(plain(pal.zones), ["#ff2bd6", "#00ffcc"]);
  assert.equal(pal.glow, 0.5);
  // A theme set on the card wins over the style's base.
  card.setConfig({ entity: MOWER, style: "night", theme: "light" });
  assert.equal(card._palette().pathOuter, "#A6A6A6");
});

test("a style sets the interface colours, glow, buttons and font, under the card's colors", async () => {
  const window = load("dreame-mower-card.js");
  registerStyle(window, NIGHT);
  const card = await mount(window, fakeHass(), { style: "night", colors: { success: "#11aa11" } });
  const el = card._el.card;
  assert.equal(el.style.getPropertyValue("--mower-brand"), "#00e5ff");
  assert.equal(el.style.getPropertyValue("--mower-success"), "#11aa11");
  assert.equal(el.style.getPropertyValue("--mower-glow-size"), "8px");
  assert.equal(el.style.getPropertyValue("font-family"), "Rajdhani, sans-serif");
  assert.equal(el.classList.contains("glow"), true);
  assert.equal(el.classList.contains("outlined"), true);
  // Back to the standard look: nothing of the style stays.
  card.setConfig({ entity: MOWER });
  card._render();
  assert.equal(el.style.getPropertyValue("--mower-brand"), "");
  assert.equal(el.style.getPropertyValue("--mower-glow-size"), "");
  assert.equal(el.style.getPropertyValue("font-family"), "");
  assert.equal(el.classList.contains("glow"), false);
  assert.equal(el.classList.contains("outlined"), false);
});

test("a style's stylesheet and class are on the card only while the style is", async () => {
  const window = load("dreame-mower-card.js");
  registerStyle(window, { ...NIGHT, css: ".style-night .primary { text-transform: uppercase; }" });
  registerStyle(window, { id: "plain", css: 42 });
  const card = await mount(window, fakeHass(), { style: "night" });
  const el = card._el.card;
  const sheet = () => card.shadowRoot.querySelector("style.stylecss").textContent;
  assert.equal(sheet(), ".style-night .primary { text-transform: uppercase; }");
  assert.equal(el.classList.contains("style-night"), true);
  // Another style swaps the class; one without a stylesheet leaves none behind.
  card.setConfig({ entity: MOWER, style: "plain" });
  card._render();
  assert.equal(sheet(), "");
  assert.equal(el.classList.contains("style-night"), false);
  assert.equal(el.classList.contains("style-plain"), true);
  // Back to the standard look: no style class at all.
  card.setConfig({ entity: MOWER });
  card._render();
  assert.equal([...el.classList].some((name) => name.startsWith("style-")), false);
});

test("a glow draws halos under the map's outlines, and none without one", async () => {
  const window = load("dreame-mower-card.js");
  registerStyle(window, NIGHT);
  registerStyle(window, { ...NIGHT, id: "flat", glow: 0 });
  const halos = async (style) => {
    const hass = fakeHass();
    const card = await mount(window, hass, { style });
    await sendFeed(window, hass, { ...ZONE, no_go: [{ polygon: [100, 100, 900, 100, 900, 900] }] }, DOCKED);
    return card._el.base.querySelectorAll("[stroke-opacity]").length;
  };
  // Three strokes under the zone and three under the no-go area.
  assert.equal(await halos("night"), 6);
  // The zone's halo lies under its lawn.
  {
    const hass = fakeHass();
    const card = await mount(window, hass, { style: "night" });
    await sendFeed(window, hass, ZONE, DOCKED);
    const shapes = [...card._el.base.children];
    const lawn = shapes.findIndex((el) => el.getAttribute("fill") !== "none");
    assert.ok(lawn > 0 && shapes.slice(0, lawn).every((el) => el.hasAttribute("stroke-opacity")));
  }
  // The zone takes the style's first colour, its outline in full.
  const hass = fakeHass();
  const card = await mount(window, hass, { style: "night" });
  await sendFeed(window, hass, ZONE, DOCKED);
  assert.equal(card._el.base.querySelector('polygon:not([stroke-opacity])[stroke-width="40"]').getAttribute("stroke"), "#ff2bd6");
  assert.equal(await halos("flat"), 0);
  assert.equal(await halos(undefined), 0);
});

test("a glow lays wider strokes under the mowing trail", async () => {
  const window = load("dreame-mower-card.js");
  registerStyle(window, NIGHT);
  const trail = async (style) => {
    const hass = fakeHass();
    const card = await mount(window, hass, { style });
    const mowing = { ...DOCKED, docked: false, state: { ...DOCKED.state, session_active: true } };
    await sendFeed(window, hass, ZONE, mowing, { type: "path", keep: 0, points: [[1000, 1000], [3000, 1000], [3000, 3000]] });
    return card._el.trail.querySelectorAll("path").length;
  };
  assert.equal(await trail("night"), 3);
  assert.equal(await trail(undefined), 1);
});

test("only valid styles register, with a warning for the others", async () => {
  const window = load("dreame-mower-card.js");
  const warned = [];
  window.console.warn = (message) => warned.push(message);
  registerStyle(window, { id: "Night" });
  registerStyle(window, NIGHT);
  registerStyle(window, NIGHT);
  assert.equal(warned.length, 2);
  assert.match(warned[0], /"Night" left out/);
  assert.match(warned[1], /"night" is already registered/);
});

test("a card set to a style takes it up once the style registers", async () => {
  const window = load("dreame-mower-card.js");
  const card = await mount(window, fakeHass(), { style: "night" });
  assert.equal(card._style(), null);
  assert.equal(card._el.card.classList.contains("glow"), false);
  assert.equal(card._el.card.classList.contains("style-night"), false);
  registerStyle(window, { ...NIGHT, css: ".style-night .primary { font-weight: 700; }" });
  await settle(window);
  assert.equal(card._style().id, "night");
  assert.equal(card._palette().background, "#080814");
  assert.equal(card._el.card.classList.contains("glow"), true);
  assert.equal(card._el.card.classList.contains("style-night"), true);
  assert.equal(card._el.styleCss.textContent, ".style-night .primary { font-weight: 700; }");
});

test("only valid styles register, each id once", async () => {
  const window = load("dreame-mower-card.js");
  registerStyle(window, { id: "Bad id" });
  registerStyle(window, { id: "standard" });
  registerStyle(window, { label: "No id" });
  registerStyle(window, { id: "plain", glow: 7, buttons: "round", zoneColors: ["#ff0000", 3, ""] });
  registerStyle(window, { id: "plain", label: "Again" });
  const card = await mount(window, fakeHass(), { style: "plain" });
  const style = plain(card._style());
  assert.equal(style.label, "plain");
  assert.equal(style.glow, 1);
  assert.equal(style.buttons, "filled");
  assert.deepEqual(style.zoneColors, ["#ff0000"]);
  card.setConfig({ entity: MOWER, style: "standard" });
  assert.equal(card._style(), null);
});

test("the editor lists the styles and sets or drops the card's style", async () => {
  const window = load("dreame-mower-card.js");
  registerStyle(window, NIGHT);
  const editor = window.document.createElement("dreame-mower-card-editor");
  const changes = [];
  editor.addEventListener("config-changed", (e) => changes.push(plain(e.detail.config)));
  editor.setConfig({ entity: MOWER, style: "dusk" });
  editor.hass = fakeHass();
  window.document.body.appendChild(editor);
  const select = editor.shadowRoot.querySelector('[data-select="style"]');
  const options = () => [...select.options].map((o) => [o.value, o.textContent]);
  // A style set but not loaded keeps its place.
  assert.deepEqual(options(), [["", "Standard"], ["night", "Night"], ["dusk", "dusk (not loaded)"]]);
  assert.equal(select.value, "dusk");
  // A style registered later shows up.
  registerStyle(window, { id: "dusk", label: "Dusk" });
  assert.deepEqual(options(), [["", "Standard"], ["night", "Night"], ["dusk", "Dusk"]]);

  select.value = "night";
  select.dispatchEvent(new window.Event("change", { bubbles: true, composed: true }));
  assert.deepEqual(changes.at(-1), { entity: MOWER, style: "night" });
  // The colour fields show the style's colours while left empty.
  assert.equal(editor.shadowRoot.querySelector('[data-cpicker="accent"]').value, "#00e5ff");

  select.value = "";
  select.dispatchEvent(new window.Event("change", { bubbles: true, composed: true }));
  assert.deepEqual(changes.at(-1), { entity: MOWER });
});

test("the cutting height reads with the viewer's decimal mark, also while it is dragged", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass({ language: "de" });
  const card = await mount(window, hass);
  await sendFeed(window, hass, GEOMETRY, { ...DOCKED, settings: { mode: "map", height_max: 7, areas: { 0: { cutting_height: 4.5 } } } });
  await openTab(window, card, "settings");
  await click(window, $(card, '[data-page="mowing"]'));
  const out = $(card, '[data-out="cutting_height"]');
  assert.equal(out.textContent, "4,5 cm");
  const slider = $(card, 'input[data-range="cutting_height"]');
  slider.value = "5.5";
  slider.dispatchEvent(new window.Event("input", { bubbles: true }));
  assert.equal($(card, '[data-out="cutting_height"]').textContent, "5,5 cm");
});

test("a change of the number format alone redraws the card", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass({ language: "de" });
  const card = await mount(window, hass);
  await sendFeed(window, hass, GEOMETRY, { ...DOCKED, settings: { mode: "map", height_max: 7, areas: { 0: { cutting_height: 4.5 } } } });
  await openTab(window, card, "settings");
  await click(window, $(card, '[data-page="mowing"]'));
  card.hass = { ...hass, locale: { language: "de", number_format: "comma_decimal" } };
  await settle(window);
  assert.equal($(card, '[data-out="cutting_height"]').textContent, "4.5 cm");
});
