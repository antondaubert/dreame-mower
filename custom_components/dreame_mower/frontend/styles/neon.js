/*
 * Neon: a dark look with glowing outlines, bright zone colours and outlined
 * controls. Leaves the card's background and text to the theme.
 */
customElements.whenDefined("dreame-mower-card").then(() => {
  customElements.get("dreame-mower-card").registerStyle({
    id: "neon",
    label: "Neon",
    base: "dark",
    colors: {
      on_accent: "#06060f",
      success: "#00ffcc",
      warning: "#ffe25c",
      error: "#e0115f",
      info: "#8440ff",
    },
    palette: {
      background: "#080814",
      surface: "#14122a",
      text: "#e8e0ff",
      zoneName: "#e8e0ff",
      muted: "#a89cc8",
      stripe: "#ffffff",
      stripeOpacity: 0.05,
      lawnShade: 0.82,
      pathOuter: "#2a2450",
      pathInner: "#15122e",
      noGo: "#e0115f",
      ignoreObstacles: "#8440ff",
      spot: "#00ffcc",
      trail: "#ffffff",
      trailOpacity: 0.8,
      zoneFillOpacity: 0.22,
      labelOpacity: 0.92,
      working: "#00ffcc",
      brand: "#00e5ff",
      edge: "#8440ff",
    },
    zoneColors: [
      "#00e5ff", "#ff2bd6", "#00ffcc", "#ffe25c", "#8440ff", "#ff7a3d", "#5cff6a", "#4d8bff",
      "#ff4d6d", "#b6ff3d", "#ff8ad8", "#3dffe0", "#c78bff", "#ffc23d", "#3dd1ff", "#ff5c8a",
    ],
    glow: 0.75,
    buttons: "outlined",
    font: "Rajdhani, sans-serif",
    // What the options above cannot do: lettering, the big buttons by role,
    // the map's chips and the progress bar.
    css: `
.style-neon .tabs button, .style-neon .strip button, .style-neon .seg button, .style-neon .chip,
.style-neon .primary, .style-neon .big, .style-neon .group, .style-neon .status .caption {
  text-transform: uppercase; letter-spacing: 1px; font-weight: 700;
}
.style-neon .status .state {
  font-weight: 700; letter-spacing: .8px;
  text-shadow: 0 0 1px #fff, 0 0 calc(var(--mower-glow-size, 12px) * .5) var(--mower-glow-color, var(--mower-brand)), 0 0 var(--mower-glow-size, 12px) var(--mower-glow-color, var(--mower-brand));
}
.style-neon .tabs button.on { color: #fff; }
.style-neon .big { border-radius: 8px; color: var(--mower-brand); background: linear-gradient(145deg, rgba(20,24,40,.78), rgba(8,10,22,.72)); border-color: color-mix(in srgb, currentColor 45%, transparent); }
.style-neon .big.start { color: var(--mower-success); }
.style-neon .big.pause { color: var(--mower-warning); }
.style-neon .big.stop { color: var(--mower-error); }
.style-neon .big ha-icon { color: inherit; }
.style-neon .big:not(:disabled) { box-shadow: 0 0 1px #fff, 0 0 calc(var(--mower-glow-size, 12px) * .4) currentColor, 0 0 calc(var(--mower-glow-size, 12px) * .8) currentColor; }
.style-neon .big:disabled { color: var(--mower-muted); border-color: var(--mower-divider); box-shadow: none; }
.style-neon .primary { border-radius: 8px; }
.style-neon .mapbtn, .style-neon .mapchip {
  background: rgba(8,10,22,.78); color: var(--mower-brand);
  border-color: color-mix(in srgb, var(--mower-brand) 50%, transparent);
  box-shadow: 0 0 calc(var(--mower-glow-size, 12px) * .5) color-mix(in srgb, var(--mower-brand) 55%, transparent);
}
.style-neon .progress { height: 10px; border-radius: 3px; background: rgba(0,0,0,.55); box-shadow: inset 0 2px 4px #000b; }
.style-neon .progress > div { border-radius: 5px; background: linear-gradient(90deg, var(--mower-working), #fff 48%, var(--mower-working) 62%, var(--mower-info)); }
`,
  });
});
