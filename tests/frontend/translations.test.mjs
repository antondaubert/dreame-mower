import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";

import { IntlMessageFormat } from "intl-messageformat";

import { $, $$, MOWER, entry, fakeHass, load, localizer, mount, openTab, settle, translations } from "./harness.mjs";

const CARD = readFileSync(new URL("../../custom_components/dreame_mower/frontend/dreame-mower-card.js", import.meta.url), "utf8");

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

test("translations Home Assistant loads for others leave the card as it is", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass({ language: "fr" });
  const card = await mount(window, hass);
  let built = 0;
  const build = card._buildShapes.bind(card);
  card._buildShapes = () => {
    built += 1;
    build();
  };

  // Another category loaded: a new localize that reads the card's texts alike.
  card.hass = { ...hass, localize: localizer("fr") };
  await settle(window);
  assert.equal(built, 0);

  card.hass = { ...hass, language: "en", locale: { language: "en" }, localize: localizer("en") };
  await settle(window);
  assert.equal(built, 1);
  assert.equal($(card, '.tabs [data-tab="mow"]').textContent, "Mow");
});

test("the card catches up with texts that arrive after their language", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass({ language: "pt" });
  const card = await mount(window, hass);
  // Both say "Corte" for the Mow tab.
  card.hass = { ...hass, language: "pt-BR", localize: localizer("pt") };
  await settle(window);
  card.hass = { ...hass, language: "pt-BR", localize: localizer("pt-BR") };
  await settle(window);
  assert.equal($(card, '.tabs [data-tab="settings"]').textContent, translations("pt-BR").common.tab_settings);
});

test("a failed load of the translations is tried again after a while, not with every state", async () => {
  const window = load("dreame-mower-card.js");
  const hass = fakeHass({ language: "fr" });
  let requests = 0;
  hass.loadBackendTranslation = async () => {
    requests += 1;
    throw new Error("socket closed");
  };
  const card = await mount(window, hass);
  assert.equal(requests, 1);

  card.hass = { ...hass, states: {} };
  await settle(window);
  assert.equal(requests, 1);

  const now = window.Date.now();
  window.Date.now = () => now + 61000;
  card.hass = { ...hass, states: {} };
  await settle(window);
  assert.equal(requests, 2);

  // Another language is asked for at once.
  card.hass = { ...hass, language: "de" };
  await settle(window);
  assert.equal(requests, 3);
});

test("sections get the card's texts and month names", async () => {
  const window = load("dreame-mower-card.js");
  await mount(window, fakeHass({ language: "fr" }));
  const { tr, trCount, monthName } = window.customElements.get("dreame-mower-card").helpers;
  assert.equal(tr("tab_mow"), "Tonte");
  assert.equal(trCount("obstacles_met", 2), "2 rencontrés");
  assert.equal(monthName(0), translations("fr").common.month_jan);
  assert.equal(monthName(12), "");
});

test("counts take the plural forms of the language", async () => {
  const window = load("dreame-mower-card.js");
  await mount(window, fakeHass({ language: "ru" }));
  const { trCount } = window.customElements.get("dreame-mower-card").helpers;
  const common = translations("ru").common;
  const zones = (key, count) => new IntlMessageFormat(common[`zone_count_${key}`], "ru").format({ count });
  assert.equal(trCount("zone_count", 1), zones("one", 1));
  assert.equal(trCount("zone_count", 3), zones("few", 3));
  assert.equal(trCount("zone_count", 5), zones("many", 5));
  assert.equal(trCount("zone_count", 21), zones("one", 21));
  assert.notEqual(zones("few", 3), zones("many", 3));
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

const LANGUAGES = readdirSync(new URL("../../custom_components/dreame_mower/translations/", import.meta.url)).map((file) => file.replace(/\.json$/, ""));
const PLURAL_FORMS = ["zero", "two", "few", "many"];

test("each language has the card's texts with the same placeholders", () => {
  const english = translations("en").common;
  const plurals = Object.keys(english).filter((key) => key.endsWith("_one")).map((key) => key.slice(0, -"_one".length)).filter((base) => `${base}_other` in english);
  for (const language of LANGUAGES) {
    const common = translations(language).common;
    // The plural forms the language takes beyond one and other for counts the
    // card shows (French "many" is for millions only).
    const rules = new Intl.PluralRules(language);
    const forms = [...new Set(Array.from({ length: 1001 }, (_, n) => rules.select(n)))].filter((form) => PLURAL_FORMS.includes(form));
    const expected = [...Object.keys(english), ...plurals.flatMap((base) => forms.map((form) => `${base}_${form}`))];
    assert.deepEqual(Object.keys(common).sort(), expected.sort(), language);
    for (const [key, message] of Object.entries(common)) {
      const form = PLURAL_FORMS.find((name) => key.endsWith(`_${name}`) && !(key in english));
      const source = form ? `${key.slice(0, -form.length - 1)}_other` : key;
      // Home Assistant drops a translation whose placeholders differ from the
      // English ones, plural forms included.
      assert.deepEqual(argumentsOf(message), argumentsOf(english[source]), `${language}: ${key}`);
    }
  }
});

test("a date reads in the order and with the marks of the language", async () => {
  const format = async (language, d) => {
    const window = load("dreame-mower-card.js");
    await mount(window, fakeHass({ language }));
    return window.customElements.get("dreame-mower-card").helpers.formatDayOf(d);
  };
  const year = new Date().getFullYear();
  const thisYear = new Date(year, 9, 16);
  const lastYear = new Date(year - 1, 9, 16);
  const weekday = (language, d) => translations(language).common[`weekday_${["sun", "mon", "tue", "wed", "thu", "fri", "sat"][d.getDay()]}`];
  assert.equal(await format("en", thisYear), `${weekday("en", thisYear)} 16 Oct`);
  assert.equal(await format("en", lastYear), `${weekday("en", lastYear)} 16 Oct ${year - 1}`);
  assert.equal(await format("de", thisYear), `${weekday("de", thisYear)}., 16. Okt.`);
  assert.equal(await format("hu", lastYear), `${year - 1}. okt. 16., ${weekday("hu", lastYear)}`);
  assert.equal(await format("ru", thisYear), `${weekday("ru", thisYear)}, 16 окт.`);
});

test("numbers follow the number format set in Home Assistant", async () => {
  const format = async (language, numberFormat) => {
    const window = load("dreame-mower-card.js");
    const hass = fakeHass({ language });
    if (numberFormat) hass.locale = { language, number_format: numberFormat };
    await mount(window, hass);
    return window.customElements.get("dreame-mower-card").helpers.formatNumber;
  };
  const en = await format("en");
  assert.deepEqual([en(75.44), en(0.5, 2), en(1234.56)], ["75.4", "0.50", "1234.6"]);
  // The language's own format, as Home Assistant's default "language" has it.
  const de = await format("de", "language");
  assert.deepEqual([de(75.44), de(0.5, 2), de(1234.56)], ["75,4", "0,50", "1234,6"]);
  assert.equal((await format("de", "comma_decimal"))(75.44), "75.4");
  assert.equal((await format("en", "decimal_comma"))(75.44), "75,4");
  assert.equal((await format("de", "none"))(75.44), "75.4");
  // Latin digits, as the card's other numbers.
  assert.equal((await format("fa"))(75.44), "75.4");
});
