/* LumenCache brightness x colour-temperature card, and its editor. No dependencies, no build step. */

const MIN_PCT = 0.1;           // the lowest brightness the system takes
const SEND_INTERVAL_MS = 150;
const SETTLE_MS = 3000;        // how long a released value stands in for the entity's state
const GLIDE_S = 0.25;          // how long the handle settles when there is no fade time to follow
const MAX_GLIDE_S = 3;         // and the longest it takes, however long the fade is
const DEFAULT_RANGE = [2700, 5000];
const DEFAULT_STEPS = [2700, 3000, 3500, 4000, 5000];   // what the editor offers when it has no list to start from
const FADE_STYLES = ["segments", "slider", "stepper", "classic"];
const SEND_MODES = ["live", "on_release"];
const LAYOUTS = ["pad", "sliders"];

/** Every setting of the card. All of them can be changed in the card editor. */
export const DEFAULTS = {
  name: "",
  layout: "pad",                // pad (colour across, brightness up) or sliders (one each)
  send_mode: "live",            // live (throttled while dragging) or on_release
  brightness_curve: "gamma",    // gamma, perceptual or linear
  min_brightness_pct: 5,        // the lowest brightness the light shows; under it the pad means off
  max_brightness_pct: 100,
  color_steps: null,            // [{kelvin, color}] or null to use the integration's list (or a smooth range)
  snap_to_steps: true,
  marker_color: "#ffffff",      // the line between off and on
  show_fade: true,
  fade_style: "segments",       // segments, slider, stepper or classic (a box with buttons)
  fade_presets: [0, 0.5, 1, 3, 10],
};

const STYLE = `
  :host { display: block; }
  [hidden] { display: none !important; }
  ha-card { padding: 16px; display: flex; flex-direction: column; gap: 12px; color: var(--primary-text-color); }
  header { display: flex; align-items: center; gap: 12px; }
  .title { flex: 1; min-width: 0; }
  .name { font-size: 16px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .readout { color: var(--secondary-text-color); font-variant-numeric: tabular-nums; font-size: 13px; }
  button { font: inherit; cursor: pointer; color: var(--primary-text-color); }
  .power {
    width: 40px; height: 40px; border-radius: 50%; border: 1px solid var(--divider-color);
    background: var(--card-background-color); display: grid; place-items: center; padding: 0;
  }
  .power[aria-pressed="true"] { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: transparent; }
  .power svg { width: 20px; height: 20px; fill: currentColor; }
  .pad {
    position: relative; height: 220px; border-radius: 12px; overflow: hidden; touch-action: none;
    cursor: crosshair; user-select: none; -webkit-user-select: none;
    border: 1px solid var(--divider-color);
  }
  .pad.off { filter: grayscale(0.85) brightness(0.8); }
  .pad .shade { position: absolute; inset: 0; background: linear-gradient(to bottom, transparent, rgba(0,0,0,.78)); }
  .pad .grid { position: absolute; inset: 0; pointer-events: none; }
  .pad .grid line { stroke: rgba(255,255,255,.28); stroke-width: 1; stroke-dasharray: 2 4; vector-effect: non-scaling-stroke; }
  .offzone {
    position: absolute; left: 0; right: 0; bottom: 0; pointer-events: none;
    background: repeating-linear-gradient(135deg, rgba(0,0,0,.45) 0 6px, rgba(0,0,0,.25) 6px 12px);
  }
  .marker { position: absolute; left: 0; right: 0; height: 0; border-top: 2px solid var(--marker, #fff); pointer-events: none; }
  .marker::before, .marker::after {
    content: ""; position: absolute; top: -6px; width: 9px; height: 9px; background: var(--marker, #fff);
    transform: rotate(45deg); box-shadow: 0 0 3px rgba(0,0,0,.6);
  }
  .marker::before { left: -5px; } .marker::after { right: -5px; }
  .marker span, .offzone span {
    position: absolute; font-size: 10px; letter-spacing: .04em; text-transform: uppercase; color: #fff;
    text-shadow: 0 0 3px rgba(0,0,0,.8); white-space: nowrap;
  }
  .marker span { right: 10px; bottom: 4px; font-variant-numeric: tabular-nums; }
  .offzone span { left: 50%; top: 50%; transform: translate(-50%, -50%); }
  .tick { position: absolute; font-size: 10px; color: rgba(255,255,255,.85); text-shadow: 0 0 3px rgba(0,0,0,.7);
    font-variant-numeric: tabular-nums; pointer-events: none; white-space: nowrap; }
  .tick.y { left: 6px; transform: translateY(-50%); }
  .tick.x { bottom: 4px; transform: translateX(-50%); }
  .tick.x.first { transform: none; } .tick.x.last { transform: translateX(-100%); }
  .handle {
    position: absolute; width: 22px; height: 22px; margin: -11px 0 0 -11px; border-radius: 50%;
    border: 3px solid #fff; box-shadow: 0 0 0 1px rgba(0,0,0,.4), 0 2px 6px rgba(0,0,0,.5);
    pointer-events: none;
  }
  .handle.glide { transition: left var(--glide) ease-out, top var(--glide) ease-out, background-color var(--glide); }
  @media (prefers-reduced-motion: reduce) { .handle { transition: none !important; } }
  .sliders { display: flex; justify-content: space-evenly; gap: 16px; }
  .scol { display: flex; flex-direction: column; align-items: center; gap: 8px; min-width: 0; }
  .slabel { display: flex; flex-direction: column; align-items: center; font-size: 13px; color: var(--secondary-text-color); }
  .slabel .sval { font-variant-numeric: tabular-nums; color: var(--primary-text-color); font-size: 15px; font-weight: 500; min-height: 1.3em; }
  .strack { display: flex; align-items: stretch; gap: 6px; height: 220px; }
  .track {
    position: relative; width: 56px; border-radius: 28px; overflow: hidden; touch-action: none; cursor: pointer;
    border: 1px solid var(--divider-color); user-select: none; -webkit-user-select: none;
  }
  .track.off { filter: grayscale(0.85) brightness(0.8); }
  .thumb {
    position: absolute; left: 50%; width: 22px; height: 22px; margin: -11px 0 0 -11px; border-radius: 50%;
    border: 3px solid #fff; box-shadow: 0 0 0 1px rgba(0,0,0,.4), 0 2px 6px rgba(0,0,0,.5); pointer-events: none;
  }
  .thumb.glide { transition: top var(--glide) ease-out, background-color var(--glide); }
  @media (prefers-reduced-motion: reduce) { .thumb { transition: none !important; } }
  .sticks { position: relative; width: 3.4em; }
  .sticks span { position: absolute; left: 0; transform: translateY(-50%); font-size: 10px; color: var(--secondary-text-color);
    font-variant-numeric: tabular-nums; white-space: nowrap; }
  .axes { display: flex; justify-content: space-between; font-size: 11px; color: var(--secondary-text-color); }
  .msg { color: var(--error-color); font-size: 13px; }

  /* Fade time: four looks. */
  .fade { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .fade .lbl { font-size: 13px; color: var(--secondary-text-color); }
  .fade input[type=number] {
    width: 4.5em; font: inherit; padding: 4px 6px; border-radius: 6px; text-align: right;
    border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color);
  }
  .chip { border: 1px solid var(--divider-color); background: transparent; border-radius: 14px; padding: 2px 10px; font-size: 12px; }
  .chip[aria-pressed="true"] { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: transparent; }
  .seg { display: inline-flex; flex-wrap: wrap; gap: 2px; padding: 3px; border-radius: 999px;
    background: var(--secondary-background-color, rgba(127,127,127,.18)); }
  .seg button { border: 0; background: transparent; border-radius: 999px; padding: 5px 12px; font-size: 12px; }
  .seg button[aria-pressed="true"] { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .fade-slider { display: block; }
  .sl-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px; }
  .sl-val { font-variant-numeric: tabular-nums; font-size: 14px; font-weight: 500; }
  .fade-slider input[type=range] {
    -webkit-appearance: none; appearance: none; width: 100%; height: 6px; border-radius: 3px; margin: 8px 0; outline: none;
    background: linear-gradient(to right, var(--primary-color) var(--fill, 0%), var(--divider-color) var(--fill, 0%));
  }
  .fade-slider input[type=range]::-webkit-slider-thumb {
    -webkit-appearance: none; width: 20px; height: 20px; border-radius: 50%; border: 3px solid var(--card-background-color);
    background: var(--primary-color); box-shadow: 0 0 0 1px var(--divider-color), 0 1px 4px rgba(0,0,0,.4); cursor: grab;
  }
  .fade-slider input[type=range]::-moz-range-thumb {
    width: 14px; height: 14px; border-radius: 50%; border: 3px solid var(--card-background-color);
    background: var(--primary-color); box-shadow: 0 0 0 1px var(--divider-color); cursor: grab;
  }
  .sl-ticks { display: flex; justify-content: space-between; font-size: 10px; color: var(--secondary-text-color); }
  .step { display: inline-flex; align-items: center; border: 1px solid var(--divider-color); border-radius: 999px; }
  .step button { width: 34px; height: 32px; border: 0; background: transparent; font-size: 18px; border-radius: 999px; }
  .step .val { min-width: 5em; text-align: center; font-variant-numeric: tabular-nums; font-size: 14px; }
`;

const POWER_ICON = '<svg viewBox="0 0 24 24"><path d="M13 3h-2v10h2V3zm4.83 2.17-1.42 1.42A6.92 6.92 0 0 1 19 12c0 3.87-3.13 7-7 7s-7-3.13-7-7c0-2.27 1.08-4.28 2.76-5.55L6.34 5.04A8.94 8.94 0 0 0 3 12a9 9 0 0 0 18 0c0-2.74-1.23-5.18-3.17-6.83z"/></svg>';

/** Approximate RGB of a blackbody of `kelvin` (Tanner Helland's fit), as [r, g, b]. */
export function kelvinToRgb(kelvin) {
  const t = kelvin / 100;
  const clamp = (v) => Math.max(0, Math.min(255, Math.round(v)));
  const r = t <= 66 ? 255 : 329.698727446 * Math.pow(t - 60, -0.1332047592);
  const g = t <= 66 ? 99.4708025861 * Math.log(t) - 161.1195681661 : 288.1221695283 * Math.pow(t - 60, -0.0755148492);
  const b = t >= 66 ? 255 : t <= 19 ? 0 : 138.5177312231 * Math.log(t - 10) - 305.0447927307;
  return [clamp(r), clamp(g), clamp(b)];
}

export const kelvinToCss = (kelvin) => `rgb(${kelvinToRgb(kelvin).join(",")})`;
export const kelvinToHex = (kelvin) => "#" + kelvinToRgb(kelvin).map((v) => v.toString(16).padStart(2, "0")).join("");

/**
 * Temperatures from a config or an attribute into [{kelvin, color}], ascending. An entry is a number or an
 * object {kelvin, color}; `color` is any CSS colour, and without one the band takes the colour of its kelvin.
 */
export function normalizeSteps(list) {
  if (!Array.isArray(list)) return [];
  const byKelvin = new Map();
  for (const item of list) {
    const kelvin = Number(typeof item === "object" && item !== null ? item.kelvin : item);
    if (!Number.isFinite(kelvin) || kelvin <= 0) continue;
    byKelvin.set(kelvin, { kelvin, color: (typeof item === "object" && item && item.color) || null });
  }
  return [...byKelvin.values()].sort((a, b) => a.kelvin - b.kelvin);
}

/** Percentages marked on the pad, per curve, chosen so the labels do not collide. */
const TICKS = { perceptual: [1, 10, 100], gamma: [10, 25, 50, 100], linear: [25, 50, 75, 100] };

/** Position 0..1 along the Y axis (0 = bottom) to a brightness in percent of the top, and back. */
export const curves = {
  perceptual: {
    toPct: (f) => MIN_PCT * Math.pow(100 / MIN_PCT, f),
    toFraction: (pct) => Math.log(Math.max(pct, MIN_PCT) / MIN_PCT) / Math.log(100 / MIN_PCT),
  },
  // Lightness grows about as the square of the signal, so equal steps up the pad look like equal steps of brightness.
  gamma: {
    toPct: (f) => 100 * f * f,
    toFraction: (pct) => Math.sqrt(Math.max(pct, 0) / 100),
  },
  linear: {
    toPct: (f) => MIN_PCT + f * (100 - MIN_PCT),
    toFraction: (pct) => (Math.max(pct, MIN_PCT) - MIN_PCT) / (100 - MIN_PCT),
  },
};

/** Round to the 0.1 % the system accepts, with fewer digits where a fraction is not visible. */
export function roundPct(pct) {
  return pct < 10 ? Math.round(pct * 10) / 10 : Math.round(pct);
}

const isColor = (value) =>
  typeof value === "string" && (typeof CSS === "undefined" || typeof CSS.supports !== "function" || CSS.supports("color", value));

/**
 * What is wrong with a card config, as [{field, message}]; empty when it is fine. Nothing is corrected or
 * dropped silently: the card refuses a config with problems, and the editor shows these and waits for a fix.
 */
export function validateConfig(config) {
  const c = config || {};
  const errors = [];
  const bad = (field, message) => errors.push({ field, message });
  const given = (key) => c[key] !== undefined && c[key] !== null;
  const number = (key, lo, hi, label) => {
    if (!given(key)) return null;
    const n = typeof c[key] === "number" ? c[key] : Number.NaN;
    if (!Number.isFinite(n) || n < lo || n > hi) {
      bad(key, `${label} must be a number from ${lo} to ${hi}.`);
      return null;
    }
    return n;
  };
  const oneOf = (key, allowed, label) => {
    if (given(key) && !allowed.includes(c[key])) bad(key, `${label} must be one of: ${allowed.join(", ")}.`);
  };
  const flag = (key, label) => {
    if (given(key) && typeof c[key] !== "boolean") bad(key, `${label} must be on or off.`);
  };

  if (typeof c.entity !== "string" || !c.entity) bad("entity", "Choose a light.");
  const min = number("min_brightness_pct", 0, 99, "The minimum brightness");
  const max = number("max_brightness_pct", 1, 100, "The maximum brightness");
  if ((min ?? DEFAULTS.min_brightness_pct) >= (max ?? DEFAULTS.max_brightness_pct) && (min !== null || max !== null)
      && !errors.some((e) => e.field === "min_brightness_pct" || e.field === "max_brightness_pct")) {
    bad("max_brightness_pct", `The maximum brightness (${max ?? DEFAULTS.max_brightness_pct} %) must be higher than the minimum (${min ?? DEFAULTS.min_brightness_pct} %).`);
  }
  oneOf("brightness_curve", Object.keys(curves), "The brightness scale");
  oneOf("layout", LAYOUTS, "The layout");
  oneOf("fade_style", FADE_STYLES, "The fade look");
  oneOf("send_mode", SEND_MODES, "Sending");
  flag("snap_to_steps", "Snapping");
  flag("show_fade", "Showing the fade time");
  number("fade", 0, 6553, "The starting fade time");
  if (given("marker_color") && !isColor(c.marker_color)) bad("marker_color", `"${c.marker_color}" is not a colour.`);

  if (given("fade_presets")) {
    const list = c.fade_presets;
    if (!Array.isArray(list) || !list.length) bad("fade_presets", "Give at least one fade choice, in seconds.");
    else if (list.some((v) => typeof v !== "number" || !Number.isFinite(v) || v < 0 || v > 6553)) {
      bad("fade_presets", "Each fade choice must be a number of seconds from 0 to 6553.");
    }
  }

  if (given("color_steps")) {
    const list = c.color_steps;
    if (!Array.isArray(list) || list.length < 2) {
      bad("color_steps", "List at least two temperatures, or leave the list out to use the integration's.");
    } else {
      const seen = new Set();
      for (const item of list) {
        const obj = typeof item === "object" && item !== null;
        const kelvin = obj ? item.kelvin : item;
        if (typeof kelvin !== "number" || !Number.isFinite(kelvin) || kelvin < 1000 || kelvin > 20000) {
          bad("color_steps", `${Number.isFinite(kelvin) ? kelvin : "A"} K is not a usable temperature: use 1000 to 20000.`);
        } else if (seen.has(kelvin)) {
          bad("color_steps", `${kelvin} K is listed twice.`);
        }
        seen.add(kelvin);
        if (obj && item.color != null && !isColor(item.color)) bad("color_steps", `"${item.color}" is not a colour (${kelvin} K).`);
      }
    }
  }
  return errors;
}

/** A valid config with the defaults filled in and the temperatures sorted. */
export function resolveConfig(config) {
  const c = { ...DEFAULTS, ...config };
  c.fade_presets = [...new Set(c.fade_presets)].sort((a, b) => a - b);
  c.color_steps = c.color_steps == null ? null : normalizeSteps(c.color_steps);
  return c;
}

class LumenCacheCard extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
    this._settled = null;       // the value just released, until the entity reports its own
    this._drag = null;          // {pct, kelvin, raw: {x, y}} while the pointer is down: the value, and where the pointer is
    this._off = false;          // in the gap under the minimum brightness: off (true) or at the minimum
    this._lastSent = 0;
    this._timer = null;
    this._fade = 0;
    this._error = "";
  }

  setConfig(config) {
    const errors = validateConfig(config);
    if (errors.length) throw new Error(errors.map((e) => e.message).join(" "));
    this._config = { entity: config.entity, ...resolveConfig(config) };
    this._fade = Number.isFinite(Number(config.fade)) ? Number(config.fade) : 0;
    this._build();
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const state = this._config && hass.states[this._config.entity];
    if (state && state.state === "on" && state.attributes.color_temp_kelvin) this._lastKelvin = state.attributes.color_temp_kelvin;
    // The released value stands in until the entity reports a new state, so the handle does not slide back first.
    if (this._settled && hass.states[this._config.entity] !== this._settled.since) this._settled = null;
    if (this._config && !this._drag) this._render();
  }

  getCardSize() { return 5; }

  static getConfigElement() { return document.createElement("lumencache-card-editor"); }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find((id) => id.startsWith("light.") && hass.states[id].attributes.min_color_temp_kelvin);
    return { entity: entity || "light.example" };
  }

  // --- model ---------------------------------------------------------------

  get _stateObj() { return this._hass && this._hass.states[this._config.entity]; }

  get _attrs() { return (this._stateObj && this._stateObj.attributes) || {}; }

  /** The temperatures the light can be set to, ascending, with their colours: the card's own list, else the integration's. */
  get _stepEntries() {
    const entries = this._config.color_steps ?? normalizeSteps(this._attrs.color_temp_steps);
    return entries.length >= 2 ? entries : [];   // fewer than two is a continuous range
  }

  get _steps() { return this._stepEntries.map((e) => e.kelvin); }

  get _range() {
    const steps = this._steps;
    if (steps.length) return [steps[0], steps[steps.length - 1]];
    const a = this._attrs;
    return [a.min_color_temp_kelvin || DEFAULT_RANGE[0], a.max_color_temp_kelvin || DEFAULT_RANGE[1]];
  }

  get _tunable() {
    return (this._attrs.supported_color_modes || []).includes("color_temp");
  }

  /**
   * With listed temperatures the X axis is split into equal bands, one each, whatever the gaps in kelvin
   * (2700 to 3000 is no narrower than 4000 to 5000). A position gives the temperature of its band; with
   * `snap_to_steps` off it gives a value between neighbouring bands' temperatures instead.
   */
  _kelvinAt(fx) {
    const steps = this._steps;
    const [lo, hi] = this._range;
    if (!steps.length) return Math.round((lo + fx * (hi - lo)) / 10) * 10;
    const n = steps.length;
    if (this._config.snap_to_steps) return steps[Math.min(n - 1, Math.floor(fx * n))];
    const pos = fx * n - 0.5;   // in bands, 0 at the middle of the first
    if (pos <= 0) return steps[0];
    if (pos >= n - 1) return steps[n - 1];
    const i = Math.floor(pos);
    return Math.round((steps[i] + (pos - i) * (steps[i + 1] - steps[i])) / 10) * 10;
  }

  /** Where a temperature sits across the pad, 0 to 1: the middle of its band. The inverse of `_kelvinAt`. */
  _xOf(kelvin) {
    const steps = this._steps;
    const [lo, hi] = this._range;
    if (!steps.length) return Math.min(1, Math.max(0, (kelvin - lo) / (hi - lo)));
    const n = steps.length;
    if (kelvin <= steps[0]) return 0.5 / n;
    if (kelvin >= steps[n - 1]) return (n - 0.5) / n;
    const i = steps.findIndex((k, j) => kelvin >= k && kelvin <= steps[j + 1]);
    return (i + (kelvin - steps[i]) / (steps[i + 1] - steps[i]) + 0.5) / n;
  }

  /** The temperature after an arrow key: the next listed one when snapping, else the moved position. */
  _nudge(kelvin, direction, moved) {
    const steps = this._steps;
    if (!(this._config.snap_to_steps && steps.length) || direction === 0) return moved;
    const next = direction > 0 ? steps.find((k) => k > kelvin) : [...steps].reverse().find((k) => k < kelvin);
    return next ?? this._kelvinAt(this._xOf(kelvin));
  }

  /** The colour for a temperature: its band's colour if it is a listed one, else the colour of its kelvin. */
  _colorOf(kelvin) {
    const entry = this._stepEntries.find((e) => e.kelvin === kelvin);
    return (entry && entry.color) || kelvinToCss(kelvin);
  }

  /** CSS for the pad: a flat colour, one band for each listed temperature, or a smooth ramp. */
  _background(direction = "to right") {
    const [lo, hi] = this._range;
    if (!this._tunable) return kelvinToCss(4000);
    const entries = this._stepEntries;
    if (!entries.length) {
      const stops = [0, 0.25, 0.5, 0.75, 1].map((f) => `${kelvinToCss(lo + f * (hi - lo))} ${f * 100}%`);
      return `linear-gradient(${direction}, ${stops.join(", ")})`;
    }
    const stops = entries.flatMap((e, i) => {
      const color = this._colorOf(e.kelvin);
      return [`${color} ${(i / entries.length) * 100}%`, `${color} ${((i + 1) / entries.length) * 100}%`];
    });
    return `linear-gradient(${direction}, ${stops.join(", ")})`;
  }

  /** What to show: the drag in progress, else the value just released, else the entity's state. */
  get _current() {
    if (this._drag) return this._drag;
    if (this._settled) return this._settled;
    const a = this._attrs;
    const [lo] = this._range;
    const kelvin = a.color_temp_kelvin || this._lastKelvin || lo;   // an off light reports none: keep the last
    if (!this._stateObj || this._stateObj.state !== "on") return { pct: 0, kelvin };   // off sits at the bottom
    return { pct: a.brightness != null ? Math.max(MIN_PCT, roundPct((a.brightness / 255) * 100)) : this._max, kelvin };
  }

  // --- brightness ------------------------------------------------------------

  /** Lowest brightness the light shows; under it the pad means off. */
  get _min() { return Math.max(MIN_PCT, this._config.min_brightness_pct); }

  get _max() { return this._config.max_brightness_pct; }

  get _hasGap() { return this._config.min_brightness_pct > MIN_PCT; }

  /** Pad height 0..1 to a brightness in percent, with the top of the pad at the maximum, and back. */
  _toPct(f) { return (curves[this._config.brightness_curve].toPct(f) * this._max) / 100; }

  _toFraction(pct) { return Math.min(1, curves[this._config.brightness_curve].toFraction((pct * 100) / this._max)); }

  _fractions({ pct, kelvin }) {
    return {
      x: this._tunable ? this._xOf(kelvin) : 0.5,
      y: pct <= 0 ? 0 : this._toFraction(pct),
    };
  }

  /**
   * Brightness for a pad height. Under the minimum there is nothing between off and the minimum, so the value
   * is one or the other: moving down gives off, moving up gives the minimum. A move of under 2% of the
   * pad height is ignored, so a shaking hand does not flip it.
   */
  _brightnessAt(fy) {
    const fmin = this._hasGap ? this._toFraction(this._min) : 0;
    if (fy >= fmin) {
      this._off = false;
      this._lastFy = fy;
      return roundPct(Math.max(MIN_PCT, this._toPct(fy)));
    }
    this._lastFy ??= fy;
    if (Math.abs(fy - this._lastFy) >= 0.02) {
      this._off = fy < this._lastFy;
      this._lastFy = fy;
    }
    return this._off ? 0 : this._min;
  }

  /**
   * The value for a pointer position, and the position itself (the handle follows it until release). The pad
   * sets both axes; in the sliders layout each slider sets its own and keeps the other's value.
   */
  _fromPointer(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    const clamp = (v) => Math.min(1, Math.max(0, v));
    if (this._role === "pad") {
      const fx = clamp((event.clientX - rect.left) / rect.width);
      const fy = clamp(1 - (event.clientY - rect.top) / rect.height);
      return {
        pct: this._brightnessAt(fy),
        kelvin: this._tunable ? this._kelvinAt(fx) : this._current.kelvin,
        raw: { x: this._tunable ? fx : 0.5, y: fy },
      };
    }
    const along = clamp(1 - (event.clientY - rect.top) / rect.height);   // up is more
    const cur = this._current;
    const at = this._fractions(cur);
    if (this._role === "bri") return { pct: this._brightnessAt(along), kelvin: cur.kelvin, raw: { x: at.x, y: along } };
    return { pct: cur.pct, kelvin: this._kelvinAt(along), raw: { x: along, y: at.y } };
  }

  // --- DOM -----------------------------------------------------------------

  _build() {
    const pad = `
        <div class="pad" role="slider" tabindex="0" aria-label="Brightness and colour temperature">
          <div class="shade"></div>
          <svg class="grid" preserveAspectRatio="none" viewBox="0 0 100 100"></svg>
          <div class="offzone"><span>Off</span></div>
          <div class="marker"><span></span></div>
          <div class="handle"></div>
        </div>
        <div class="axes"><span class="xl"></span><span>Brightness ↑</span></div>`;
    const sliders = `
        <div class="sliders">
          <div class="scol">
            <div class="slabel"><span>Brightness</span><span class="sval bval"></span></div>
            <div class="strack">
              <div class="track bri" data-role="bri" role="slider" tabindex="0" aria-label="Brightness">
                <div class="offzone"><span>Off</span></div>
                <div class="marker"><span></span></div>
                <div class="thumb"></div>
              </div>
              <div class="sticks bticks"></div>
            </div>
          </div>
          <div class="scol cct-col">
            <div class="slabel"><span>Colour temperature</span><span class="sval cval"></span></div>
            <div class="strack">
              <div class="track cct" data-role="cct" role="slider" tabindex="0" aria-label="Colour temperature"><div class="thumb"></div></div>
              <div class="sticks cticks"></div>
            </div>
          </div>
        </div>`;
    this._root.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <header>
          <div class="title"><div class="name"></div><div class="readout"></div></div>
          <button class="power" aria-label="Power" aria-pressed="false">${POWER_ICON}</button>
        </header>
        ${this._config.layout === "sliders" ? sliders : pad}
        <div class="fade"></div>
        <div class="msg" hidden></div>
      </ha-card>`;
    const $ = (sel) => this._root.querySelector(sel);
    this._name = $(".name");
    this._readout = $(".readout");
    this._power = $(".power");
    this._msg = $(".msg");
    this._fadeBox = $(".fade");
    this._pad = $(".pad");   // null in the sliders layout
    this._handle = $(".handle");
    this._offzone = $(".offzone");
    this._marker = $(".marker");
    this._surfaces = this._pad
      ? [{ el: this._pad, role: "pad" }]
      : [{ el: $(".track.bri"), role: "bri" }, { el: $(".track.cct"), role: "cct" }];
    if (!this._pad) {
      this._briTrack = $(".track.bri");
      this._cctTrack = $(".track.cct");
      this._briThumb = this._briTrack.querySelector(".thumb");
      this._cctThumb = this._cctTrack.querySelector(".thumb");
    }

    for (const { el, role } of this._surfaces) {
      el.addEventListener("pointerdown", (e) => this._down(e, role));
      el.addEventListener("pointermove", (e) => this._move(e));
      el.addEventListener("pointerup", (e) => this._up(e));
      el.addEventListener("pointercancel", (e) => this._up(e));
      el.addEventListener("keydown", (e) => this._key(e, role));
    }
    this._power.addEventListener("click", () => this._toggle());
    this._buildFade();
    this._ticksKey = "";   // the ticks are drawn in _render, once the entity's range is known
  }

  // --- fade time: four looks, all setting the same value ----------------------

  _buildFade() {
    const box = this._fadeBox;
    const { show_fade: show, fade_style: style, fade_presets: presets } = this._config;
    box.hidden = !show;
    box.className = `fade fade-${style}`;
    box.innerHTML = "";
    this._fadeInput = this._fadeSlider = this._fadeValue = null;
    if (!show) return;
    const label = (s) => (s === 0 ? "Instant" : `${s} s`);
    const buttons = (cls, text) => presets
      .map((s) => `<button class="${cls}" data-s="${s}" aria-pressed="false">${text(s)}</button>`).join("");

    if (style === "classic") {
      box.innerHTML = `<label class="lbl" for="fade">Fade</label><input id="fade" type="number" min="0" max="6553" step="0.1"><span>s</span>${buttons("chip", (s) => (s === 0 ? "none" : `${s} s`))}`;
      this._fadeInput = box.querySelector("input");
      this._fadeInput.addEventListener("change", () => this._setFade(parseFloat(this._fadeInput.value) || 0));
    } else if (style === "slider") {
      box.innerHTML = `
        <div class="sl-head"><span class="lbl">Fade</span><span class="sl-val"></span></div>
        <input type="range" min="0" max="${presets.length - 1}" step="1" aria-label="Fade time">
        <div class="sl-ticks">${presets.map((s) => `<span>${label(s)}</span>`).join("")}</div>`;
      this._fadeSlider = box.querySelector("input");
      this._fadeValue = box.querySelector(".sl-val");
      this._fadeSlider.addEventListener("input", () => this._setFade(presets[Number(this._fadeSlider.value)]));
    } else if (style === "stepper") {
      box.innerHTML = `<span class="lbl">Fade</span><div class="step"><button class="minus" aria-label="Shorter fade">−</button><span class="val"></span><button class="plus" aria-label="Longer fade">+</button></div>`;
      this._fadeValue = box.querySelector(".val");
      box.querySelector(".minus").addEventListener("click", () => this._setFade(this._nextFade(-1)));
      box.querySelector(".plus").addEventListener("click", () => this._setFade(this._nextFade(1)));
    } else {
      box.innerHTML = `<span class="lbl">Fade</span><div class="seg" role="group" aria-label="Fade time">${buttons("", label)}</div>`;
    }
    box.querySelectorAll("button[data-s]").forEach((b) =>
      b.addEventListener("click", () => this._setFade(parseFloat(b.dataset.s))));
  }

  /** The next fade time for the stepper: tenths below 1 s, halves below 5 s, then whole seconds, then fives. */
  _nextFade(direction) {
    const v = this._fade;
    const at = direction > 0 ? v : v - 1e-9;
    const inc = at < 1 ? 0.1 : at < 5 ? 0.5 : at < 20 ? 1 : 5;
    return Math.round((v + direction * inc) * 10) / 10;
  }

  _setFade(seconds) {
    this._fade = Math.max(0, Math.min(6553, seconds));
    this._renderFade();
  }

  _renderFade() {
    const box = this._fadeBox;
    if (!box || box.hidden) return;
    const text = this._fade === 0 ? "Instant" : `${this._fade} s`;
    if (this._fadeInput && this._root.activeElement !== this._fadeInput) this._fadeInput.value = this._fade;
    if (this._fadeValue) this._fadeValue.textContent = text;
    if (this._fadeSlider) {
      const presets = this._config.fade_presets;
      const nearest = presets.reduce((best, s, i) => (Math.abs(s - this._fade) < Math.abs(presets[best] - this._fade) ? i : best), 0);
      this._fadeSlider.value = nearest;
      this._fadeSlider.style.setProperty("--fill", `${presets.length > 1 ? (nearest / (presets.length - 1)) * 100 : 0}%`);
    }
    box.querySelectorAll("button[data-s]").forEach((b) =>
      b.setAttribute("aria-pressed", String(parseFloat(b.dataset.s) === this._fade)));
  }

  // --- drawing ---------------------------------------------------------------

  _renderTicks() {
    const [lo, hi] = this._range;
    const { brightness_curve: curveName, min_brightness_pct: minPct } = this._config;
    const key = JSON.stringify([lo, hi, this._tunable, curveName, this._max, minPct, this._stepEntries.map((e) => e.kelvin)]);
    if (key === this._ticksKey) return;
    this._ticksKey = key;
    this._pad.querySelectorAll(".tick").forEach((el) => el.remove());
    const lines = [];
    const marks = [...new Set(TICKS[curveName].map((p) => Math.min(p, this._max)))].filter((p) => p > this._min * 1.5 || !this._hasGap);
    for (const pct of marks) {
      const y = 100 - this._toFraction(pct) * 100;
      lines.push(`<line x1="0" x2="100" y1="${y}" y2="${y}"/>`);
      const tick = document.createElement("span");
      tick.className = "tick y";
      tick.style.top = `${Math.min(94, Math.max(6, y))}%`;
      tick.textContent = `${pct}%`;
      this._pad.appendChild(tick);
    }
    if (this._tunable) {
      const steps = this._steps;
      const labels = steps.length ? steps : [0, 1, 2, 3, 4].map((i) => Math.round((lo + ((hi - lo) * i) / 4) / 100) * 100);
      labels.forEach((k, i) => {
        const f = steps.length ? (i + 0.5) / labels.length : (k - lo) / (hi - lo);   // a band's middle
        const tick = document.createElement("span");
        tick.className = `tick x${!steps.length && f < 0.04 ? " first" : !steps.length && f > 0.96 ? " last" : ""}`;
        tick.style.left = `${f * 100}%`;
        tick.textContent = k;
        this._pad.appendChild(tick);
      });
    }
    this._pad.querySelector(".grid").innerHTML = lines.join("");
    this._root.querySelector(".xl").textContent = this._tunable
      ? (this._steps.length ? "Warm → cool, in kelvin" : `Warm ${lo} K → cool ${hi} K`)
      : "Brightness only";
  }

  /** The line between off and on, and the hatched zone under it. */
  _renderMarker() {
    this._offzone.hidden = this._marker.hidden = !this._hasGap;
    if (!this._hasGap) return;
    const at = this._toFraction(this._min) * 100;
    this._offzone.style.height = `${at}%`;
    this._marker.style.bottom = `calc(${at}% - 1px)`;
    this._marker.style.setProperty("--marker", this._config.marker_color);
    this._marker.firstElementChild.textContent = this._pad ? `on from ${this._min}%` : "";   // a slider has no room for it
  }

  /** Labels beside the two sliders, where the pad has them on its edges. */
  _renderSliderTicks() {
    const [lo, hi] = this._range;
    const key = JSON.stringify([lo, hi, this._tunable, this._config.brightness_curve, this._max, this._config.min_brightness_pct, this._steps]);
    if (key === this._ticksKey) return;
    this._ticksKey = key;
    const label = (box, items) => {
      box.innerHTML = "";
      for (const [f, text] of items) {
        const span = document.createElement("span");
        span.style.top = `${(1 - f) * 100}%`;
        span.textContent = text;
        box.appendChild(span);
      }
    };
    const marks = [...new Set(TICKS[this._config.brightness_curve].map((p) => Math.min(p, this._max)))]
      .filter((p) => p > this._min * 1.5 || !this._hasGap);
    label(this._root.querySelector(".bticks"), marks.map((p) => [this._toFraction(p), `${p}%`]));
    const steps = this._steps;
    const kelvins = steps.length ? steps : [0, 1, 2, 3, 4].map((i) => Math.round((lo + ((hi - lo) * i) / 4) / 100) * 100);
    label(this._root.querySelector(".cticks"), kelvins.map((k, i) => [steps.length ? (i + 0.5) / kelvins.length : (k - lo) / (hi - lo), k]));
    this._root.querySelector(".cct-col").hidden = !this._tunable;
  }

  _render() {
    if (!this._name) return;
    const s = this._stateObj;
    const name = (s && s.attributes.friendly_name) || this._config.entity;
    this._name.textContent = this._config.name || name;
    if (!s) { this._readout.textContent = "Entity not found"; return; }

    const on = s.state === "on";
    const cur = this._current;
    const held = this._drag || this._settled;
    const off = held ? cur.pct === 0 : !on;
    const glide = `${this._fade > 0 ? Math.min(this._fade, MAX_GLIDE_S) : GLIDE_S}s`;
    const color = this._tunable ? this._colorOf(cur.kelvin) : kelvinToCss(4000);
    const { x, y } = this._drag ? this._drag.raw : this._fractions(cur);

    if (this._pad) {
      this._renderTicks();
      this._pad.style.background = this._background();
      this._pad.classList.toggle("off", off);
      // The handle follows the pointer exactly, then settles on the value over the fade time.
      this._handle.classList.toggle("glide", !this._drag);
      this._handle.style.setProperty("--glide", glide);
      this._handle.style.left = `${x * 100}%`;
      this._handle.style.top = `${(1 - y) * 100}%`;
      this._handle.style.background = color;
    } else {
      this._renderSliderTicks();
      this._briTrack.style.background = `linear-gradient(to top, rgba(0,0,0,.85), ${color})`;
      this._cctTrack.style.background = this._background("to top");   // warm at the bottom
      this._briTrack.classList.toggle("off", off);
      this._cctTrack.classList.toggle("off", off);
      for (const [thumb, f] of [[this._briThumb, y], [this._cctThumb, x]]) {
        thumb.classList.toggle("glide", !this._drag);
        thumb.style.setProperty("--glide", glide);
        thumb.style.top = `${(1 - f) * 100}%`;
        thumb.style.background = color;
      }
      this._root.querySelector(".bval").textContent = off ? "Off" : `${cur.pct} %`;
      this._root.querySelector(".cval").textContent = this._tunable ? `${cur.kelvin} K` : "";
    }
    this._renderMarker();

    this._power.setAttribute("aria-pressed", String(on));
    const showing = held ? cur.pct > 0 : on;
    this._readout.textContent = showing
      ? `${this._tunable ? cur.kelvin + " K · " : ""}${cur.pct} %`
      : "Off";
    for (const { el } of this._surfaces) el.setAttribute("aria-valuetext", this._readout.textContent);
    this._renderFade();
    this._msg.hidden = !this._error;
    this._msg.textContent = this._error;
  }

  // --- input ---------------------------------------------------------------

  _down(event, role) {
    this._role = role;
    event.currentTarget.setPointerCapture(event.pointerId);
    this._off = !this._stateObj || this._stateObj.state !== "on";
    this._lastFy = null;
    this._lastDragSent = null;
    this._drag = this._fromPointer(event);
    this._render();
    if (this._config.send_mode === "live") this._send(this._drag);
  }

  _move(event) {
    if (!this._drag) return;
    this._drag = this._fromPointer(event);
    this._render();
    if (this._config.send_mode === "live") this._throttledSend();
  }

  _up(event) {
    if (!this._drag) return;
    const final = this._fromPointer(event);
    this._drag = null;
    clearTimeout(this._timer);
    this._settled = { pct: final.pct, kelvin: final.kelvin, since: this._stateObj };
    clearTimeout(this._settleTimer);
    // In case no new state arrives; a long fade keeps the value until it has finished.
    this._settleTimer = setTimeout(() => { this._settled = null; this._render(); }, Math.max(SETTLE_MS, this._fade * 1000 + 500));
    this._send(final);
    this._render();
  }

  _key(event, role = "pad") {
    const keys = {
      pad: { ArrowUp: [0, 0.03], ArrowDown: [0, -0.03], ArrowRight: [0.03, 0], ArrowLeft: [-0.03, 0] },
      bri: { ArrowUp: [0, 0.03], ArrowRight: [0, 0.03], ArrowDown: [0, -0.03], ArrowLeft: [0, -0.03] },
      cct: { ArrowUp: [0.03, 0], ArrowRight: [0.03, 0], ArrowDown: [-0.03, 0], ArrowLeft: [-0.03, 0] },
    };
    const step = keys[role][event.key];
    if (!step) return;
    event.preventDefault();
    const cur = this._current;
    const on = this._stateObj && this._stateObj.state === "on";
    const { x, y } = this._fractions(cur);
    const fx = Math.min(1, Math.max(0, x + step[0]));
    let pct = on ? cur.pct : 0;
    if (step[1] > 0) {
      pct = this._hasGap && pct < this._min ? this._min : roundPct(Math.max(MIN_PCT, this._toPct(Math.min(1, y + step[1]))));
    } else if (step[1] < 0) {
      const lower = roundPct(this._toPct(Math.max(0, y + step[1])));
      pct = this._hasGap ? (pct <= this._min || lower < this._min ? 0 : lower) : Math.max(MIN_PCT, lower);
    }
    this._send({
      pct,
      kelvin: this._tunable ? this._nudge(cur.kelvin, step[0], this._kelvinAt(fx)) : cur.kelvin,
    });
  }

  _toggle() {
    const s = this._stateObj;
    if (!s) return;
    this._call(s.state === "on" ? "turn_off" : "turn_on", {}, "light");
  }

  _throttledSend() {
    // The value only changes at a band's edge or a brightness step, so skip repeats.
    const last = this._lastDragSent;
    if (last && last.pct === this._drag.pct && last.kelvin === this._drag.kelvin) return;
    const wait = SEND_INTERVAL_MS - (Date.now() - this._lastSent);
    if (wait <= 0) { this._send(this._drag); return; }
    clearTimeout(this._timer);
    this._timer = setTimeout(() => this._drag && this._send(this._drag), wait);
  }

  _send({ pct, kelvin }) {
    this._lastSent = Date.now();
    this._lastDragSent = { pct, kelvin };
    const data = { brightness_pct: pct };
    if (this._tunable) data.color_temp_kelvin = kelvin;
    if (this._fade > 0) data.transition = this._fade;
    this._call("set_light", data, "lumencache");
  }

  async _call(service, data, domain) {
    try {
      await this._hass.callService(domain, service, data, { entity_id: this._config.entity });
      this._error = "";
    } catch (err) {
      this._error = (err && err.message) || "The command failed";
    }
    if (!this._drag) this._render();
  }
}

// --- the editor: every setting above, in Home Assistant's card editor ------------

const EDITOR_STYLE = `
  :host { display: block; }
  [hidden] { display: none !important; }
  .editor { display: flex; flex-direction: column; gap: 14px; color: var(--primary-text-color); }
  fieldset { border: 1px solid var(--divider-color); border-radius: 8px; margin: 0; padding: 10px 12px 12px;
    display: flex; flex-direction: column; gap: 10px; min-width: 0; }
  legend { padding: 0 6px; font-size: 12px; letter-spacing: .06em; text-transform: uppercase; color: var(--secondary-text-color); }
  label.row { display: flex; align-items: center; justify-content: space-between; gap: 12px; font-size: 14px; }
  label.row > span { flex: 1; min-width: 0; }
  input, select { font: inherit; padding: 6px 8px; border-radius: 6px; min-width: 0;
    border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); }
  input[type=number] { width: 6em; text-align: right; }
  input[type=text], select { width: 55%; }
  input[type=color] { width: 40px; height: 32px; padding: 2px; }
  input[type=checkbox] { width: 18px; height: 18px; }
  .hint { font-size: 12px; color: var(--secondary-text-color); margin: 0; }
  .steps { display: flex; flex-direction: column; gap: 8px; }
  .step-row { display: flex; align-items: center; gap: 8px; }
  .step-row input[type=number] { width: 5.5em; }
  .step-row .unit { font-size: 13px; color: var(--secondary-text-color); }
  .step-row .spacer { flex: 1; }
  button { font: inherit; cursor: pointer; border: 1px solid var(--divider-color); background: transparent;
    color: var(--primary-text-color); border-radius: 6px; padding: 5px 10px; }
  button.icon { padding: 4px 8px; }
  .errors { border: 1px solid var(--error-color, #d33); border-radius: 8px; padding: 10px 12px; font-size: 13px;
    background: color-mix(in srgb, var(--error-color, #d33) 12%, transparent); display: flex; flex-direction: column; gap: 6px; }
  .errors ul { margin: 0; padding-left: 18px; }
  .errors span { color: var(--secondary-text-color); }
  [aria-invalid="true"] { border-color: var(--error-color, #d33); outline: 1px solid var(--error-color, #d33); }
  button.add { align-self: flex-start; }
`;

const RECENT_KEY = "lumencache-card:recent";
const CARD_TYPE = "custom:lumencache-card";
const COPIED = ["layout", "send_mode", "brightness_curve", "min_brightness_pct", "max_brightness_pct", "color_steps", "snap_to_steps",
  "marker_color", "show_fade", "fade_style", "fade_presets"];   // what "copy from another card" takes over

/** Every lumencache card in a dashboard config, however deep in stacks, grids and sections. */
function cardsIn(node, found = []) {
  if (Array.isArray(node)) node.forEach((n) => cardsIn(n, found));
  else if (node && typeof node === "object") {
    if (node.type === CARD_TYPE && typeof node.entity === "string") found.push(node);
    Object.values(node).forEach((n) => cardsIn(n, found));
  }
  return found;
}

class LumenCacheCardEditor extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
    this._draft = { type: CARD_TYPE };   // what is in the form; it may have problems
    this._emitted = "";                  // the last config handed to Home Assistant, which is always a good one
    this._errors = [];
  }

  setConfig(config) {
    const same = JSON.stringify(config) === this._emitted;   // our own change coming back: keep the focus where it is
    this._draft = { ...config };
    if (!same || !this._built) {
      this._errors = validateConfig(this._draft);
      this._render();
    }
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first && this._built) this._render();
  }

  set lovelace(lovelace) {
    this._lovelace = lovelace;
    if (this._built) this._render();
  }

  /** The rows of the temperature list: the form's own, else the integration's for this entity, else a typical one. */
  _rows() {
    const asRow = (item) => (typeof item === "object" && item !== null
      ? { kelvin: Number(item.kelvin), color: item.color || null }
      : { kelvin: Number(item), color: null });
    if (Array.isArray(this._draft.color_steps)) return this._draft.color_steps.map(asRow);
    const state = this._hass && this._hass.states[this._draft.entity];
    const listed = normalizeSteps(state && state.attributes.color_temp_steps);
    return (listed.length ? listed : normalizeSteps(DEFAULT_STEPS)).map(asRow);
  }

  _lights() {
    return Object.keys((this._hass && this._hass.states) || {}).filter((id) => id.startsWith("light.")).sort();
  }

  /** The settings of other lights' cards: in this dashboard, and ones edited earlier in this browser. */
  _others() {
    const byEntity = new Map();
    try {
      const recent = JSON.parse(localStorage.getItem(RECENT_KEY) || "{}");
      for (const [entity, config] of Object.entries(recent)) byEntity.set(entity, config);
    } catch (err) { /* no storage: the dashboard's cards still work */ }
    try {
      for (const card of cardsIn(this._lovelace && this._lovelace.config)) byEntity.set(card.entity, card);
    } catch (err) { /* an editor without the dashboard config */ }
    byEntity.delete(this._draft.entity);
    return [...byEntity.entries()].map(([entity, config]) => ({ entity, config }));
  }

  _remember(config) {
    try {
      const recent = JSON.parse(localStorage.getItem(RECENT_KEY) || "{}");
      const kept = {};
      for (const key of COPIED) if (key in config) kept[key] = config[key];
      recent[config.entity] = kept;
      localStorage.setItem(RECENT_KEY, JSON.stringify(recent));
    } catch (err) { /* nothing to remember it in */ }
  }

  _set(key, value) {
    if (value === undefined || value === "") delete this._draft[key];
    else this._draft[key] = value;
    this._apply();
  }

  _setRows(rows) {
    this._draft.color_steps = rows.map((r) => (r.color ? { kelvin: r.kelvin, color: r.color } : r.kelvin));
    this._apply();
  }

  /** Hand the form to Home Assistant only if it has no problems; otherwise show them and wait for a fix. */
  _apply() {
    this._errors = validateConfig(this._draft);
    if (!this._errors.length) {
      if (Array.isArray(this._draft.color_steps)) {   // ascending, as the card lays them out
        this._draft.color_steps = normalizeSteps(this._draft.color_steps)
          .map((e) => (e.color ? { kelvin: e.kelvin, color: e.color } : e.kelvin));
      }
      this._emitted = JSON.stringify(this._draft);
      this._remember(this._draft);
      this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: { ...this._draft } }, bubbles: true, composed: true }));
    }
    this._showErrors();
  }

  _showErrors() {
    const banner = this._root.querySelector(".errors");
    if (!banner) return;
    banner.hidden = !this._errors.length;
    banner.innerHTML = this._errors.length
      ? `<strong>Fix this before the card changes:</strong><ul>${this._errors.map((e) => `<li>${esc(e.message)}</li>`).join("")}</ul><span>The card keeps its last good settings until then.</span>`
      : "";
    this._root.querySelectorAll("[aria-invalid]").forEach((el) => el.removeAttribute("aria-invalid"));
    for (const { field } of this._errors) {
      const targets = field === "color_steps" ? ".step-row input"
        : field === "fade_presets" ? '[data-role="presets"]' : `[data-key="${field}"]`;
      this._root.querySelectorAll(targets).forEach((el) => el.setAttribute("aria-invalid", "true"));
    }
  }

  _render() {
    this._built = true;
    const c = { ...DEFAULTS, ...this._draft };
    const own = Array.isArray(this._draft.color_steps);
    const rows = this._rows();
    const lights = this._lights();
    const others = this._others();
    const option = (value, label, current) => `<option value="${esc(value)}"${value === current ? " selected" : ""}>${esc(label)}</option>`;
    const nameOf = (id) => (this._hass && this._hass.states[id] && this._hass.states[id].attributes.friendly_name) || id;
    const shown = (v) => (Number.isFinite(Number(v)) ? v : "");

    this._root.innerHTML = `
      <style>${EDITOR_STYLE}</style>
      <div class="editor">
        <div class="errors" role="alert" hidden></div>
        <fieldset><legend>Light</legend>
          <label class="row"><span>Entity</span>
            <select data-key="entity">
              ${!this._draft.entity ? option("", "Choose a light", "") : ""}
              ${this._draft.entity && !lights.includes(this._draft.entity) ? option(this._draft.entity, this._draft.entity, this._draft.entity) : ""}
              ${lights.map((id) => option(id, `${nameOf(id)} (${id})`, this._draft.entity)).join("")}
            </select></label>
          <label class="row"><span>Name</span><input type="text" data-key="name" value="${esc(this._draft.name)}" placeholder="the entity's name"></label>
          ${others.length ? `
          <label class="row"><span>Copy the settings of another light's card</span>
            <select data-role="copy-from">${option("", "Choose…", "")}${others.map((o) => option(o.entity, `${nameOf(o.entity)} (${o.entity})`, "")).join("")}</select></label>
          <p class="hint">Takes over the layout, the temperatures and colours, the brightness limits, the fade and the sending. This card keeps its own light and name.</p>` : ""}
          <label class="row"><span>Layout</span>
            <select data-key="layout">
              ${option("pad", "Pad (colour × brightness)", c.layout)}
              ${option("sliders", "Two sliders", c.layout)}
            </select></label>
        </fieldset>

        <fieldset><legend>Colour temperatures</legend>
          <label class="row"><span>Use the list from the integration</span><input type="checkbox" data-role="own" ${own ? "" : "checked"}></label>
          <p class="hint">${own ? "Each temperature is one band, all the same width. The colour is the band's background and the handle's." : "The integration's options set the list. Untick to choose the temperatures and their colours here."}</p>
          ${own ? `<div class="steps">${rows.map((e, i) => `
            <div class="step-row" data-i="${i}">
              <input type="number" data-role="kelvin" step="50" value="${shown(e.kelvin)}" aria-label="Kelvin">
              <span class="unit">K</span>
              <input type="color" data-role="color" value="${esc(toHex(e.color) || (Number.isFinite(e.kelvin) && e.kelvin > 0 ? kelvinToHex(e.kelvin) : "#ffffff"))}" aria-label="Background colour">
              <button class="icon" data-role="auto" title="Use the natural colour of this temperature" ${e.color ? "" : "disabled"}>Auto</button>
              <span class="spacer"></span>
              <button class="icon" data-role="remove" aria-label="Remove" ${rows.length <= 2 ? "disabled" : ""}>✕</button>
            </div>`).join("")}</div>
            <button class="add" data-role="add">Add a temperature</button>` : ""}
          <label class="row"><span>Snap to the listed temperatures</span><input type="checkbox" data-key="snap_to_steps" ${c.snap_to_steps ? "checked" : ""}></label>
        </fieldset>

        <fieldset><legend>Brightness</legend>
          <label class="row"><span>Minimum, in % (under it the pad means off; 0 for none)</span><input type="number" data-key="min_brightness_pct" step="0.1" value="${shown(c.min_brightness_pct)}"></label>
          <label class="row"><span>Maximum, in %</span><input type="number" data-key="max_brightness_pct" step="1" value="${shown(c.max_brightness_pct)}"></label>
          <label class="row"><span>Scale up the pad</span>
            <select data-key="brightness_curve">
              ${option("gamma", "Gamma (even to the eye)", c.brightness_curve)}
              ${option("perceptual", "Logarithmic (room for the dimmest)", c.brightness_curve)}
              ${option("linear", "Linear", c.brightness_curve)}
            </select></label>
          <label class="row"><span>Colour of the off / on line</span><input type="color" data-key="marker_color" value="${esc(toHex(c.marker_color) || "#ffffff")}"></label>
        </fieldset>

        <fieldset><legend>Fade time</legend>
          <label class="row"><span>Show it</span><input type="checkbox" data-key="show_fade" ${c.show_fade ? "checked" : ""}></label>
          <label class="row"><span>Look</span>
            <select data-key="fade_style">
              ${option("segments", "Buttons in a row", c.fade_style)}
              ${option("slider", "Slider", c.fade_style)}
              ${option("stepper", "Minus and plus", c.fade_style)}
              ${option("classic", "Box and chips", c.fade_style)}
            </select></label>
          <label class="row"><span>Choices, in seconds (0 is instant)</span><input type="text" data-role="presets" value="${esc((Array.isArray(c.fade_presets) ? c.fade_presets : []).join(", "))}"></label>
        </fieldset>

        <fieldset><legend>Sending</legend>
          <label class="row"><span>While dragging</span>
            <select data-key="send_mode">
              ${option("live", "Send as you drag", c.send_mode)}
              ${option("on_release", "Send when you let go", c.send_mode)}
            </select></label>
        </fieldset>
      </div>`;
    this._wire();
    this._showErrors();
  }

  _wire() {
    const q = (sel) => [...this._root.querySelectorAll(sel)];
    const numberKeys = new Set(["min_brightness_pct", "max_brightness_pct"]);

    q("[data-key]").forEach((el) => el.addEventListener("change", () => {
      const key = el.dataset.key;
      if (el.type === "checkbox") this._set(key, el.checked);
      else if (numberKeys.has(key)) this._set(key, el.value === "" ? undefined : Number(el.value));
      else this._set(key, el.value);
    }));

    const own = this._root.querySelector('[data-role="own"]');
    if (own) own.addEventListener("change", () => {
      if (own.checked) { delete this._draft.color_steps; this._apply(); }
      else this._setRows(this._rows());
      this._render();
    });

    q('[data-role="presets"]').forEach((el) => el.addEventListener("change", () => {
      const parts = el.value.split(",").map((t) => t.trim()).filter((t) => t !== "");
      this._set("fade_presets", parts.length ? parts.map((t) => (t === "" || Number.isNaN(Number(t)) ? t : Number(t))) : undefined);
      this._render();
    }));

    q(".step-row").forEach((row) => {
      const i = Number(row.dataset.i);
      const edit = (change) => {
        const rows = this._rows();
        change(rows);
        this._setRows(rows);
        this._render();
      };
      row.querySelector('[data-role="kelvin"]').addEventListener("change", (e) =>
        edit((rows) => { rows[i] = { ...rows[i], kelvin: e.target.value === "" ? Number.NaN : Number(e.target.value) }; }));
      row.querySelector('[data-role="color"]').addEventListener("change", (e) =>
        edit((rows) => { rows[i] = { ...rows[i], color: e.target.value }; }));
      row.querySelector('[data-role="auto"]').addEventListener("click", () =>
        edit((rows) => { rows[i] = { ...rows[i], color: null }; }));
      row.querySelector('[data-role="remove"]').addEventListener("click", () =>
        edit((rows) => { rows.splice(i, 1); }));
    });

    const add = this._root.querySelector('[data-role="add"]');
    if (add) add.addEventListener("click", () => {
      const rows = this._rows();
      const last = rows.length && Number.isFinite(rows[rows.length - 1].kelvin) ? rows[rows.length - 1].kelvin : 2700;
      rows.push({ kelvin: Math.min(20000, last + 500), color: null });
      this._setRows(rows);
      this._render();
    });

    const copy = this._root.querySelector('[data-role="copy-from"]');
    if (copy) copy.addEventListener("change", () => {
      const from = this._others().find((o) => o.entity === copy.value);
      if (!from) return;
      const next = { type: CARD_TYPE, entity: this._draft.entity };
      if (this._draft.name) next.name = this._draft.name;
      for (const key of COPIED) if (key in from.config) next[key] = JSON.parse(JSON.stringify(from.config[key]));
      this._draft = next;
      this._apply();
      this._render();
    });
  }
}

const esc = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

/** A CSS colour as #rrggbb for an <input type=color>, or "" if it is not one this can read. */
function toHex(color) {
  if (typeof color !== "string") return "";
  if (/^#[0-9a-f]{6}$/i.test(color)) return color.toLowerCase();
  if (/^#[0-9a-f]{3}$/i.test(color)) return "#" + [...color.slice(1)].map((ch) => ch + ch).join("").toLowerCase();
  const m = color.match(/^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/i);
  return m ? "#" + m.slice(1).map((v) => Number(v).toString(16).padStart(2, "0")).join("") : "";
}

if (!customElements.get("lumencache-card")) {
  customElements.define("lumencache-card", LumenCacheCard);
  customElements.define("lumencache-card-editor", LumenCacheCardEditor);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "lumencache-card",
    name: "LumenCache brightness × colour",
    description: "A pad with colour temperature across and brightness up, plus a fade time.",
    preview: true,
  });
}
