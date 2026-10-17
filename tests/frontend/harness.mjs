// Runs the card's modules in a fresh DOM, with a Home Assistant that records
// what the card asks of it.

import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";

const FRONTEND = new URL("../../custom_components/dreame_mower/frontend/", import.meta.url);

export const MOWER = "lawn_mower.a2";
export const DEVICE = "device-a2";

// A window with the given modules of the frontend folder loaded, in order.
export function load(...files) {
  const dom = new JSDOM("<!doctype html><html><body></body></html>", { runScripts: "outside-only", pretendToBeVisual: true });
  const window = dom.window;
  // The confirm dialogs answer what the test sets; yes by default.
  window.confirmAnswer = true;
  window.confirm = () => window.confirmAnswer;
  for (const file of files) window.eval(readFileSync(new URL(file, FRONTEND), "utf8"));
  return window;
}

// An entity of the mower's device, as the entity registry lists it.
export function entry(entityId, translationKey) {
  return { entity_id: entityId, device_id: DEVICE, platform: "dreame_mower", translation_key: translationKey };
}

// A Home Assistant with the mower and `states`; the websocket subscriptions,
// calls and service calls the card makes are recorded. fire("ready") and
// fire("disconnected") play the socket coming back and going away.
export function fakeHass({ states = {}, entities = {}, ws = () => ({}) } = {}) {
  const listeners = new Map();
  const hass = {
    fire(name) {
      // Subscriptions die with the socket.
      if (name === "disconnected") for (const subscription of hass.subscriptions) subscription.active = false;
      for (const listener of listeners.get(name) || []) listener();
    },
    states: { [MOWER]: { entity_id: MOWER, state: "docked", attributes: { friendly_name: "A2" } }, ...states },
    entities: { [MOWER]: entry(MOWER, null), ...entities },
    config: { time_zone: "UTC" },
    subscriptions: [],
    calls: [],
    services: [],
    connection: {
      subscribeMessage(callback, message) {
        const subscription = { callback, message, active: true };
        hass.subscriptions.push(subscription);
        return Promise.resolve(() => {
          subscription.active = false;
        });
      },
      addEventListener(name, listener) {
        listeners.set(name, [...(listeners.get(name) || []), listener]);
      },
      removeEventListener(name, listener) {
        listeners.set(name, (listeners.get(name) || []).filter((l) => l !== listener));
      },
    },
    async callWS(message) {
      hass.calls.push(message);
      return ws(message);
    },
    async callService(domain, service, data, target) {
      hass.services.push({ domain, service, data, target });
    },
  };
  return hass;
}

// The open subscriptions of a websocket command type.
export function subscribed(hass, type) {
  return hass.subscriptions.filter((s) => s.active && s.message.type === type);
}

// Lets pending promises settle and the card draw its next frame.
export async function settle(window) {
  for (let i = 0; i < 3; i++) {
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => window.requestAnimationFrame(() => resolve()));
  }
}

// A card on the page for the mower.
export async function mount(window, hass, config = {}) {
  const card = window.document.createElement("dreame-mower-card");
  card.setConfig({ entity: MOWER, ...config });
  card.hass = hass;
  window.document.body.appendChild(card);
  await settle(window);
  return card;
}

// Objects made in the page as plain ones of the test, to compare them.
export const plain = (value) => JSON.parse(JSON.stringify(value));

export const $ = (card, selector) => card.shadowRoot.querySelector(selector);
export const $$ = (card, selector) => [...card.shadowRoot.querySelectorAll(selector)];

export async function click(window, element) {
  element.dispatchEvent(new window.MouseEvent("click", { bubbles: true, composed: true }));
  await settle(window);
}

export async function openTab(window, card, tab) {
  await click(window, $(card, `.tabs [data-tab="${tab}"]`));
}
