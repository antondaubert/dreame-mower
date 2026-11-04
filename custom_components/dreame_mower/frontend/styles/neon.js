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
  });
});
