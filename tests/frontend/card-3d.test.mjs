import assert from "node:assert/strict";
import { test } from "node:test";

import { $, MOWER, click, fakeHass, load, mount, openTab, settle } from "./harness.mjs";

// The mower's two maps, of which only the lawn has a stored cloud.
const CLOUDS = {
  maps: [
    { id: 1, index: 0, name: "Lawn", url: "/api/dreame_mower/entry1/point_cloud/0", has_cloud: true },
    { id: 2, index: 1, name: "Meadow", url: "/api/dreame_mower/entry1/point_cloud/1", has_cloud: false },
  ],
  active_index: 0,
};

// A page with the card and its 3D view, once the frontend is up.
async function page() {
  const window = load("dreame-mower-card.js", "dreame-mower-card-3d.js");
  window.customElements.define("home-assistant", class extends window.HTMLElement {});
  await settle(window);
  return window;
}

function mowerOn(hass, mapId) {
  hass.states[MOWER] = { ...hass.states[MOWER], attributes: { ...hass.states[MOWER].attributes, current_map_id: mapId } };
  return hass;
}

function hassWithClouds(mapId) {
  const hass = fakeHass({ ws: (message) => (message.type === "dreame_mower/point_clouds" ? CLOUDS : {}) });
  hass.fetched = [];
  hass.fetchWithAuth = async (url) => {
    hass.fetched.push(url);
    return { ok: false, status: 404, headers: new Map() };
  };
  return mowerOn(hass, mapId);
}

async function showMap(window, card, hass, mapId) {
  card.hass = { ...mowerOn(hass, mapId) };
  await settle(window);
}

const openButton = (card) => $(card, '.secbtns [data-pc3d="open"]');

test("the 3D button only shows when the map the card shows has a stored cloud", async () => {
  const window = await page();
  const hass = hassWithClouds(2);
  const card = await mount(window, hass);
  assert.equal(openButton(card), null);
  await showMap(window, card, hass, 1);
  assert.ok(openButton(card));
  // Nothing is downloaded to decide.
  assert.deepEqual(hass.fetched, []);
});

test("the 3D view takes the map's place and closing it brings the map back", async () => {
  const window = await page();
  window.console.error = () => {};
  const hass = hassWithClouds(1);
  const card = await mount(window, hass);
  await click(window, openButton(card));
  assert.ok($(card, ".map").hidden);
  assert.ok(!$(card, ".cover").hidden);
  assert.ok($(card, ".cover .pc3d"));
  await click(window, $(card, '.cover [data-pc3d="close"]'));
  assert.ok(!$(card, ".map").hidden);
  assert.ok($(card, ".cover").hidden);
});

test("leaving the Mow tab closes the 3D view", async () => {
  const window = await page();
  window.console.error = () => {};
  const hass = hassWithClouds(1);
  const card = await mount(window, hass);
  await click(window, openButton(card));
  await openTab(window, card, "history");
  await openTab(window, card, "mow");
  assert.ok(!$(card, ".map").hidden);
  assert.ok($(card, ".cover").hidden);
});

test("switching to a map without a cloud closes the 3D view", async () => {
  const window = await page();
  window.console.error = () => {};
  const hass = hassWithClouds(1);
  const card = await mount(window, hass);
  await click(window, openButton(card));
  await showMap(window, card, hass, 2);
  assert.ok(!$(card, ".map").hidden);
  assert.ok($(card, ".cover").hidden);
  assert.equal(openButton(card), null);
});

test("the help of the 3D view offers to invert the ↑ ↓ keys", async () => {
  const window = await page();
  window.console.error = () => {};
  const hass = hassWithClouds(1);
  const card = await mount(window, hass);
  await click(window, openButton(card));
  await click(window, $(card, '.cover [data-pc3d="help"]'));
  assert.ok(!$(card, ".cover .help").hidden);
  const box = $(card, '.cover .help [data-pc3d="invert"]');
  assert.equal(box.checked, false);
  assert.match($(card, ".cover .help").textContent, /invert ↑ ↓/);
});
