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

// A Home Assistant whose list of clouds answers with what `answer` returns,
// counting the lists asked for; the page's clock is set with now.at.
function hassListing(window, answer) {
  const hass = hassWithClouds(1);
  hass.lists = 0;
  hass.callWS = async (message) => {
    if (message.type !== "dreame_mower/point_clouds") return {};
    hass.lists++;
    return answer();
  };
  let now = 1000000;
  window.Date.now = () => now;
  return { hass, now: { at: (ms) => (now = ms) } };
}

test("a list of clouds that failed is asked for again after a while", async () => {
  const window = await page();
  let offline = true;
  const { hass, now } = hassListing(window, () => {
    if (offline) throw new Error("the mower is offline");
    return CLOUDS;
  });
  const card = await mount(window, hass);
  const asked = hass.lists;
  assert.equal(openButton(card), null);
  offline = false;
  // Not on every change of state.
  await showMap(window, card, hass, 1);
  assert.equal(hass.lists, asked);
  now.at(1000000 + 60000);
  await showMap(window, card, hass, 1);
  assert.equal(hass.lists, asked + 1);
  assert.ok(openButton(card));
});

test("a list of clouds without the map the card shows is asked for again", async () => {
  const window = await page();
  let maps = [];
  const { hass, now } = hassListing(window, () => ({ maps, active_index: null }));
  const card = await mount(window, hass);
  const asked = hass.lists;
  maps = CLOUDS.maps;
  now.at(1000000 + 60000);
  await showMap(window, card, hass, 1);
  assert.equal(hass.lists, asked + 1);
  assert.ok(openButton(card));
  // Once it holds the map, a change of state asks nothing more.
  now.at(1000000 + 180000);
  await showMap(window, card, hass, 1);
  assert.equal(hass.lists, asked + 1);
});

test("a cloud the mower stores later gets its button after a while", async () => {
  const window = await page();
  let clouds = { maps: CLOUDS.maps.map((m) => ({ ...m, has_cloud: false })), active_index: 0 };
  const { hass, now } = hassListing(window, () => clouds);
  const card = await mount(window, hass);
  assert.equal(openButton(card), null);
  clouds = CLOUDS;
  now.at(1000000 + 60000);
  await showMap(window, card, hass, 1);
  assert.ok(openButton(card));
});

test("a card taken off the page asks nothing, and lists again once it is back", async () => {
  const window = await page();
  const { hass, now } = hassListing(window, () => {
    throw new Error("the mower is offline");
  });
  const card = await mount(window, hass);
  card.remove();
  await settle(window);
  const asked = hass.lists;
  now.at(1000000 + 600000);
  await showMap(window, card, hass, 1);
  await showMap(window, card, hass, 2);
  assert.equal(hass.lists, asked);
  window.document.body.appendChild(card);
  await settle(window);
  assert.equal(hass.lists, asked + 1);
});
