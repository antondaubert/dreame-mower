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
