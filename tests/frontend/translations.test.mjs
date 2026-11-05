import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { IntlMessageFormat } from "intl-messageformat";

import { $, $$, MOWER, entry, fakeHass, load, localizer, mount, openTab, settle, translations } from "./harness.mjs";

const CARD = readFileSync(new URL("../../custom_components/dreame_mower/frontend/dreame-mower-card.js", import.meta.url), "utf8");
const LANGUAGES = ["en", "fr"];

function argumentsOf(message) {
  const names = new Set();
  const walk = (elements) => {
    for (const element of elements) {
      if (element.value && typeof element.value === "string" && element.type !== 0) names.add(element.value);
      for (const option of Object.values(element.options || {})) walk(option.value);
    }
  };
  walk(new IntlMessageFormat(message, "en").getAst());
  return [...names].sort();
}

test("the card speaks French when Home Assistant does", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass({ language: "fr" });
  const card = await mount(window, hass);
  assert.deepEqual(
    $$(card, ".tabs [data-tab]").map((b) => b.textContent),
    ["Tonte", "Historique", "Programmation", "Réglages"],
  );
  assert.equal($(card, '.status [data-action="find"]').getAttribute("aria-label"), "Trouver mon robot");
  assert.equal($(card, '.mapbtn[data-zoom="in"]').title, "Zoom avant");
  assert.deepEqual(hass.translationRequests, [["common", "dreame_mower"]]);
});

test("the card redraws once the translations arrive", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass({ language: "fr" });
  hass.localize = () => "";
  const card = await mount(window, hass);
  assert.deepEqual($$(card, ".tabs [data-tab]").map((b) => b.textContent), ["", "", "", ""]);

  card.hass = { ...hass, localize: localizer("fr") };
  await settle(window);
  assert.deepEqual(
    $$(card, ".tabs [data-tab]").map((b) => b.textContent),
    ["Tonte", "Historique", "Programmation", "Réglages"],
  );
});

test("schedules read in French, days and plurals included", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass({
    language: "fr",
    states: {
      "switch.a2_schedule_1": {
        entity_id: "switch.a2_schedule_1",
        state: "on",
        attributes: {
          schedule_name: "Semaine",
          tasks: [
            { week_day: "monday", start_time: 600, type: "all_area" },
            { week_day: "saturday", start_time: 570, type: "edge" },
          ],
        },
      },
    },
    entities: { "switch.a2_schedule_1": entry("switch.a2_schedule_1", "schedule") },
  });
  const card = await mount(window, hass);
  await openTab(window, card, "schedules");
  assert.match($(card, ".view.schedules .row").textContent, /sam\. 09:30 bordures · lun\. 10:00 globale/);
  assert.match($(card, ".view.schedules .group").textContent, /Programmations du robot/);
});

test("the editor speaks French when Home Assistant does", async () => {
  const window = load("dreame-mower-card.js");
  const editor = window.document.createElement("dreame-mower-card-editor");
  editor.setConfig({ entity: MOWER });
  editor.hass = fakeHass({ language: "fr" });
  window.document.body.appendChild(editor);
  const root = editor.shadowRoot;
  assert.equal(root.querySelector("summary").textContent, "Interface");
  assert.equal(root.querySelector('[data-tr="color_background"]').textContent, "Fond de la carte");
  assert.equal(root.querySelector('[data-select="style"]').options[0].textContent, "Standard");
});

test("every text the card names is in the English translations", () => {
  const common = translations("en").common;
  const named = [
    ...[...CARD.matchAll(/\btr\("([a-z0-9_]+)"/g)].map((match) => match[1]),
    ...[...CARD.matchAll(/\btrCount\("([a-z0-9_]+)"/g)].flatMap((match) => [`${match[1]}_one`, `${match[1]}_other`]),
  ];
  assert.ok(named.length > 100);
  assert.deepEqual([...new Set(named.filter((key) => !(key in common)))], []);
});

test("each language has the card's texts with the same placeholders", () => {
  const english = translations("en").common;
  for (const language of LANGUAGES) {
    const common = translations(language).common;
    assert.deepEqual(Object.keys(common).sort(), Object.keys(english).sort(), language);
    for (const [key, message] of Object.entries(common)) {
      assert.deepEqual(argumentsOf(message), argumentsOf(english[key]), `${language}: ${key}`);
    }
  }
});
