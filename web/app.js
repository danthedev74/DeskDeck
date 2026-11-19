"use strict";
(() => {
  /* =========================================================================
     helpers
     ========================================================================= */
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const pad = (n) => String(n).padStart(2, "0");
  const nowS = () => Date.now() / 1000;
  const LS = {
    get(k, d) { try { const v = localStorage.getItem("dd_" + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("dd_" + k, JSON.stringify(v)); } catch (e) {} },
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const remPx = () => parseFloat(getComputedStyle(document.documentElement).fontSize) || 10;
  const buzz = (ms = 7) => { try { navigator.vibrate && navigator.vibrate(ms); } catch (e) {} };

  let H24 = LS.get("h24", true);

  /* =========================================================================
     icons (drawn for this project, SF-style line weight)
     ========================================================================= */
  const F = 'fill="currentColor" stroke="none"';
  const SPK = `<path ${F} d="M3.8 9.4h3.1l4.4-3.9c.5-.4 1.2-.1 1.2.6v11.8c0 .7-.7 1-1.2.6l-4.4-3.9H3.8c-.5 0-.9-.4-.9-.9v-3.4c0-.5.4-.9.9-.9z"/>`;
  const ICONS = {
    play: `<path ${F} d="M7.2 4.9v14.2c0 .9 1 1.5 1.8 1l11.2-7.1c.7-.5.7-1.5 0-2L9 3.9c-.8-.5-1.8.1-1.8 1z"/>`,
    pause: `<rect ${F} x="5.6" y="4" width="4.4" height="16" rx="1.3"/><rect ${F} x="14" y="4" width="4.4" height="16" rx="1.3"/>`,
    fwd: `<path ${F} d="M2.6 6.9v10.2c0 .8.9 1.3 1.6.8l6.9-5.1c.5-.4.5-1.2 0-1.6L4.2 6.1c-.7-.5-1.6 0-1.6.8zM12.2 6.9v10.2c0 .8.9 1.3 1.6.8l6.9-5.1c.5-.4.5-1.2 0-1.6l-6.9-5.1c-.7-.5-1.6 0-1.6.8z"/>`,
    back: `<path ${F} d="M21.4 6.9v10.2c0 .8-.9 1.3-1.6.8l-6.9-5.1c-.5-.4-.5-1.2 0-1.6l6.9-5.1c.7-.5 1.6 0 1.6.8zM11.8 6.9v10.2c0 .8-.9 1.3-1.6.8l-6.9-5.1c-.5-.4-.5-1.2 0-1.6l6.9-5.1c.7-.5 1.6 0 1.6.8z"/>`,
    mic: `<rect x="9" y="2.8" width="6" height="11.4" rx="3"/><path d="M5.6 11.2a6.4 6.4 0 0 0 12.8 0M12 17.6v3.4"/>`,
    micoff: `<path d="M15 9.6V5.8a3 3 0 0 0-5.6-1.5M9 9v2.2a3 3 0 0 0 4.9 2.3M5.6 11.2a6.4 6.4 0 0 0 10.4 5M18.4 11.2c0 .9-.2 1.8-.5 2.6M12 17.6v3.4M3.6 3.6l16.8 16.8"/>`,
    hand: `<path d="M8 13V5.5a1.5 1.5 0 0 1 3 0V12M11 11V4a1.5 1.5 0 0 1 3 0v7M14 11V5.5a1.5 1.5 0 0 1 3 0V14a7 7 0 0 1-12.6 4.2L2.6 15.5a1.5 1.5 0 0 1 2.4-1.9L8 16"/>`,
    timer: `<circle cx="12" cy="13.4" r="7.6"/><path d="M12 9.2v4.4l2.6 1.6M9.6 2.8h4.8"/>`,
    "mic.slash": `<path d="M15 10.4V5.8a3 3 0 0 0-5.7-1.4M9 9.2v2a3 3 0 0 0 4.6 2.6M5.6 11.2a6.4 6.4 0 0 0 10.7 4.7M18.4 11.2c0 .9-.2 1.8-.5 2.6M12 17.6v3.4M4 4l16 16"/>`,
    speaker: SPK + `<path d="M15.6 9.2a4 4 0 0 1 0 5.6M18.4 6.6a7.6 7.6 0 0 1 0 10.8"/>`,
    "speaker.1": SPK + `<path d="M15.6 9.2a4 4 0 0 1 0 5.6"/>`,
    "speaker.0": SPK,
    "speaker.slash": SPK + `<path d="M15.8 9.6l4.8 4.8M20.6 9.6l-4.8 4.8"/>`,
    camera: `<path d="M3.5 8.6c0-.9.7-1.6 1.6-1.6h2.3l1.4-2h6.4l1.4 2h2.3c.9 0 1.6.7 1.6 1.6v9.2c0 .9-.7 1.6-1.6 1.6H5.1c-.9 0-1.6-.7-1.6-1.6z"/><circle cx="12" cy="13.1" r="3.3"/>`,
    snip: `<path d="M4 8.5V5.6C4 4.7 4.7 4 5.6 4h2.9M15.5 4h2.9c.9 0 1.6.7 1.6 1.6v2.9M20 15.5v2.9c0 .9-.7 1.6-1.6 1.6h-2.9M8.5 20H5.6c-.9 0-1.6-.7-1.6-1.6v-2.9M9.6 12h4.8M12 9.6v4.8"/>`,
    desktop: `<rect x="2.8" y="3.8" width="18.4" height="12.6" rx="2"/><path d="M8.8 20.2h6.4M12 16.4v3.8"/>`,
    lock: `<rect x="4.8" y="10.4" width="14.4" height="10.4" rx="2.4"/><path d="M8 10.4V7.6a4 4 0 0 1 8 0v2.8"/>`,
    bubble: `<path d="M5.6 4.6h12.8c1.4 0 2.6 1.2 2.6 2.6v7.2c0 1.4-1.2 2.6-2.6 2.6H11l-4.4 3.4c-.4.3-.9 0-.9-.4v-3H5.6C4.2 17 3 15.8 3 14.4V7.2c0-1.4 1.2-2.6 2.6-2.6z"/>`,
    gamepad: `<path d="M7.6 7.4h8.8c2.2 0 4 1.5 4.4 3.6l.9 4.7a2.6 2.6 0 0 1-4.5 2.2l-1.9-2H8.7l-1.9 2a2.6 2.6 0 0 1-4.5-2.2l.9-4.7c.4-2.1 2.2-3.6 4.4-3.6z"/><path d="M8 10.4v3M6.5 11.9h3"/><circle ${F} cx="15.6" cy="11" r=".9"/><circle ${F} cx="17.4" cy="12.8" r=".9"/>`,
    globe: `<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.4 2.6 3.7 5.6 3.7 9s-1.3 6.4-3.7 9c-2.4-2.6-3.7-5.6-3.7-9S9.6 5.6 12 3z"/>`,
    folder: `<path d="M3.4 7.4c0-1.1.9-2 2-2h3.7l2 2h7.5c1.1 0 2 .9 2 2v8.2c0 1.1-.9 2-2 2H5.4c-1.1 0-2-.9-2-2z"/>`,
    pulse: `<path d="M2.8 12.4h3.8l2.4-6 4 12 2.6-6h5.6"/>`,
    gear: `<path d="M4 7.2h9.4M18.2 7.2H20M4 16.8h2.2M11 16.8h9"/><circle cx="15.8" cy="7.2" r="2.4"/><circle cx="8.6" cy="16.8" r="2.4"/>`,
    clipboard: `<rect x="5" y="4.4" width="14" height="16.6" rx="2.2"/><path d="M9 4.6c0-.8.6-1.4 1.4-1.4h3.2c.8 0 1.4.6 1.4 1.4v.2c0 .8-.6 1.4-1.4 1.4h-3.2C9.6 6.2 9 5.6 9 4.8zM8.6 11h6.8M8.6 14.8h4.6"/>`,
    windows: `<rect x="3.2" y="5" width="11" height="9" rx="1.6"/><path d="M17.6 8.6h1.6c.9 0 1.6.7 1.6 1.6v6.8c0 .9-.7 1.6-1.6 1.6H8.8c-.9 0-1.6-.7-1.6-1.6v-.6"/>`,
    smile: `<circle cx="12" cy="12" r="9"/><path d="M8.4 14.2a4.6 4.6 0 0 0 7.2 0"/><circle ${F} cx="9.2" cy="9.9" r="1"/><circle ${F} cx="14.8" cy="9.9" r="1"/>`,
    leaf: `<path d="M5 19.2C5 11.4 9.8 5.4 20 4.6c-.2 9.6-5.6 15-13.6 14.8M5 19.2l7.2-7.4"/>`,
    dial: `<path d="M3.6 16.4a8.4 8.4 0 1 1 16.8 0"/><path d="M12 16.4l4-4.6"/><circle ${F} cx="12" cy="16.4" r="1.5"/>`,
    flame: `<path d="M12 21.2c-4 0-6.6-2.6-6.6-6.2 0-3.4 2.4-5.4 3.8-7.6.4 1.6 1.3 2.8 2.4 3.4.4-3 1.6-5.8 3.8-7.6-.3 3.2 1.2 5.2 2.4 7 1 1.5 1.8 3 1.8 5 0 3.5-2.8 6-7.6 6z"/>`,
    bolt: `<path ${F} d="M13.4 2.4L4.8 13.2c-.3.4 0 .9.4.9H11l-1.2 7.2c-.1.5.6.8.9.4l8.6-10.8c.3-.4 0-.9-.4-.9H13l1.3-7.2c.1-.5-.6-.8-.9-.4z"/>`,
    location: `<path ${F} d="M20.6 3.4L3.6 10.5c-.6.3-.5 1.1.1 1.3l7 2 2 7c.2.6 1 .7 1.3.1l7.1-17c.2-.4-.2-.8-.5-.5z"/>`,
    laptop: `<path d="M5 6.4c0-.9.7-1.6 1.6-1.6h10.8c.9 0 1.6.7 1.6 1.6v8.4H5zM2.6 18.4h18.8"/>`,
    chip: `<rect x="6.2" y="6.2" width="11.6" height="11.6" rx="2"/><rect x="9.6" y="9.6" width="4.8" height="4.8" rx=".8"/><path d="M9.4 3.2v3M14.6 3.2v3M9.4 17.8v3M14.6 17.8v3M3.2 9.4h3M3.2 14.6h3M17.8 9.4h3M17.8 14.6h3"/>`,
    gpu: `<rect x="2.6" y="6.4" width="18.8" height="10.6" rx="2"/><circle cx="9" cy="11.7" r="2.9"/><path d="M15 10h3M15 13.4h3M5.6 17v2.6M9 17v2.6"/>`,
    note: `<path d="M9 18V5.6l11-2.4v12"/><circle ${F} cx="6.4" cy="18" r="2.6"/><circle ${F} cx="17.4" cy="15.2" r="2.6"/>`,
    check: `<circle cx="12" cy="12" r="9.2"/><path d="M7.9 12.3l2.8 2.8 5.5-5.9"/>`,
    xmark: `<circle cx="12" cy="12" r="9.2"/><path d="M8.8 8.8l6.4 6.4M15.2 8.8l-6.4 6.4"/>`,
    down: `<path d="M12 4.4v11.4M7 11l5 5 5-5M5 20.2h14"/>`,
    up: `<path d="M12 19.6V8.2M7 13l5-5 5 5M5 3.8h14"/>`,
    photo: `<rect x="3" y="4.6" width="18" height="14.8" rx="2.4"/><circle cx="8.6" cy="9.6" r="1.7"/><path d="M21 15.4l-4.6-4.6-8.8 8.6"/>`,
    car: `<path d="M5 15.4v-3.3l1.8-4.5c.3-.8 1.1-1.4 2-1.4h6.4c.9 0 1.7.6 2 1.4l1.8 4.5v3.3M3.4 15.4h17.2v2.4c0 .6-.4 1-1 1h-1.7c-.6 0-1-.4-1-1V17H7.1v.8c0 .6-.4 1-1 1H4.4c-.6 0-1-.4-1-1zM5.3 12.1h13.4"/><circle ${F} cx="7.7" cy="14.4" r="1"/><circle ${F} cx="16.3" cy="14.4" r="1"/>`,
    record: `<circle cx="12" cy="12" r="8.8"/><circle ${F} cx="12" cy="12" r="4.6"/>`,
    power: `<path d="M12 3.4v8.2M7.1 6.3a7.7 7.7 0 1 0 9.8 0"/>`,
    grid: `<rect x="4" y="4" width="6.6" height="6.6" rx="1.7"/><rect x="13.4" y="4" width="6.6" height="6.6" rx="1.7"/><rect x="4" y="13.4" width="6.6" height="6.6" rx="1.7"/><rect x="13.4" y="13.4" width="6.6" height="6.6" rx="1.7"/>`,
    gauge: `<path d="M3.6 16.6a8.4 8.4 0 1 1 16.8 0"/><path d="M12 16.6l-3.6-5.2"/><circle ${F} cx="12" cy="16.6" r="1.6"/>`,
    memory: `<rect x="2.8" y="6.6" width="18.4" height="10.4" rx="1.8"/><path d="M7 9.8v4.2M10.4 9.8v4.2M13.8 9.8v4.2M17.2 9.8v4.2M6 17v2.6M10 17v2.6M14 17v2.6M18 17v2.6"/>`,
    rotate: `<rect x="2.6" y="7" width="18.8" height="10" rx="2.4"/><path d="M18.2 12h.01"/>`,
    umbrella: `<path d="M12 3.4a8.8 8.8 0 0 1 8.8 8.6H3.2A8.8 8.8 0 0 1 12 3.4zM12 12v6.2a2.2 2.2 0 0 1-4.4 0"/>`,
    flag: `<path d="M5 21V3.8M5 4.4h13l-2.6 4.2 2.6 4.2H5"/>`,
    queue: `<path d="M9 6h11M9 12h11M9 18h7"/><circle ${F} cx="4.5" cy="6" r="1.2"/><circle ${F} cx="4.5" cy="12" r="1.2"/><circle ${F} cx="4.5" cy="18" r="1.2"/>`,
    shuffle: `<path d="M3.5 7h3.2c2 0 3.2 1 4.3 2.7l2 3.6c1.1 1.7 2.3 2.7 4.3 2.7h3.2M17.6 13l2.9 3-2.9 3M3.5 17h3.2c1.4 0 2.4-.5 3.2-1.3M13.3 8.3c.8-.8 1.8-1.3 3.2-1.3h4M17.6 4l2.9 3-2.9 3"/>`,
    star: `<path ${F} d="M12 3.2l2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 16.6l-5.2 2.8 1-5.9-4.3-4.1 5.9-.8z"/>`,
  };
  const svg = (name) => ICONS[name]
    ? `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`
    : "";
  const paintIcons = (root = document) => $$("[data-ic]", root).forEach((el) => { el.innerHTML = svg(el.dataset.ic); });

  /* weather symbols (multicolour, 32x32) */
  const CLOUD = "M9.4 25.4h13.4a5.4 5.4 0 0 0 .7-10.75 7.3 7.3 0 0 0-14-1.65A6.2 6.2 0 0 0 9.4 25.4z";
  const sunG = (cx, cy, r, ray = true) => {
    let s = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="#FFD60A"/>`;
    if (ray) for (let i = 0; i < 8; i++) {
      const a = (i * Math.PI) / 4, r1 = r + 2.4, r2 = r + 4.6;
      s += `<path d="M${(cx + r1 * Math.cos(a)).toFixed(2)} ${(cy + r1 * Math.sin(a)).toFixed(2)}L${(cx + r2 * Math.cos(a)).toFixed(2)} ${(cy + r2 * Math.sin(a)).toFixed(2)}" stroke="#FFD60A" stroke-width="2.2" stroke-linecap="round"/>`;
    }
    return s;
  };
  const moonG = (tx = 0, ty = 0, sc = 1) => `<path transform="translate(${tx} ${ty}) scale(${sc})" d="M22.6 19.6A10 10 0 0 1 12.4 6.2a10.2 10.2 0 1 0 10.2 13.4z" fill="#fff"/>`;
  const cloudG = (fill = "#fff", tr = "") => `<path d="${CLOUD}" fill="${fill}" ${tr ? `transform="${tr}"` : ""}/>`;
  const drops = (col = "#64D2FF") => `<path d="M11.2 27.2l-1.3 2.6M16.2 27.2l-1.3 2.6M21.2 27.2l-1.3 2.6" stroke="${col}" stroke-width="2.2" stroke-linecap="round"/>`;
  function wxKind(c) {
    if (c === 0 || c === 1) return "clear";
    if (c === 2) return "partly";
    if (c === 45 || c === 48) return "fog";
    if (c >= 51 && c <= 57) return "drizzle";
    if ((c >= 61 && c <= 67) || (c >= 80 && c <= 82)) return "rain";
    if ((c >= 71 && c <= 77) || c === 85 || c === 86) return "snow";
    if (c >= 95) return "storm";
    return "cloudy";
  }
  function wxSvg(code, day) {
    const k = wxKind(code);
    let b = "";
    if (k === "clear") b = day ? sunG(16, 16, 6.4) : moonG(1, 1, 1);
    else if (k === "partly") b = (day ? sunG(11.5, 11, 4.6) : moonG(-3, -3, .78)) + cloudG("#fff", "translate(3 2) scale(.86)");
    else if (k === "cloudy") b = cloudG("#d8dde3", "translate(4 -3) scale(.7)") + cloudG("#fff", "translate(0 1)");
    else if (k === "fog") b = cloudG("#fff", "translate(0 -4)") + `<path d="M6 25h20M9 29h14" stroke="#c7ccd2" stroke-width="2.2" stroke-linecap="round"/>`;
    else if (k === "drizzle") b = cloudG("#fff", "translate(0 -4)") + `<circle cx="11" cy="27.6" r="1.3" fill="#64D2FF"/><circle cx="16" cy="28.8" r="1.3" fill="#64D2FF"/><circle cx="21" cy="27.6" r="1.3" fill="#64D2FF"/>`;
    else if (k === "rain") b = cloudG("#fff", "translate(0 -4)") + drops();
    else if (k === "snow") b = cloudG("#fff", "translate(0 -4)") + `<circle cx="11" cy="28" r="1.4" fill="#fff"/><circle cx="16" cy="29" r="1.4" fill="#fff"/><circle cx="21" cy="28" r="1.4" fill="#fff"/>`;
    else b = cloudG("#fff", "translate(0 -4)") + `<path d="M17.2 21.6l-4 5.6h3.4l-1.4 4.4 4.8-6.2h-3.4l1.8-3.8z" fill="#FFD60A"/>` + `<path d="M9.8 27.4l-1.2 2.4M23.4 27.4l-1.2 2.4" stroke="#64D2FF" stroke-width="2.2" stroke-linecap="round"/>`;
    return `<svg class="ic" viewBox="0 0 32 32" aria-hidden="true">${b}</svg>`;
  }
  const WX_TEXT = { 0: "Clear", 1: "Mostly Clear", 2: "Partly Cloudy", 3: "Cloudy", 45: "Foggy", 48: "Foggy", 51: "Light Drizzle", 53: "Drizzle", 55: "Heavy Drizzle", 56: "Freezing Drizzle", 57: "Freezing Drizzle", 61: "Light Rain", 63: "Rain", 65: "Heavy Rain", 66: "Freezing Rain", 67: "Freezing Rain", 71: "Light Snow", 73: "Snow", 75: "Heavy Snow", 77: "Snow", 80: "Showers", 81: "Showers", 82: "Heavy Showers", 85: "Snow Showers", 86: "Snow Showers", 95: "Thunderstorms", 96: "Thunderstorms", 99: "Thunderstorms" };
  const wxText = (c, day) => (c <= 1 ? (day ? (c === 0 ? "Sunny" : "Mostly Sunny") : WX_TEXT[c]) : WX_TEXT[c] || "Cloudy");
  function skyOf(code, day) {
    const k = wxKind(code);
    if (k === "storm") return "storm";
    if (k === "rain" || k === "drizzle") return day ? "rain-day" : "rain-night";
    if (k === "clear" || k === "partly") return day ? "clear-day" : "clear-night";
    return day ? "cloudy-day" : "cloudy-night";
  }

  const TEAM = { mclaren: "#FF8000", ferrari: "#E8002D", red_bull: "#3671C6", mercedes: "#27F4D2", aston_martin: "#229971", alpine: "#0093CC", williams: "#64C4FF", rb: "#6692FF", racing_bulls: "#6692FF", sauber: "#52E252", kick_sauber: "#52E252", audi: "#B5B8BD", haas: "#B6BABD", cadillac: "#A9ABAE" };
  const teamCol = (id) => TEAM[id] || "#8e8e93";

  /* =========================================================================
     state
     ========================================================================= */
  const S = { hello: null, sys: null, laptop: null, media: null, vol: null, air: { mic: [], cam: [] }, ping: null, wx: null, f1: null, photos: { n: 0, v: "" } };
  const M = { active: false, playing: false, pos: 0, at: performance.now(), dur: 0, title: "", artist: "", art: null };
  const AUDIO = { t: new Array(24).fill(0), s: new Array(24).fill(0), at: 0, bass: 0 };
  const TOKEN = (() => {
    const k = new URL(location.href).searchParams.get("k");
    if (k) { LS.set("k", k); return k; }
    return LS.get("k", "");
  })();

  /* =========================================================================
     websocket
     ========================================================================= */
  let ws = null, backoff = 400, offTimer = null, everConnected = false;
  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws?k=${encodeURIComponent(TOKEN)}`);
    ws.onopen = () => { backoff = 400; everConnected = true; setOnline(true); };
    ws.onmessage = (e) => { let m; try { m = JSON.parse(e.data); } catch (err) { return; } const h = Hd[m.t]; if (h) { try { h(m); } catch (err) { console.error(m.t, err); } } };
    ws.onclose = () => { setOnline(false); setTimeout(connect, backoff); backoff = Math.min(backoff * 1.7, 5000); };
    ws.onerror = () => { try { ws.close(); } catch (e) {} };
  }
  const send = (o) => { if (ws && ws.readyState === 1) ws.send(JSON.stringify(o)); };
  function setOnline(on) {
    clearTimeout(offTimer);
    const o = $("#offline");
    if (on) { o.classList.remove("on"); return; }
    offTimer = setTimeout(() => {
      $("#off-t").textContent = TOKEN ? "Connecting to PC" : "Link missing";
      $("#off-s").textContent = TOKEN
        ? (everConnected ? "Lost connection. Retrying..." : "Make sure agent.py is running on your PC.")
        : "Open the full link printed by agent.py (the one ending in ?k=...).";
      o.classList.add("on");
    }, everConnected ? 1500 : 600);
  }

  /* =========================================================================
     pager
     ========================================================================= */
  const CTX = { game: null, call: null, rules: [] };
  let FC = null;
  const mmss = (sec) => { sec = Math.max(0, Math.round(sec)); return `${pad(Math.floor(sec / 60))}:${pad(sec % 60)}`; };
  const fcLeft = () => (!FC || FC.mode === "idle" ? (FC ? FC.len.work * 60 : 1500) : FC.paused ? FC.left : FC.end - Date.now() / 1000);
  const GAME = { d: null, ft: [] };
  const pager = $("#pager");
  const SECS = {};
  $$(".page").forEach((el) => { SECS[el.id.slice(2)] = el; });
  const ORDER = Object.keys(SECS);
  const PAGE_T = { home: "Home", music: "Music", f1: "F1", cc: "Control", health: "Health", focus: "Focus",
    drive: "Drive", gaming: "Gaming", meet: "Meeting", room: "Room" };
  const AUTO_OK = new Set(["drive", "gaming", "meet", "room"]);   // pages that can appear only when needed
  const PV_DEF = { home: "on", music: "on", f1: "on", cc: "on", health: "on", focus: "on", drive: "on", gaming: "auto", meet: "auto", room: "auto" };
  let PV = Object.assign({}, PV_DEF, LS.get("pagevis", {}));      // per device: on | auto | off
  const AUTO = new Set();                                           // auto pages currently triggered
  let vis = [], page = 0, pid = "home", goTarget = null;
  const pageHooks = [];
  let scrollT = null;
  let touching = false;
  const settle = () => {
    clearTimeout(scrollT);
    scrollT = setTimeout(() => {
      if (touching) return settle();
      const w = pager.clientWidth, i = Math.round(pager.scrollLeft / Math.max(1, w));
      if (Math.abs(pager.scrollLeft - i * w) > 0.5) pager.scrollLeft = i * w;
      document.body.classList.remove("scrolling");
      goTarget = null;
    }, 260);
  };
  const markScrolling = () => { document.body.classList.add("scrolling"); settle(); };
  pager.addEventListener("touchstart", () => { touching = true; markScrolling(); }, { passive: true });
  pager.addEventListener("touchend", () => { touching = false; settle(); }, { passive: true });
  pager.addEventListener("touchcancel", () => { touching = false; settle(); }, { passive: true });
  function setPage(i, force) {
    i = clamp(i, 0, vis.length - 1);
    if (!force && i === page && vis[i] === pid) return;
    page = i; pid = vis[i];
    ORDER.forEach((id) => SECS[id].classList.toggle("cur", id === pid));
    document.body.dataset.page = pid;
    $$("#dots i").forEach((d, k) => d.classList.toggle("on", k === i));
    if (pid === "music") requestAnimationFrame(() => layoutLyrics(true));
    if (pid === "f1") renderF1();
    pageHooks.forEach((fn) => fn(pid));
  }
  function layoutPages(keep) {
    const cur = keep || goTarget || pid;
    vis = ORDER.filter((id) => id === "home" || PV[id] === "on" || (PV[id] === "auto" && AUTO.has(id)));
    ORDER.forEach((id) => SECS[id].classList.toggle("off", !vis.includes(id)));
    $("#dots").innerHTML = vis.map(() => "<i></i>").join("");
    let i = vis.indexOf(cur);
    if (i < 0) i = Math.min(page, vis.length - 1);
    setPage(i, true);
    pager.scrollLeft = i * pager.clientWidth;
  }
  function onScroll() {
    markScrolling();
    const i = Math.round(pager.scrollLeft / Math.max(1, pager.clientWidth));
    if (i !== page) setPage(i);
  }
  pager.addEventListener("scroll", onScroll, { passive: true });
  const go = (t) => {
    const i = typeof t === "number" ? t : vis.indexOf(t);
    if (i < 0 || i >= vis.length) return false;
    goTarget = vis[i];
    pager.scrollTo({ left: i * pager.clientWidth, behavior: "smooth" });
    return true;
  };
  function autoPage(id, on) {
    const had = AUTO.has(id);
    if (on) AUTO.add(id); else AUTO.delete(id);
    if (had !== on && PV[id] === "auto") layoutPages(!on && pid === id ? vis[Math.max(0, page - 1)] : undefined);
  }
  layoutPages("home");
  window.addEventListener("resize", () => {
    pager.scrollLeft = page * pager.clientWidth;
    layoutLyrics(true); renderF1(); fitMarquees();
  });

  /* rules: jump to a page while something is happening, come back when it's over */
  const RULE = {};
  const ruleOn = (id) => PV[id] !== "off";
  function autoEnter(id) {
    if (!ruleOn(id) || !SECS[id]) return;
    const r = RULE[id];
    if (r) { clearTimeout(r.exitT); r.exitT = null; return; }
    RULE[id] = { prev: pid === id ? null : pid };
    autoPage(id, true);
    requestAnimationFrame(() => go(id));
  }
  function autoExit(id, delay = 0) {
    const r = RULE[id];
    if (!r) { autoPage(id, false); return; }
    if (r.exitT) return;
    r.exitT = setTimeout(() => {
      delete RULE[id];
      if (pid === id && r.prev && vis.includes(r.prev)) go(r.prev);
      setTimeout(() => autoPage(id, false), 650);
    }, delay);
  }

  /* =========================================================================
     clock (digital / analog / photo)
     ========================================================================= */
  const DF = {
    wd: new Intl.DateTimeFormat("en-GB", { weekday: "long" }),
    dm: new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long" }),
    short: new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short" }),
    wds: new Intl.DateTimeFormat("en-GB", { weekday: "short" }),
  };
  const fmtHM = (d) => (H24 ? `${pad(d.getHours())}:${pad(d.getMinutes())}` : `${d.getHours() % 12 || 12}:${pad(d.getMinutes())}${d.getHours() < 12 ? " AM" : " PM"}`);
  const clockEl = $("#clock");
  const STYLES = ["digital", "analog", "photo"];
  let clockStyle = LS.get("clock", "digital");
  clockEl.dataset.style = clockStyle;

  function tickClock() {
    const d = new Date();
    const h = d.getHours();
    $("#cl-h").textContent = H24 ? pad(h) : String(h % 12 || 12);
    $("#cl-m").textContent = pad(d.getMinutes());
    $("#cl-ap").textContent = H24 ? "" : h < 12 ? "AM" : "PM";
    $("#cl-wd").textContent = DF.wd.format(d);
    $("#cl-dm").textContent = DF.dm.format(d);
    $("#sb-time").textContent = fmtHM(d).replace(/ (AM|PM)$/, "");
    $("#ph-time").textContent = H24 ? `${pad(h)}:${pad(d.getMinutes())}` : `${h % 12 || 12}:${pad(d.getMinutes())}`;
    $("#ph-date").textContent = `${DF.wd.format(d)} ${DF.dm.format(d)}`;
    $("#amb-time").textContent = fmtHM(d);
    $("#cp-time").textContent = fmtHM(d).replace(/ (AM|PM)$/, "");
    if (ANALOG.dateEl) ANALOG.dateEl.textContent = d.getDate();
  }
  function secondLoop() {
    tickClock(); tickCountdowns(); islandUpdate(); idleCheck(); driveIdleCheck();
    if (new Date().getSeconds() === 0) { renderClockSub(); renderWx(); }
    setTimeout(secondLoop, 1000 - (Date.now() % 1000) + 5);
  }

  let pressT = null, longPressed = false;
  clockEl.addEventListener("pointerdown", () => {
    longPressed = false;
    pressT = setTimeout(() => {
      longPressed = true; H24 = !H24; LS.set("h24", H24); buzz(); tickClock(); renderF1();
      toast(H24 ? "24-hour time" : "12-hour time", "check");
    }, 650);
  });
  ["pointerup", "pointercancel", "pointerleave"].forEach((ev) => clockEl.addEventListener(ev, () => clearTimeout(pressT)));
  clockEl.addEventListener("click", () => {
    if (longPressed) return;
    clockStyle = STYLES[(STYLES.indexOf(clockStyle) + 1) % STYLES.length];
    clockEl.dataset.style = clockStyle; LS.set("clock", clockStyle); buzz();
    if (clockStyle === "photo") photoNext(true);
  });
  (() => {
    const n = LS.get("hints", 0);
    if (n < 3) { LS.set("hints", n + 1); const h = $("#cl-hint"); h.textContent = "Tap to change clock · hold for 12/24h"; setTimeout(() => h.classList.add("on"), 1200); setTimeout(() => h.classList.remove("on"), 7000); }
  })();

  const ANALOG = { h: null, m: null, s: null, dateEl: null };
  (function buildAnalog() {
    const NS = "http://www.w3.org/2000/svg";
    let h = `<defs><radialGradient id="face" cx="50%" cy="38%" r="70%"><stop offset="0" stop-color="#232326"/><stop offset="1" stop-color="#141415"/></radialGradient></defs>`;
    h += `<circle cx="100" cy="100" r="98" fill="url(#face)"/>`;
    for (let i = 0; i < 60; i++) {
      const a = (i * 6 * Math.PI) / 180, major = i % 5 === 0, r1 = major ? 83.5 : 88.5, r2 = 93;
      h += `<line x1="${(100 + r1 * Math.sin(a)).toFixed(2)}" y1="${(100 - r1 * Math.cos(a)).toFixed(2)}" x2="${(100 + r2 * Math.sin(a)).toFixed(2)}" y2="${(100 - r2 * Math.cos(a)).toFixed(2)}" stroke="${major ? "#fff" : "rgba(255,255,255,.32)"}" stroke-width="${major ? 2.4 : 1.1}" stroke-linecap="round"/>`;
    }
    for (let n = 1; n <= 12; n++) {
      if (n === 3) continue;
      const a = (n * 30 * Math.PI) / 180, r = 69;
      h += `<text x="${(100 + r * Math.sin(a)).toFixed(2)}" y="${(100 - r * Math.cos(a) + 5.4).toFixed(2)}" text-anchor="middle" font-family="Inter" font-weight="${n % 3 === 0 ? 700 : 560}" font-size="${n % 3 === 0 ? 16 : 13.5}" fill="${n % 3 === 0 ? "#fff" : "rgba(255,255,255,.78)"}">${n}</text>`;
    }
    h += `<rect x="146" y="90.5" width="24" height="19" rx="4.5" fill="#f2f2f2"/><text id="an-date" x="158" y="105" text-anchor="middle" font-family="Inter" font-weight="750" font-size="13" fill="#111">1</text>`;
    h += `<g id="an-h"><line x1="100" y1="100" x2="100" y2="90" stroke="#fff" stroke-width="3" stroke-linecap="round"/><line x1="100" y1="90" x2="100" y2="54" stroke="#fff" stroke-width="7.2" stroke-linecap="round"/></g>`;
    h += `<g id="an-m"><line x1="100" y1="100" x2="100" y2="90" stroke="#fff" stroke-width="3" stroke-linecap="round"/><line x1="100" y1="90" x2="100" y2="21" stroke="#fff" stroke-width="7.2" stroke-linecap="round"/></g>`;
    h += `<circle cx="100" cy="100" r="5.2" fill="#fff"/>`;
    h += `<g id="an-s"><line x1="100" y1="118" x2="100" y2="13" stroke="#FF9F0A" stroke-width="1.7" stroke-linecap="round"/><circle cx="100" cy="100" r="3.6" fill="#FF9F0A"/><circle cx="100" cy="100" r="1.4" fill="#141415"/></g>`;
    const el = $("#analog");
    el.innerHTML = h;
    ANALOG.h = $("#an-h", el); ANALOG.m = $("#an-m", el); ANALOG.s = $("#an-s", el); ANALOG.dateEl = $("#an-date", el);
    void NS;
  })();
  function drawAnalog() {
    const d = new Date();
    const s = d.getSeconds() + d.getMilliseconds() / 1000, m = d.getMinutes() + s / 60, h = (d.getHours() % 12) + m / 60;
    ANALOG.h.setAttribute("transform", `rotate(${(h * 30).toFixed(3)} 100 100)`);
    ANALOG.m.setAttribute("transform", `rotate(${(m * 6).toFixed(3)} 100 100)`);
    ANALOG.s.setAttribute("transform", `rotate(${(s * 6).toFixed(3)} 100 100)`);
  }

  /* photo frame */
  const PH = { order: [], i: -1, timer: null, flip: false };
  function photoNext(now) {
    const n = S.photos.n;
    $(".cl-photo").classList.toggle("has", n > 0);
    if (!n || clockStyle !== "photo") return;
    if (!PH.order.length || PH.order.length !== n) {
      PH.order = Array.from({ length: n }, (_, i) => i).sort(() => Math.random() - 0.5); PH.i = -1;
    }
    PH.i = (PH.i + 1) % n;
    const stage = $("#ph-stage");
    const img = new Image();
    img.onload = () => {
      img.style.setProperty("--kx", `${(Math.random() * 4 - 2).toFixed(2)}%`);
      img.style.setProperty("--ky", `${(Math.random() * 4 - 2).toFixed(2)}%`);
      stage.appendChild(img);
      requestAnimationFrame(() => requestAnimationFrame(() => img.classList.add("on")));
      const old = $$("img", stage).filter((x) => x !== img);
      old.forEach((o) => o.classList.remove("on"));
      setTimeout(() => old.forEach((o) => o.remove()), 2000);
    };
    img.src = `/photo/${PH.order[PH.i]}?k=${encodeURIComponent(TOKEN)}&v=${S.photos.v}`;
    clearTimeout(PH.timer);
    PH.timer = setTimeout(() => photoNext(false), now ? 20000 : 20000);
  }

  /* subtitle under the digital clock */
  function renderClockSub() {
    const el = $("#cl-sub");
    const bits = [];
    const r = rainState();
    if (S.wx) {
      if (r) bits.push(`<span class="rain">${svg("umbrella")}${r.now ? "Raining now" : `Rain in ${r.inMin} min`}</span>`);
      else bits.push(`<span>${wxSvg(S.wx.code, S.wx.day)}${S.wx.temp}° ${esc(wxText(S.wx.code, S.wx.day))}</span>`);
    }
    const n = S.f1 && S.f1.next;
    if (n) {
      const left = n.race - nowS();
      if (left > -7200 && left < 14 * 86400) bits.push(`<span>${svg("flag")}${esc(shortGP(n.name))} ${left <= 0 ? "live" : "in " + fmtLeft(left, true)}</span>`);
    }
    el.innerHTML = bits.join("");
  }

  /* =========================================================================
     widgets
     ========================================================================= */
  const fmtRate = (b) => (b < 1024 ? `${b}B` : b < 1048576 ? `${(b / 1024).toFixed(b < 10240 ? 1 : 0)}K` : `${(b / 1048576).toFixed(1)}M`);
  const ring = (el, v) => { el.style.strokeDasharray = `${clamp(v, 0, 100).toFixed(2)} 100`; };

  const Hd = {};
  Hd.hello = (m) => {
    S.hello = m;
    $("#sb-demo").hidden = !m.demo;
    buildCC(m);
    if (m.forza && m.forza.port) $("#cp-port").textContent = m.forza.port;
  };
  Hd.sys = (m) => {
    S.sys = m;
    ring($("#rg-cpu"), m.cpu); ring($("#rg-gpu"), m.gpu ?? 0); ring($("#rg-ram"), m.ram);
    $("#sys-cpu").textContent = Math.round(m.cpu);
    $("#sys-gpu").textContent = m.gpu == null ? "--" : Math.round(m.gpu);
    $("#sys-ram").textContent = Math.round(m.ram);
    $("#sys-ramu").textContent = "%";
    $("#sys-net").textContent = `↓${fmtRate(m.down)} ↑${fmtRate(m.up)}`;
    const r = $("#lr-ram");
    setR(r, m.ram, m.ram >= 85 ? "var(--red)" : m.ram >= 70 ? "var(--orange)" : "var(--green)", `${Math.round(m.ram)}%`);
  };
  const setR = (el, val, col, txt) => { ring($(".v", el), val); el.style.setProperty("--rc", col); $(".lr-v", el).textContent = txt; };
  Hd.laptop = (d) => {
    S.laptop = d;
    const cpu = $("#lr-cpu"), gpu = $("#lr-gpu");
    const tcol = (t) => (t >= 85 ? "var(--red)" : t >= 70 ? "var(--orange)" : "var(--green)");
    if (d.cpuT != null) setR(cpu, d.cpuT, tcol(d.cpuT), `${d.cpuT}°`); else setR(cpu, 0, "var(--gray)", "--");
    if (d.gpuT != null) setR(gpu, d.gpuT, tcol(d.gpuT), `${d.gpuT}°`); else setR(gpu, 0, "var(--gray)", d.lhm ? "Off" : "--");
    let foot;
    if (!d.lhm) foot = "Temps need LibreHardwareMonitor";
    else {
      const parts = [];
      if (d.fans && d.fans.length) parts.push(`Fan ${Math.round(d.fans.reduce((a, b) => a + b, 0) / d.fans.length).toLocaleString("en")} rpm`);
      else parts.push("Fans quiet");
      if (S.sys) parts.push(`${S.sys.ramUsed.toFixed(1)} / ${Math.round(S.sys.ramTot)} GB`);
      foot = parts.join(" · ");
    }
    $("#lap-foot").textContent = foot;
    const pill = $("#lap-mode");
    pill.hidden = !d.mode;
    if (d.mode) {
      const base = ["silent", "balanced", "turbo"].includes(d.mode);
      pill.dataset.m = base ? d.mode : "custom";
      pill.textContent = base ? d.mode[0].toUpperCase() + d.mode.slice(1) : (d.modeName || "Custom");
    }
    const perf = $("#cc-perf");
    perf.classList.toggle("na", !d.mode);
    $(".mod-t", perf).textContent = d.mode ? "Performance" : "Performance · G-Helper not found";
    $$("button", perf).forEach((b) => b.classList.toggle("on", b.dataset.mode === d.mode));
    const sb = $("#sb-bat");
    sb.hidden = d.bat == null;
    if (d.bat != null) {
      $(".pct", sb).textContent = d.bat;
      $(".lvl", sb).style.width = `${clamp(d.bat, 4, 100)}%`;
      sb.classList.toggle("chg", !!d.plugged);
      sb.classList.toggle("low", d.bat <= 20 && !d.plugged);
      $(".bolt", sb).innerHTML = svg("bolt");
    }
  };
  Hd.wx = (w) => { S.wx = w; renderWx(); renderClockSub(); islandUpdate(); };
  function renderWx() {
    const w = S.wx; if (!w) return;
    $("#wx-loc").textContent = w.name;
    $("#wx-temp").textContent = `${w.temp}°`;
    $("#w-wx").dataset.sky = skyOf(w.code, w.day);
    $("#wx-ic").innerHTML = wxSvg(w.code, w.day);
    const r = rainState(), c = $("#wx-cond");
    if (r) { c.textContent = r.now ? (r.endMin ? `Rain easing in ${r.endMin} min` : "Raining now") : `Rain in ${r.inMin} min`; c.classList.add("rain"); }
    else { c.textContent = wxText(w.code, w.day); c.classList.remove("rain"); }
    $("#wx-hl").textContent = `H:${w.hi}° L:${w.lo}°`;
  }
  function rainState() {
    const w = S.wx; if (!w || !w.rain) return null;
    const r = w.rain, t = nowS();
    if (r.now) return { now: true, endMin: r.end && r.end > t ? Math.round((r.end - t) / 60) : null, prob: r.prob };
    if (r.start && r.start > t - 900 && r.start - t < 3 * 3600) {
      const m = Math.max(0, Math.round((r.start - t) / 60));
      return m === 0 ? { now: true, endMin: null, prob: r.prob, start: r.start } : { now: false, inMin: m, prob: r.prob, start: r.start };
    }
    return null;
  }
  Hd.ping = (m) => {
    const el = $("#sb-ping");
    const ms = m.ms;
    el.dataset.q = ms == null ? 0 : ms < 30 ? 4 : ms < 60 ? 3 : ms < 120 ? 2 : 1;
    $(".ms", el).textContent = ms == null ? "offline" : `${Math.round(ms)} ms`;
  };
  Hd.photos = (m) => {
    const changed = m.v !== S.photos.v;
    S.photos = m;
    $(".cl-photo").classList.toggle("has", m.n > 0);
    $("#ph-dir").textContent = `Drop pictures into ${m.dir || "Pictures\\DeskDeck"} on your PC`;
    if (changed && clockStyle === "photo") { PH.order = []; photoNext(true); }
  };

  /* =========================================================================
     F1
     ========================================================================= */
  const SESS_DUR = { "Practice 1": 3600, "Practice 2": 3600, "Practice 3": 3600, "Sprint Qualifying": 2700, "Sprint Shootout": 2700, Sprint: 3600, Qualifying: 3600, Race: 7200 };
  const shortGP = (n) => String(n || "").replace(/ Grand Prix$/i, " GP");
  function fmtLeft(sec, compact) {
    sec = Math.max(0, Math.floor(sec));
    const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    if (d > 0) return compact ? `${d}d ${h}h` : `${d}d ${h}h ${pad(m)}m`;
    if (h > 0) return `${h}h ${pad(m)}m`;
    return compact ? `${m}m` : `${m}m ${pad(s)}s`;
  }
  function f1State() {
    const n = S.f1 && S.f1.next; if (!n) return null;
    const t = nowS(); let live = null, next = null;
    for (const s of n.sessions) {
      const end = s.ts + (SESS_DUR[s.k] || 3600);
      if (t >= s.ts && t < end) live = s;
      else if (s.ts > t && !next) next = s;
    }
    return { live, next, soonMin: next ? (next.ts - t) / 60 : Infinity, n };
  }
  const fmtSessT = (ts) => { const d = new Date(ts * 1000); return H24 ? `${pad(d.getHours())}:${pad(d.getMinutes())}` : `${d.getHours() % 12 || 12}:${pad(d.getMinutes())} ${d.getHours() < 12 ? "AM" : "PM"}`; };
  Hd.f1 = (m) => { S.f1 = m; renderF1(); renderClockSub(); };
  function renderF1() {
    const f = S.f1; if (!f) return;
    const n = f.next, t = nowS();
    if (n) {
      $("#f1-kick").textContent = `Round ${n.round}${f.total ? ` of ${f.total}` : ""}${n.country ? ` · ${n.country}` : ""}`;
      $("#f1-name").textContent = n.name;
      $("#f1-circ").textContent = n.circuit || "";
      const rd = new Date(n.race * 1000);
      $("#f1-rt").textContent = `Race · ${DF.short.format(rd)}, ${fmtSessT(n.race)}`;
      const ul = $("#f1-sess");
      const st = f1State();
      ul.innerHTML = n.sessions.map((s) => {
        const end = s.ts + (SESS_DUR[s.k] || 3600);
        let cls = "", status = "";
        if (t >= end) { cls = "past"; status = "Done"; }
        else if (t >= s.ts) { cls = "live"; status = "LIVE"; }
        else if (st && st.next === s) { cls = "next"; status = `in ${fmtLeft(s.ts - t, true)}`; }
        if (s.k === "Race") cls += " race";
        return `<li class="${cls}"><div><div class="ss-n">${esc(s.k)}</div><div class="ss-d">${DF.short.format(new Date(s.ts * 1000))}</div></div><div><div class="ss-t">${fmtSessT(s.ts)}</div><div class="ss-s">${status}</div></div></li>`;
      }).join("");
      $("#f1w-name").textContent = shortGP(n.name);
      $("#f1w-round").textContent = `R${n.round}`;
    } else {
      $("#f1-kick").textContent = "Season complete";
      $("#f1-name").textContent = "See you next season";
      $("#f1-circ").textContent = "";
      $("#f1-sess").innerHTML = "";
      $("#f1w-name").textContent = "Off-season";
      $("#f1w-round").textContent = "";
    }
    $("#f1-season").textContent = f.season || "";
    // standings, fit to card height
    const ol = $("#f1-table");
    const card = ol.parentElement;
    const rp = remPx();
    const lastH = f.last ? 2.6 * rp : 0;
    const avail = card.clientHeight - 3.2 * rp - $(".card-t", card).offsetHeight - 0.5 * rp - lastH;
    const rows = Math.max(3, Math.floor(avail / (2.25 * rp)));
    const favId = f.fav || (S.hello && S.hello.fav);
    const list = f.standings || [];
    const fi = list.findIndex((x) => x.id === favId);
    let shown = list.slice(0, rows);
    let gap = false;
    if (fi >= rows) { shown = list.slice(0, rows - 2); gap = true; }
    const row = (x) => `<li class="${x.id === favId ? "fav" : ""}" style="--team:${teamCol(x.teamId)}"><span class="st-p">${x.pos ?? "-"}</span><span class="st-bar"></span><span class="st-c">${esc(x.code)}</span><span class="st-n">${esc(x.last)}</span><span class="st-pts">${Number.isInteger(x.pts) ? x.pts : x.pts.toFixed(1)}</span></li>`;
    ol.innerHTML = shown.map(row).join("") + (gap ? `<li class="gap"></li>${row(list[fi])}` : "");
    if (f.last) {
      const top = (f.last.top || []).map((x) => `<b>${x.pos}</b> ${esc(x.code)}`).join("  ");
      const fav = f.last.fav && fi >= 0 ? ` · ${esc(list[fi].code)} P${esc(f.last.fav.pos)}` : "";
      $("#f1-last").innerHTML = `${esc(shortGP(f.last.name))}: ${top}${fav}`;
    } else $("#f1-last").textContent = "";
    // favourite driver (widget + hero)
    const fav = list[fi];
    $("#f1w-fav").innerHTML = fav ? `<i class="tdot" style="--team:${teamCol(fav.teamId)}"></i>${esc(fav.last)} · P${fav.pos ?? "-"} · ${fav.pts} pts` : "";
    $("#f1-chip-fav").innerHTML = fav ? `<i class="tdot" style="--team:${teamCol(fav.teamId)}"></i><b>${esc(fav.first)} ${esc(fav.last)}</b> · P${fav.pos ?? "-"} · ${fav.pts} pts` : "";
    tickCountdowns();
  }
  let lastSessRender = 0;
  function tickCountdowns() {
    const f = S.f1; if (!f || !f.next) return;
    const n = f.next, t = nowS(), st = f1State();
    const raceLive = t >= n.race && t < n.race + 7200;
    const left = n.race - t;
    const d = Math.floor(Math.max(0, left) / 86400), h = Math.floor((Math.max(0, left) % 86400) / 3600), m = Math.floor((Math.max(0, left) % 3600) / 60), s = Math.floor(Math.max(0, left) % 60);
    $("#cd-d").textContent = pad(d); $("#cd-h").textContent = pad(h); $("#cd-m").textContent = pad(m); $("#cd-s").textContent = pad(s);
    $("#f1-cd").style.opacity = raceLive ? 0.35 : 1;
    const live = st && st.live;
    $("#f1-live").hidden = !live;
    if (live) $("#f1-live-t").textContent = `${live.k.toUpperCase()} LIVE`;
    const cdw = $("#f1w-cd").parentElement;
    cdw.classList.toggle("live", !!raceLive);
    $("#f1w-cdl").textContent = raceLive ? "Race" : "Race in";
    $("#f1w-cd").textContent = raceLive ? "LIVE" : fmtLeft(left, false).replace(/ \d+s$/, "");
    const chip = $("#f1-chip-next");
    if (live) chip.innerHTML = `<span class="k lv">LIVE</span><b>${esc(live.k)}</b> · ends ${fmtSessT(live.ts + (SESS_DUR[live.k] || 3600))}`;
    else if (st && st.next) chip.innerHTML = `<span class="k">NEXT</span><b>${esc(st.next.k)}</b> · in ${fmtLeft(st.next.ts - t, true)}`;
    else chip.innerHTML = "";
    if (live && live.k !== "Race") $("#f1w-next").textContent = `${live.k} · live now`;
    else if (st && st.next && st.next.k !== "Race") $("#f1w-next").textContent = `${st.next.k} · ${DF.wds.format(new Date(st.next.ts * 1000))} ${fmtSessT(st.next.ts)}`;
    else $("#f1w-next").textContent = `${DF.wds.format(new Date(n.race * 1000))} ${fmtSessT(n.race)}`;
    if (pid === "f1" && Date.now() - lastSessRender > 15000) { lastSessRender = Date.now(); renderF1(); }
  }
  $("#w-f1").addEventListener("click", () => go("f1"));
  $("#w-lap").addEventListener("click", () => go("cc"));

  /* =========================================================================
     now playing
     ========================================================================= */
  const curPos = () => clamp(M.playing ? M.pos + (performance.now() - M.at) / 1000 : M.pos, 0, M.dur || 1e9);
  const fmtT = (s) => { s = Math.max(0, Math.floor(s)); return `${Math.floor(s / 60)}:${pad(s % 60)}`; };
  let lastTitleKey = null;
  Hd.media = (m) => {
    S.media = m;
    if (!m.active) {
      M.active = false; M.playing = false;
      setTitle("Not Playing"); $("#np-artist").textContent = ""; $("#ccm-title").textContent = "Not Playing"; $("#ccm-artist").textContent = "";
      $("#np-app").textContent = ""; setArt(null); setPP(false); renderProgress(0);
      renderCard(); syncMV();
      return;
    }
    const key = `${m.title}\u0001${m.artist}`;
    const changed = key !== lastTitleKey;
    const firstTrack = lastTitleKey === null;
    M.active = true; M.title = m.title; M.artist = m.artist; M.dur = m.dur || 0;
    if (typeof m.pos === "number") { M.pos = m.pos; M.at = performance.now(); }
    if (M.playing !== m.playing) { M.pos = typeof m.pos === "number" ? m.pos : curPos(); M.at = performance.now(); }
    M.playing = !!m.playing;
    if (changed) {
      lastTitleKey = key;
      setTitle(m.title || "Unknown");
      $("#np-artist").textContent = [m.artist, m.album].filter(Boolean).join(" — ");
      $("#ccm-title").textContent = m.title; $("#ccm-artist").textContent = m.artist;
      $("#amb-title").textContent = m.title; $("#amb-artist").textContent = m.artist;
      if (M.playing && !firstTrack) islandQueue({ id: "music" });
    }
    $("#np-app").textContent = m.app || "";
    setArt(m.art);
    setPP(M.playing);
    renderCard(); syncMV();
  };
  function setTitle(t) { const el = $("#np-title"); el.firstElementChild.textContent = t; fitMarquees(); }
  function fitMarquees() {
    $$(".marquee").forEach((el) => {
      const sp = el.firstElementChild; el.classList.remove("run");
      const over = sp.scrollWidth - el.clientWidth;
      if (over > 4) { el.classList.add("run"); el.style.setProperty("--mqx", `${-over - 6}px`); el.style.setProperty("--mqd", `${Math.max(8, over / 18)}s`); }
    });
  }
  function setPP(playing) {
    $$('[data-media="toggle"]').forEach((b) => { b.innerHTML = `<i>${svg(playing ? "pause" : "play")}</i>`; });
    $("#np-artbox").classList.toggle("paused", !playing && M.active);
  }
  function renderProgress(p) {
    const f = M.dur > 0 ? p / M.dur : 0;
    $("#np-fill").style.width = `${(f * 100).toFixed(3)}%`;
    $("#np-cur").textContent = fmtT(p);
    $("#np-rem").textContent = M.dur > 0 ? `-${fmtT(M.dur - p)}` : "";
  }
  $("#np-prog").addEventListener("click", (e) => {
    if (!M.dur) return;
    const r = $(".np-track").getBoundingClientRect();
    const v = clamp((e.clientX - r.left) / r.width, 0, 1) * M.dur;
    M.pos = v; M.at = performance.now(); send({ a: "media", cmd: "seek", v: +v.toFixed(2) }); buzz();
  });
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-media]");
    if (!b) return;
    const cmd = b.dataset.media; buzz();
    if (cmd === "toggle") { M.pos = curPos(); M.at = performance.now(); M.playing = !M.playing; setPP(M.playing); }
    send({ a: "media", cmd });
  });

  /* album art + palette */
  let artUrl;
  function setArt(url) {
    if (url === artUrl) return;
    artUrl = url;
    const imgs = [$("#np-art"), $("#ccm-art"), $("#amb-art")];
    if (!url) { imgs.forEach((i) => { i.classList.remove("ok"); i.removeAttribute("src"); }); BG.art = null; islandArt = null; return; }
    const im = new Image();
    im.onload = () => {
      if (artUrl !== url) return;
      imgs.forEach((i) => { i.src = url; i.classList.add("ok"); });
      renderCard();
      BG.art = im; islandArt = url;
      const p = palette(im);
      BG.target = p.cols;
      document.documentElement.style.setProperty("--accent", `rgb(${p.accent.join(",")})`);
    };
    im.src = url;
  }
  function rgb2hsl(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b); let h = 0, s = 0; const l = (mx + mn) / 2;
    if (mx !== mn) { const d = mx - mn; s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn); h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4; h /= 6; }
    return [h, s, l];
  }
  function hsl2rgb(h, s, l) {
    if (s === 0) return [l * 255, l * 255, l * 255].map(Math.round);
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
    const f = (t) => { t = (t + 1) % 1; return t < 1 / 6 ? p + (q - p) * 6 * t : t < 1 / 2 ? q : t < 2 / 3 ? p + (q - p) * (2 / 3 - t) * 6 : p; };
    return [f(h + 1 / 3), f(h), f(h - 1 / 3)].map((v) => Math.round(v * 255));
  }
  function palette(img) {
    const c = document.createElement("canvas"); c.width = c.height = 28;
    const x = c.getContext("2d", { willReadFrequently: true });
    x.drawImage(img, 0, 0, 28, 28);
    let data; try { data = x.getImageData(0, 0, 28, 28).data; } catch (e) { return { cols: BG.cols, accent: [255, 255, 255] }; }
    const B = new Map();
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i], g = data[i + 1], b = data[i + 2];
      const [h, s, l] = rgb2hsl(r, g, b);
      if (l < 0.07 || l > 0.95) continue;
      const key = s < 0.16 ? 99 : Math.round(h * 14) % 14;
      const w = 0.4 + s * 1.6;
      const e = B.get(key) || { w: 0, r: 0, g: 0, b: 0, s: 0 };
      e.w += w; e.r += r * w; e.g += g * w; e.b += b * w; e.s += s * w; B.set(key, e);
    }
    const arr = [...B.values()].sort((a, b) => b.w - a.w).map((e) => ({ rgb: [e.r / e.w, e.g / e.w, e.b / e.w], s: e.s / e.w, w: e.w }));
    if (!arr.length) return { cols: [[70, 70, 80], [50, 50, 60], [90, 90, 100], [40, 40, 50]], accent: [255, 255, 255] };
    const tune = (rgb, lo, hi, sat = 1.15) => { const [h, s, l] = rgb2hsl(...rgb); return hsl2rgb(h, Math.min(1, s * sat), clamp(l, lo, hi)); };
    const cols = [];
    for (let i = 0; i < 4; i++) cols.push(tune(arr[i % arr.length].rgb, 0.2 + i * 0.04, 0.56));
    const vivid = [...arr].sort((a, b) => b.s * Math.sqrt(b.w) - a.s * Math.sqrt(a.w))[0];
    const [ah, as] = rgb2hsl(...vivid.rgb);
    return { cols, accent: as < 0.15 ? [255, 255, 255] : hsl2rgb(ah, Math.min(1, as * 1.1 + 0.1), 0.66) };
  }

  /* animated background (tiny canvas, upscaled = free blur) */
  const BG = {
    cols: [[58, 52, 88], [40, 70, 110], [96, 48, 92], [32, 44, 70]], target: null, art: null, t: Math.random() * 100,
    step() {
      if (!this.target) return;
      for (let i = 0; i < 4; i++) for (let k = 0; k < 3; k++) this.cols[i][k] += (this.target[i][k] - this.cols[i][k]) * 0.035;
    },
    draw(cv) {
      const x = cv.getContext("2d"), w = cv.width, h = cv.height, c = this.cols, t = this.t, bass = AUDIO.bass;
      x.globalAlpha = 1; x.globalCompositeOperation = "source-over";
      x.fillStyle = `rgb(${c[3].map((v) => (v * 0.45) | 0).join(",")})`; x.fillRect(0, 0, w, h);
      if (this.art) {
        x.globalAlpha = 0.55; const s = w * 1.3;
        x.drawImage(this.art, (w - s) / 2 + Math.sin(t * 0.05) * 8, (h - s) / 2 + Math.cos(t * 0.04) * 8, s, s);
        x.globalAlpha = 1;
      }
      for (let i = 0; i < 4; i++) {
        const col = c[i].map((v) => v | 0).join(",");
        const px = w * (0.5 + 0.5 * Math.sin(t * (0.09 + i * 0.031) + i * 1.9));
        const py = h * (0.5 + 0.55 * Math.cos(t * (0.075 + i * 0.027) + i * 1.3));
        const r = w * (0.4 + 0.09 * Math.sin(t * 0.17 + i)) * (1 + bass * 0.22);
        const g = x.createRadialGradient(px, py, 0, px, py, r);
        g.addColorStop(0, `rgba(${col},.9)`); g.addColorStop(1, `rgba(${col},0)`);
        x.fillStyle = g; x.fillRect(0, 0, w, h);
      }
      x.fillStyle = "rgba(0,0,0,.16)"; x.fillRect(0, 0, w, h);
    },
  };

  /* lyrics */
  const LY = { key: null, lines: [], els: [], synced: false, plain: false, idx: -2, offset: 0.3 };
  Hd.lyrics = (m) => {
    const box = $("#ly"), r = $(".np-r");
    $$(".ly-msg", r).forEach((x) => x.remove());
    box.innerHTML = ""; box.className = "ly"; LY.els = []; LY.lines = []; LY.idx = -2; LY.synced = false; LY.plain = false; LY.key = m.key;
    r.classList.remove("nolyr");
    const msg = (b, s) => { const d = document.createElement("div"); d.className = "ly-msg"; d.innerHTML = `<b>${esc(b)}</b>${s ? `<span>${esc(s)}</span>` : ""}`; $("#lyrics").appendChild(d); r.classList.add("nolyr"); };
    if (m.loading) { $("#amb-line").textContent = ""; return; }
    if (m.instrumental) { msg("Instrumental", ""); return; }
    if (m.synced && m.lines && m.lines.length) {
      const raw = m.lines.map(([t, txt]) => ({ t, txt: txt || "" }));
      if (raw[0].t > 4 && raw[0].txt) raw.unshift({ t: 0, txt: "" });
      const L = [];
      raw.forEach((l, i) => {
        if (!l.txt) {
          const nxt = raw[i + 1]; const gap = (nxt ? nxt.t : l.t + 6) - l.t;
          if (gap < 3.5 || (L.length && !L[L.length - 1].txt)) return;
          L.push({ t: l.t, txt: "", gap });
        } else L.push(l);
      });
      LY.lines = L; LY.synced = true;
      L.forEach((l) => {
        const el = document.createElement("div");
        el.className = "ly-l";
        if (!l.txt) { el.innerHTML = `<div class="ly-dots"><i></i><i></i><i></i></div>`; el.style.setProperty("--gap", `${Math.max(1, l.gap - 0.5).toFixed(2)}s`); }
        else el.textContent = l.txt;
        el.addEventListener("click", () => { M.pos = l.t; M.at = performance.now(); send({ a: "media", cmd: "seek", v: l.t }); buzz(); });
        box.appendChild(el); LY.els.push(el);
      });
      requestAnimationFrame(() => layoutLyrics(true));
      return;
    }
    if (m.plain && m.plain.length) {
      LY.plain = true; box.classList.add("ly-plain");
      m.plain.forEach((t) => { const el = document.createElement("div"); el.className = "ly-l"; el.textContent = t || " "; box.appendChild(el); LY.els.push(el); });
      return;
    }
    msg("Lyrics not available", M.title ? `${M.title}` : "");
  };
  function lyricsTick(pos) {
    if (LY.plain) {
      const box = $("#ly"), h = $("#lyrics").clientHeight;
      const f = M.dur ? clamp((pos - 8) / (M.dur - 20), 0, 1) : 0;
      box.style.transform = `translate3d(0,${-(Math.max(0, box.scrollHeight - h * 0.6) * f).toFixed(1)}px,0)`;
      return;
    }
    if (!LY.synced) return;
    const p = pos + LY.offset;
    let lo = 0, hi = LY.lines.length - 1, i = -1;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (LY.lines[mid].t <= p) { i = mid; lo = mid + 1; } else hi = mid - 1; }
    if (i !== LY.idx) {
      LY.idx = i; layoutLyrics(false);
      const line = i >= 0 ? LY.lines[i].txt : "";
      ambLine(line);
    }
  }
  function layoutLyrics(instant) {
    if (!LY.synced || !LY.els.length) return;
    const box = $("#lyrics");
    const anchor = box.clientHeight * 0.3;
    const a = Math.max(0, LY.idx);
    const off = LY.els[a].offsetTop - anchor;
    LY.els.forEach((el, k) => {
      const d = k - LY.idx, ad = Math.abs(d);
      el.classList.toggle("on", k === LY.idx);
      el.classList.remove("b1", "b2", "b3");
      if (k !== LY.idx && LY.idx >= 0 && ad <= 7) el.classList.add(ad <= 1 ? "b1" : ad === 2 ? "b2" : "b3");
      const delay = instant ? 0 : clamp(d + 1, 0, 8) * 48;
      el.style.transitionDelay = `${delay}ms, 0ms, 0ms`;
      el.style.transitionDuration = instant ? "0ms, .45s, .45s" : "";
      el.style.transform = `translate3d(0,${(-off).toFixed(1)}px,0)`;
    });
  }

  /* spectrum */
  Hd.spec = (m) => { const b = m.b; for (let i = 0; i < 24; i++) AUDIO.t[i] = b[i] || 0; AUDIO.at = performance.now(); };
  function drawSpec() {
    const c = $("#np-spec"); const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = Math.round(c.clientWidth * dpr), h = Math.round(c.clientHeight * dpr);
    if (!w || !h) return;
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    const x = c.getContext("2d"); x.clearRect(0, 0, w, h);
    const n = 24, gap = w * 0.014, bw = (w - gap * (n - 1)) / n;
    x.fillStyle = "rgba(255,255,255,.82)";
    for (let i = 0; i < n; i++) {
      const v = AUDIO.s[i] / 100, bh = Math.max(bw, v * h * 0.96);
      const px = i * (bw + gap), py = h - bh;
      if (x.roundRect) { x.beginPath(); x.roundRect(px, py, bw, bh, bw / 2); x.fill(); } else x.fillRect(px, py, bw, bh);
    }
  }

  /* =========================================================================
     ambient (idle full-screen art)
     ========================================================================= */
  let lastTouch = performance.now(), ambOn = false, pausedSince = 0;
  const amb = $("#ambient");
  document.addEventListener("pointerdown", () => { lastTouch = performance.now(); if (ambOn) setAmbient(false); }, { capture: true });
  function setAmbient(on) {
    ambOn = on; amb.classList.toggle("on", on);
    if (on) ambLine(LY.idx >= 0 && LY.lines[LY.idx] ? LY.lines[LY.idx].txt : "");
  }
  function ambLine(txt) {
    const el = $("#amb-line");
    if (!ambOn) { el.textContent = txt; return; }
    el.classList.add("out");
    setTimeout(() => { el.textContent = txt; el.classList.remove("out"); }, 280);
  }
  function idleCheck() {
    const idle = (performance.now() - lastTouch) / 1000;
    if (!M.playing) { if (!pausedSince) pausedSince = performance.now(); } else pausedSince = 0;
    if (!ambOn && M.active && M.playing && artUrl && idle > 75 && $("#sheet").hidden && !FZ.live) setAmbient(true);
    if (ambOn && FZ.live) setAmbient(false);
    if (ambOn && (!M.active || (pausedSince && performance.now() - pausedSince > 20000))) setAmbient(false);
  }
  $("#np-artbox").addEventListener("click", () => { if (M.active && artUrl) setTimeout(() => setAmbient(true), 60); });

  /* =========================================================================
     dynamic island
     ========================================================================= */
  const ISL = { mode: "hidden", until: 0, queue: [], seenAir: false, rainKey: null, f1Key: null, cur: null };
  let islandArt = null;
  const island = $("#island"), bub = $("#isl-bub");
  function islandQueue(ev) {
    if (ISL.queue.some((q) => q.id === ev.id)) return;
    ISL.queue.push(ev); islandUpdate();
  }
  function activities() {
    const a = [];
    if (FZ.live && FZ.d && FZ.d.on && pid !== "drive") a.push({ id: "drive" });
    if (CTX.game && pid !== "gaming") a.push({ id: "game" });
    if (FC && FC.mode !== "idle" && pid !== "focus") a.push({ id: "focus" });
    if (M.active && M.playing) a.push({ id: "music" });
    const mic = S.air.mic || [], cam = S.air.cam || [];
    if (mic.length || cam.length) a.push({ id: "air" });
    const f = f1State();
    if (f && (f.live || f.soonMin <= 15)) a.push({ id: "f1", f });
    const r = rainState();
    if (r && (r.now || r.inMin <= 30)) a.push({ id: "rain", r });
    return a;
  }
  const wave = (n = 5) => `<span class="wave">${"<i></i>".repeat(n)}</span>`;
  function compactHTML(act) {
    if (act.id === "drive") return [`<span class="isl-gear">${gearTxt(FZ.d.gear)}</span>`, `<span>${Math.round(FZ.d.kmh)} km/h</span>`];
    if (act.id === "focus") {
      const brk = FC.mode !== "work";
      return [`<i class="ii ${brk ? "c-gr" : "c-pu"}">${svg(brk ? "leaf" : "timer")}</i>`, `<span class="${brk ? "c-gr" : "c-pu"}">${FC.paused ? "Paused" : mmss(fcLeft())}</span>`];
    }
    if (act.id === "game") {
      const f = GAME.d && GAME.d.fps;
      return [`<i class="ii c-gr">${svg("gamepad")}</i>`, f ? `<span><b class="c-gr">${Math.round(f)}</b> FPS</span>` : `<span>${esc((CTX.game.name || "").slice(0, 16))}</span>`];
    }
    if (act.id === "music") return [islandArt ? `<img src="${islandArt}" alt="">` : `<i class="ii">${svg("note")}</i>`, wave(5)];
    if (act.id === "air") {
      const mic = S.air.mic || [], cam = S.air.cam || [];
      const who = (mic[0] || cam[0] || "").slice(0, 14);
      return [`<i class="ii ${cam.length && !mic.length ? "c-gr" : "c-or"}">${svg(cam.length && !mic.length ? "camera" : "mic")}</i>`, `<span class="${cam.length && !mic.length ? "c-gr" : "c-or"}">${esc(who) || "On Air"}</span>`];
    }
    if (act.id === "f1") {
      const f = act.f; const txt = f.live ? "LIVE" : `${Math.max(1, Math.round(f.soonMin))}m`;
      return [`<span class="f1-mark">F1</span>`, `<span class="${f.live ? "c-rd" : ""}">${txt}</span>`];
    }
    const r = act.r;
    return [`<i class="ii c-bl">${svg("umbrella")}</i>`, `<span class="c-bl">${r.now ? "Now" : `${r.inMin}m`}</span>`];
  }
  function bubbleHTML(act) {
    if (act.id === "drive") return `<span class="isl-gear" style="font-size:1.15rem">${gearTxt(FZ.d.gear)}</span>`;
    if (act.id === "game") return `<span class="c-gr">${svg("gamepad")}</span>`;
    if (act.id === "focus") return `<span class="${FC.mode !== "work" ? "c-gr" : "c-pu"}">${svg(FC.mode !== "work" ? "leaf" : "timer")}</span>`;
    if (act.id === "music") return islandArt ? `<img src="${islandArt}" style="width:1.9rem;height:1.9rem;border-radius:50%;object-fit:cover" alt="">` : `<span class="c-gr">${svg("note")}</span>`;
    if (act.id === "air") return `<span class="c-or">${svg("mic")}</span>`;
    if (act.id === "f1") return `<span class="f1-mark" style="font-size:.8rem;padding:.05rem .3rem">F1</span>`;
    return `<span class="c-bl">${svg("umbrella")}</span>`;
  }
  function expandedHTML(ev) {
    if (ev.id === "music") {
      return `${islandArt ? `<img class="ix-art" src="${islandArt}" alt="">` : `<div class="ix-ic">${svg("note")}</div>`}
        <div class="ix-t"><small>Now Playing</small><b>${esc(M.title)}</b><span>${esc(M.artist)}</span></div><div class="ix-r">${wave(6)}</div>`;
    }
    if (ev.id === "air") {
      const mic = S.air.mic || [], cam = S.air.cam || [];
      const what = mic.length && cam.length ? "Mic & camera in use" : mic.length ? "Microphone in use" : "Camera in use";
      return `<div class="ix-ic" style="--ixc:${mic.length ? "var(--orange)" : "var(--green)"}">${svg(mic.length ? "mic" : "camera")}</div>
        <div class="ix-t"><small>On Air</small><b>${esc(what)}</b><span>${esc([...new Set([...mic, ...cam])].join(", "))}</span></div>`;
    }
    if (ev.id === "note") {
      const n = ev.n;
      return `<div class="ix-ic ix-note" style="--ixc:${noteCol(n.app)}"><b>${esc((n.app || "?").slice(0, 1).toUpperCase())}</b></div>
        <div class="ix-t"><small>${esc(n.app || "Notification")}</small><b>${esc(n.title || "")}</b><span>${esc(n.body || "")}</span></div>`;
    }
    if (ev.id === "rain") {
      const r = rainState(); if (!r) return "";
      return `<div class="ix-ic" style="--ixc:var(--blue)">${svg("umbrella")}</div>
        <div class="ix-t"><small>Rain Alert · ${esc(S.wx.name)}</small><b>${r.now ? "Rain starting now" : `Rain in about ${r.inMin} min`}</b><span>${r.prob != null ? `${r.prob}% chance in the next hours` : "Grab an umbrella"}</span></div>`;
    }
    if (ev.id === "f1") {
      const f = f1State(); if (!f) return "";
      const s = f.live || f.next;
      return `<div class="ix-ic" style="--ixc:#e10600"><span class="f1-mark" style="background:none;font-size:1.8rem">F1</span></div>
        <div class="ix-t"><small>${esc(f.n.name)}</small><b>${f.live ? `${esc(s.k)} is live` : `${esc(s.k)} in ${Math.max(1, Math.round(f.soonMin))} min`}</b><span>${esc(f.n.circuit || "")}</span></div>`;
    }
    return "";
  }
  function islandUpdate() {
    const acts = activities();
    const t = performance.now();
    // fire one-shot expansions on state changes
    const air = acts.some((a) => a.id === "air");
    if (air && !ISL.seenAir) islandQueue({ id: "air" });
    ISL.seenAir = air;
    const r = rainState();
    if (r && (r.now || r.inMin <= 30)) { const k = String(S.wx.rain.start || "now"); if (ISL.rainKey !== k) { ISL.rainKey = k; islandQueue({ id: "rain" }); } }
    const f = f1State();
    if (f && (f.live || f.soonMin <= 10)) { const s = f.live || f.next; const k = `${s.k}${s.ts}${f.live ? "L" : "S"}`; if (ISL.f1Key !== k) { ISL.f1Key = k; islandQueue({ id: "f1" }); } }

    if (ISL.mode === "expanded" && t < ISL.until) return;
    if (ISL.queue.length) {
      const ev = ISL.queue.shift();
      const html = expandedHTML(ev);
      if (html) {
        $("#isl-x").innerHTML = html; ISL.cur = ev; ISL.mode = "expanded"; ISL.until = t + (ev.id === "note" ? 6500 : 4200);
        island.dataset.mode = "expanded"; bub.classList.remove("on");
        return;
      }
    }
    const prim = acts[0], sec = acts[1];
    if (!prim) { ISL.mode = "hidden"; island.dataset.mode = "hidden"; bub.classList.remove("on"); ISL.cur = null; return; }
    const sig = `${prim.id}|${prim.id === "drive" ? gearTxt(FZ.d.gear) + Math.round(FZ.d.kmh) : ""}|${prim.id === "game" && GAME.d ? Math.round(GAME.d.fps || 0) : ""}|${prim.id === "focus" ? Math.round(fcLeft()) + "" + FC.paused : ""}|${islandArt}|${JSON.stringify(S.air)}|${prim.f ? Math.round(prim.f.soonMin) + "" + !!prim.f.live : ""}|${prim.r ? prim.r.inMin + "" + prim.r.now : ""}`;
    if (ISL.sig !== sig || ISL.mode !== "compact") {
      const [l, rr] = compactHTML(prim);
      $("#isl-l").innerHTML = l; $("#isl-r").innerHTML = rr; ISL.sig = sig;
    }
    ISL.cur = prim; ISL.mode = "compact"; island.dataset.mode = "compact";
    if (sec) { bub.innerHTML = bubbleHTML(sec); bub.dataset.id = sec.id; bub.classList.add("on"); } else bub.classList.remove("on");
  }
  const routeFor = (id) => ({ music: "music", f1: "f1", rain: "home", air: CTX.call ? "meet" : "cc", drive: "drive", game: "gaming", focus: "focus", note: "home" }[id] ?? "home");
  island.addEventListener("click", () => {
    if (!ISL.cur) return;
    if (ISL.cur.id === "note") { buzz(); if (ISL.cur.n.app && ISL.cur.n.app !== "Webhook") send({ a: "note_open", app: ISL.cur.n.app }); }
    else go(routeFor(ISL.cur.id));
    ISL.until = 0; islandUpdate();
  });
  bub.addEventListener("click", () => go(routeFor(bub.dataset.id)));
  function waveTick(t) {
    const bars = $$(".wave i", island);
    if (!bars.length) return;
    const idx = [1, 4, 8, 12, 16, 20];
    const silent = AUDIO.s.every((v) => v < 2);
    bars.forEach((b, k) => {
      let v = AUDIO.s[idx[k % idx.length]] / 100;
      if (silent && M.playing) v = 0.32 + 0.26 * Math.sin(t / 170 + k * 1.3);
      b.style.height = `${(16 + clamp(v, 0, 1) * 84).toFixed(0)}%`;
    });
  }

  /* =========================================================================
     volume / privacy
     ========================================================================= */
  const VOL = { level: 0, muted: false, mic: null, dragUntil: 0 };
  Hd.vol = (m) => {
    S.vol = m;
    if (performance.now() > VOL.dragUntil && m.level != null) VOL.level = m.level;
    VOL.muted = !!m.muted; VOL.mic = m.mic;
    renderVol();
  };
  function renderVol() {
    const v = $("#cc-vol");
    $("#cc-vol-fill").style.height = `${(VOL.level * 100).toFixed(1)}%`;
    $("#cc-vol-pct").textContent = VOL.muted ? "Muted" : `${Math.round(VOL.level * 100)}`;
    v.classList.toggle("lit", VOL.level > 0.13);
    v.classList.toggle("muted", VOL.muted);
    const icn = VOL.muted ? "speaker.slash" : VOL.level < 0.02 ? "speaker.0" : VOL.level < 0.5 ? "speaker.1" : "speaker";
    $("#cc-vol-ic").innerHTML = svg(icn);
    const mute = $("#cc-mute");
    mute.classList.toggle("off", VOL.muted);
    $(".rb-c", mute).innerHTML = `<i>${svg(VOL.muted ? "speaker.slash" : "speaker")}</i>`;
    $("label", mute).textContent = VOL.muted ? "Muted" : "Sound";
    const mic = $("#cc-mic");
    mic.classList.toggle("live", VOL.mic === false);
    mic.classList.toggle("off", VOL.mic === true);
    $(".rb-c", mic).innerHTML = `<i>${svg(VOL.mic ? "mic.slash" : "mic")}</i>`;
    $("label", mic).textContent = VOL.mic == null ? "No mic" : VOL.mic ? "Mic off" : "Mic on";
  }
  (() => {
    const el = $("#cc-vol"); let drag = null, lastSend = 0;
    el.addEventListener("pointerdown", (e) => { el.setPointerCapture(e.pointerId); drag = { y: e.clientY, v: VOL.level, h: el.clientHeight, moved: false }; el.classList.add("drag"); });
    el.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const dv = (drag.y - e.clientY) / drag.h;
      if (Math.abs(dv) > 0.01) drag.moved = true;
      VOL.level = clamp(drag.v + dv, 0, 1); VOL.dragUntil = performance.now() + 900;
      if (VOL.muted && VOL.level > 0) VOL.muted = false;
      renderVol();
      const t = performance.now();
      if (t - lastSend > 70) { lastSend = t; send({ a: "vol", set: +VOL.level.toFixed(3) }); }
    });
    const end = () => {
      if (!drag) return;
      if (drag.moved) { send({ a: "vol", set: +VOL.level.toFixed(3) }); VOL.dragUntil = performance.now() + 900; }
      drag = null; el.classList.remove("drag");
    };
    el.addEventListener("pointerup", end); el.addEventListener("pointercancel", end);
  })();
  Hd.air = (m) => {
    S.air = { mic: m.mic || [], cam: m.cam || [] };
    const p = $("#sb-priv");
    p.classList.toggle("mic", S.air.mic.length > 0);
    p.classList.toggle("cam", S.air.cam.length > 0);
    islandUpdate();
  };

  /* =========================================================================
     control center
     ========================================================================= */
  const TILE_COLS = ["94 92 230", "10 132 255", "255 159 10", "48 209 88", "255 55 95", "142 142 147", "191 90 242", "64 203 224"];
  function buildCC(h) {
    const apps = $("#cc-apps");
    apps.innerHTML = (h.apps || []).slice(0, 6).map((a, i) => `<button class="tile sc" data-app="${esc(a.id)}" style="--tc:${TILE_COLS[i % TILE_COLS.length]}"><i data-ic="${esc(a.icon)}"></i><span>${esc(a.label)}</span></button>`).join("");
    const mac = $("#cc-macros");
    mac.innerHTML = (h.macros || []).slice(0, 4).map((a) => `<button class="tile" data-macro="${esc(a.id)}"><i data-ic="${esc(a.icon)}"></i><span>${esc(a.label)}</span></button>`).join("");
    paintIcons(apps); paintIcons(mac);
  }
  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-app],[data-macro],[data-sys],[data-mode],[data-a]");
    if (!t) return;
    buzz();
    if (t.dataset.app) {
      send({ a: "app", id: t.dataset.app });
    } else if (t.dataset.macro) {
      send({ a: "macro", id: t.dataset.macro });
      toast($("span", t).textContent, "check");
    } else if (t.dataset.sys) {
      send({ a: "sys", v: t.dataset.sys });
      toast({ shot: "Screenshot saved", snip: "Snip", desk: "Show desktop", lock: "PC locked", gshot: "Game screenshot captured", gclip: "Clip saved (last 30s)" }[t.dataset.sys] || "Done", "check");
    } else if (t.dataset.mode) {
      if ($("#cc-perf").classList.contains("na")) { toast("G-Helper not found", "xmark", true); return; }
      $$("#cc-perf button").forEach((b) => b.classList.toggle("on", b === t));
      send({ a: "mode", v: t.dataset.mode });
    } else if (t.dataset.a === "mic") {
      if (VOL.mic != null) { VOL.mic = !VOL.mic; renderVol(); }
      send({ a: "mic" });
    } else if (t.dataset.a === "mute") {
      VOL.muted = !VOL.muted; renderVol(); send({ a: "vol", mute: true });
    }
  });

  /* clipboard */
  let wantCopy = false;
  $("#clip-pull").addEventListener("click", () => { wantCopy = true; send({ a: "clip_get" }); buzz(); });
  Hd.clip = async (m) => {
    const prev = $("#clip-prev");
    prev.textContent = m.text || "PC clipboard is empty"; prev.classList.toggle("has", !!m.text);
    if (!wantCopy) return;
    wantCopy = false;
    if (!m.text) { toast("PC clipboard is empty", "xmark", true); return; }
    try { await navigator.clipboard.writeText(m.text); toast("Copied to phone", "check"); }
    catch (e) { openSheet(m.text); toast("Long-press the text to copy", "clipboard"); }
  };
  function openSheet(text) {
    const sh = $("#sheet"); sh.hidden = false;
    const ta = $("#clip-text"); if (text != null) ta.value = text;
    requestAnimationFrame(() => sh.classList.add("on"));
  }
  function closeSheet() { const sh = $("#sheet"); sh.classList.remove("on"); setTimeout(() => { sh.hidden = true; }, 300); $("#clip-text").blur(); }
  $("#clip-open").addEventListener("click", () => { openSheet(""); setTimeout(() => $("#clip-text").focus(), 120); });
  $("#sheet-cancel").addEventListener("click", closeSheet);
  $("#sheet").addEventListener("click", (e) => { if (e.target.id === "sheet") closeSheet(); });
  $("#clip-paste").addEventListener("click", async () => {
    try { const t = await navigator.clipboard.readText(); $("#clip-text").value = t; } catch (e) { toast("Phone blocked clipboard read", "xmark", true); }
  });
  $("#clip-send").addEventListener("click", () => {
    const text = $("#clip-text").value;
    if (!text) { closeSheet(); return; }
    send({ a: "clip_set", text, paste: $("#clip-auto").checked });
    $("#clip-prev").textContent = text; $("#clip-prev").classList.add("has");
    closeSheet();
  });

  /* =========================================================================
     FH6 Universal Radio: drive card, music volume, Up Next sheet
     ========================================================================= */
  const R = { on: false, d: null, pos: 0, at: 0 };
  const Q = { open: false, tracks: [], cursor: null, loaded: false };
  const MV = { level: null, dragUntil: 0, last: 0 };
  const rPlaying = () => R.on && R.d.state === "playing";
  const rPos = () => !R.on ? 0 : clamp(rPlaying() ? R.pos + (performance.now() - R.at) / 1000 : R.pos, 0, R.d.dur || 1e9);
  function setImg(img, url) {
    url = url || "";
    if (img.dataset.u === url) return;
    img.dataset.u = url; img.classList.remove("ok");
    if (!url) { img.removeAttribute("src"); return; }
    img.onload = () => { if (img.dataset.u === url) img.classList.add("ok"); };
    img.src = url;
  }
  function ppIcons(sel, playing) { $$(sel).forEach((b) => { b.innerHTML = `<i>${svg(playing ? "pause" : "play")}</i>`; }); }
  function renderCard() {
    const card = $("#cw-radio");
    card.classList.toggle("radio", R.on);
    if (R.on) {
      const d = R.d;
      $("#cwr-srcn").textContent = "FH6 Radio";
      $("#cwr-st").textContent = d.station || d.sourceName ? `· ${d.station || d.sourceName}` : "";
      $("#cwr-dot").classList.toggle("live", d.attached && d.state === "playing");
      $("#cwr-title").textContent = d.title || (d.state === "buffering" ? "Loading…" : "Not Playing");
      $("#cwr-artist").textContent = d.artist || "";
      setImg($("#cwr-art"), d.art);
      ppIcons('#cw-radio [data-rad="toggle"]', d.state === "playing" || d.state === "buffering");
      $("#cwr-q").hidden = false;
    } else {
      const m = S.media || {};
      $("#cwr-srcn").textContent = m.active ? (m.app || "Now Playing") : "Now Playing";
      $("#cwr-st").textContent = "";
      $("#cwr-title").textContent = m.active ? (m.title || "Unknown") : "Not Playing";
      $("#cwr-artist").textContent = m.active ? (m.artist || "") : "";
      setImg($("#cwr-art"), m.active ? artUrl : null);
      ppIcons('#cw-radio [data-rad="toggle"]', M.active && M.playing);
      $("#cwr-q").hidden = true;
    }
  }
  Hd.radio = (m) => {
    const was = R.on;
    R.on = !!m.on; R.d = R.on ? m : null;
    if (R.on && typeof m.pos === "number") { R.pos = m.pos; R.at = performance.now(); }
    if (was && !R.on && Q.open) qsOpen(false);
    renderCard(); syncMV();
    if (Q.open) { renderQsNow(); renderStations(); renderRows(false); }
  };

  /* music volume: Universal Radio's own output gain, else the player app's volume (never the system master) */
  function syncMV() {
    if (performance.now() < MV.dragUntil) return;
    if (R.on) MV.level = typeof R.d.gain === "number" ? R.d.gain : null;
    else MV.level = S.media && S.media.active && typeof S.media.avol === "number" ? S.media.avol : null;
    renderMV();
  }
  function renderMV() {
    const v = MV.level, na = v == null, pct = Math.round((v ?? 0) * 100);
    const pill = $("#mvol");
    pill.classList.toggle("na", na); pill.classList.toggle("lit", !na && v > 0.16);
    $("#mvol-fill").style.height = `${pct}%`;
    $("#mvol-pct").textContent = na ? "--" : pct;
    $("#mvol-ic").innerHTML = svg(na || v < 0.02 ? "speaker.0" : v < 0.5 ? "speaker.1" : "speaker");
    $("#qs-vol").classList.toggle("na", na);
    $("#qs-vfill").style.width = `${pct}%`;
  }
  function pushMV(force) {
    const t = performance.now();
    if (MV.level == null || (!force && t - MV.last < 80)) return;
    MV.last = t;
    const v = +MV.level.toFixed(3);
    if (R.on) send({ a: "radio", cmd: "gain", v }); else send({ a: "avol", set: v });
  }
  function bindVol(el, axis, track) {
    let drag = null;
    const fromPoint = (e) => {
      const r = (track || el).getBoundingClientRect();
      return axis === "y" ? clamp((r.bottom - e.clientY) / r.height, 0, 1) : clamp((e.clientX - r.left) / r.width, 0, 1);
    };
    el.addEventListener("pointerdown", (e) => {
      if (MV.level == null) return;
      e.stopPropagation(); el.setPointerCapture(e.pointerId); el.classList.add("drag");
      drag = { p: axis === "y" ? e.clientY : e.clientX, v: MV.level, moved: false };
    });
    el.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const r = (track || el).getBoundingClientRect();
      const dv = axis === "y" ? (drag.p - e.clientY) / r.height : (e.clientX - drag.p) / r.width;
      if (Math.abs(dv) > 0.015) drag.moved = true;
      if (!drag.moved) return;
      MV.level = clamp(drag.v + dv, 0, 1); MV.dragUntil = performance.now() + 1500;
      renderMV(); pushMV(false);
    });
    const end = (e) => {
      if (!drag) return;
      if (!drag.moved && e.type === "pointerup") MV.level = fromPoint(e);
      MV.dragUntil = performance.now() + 1500;
      renderMV(); pushMV(true); buzz();
      drag = null; el.classList.remove("drag");
    };
    el.addEventListener("pointerup", end); el.addEventListener("pointercancel", end);
  }
  bindVol($("#mvol"), "y");
  bindVol($("#qs-vol"), "x", $(".qs-vtrack"));

  /* transport buttons: radio when Universal Radio is up, otherwise the Windows media session (Apple Music etc.) */
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-rad]");
    if (!b) return;
    const cmd = b.dataset.rad; buzz();
    if (R.on) {
      if (cmd === "toggle") {
        const playing = R.d.state === "playing";
        R.pos = rPos(); R.at = performance.now(); R.d.state = playing ? "paused" : "playing";
        renderCard(); if (Q.open) renderQsNow();
      }
      send({ a: "radio", cmd });
    } else {
      if (cmd === "toggle") { M.pos = curPos(); M.at = performance.now(); M.playing = !M.playing; setPP(M.playing); renderCard(); }
      send({ a: "media", cmd });
    }
  });

  /* Up Next sheet */
  function qsOpen(open) {
    const sh = $("#qsheet");
    Q.open = open;
    if (open) {
      sh.hidden = false; requestAnimationFrame(() => sh.classList.add("on"));
      Q.loaded = false; renderQsNow(); renderStations(); renderRows(true);
      send({ a: "radio", cmd: "queue" });
    } else {
      sh.classList.remove("on"); setTimeout(() => { if (!Q.open) sh.hidden = true; }, 320);
    }
  }
  const openQueue = () => { if (R.on) { buzz(); qsOpen(true); } };
  $("#cwr-q").addEventListener("click", openQueue);
  $("#cwr-artbox").addEventListener("click", openQueue);
  $(".cwr-meta").addEventListener("click", openQueue);
  $("#qs-done").addEventListener("click", () => qsOpen(false));
  $("#qsheet").addEventListener("click", (e) => { if (e.target.id === "qsheet") qsOpen(false); });
  function renderQsNow() {
    if (!R.on) return;
    const d = R.d;
    setImg($("#qs-art"), d.art);
    $(".qs-art").classList.toggle("paused", d.state !== "playing" && d.state !== "buffering");
    $("#qs-src").textContent = ["FH6 Radio", d.sourceName].filter(Boolean).join(" · ");
    $("#qs-t").textContent = d.title || "Not Playing";
    $("#qs-a").textContent = d.artist || "";
    ppIcons('#qsheet [data-rad="toggle"]', d.state === "playing" || d.state === "buffering");
    const sh = $("#qs-shuf");
    sh.hidden = typeof d.shuffle !== "boolean";
    sh.classList.toggle("on", !!d.shuffle);
  }
  let stKey = "";
  function renderStations() {
    const d = R.d || {}, list = d.stations || [];
    const key = JSON.stringify([list, d.station]);
    if (key === stKey) return;
    stKey = key;
    $("#qs-st").innerHTML = list.map((n) => `<button class="${n === d.station ? "on" : ""}" data-st="${esc(n)}">${esc(n)}</button>`).join("");
    const on = $("#qs-st .on");
    if (on) on.scrollIntoView({ block: "nearest", inline: "center" });
  }
  $("#qs-st").addEventListener("click", (e) => {
    const b = e.target.closest("[data-st]");
    if (!b || !R.on) return;
    buzz(); R.d.station = b.dataset.st; renderStations();
    Q.tracks = []; Q.loaded = false; renderRows(false);
    send({ a: "radio", cmd: "station", v: b.dataset.st });
  });
  $("#qs-shuf").addEventListener("click", () => {
    if (!R.on) return;
    buzz(); R.d.shuffle = !R.d.shuffle; renderQsNow();
    send({ a: "radio", cmd: "shuffle", v: R.d.shuffle });
  });
  Hd.radioq = (m) => { Q.tracks = m.tracks || []; Q.cursor = m.cursor; Q.loaded = true; if (Q.open) renderRows(true); };
  Hd.radioqdirty = () => { if (Q.open) send({ a: "radio", cmd: "queue" }); };
  let rowsKey = "";
  function renderRows(scroll) {
    const box = $("#qs-rows");
    const cur = R.on && typeof R.d.cursor === "number" ? R.d.cursor : Q.cursor;
    const playing = rPlaying();
    let html;
    if (!R.on || !R.d.queue) html = `<div class="qs-empty">This source doesn't have a queue.</div>`;
    else if (!Q.loaded && !Q.tracks.length) html = `<div class="qs-empty">Loading queue…</div>`;
    else if (!Q.tracks.length) html = `<div class="qs-empty">Queue is empty.</div>`;
    else {
      const ci = Q.tracks.findIndex((t) => t.i === cur);
      html = Q.tracks.map((t, k) => {
        const isCur = k === ci, past = ci >= 0 && k < ci;
        const right = isCur ? `<span class="qs-eq${playing ? "" : " paused"}"><i></i><i></i><i></i><i></i></span>` : "<span></span>";
        const th = t.th ? `<img loading="lazy" src="${esc(t.th)}" alt="" onerror="this.remove()">` : "";
        return (ci >= 0 && k === ci + 1 ? `<div class="qs-lbl">Up next</div>` : "")
          + `<button class="qs-r${isCur ? " cur" : ""}${past ? " past" : ""}" data-qi="${t.i}"><span class="th">${th}</span>`
          + `<span><b>${esc(t.t || "Unknown")}</b><small>${esc(t.a || "")}</small></span>${right}</button>`;
      }).join("");
    }
    const key = html.length + ":" + cur + ":" + playing + ":" + Q.tracks.length;
    if (key !== rowsKey) { rowsKey = key; box.innerHTML = html; }
    if (scroll) {
      const c = $(".qs-r.cur", box);
      requestAnimationFrame(() => { box.scrollTop = c ? Math.max(0, c.offsetTop - box.offsetTop - (c.previousElementSibling ? c.offsetHeight * 0.6 : 0)) : 0; });
    }
  }
  $("#qs-rows").addEventListener("click", (e) => {
    const b = e.target.closest("[data-qi]");
    if (!b || !R.on) return;
    buzz();
    const i = +b.dataset.qi;
    Q.cursor = i; R.d.cursor = i; renderRows(false);
    send({ a: "radio", cmd: "jump", v: i });
  });

  /* =========================================================================
     rules engine (agent says what's happening; we jump to the page and back)
     ========================================================================= */
  Hd.ctx = (m) => {
    const was = { game: CTX.game, call: CTX.call, rules: CTX.rules.slice() };
    CTX.game = m.game || null; CTX.call = m.call || null; CTX.rules = m.rules || [];
    if (CTX.game && !was.game) autoEnter("gaming");
    if (!CTX.game && was.game) { autoExit("gaming", 5000); GAME.d = null; GAME.ft = []; }
    CTX.rules.filter((id) => !was.rules.includes(id)).forEach((id) => autoEnter(id));
    was.rules.filter((id) => !CTX.rules.includes(id)).forEach((id) => autoExit(id, 3000));
    if (CTX.call && !was.call) autoEnter("meet");
    if (!CTX.call && was.call) autoExit("meet", 2500);
    if (typeof renderMeet === "function") renderMeet();
    islandUpdate();
  };

  /* =========================================================================
     Gaming HUD
     ========================================================================= */
  function gRing(id, v, col) {
    const el = $(id); if (!el) return;
    const p = clamp(v || 0, 0, 100);
    el.style.strokeDasharray = `${p} 100`;
    if (col) el.style.stroke = col;
  }
  const tCol = (t) => (t == null ? "#8e8e93" : t < 70 ? "#30d158" : t < 85 ? "#ff9f0a" : "#ff453a");
  function renderGame() {
    const g = GAME.d, sy = S.sys || {}, lp = S.laptop || {};
    $("#gm-name").textContent = (g && g.name) || (CTX.game && CTX.game.name) || "No game running";
    const fps = g && g.fps;
    setTxt($("#gm-fps"), fps ? String(Math.round(fps)) : "—");
    $("#gm-fps").classList.toggle("none", !fps);
    setTxt($("#gm-avg"), g && g.avg ? String(g.avg) : "--");
    setTxt($("#gm-min"), g && g.min ? String(g.min) : "--");
    setTxt($("#gm-ftv"), g && g.ft ? g.ft.toFixed(1) : "--");
    $("#gm-hint").hidden = !(g && !g.rtss);
    $("#gm-fps").style.color = fps ? (fps >= 100 ? "#fff" : fps >= 50 ? "var(--yellow)" : "var(--red)") : "";
    const pts = GAME.ft.slice(-60);
    if (pts.length > 1) {
      const max = Math.max(20, ...pts) * 1.15;
      const line = pts.map((v, i) => `${((i + 60 - pts.length) / 59 * 300).toFixed(1)},${(60 - v / max * 56).toFixed(1)}`);
      $("#gm-line").setAttribute("points", line.join(" "));
      $("#gm-area").setAttribute("d", `M${line[0].split(",")[0]},60 L${line.join(" L")} L${line[line.length - 1].split(",")[0]},60Z`);
    }
    // CPU / GPU
    gRing("#gm-cpu-r", lp.cpuT != null ? lp.cpuT : 0, tCol(lp.cpuT));
    gRing("#gm-gpu-r", lp.gpuT != null ? lp.gpuT : 0, tCol(lp.gpuT));
    setTxt($("#gm-cpu-t"), lp.cpuT != null ? `${lp.cpuT}°` : "--");
    setTxt($("#gm-gpu-t"), lp.gpuT != null ? `${lp.gpuT}°` : "--");
    setTxt($("#gm-cpu-l"), sy.cpu != null ? `${Math.round(sy.cpu)}%` : "--");
    setTxt($("#gm-gpu-l"), sy.gpu != null ? `${Math.round(sy.gpu)}%` : "--");
    setTxt($("#gm-cpu-w"), lp.cpuW != null ? `${Math.round(lp.cpuW)} W` : "--");
    setTxt($("#gm-gpu-w"), lp.gpuW != null ? `${Math.round(lp.gpuW)} W` : "--");
    // memory
    setTxt($("#gm-ram"), sy.ramUsed != null ? sy.ramUsed.toFixed(1) : "--");
    setTxt($("#gm-ramt"), sy.ramTot ? ` / ${Math.round(sy.ramTot)} GB` : "");
    $("#gm-ramb").style.width = `${sy.ram || 0}%`;
    setTxt($("#gm-vram"), sy.vram != null ? `VRAM ${sy.vram.toFixed(1)} GB` : "VRAM --");
    // fans + mode
    const fan = (lp.fans || [])[0];
    const MODE_N = { silent: "Silent", balanced: "Balanced", turbo: "Turbo" };
    const mEl = $("#gm-mode");
    setTxt(mEl, lp.mode === "custom" ? (lp.modeName || "Custom") : MODE_N[lp.mode] || "--");
    mEl.dataset.mode = lp.mode || "";
    const watts = (lp.cpuW || 0) + (lp.gpuW || 0);
    setTxt($("#gm-perfsub"), fan ? `Fans ${fan.toLocaleString("en-US")} rpm` : watts ? `Drawing ${Math.round(watts)} W` : "");
    $$("#gm-modes [data-mode]").forEach((b) => b.classList.toggle("on", b.dataset.mode === lp.mode));
  }
  Hd.game = (m) => {
    GAME.d = m;
    if (m.ft) { GAME.ft.push(m.ft); if (GAME.ft.length > 60) GAME.ft.shift(); }
    if (pid === "gaming") renderGame();
    if (ISL.cur && ISL.cur.id === "game") islandUpdate();
  };
  pageHooks.push((id) => { if (id === "gaming") renderGame(); });
  const statHooks = [() => { if (pid === "gaming") renderGame(); }];
  { const hs = Hd.sys, hl = Hd.laptop;
    Hd.sys = (m) => { hs(m); statHooks.forEach((fn) => fn()); };
    Hd.laptop = (m) => { hl(m); statHooks.forEach((fn) => fn()); }; }
  $("#gm-modes").addEventListener("click", (e) => {
    const b = e.target.closest("[data-mode]"); if (!b) return;
    buzz(); send({ a: "mode", v: b.dataset.mode });
    $$("#gm-modes [data-mode]").forEach((x) => x.classList.toggle("on", x === b));
  });

  /* =========================================================================
     Overview (tap the page dots) + per-device page list
     ========================================================================= */
  const OV = { open: false, edit: false };
  const PV_LBL = { on: "Always", auto: "Auto", off: "Hidden" };
  function ovRender() {
    const grid = $("#ov-grid");
    grid.innerHTML = "";
    const ids = OV.edit ? ORDER : vis;
    grid.classList.toggle("edit", OV.edit);
    grid.style.setProperty("--cols", ids.length > 8 ? 5 : ids.length > 6 ? 4 : 3);
    $("#ov-edit").textContent = OV.edit ? "Done" : "Edit";
    $("#ov-sub").textContent = OV.edit ? "Tap a page to choose: Always · Auto (only when it's happening) · Hidden. Saved on this device." : "";
    const W = window.innerWidth, H = window.innerHeight;
    ids.forEach((id) => {
      const it = document.createElement("button");
      it.className = `ov-it${id === pid && !OV.edit ? " cur" : ""} pv-${PV[id]}`;
      it.dataset.id = id;
      const th = document.createElement("div"); th.className = "ov-th";
      th.style.aspectRatio = `${W} / ${H}`;
      const inner = document.createElement("div"); inner.className = "ov-in";
      inner.style.width = `${W}px`; inner.style.height = `${H}px`;
      const clone = SECS[id].cloneNode(true);
      clone.classList.remove("off"); clone.classList.add("cur", "ov-clone");
      const src = $$("canvas", SECS[id]), dst = $$("canvas", clone);
      src.forEach((c, k) => { const d = dst[k]; if (!d || !c.width) return; d.width = c.width; d.height = c.height; try { d.getContext("2d").drawImage(c, 0, 0); } catch (e) { /* tainted */ } });
      inner.appendChild(clone); th.appendChild(inner); it.appendChild(th);
      const lab = document.createElement("span"); lab.className = "ov-l";
      lab.innerHTML = `${esc(PAGE_T[id] || id)}${OV.edit ? ` <em>${PV_LBL[PV[id]]}</em>` : PV[id] === "auto" ? " <small>auto</small>" : ""}`;
      it.appendChild(lab);
      grid.appendChild(it);
    });
    requestAnimationFrame(() => $$(".ov-th", grid).forEach((th) => {
      const k = th.clientWidth / W; $(".ov-in", th).style.transform = `scale(${k})`;
    }));
  }
  function ovOpen(open) {
    const ov = $("#ov");
    OV.open = open;
    if (open) { OV.edit = false; ov.hidden = false; ovRender(); requestAnimationFrame(() => ov.classList.add("on")); }
    else { ov.classList.remove("on"); setTimeout(() => { if (!OV.open) { ov.hidden = true; $("#ov-grid").innerHTML = ""; } }, 300); }
  }
  $("#dots").addEventListener("click", () => { buzz(); ovOpen(true); });
  $("#ov-edit").addEventListener("click", () => {
    buzz(); OV.edit = !OV.edit;
    if (!OV.edit) { LS.set("pagevis", PV); layoutPages(); }
    ovRender();
  });
  $("#ov").addEventListener("click", (e) => {
    const it = e.target.closest(".ov-it");
    if (!it) { if (e.target.id === "ov" || e.target.id === "ov-grid") ovOpen(false); return; }
    const id = it.dataset.id; buzz();
    if (OV.edit) {
      if (id === "home") { toast("Home is always on", "grid"); return; }
      const cyc = AUTO_OK.has(id) ? ["on", "auto", "off"] : ["on", "off"];
      PV[id] = cyc[(cyc.indexOf(PV[id]) + 1) % cyc.length];
      ovRender();
      return;
    }
    ovOpen(false);
    setTimeout(() => { pager.scrollLeft = vis.indexOf(id) * pager.clientWidth; }, 10);
  });

  /* =========================================================================
     Health: network, heavy apps, Claude usage
     ========================================================================= */
  const NET = { dn: [], up: [] };
  const mbps = (b) => (b || 0) * 8 / 1e6;
  const fmtMb = (v) => (v >= 100 ? Math.round(v) : v >= 10 ? v.toFixed(1) : v.toFixed(2));
  { const hs = Hd.sys; Hd.sys = (m) => {
    NET.dn.push(mbps(m.down)); NET.up.push(mbps(m.up));
    if (NET.dn.length > 60) { NET.dn.shift(); NET.up.shift(); }
    hs(m);
    if (pid === "health") renderNet();
  }; }
  function renderNet() {
    const sy = S.sys || {}, w = S.wifi || {};
    setTxt($("#hl-dn"), fmtMb(mbps(sy.down)));
    setTxt($("#hl-up"), fmtMb(mbps(sy.up)));
    $("#hl-netl").textContent = w.ssid ? `Network · ${w.ssid}` : "Network";
    $("#hl-netf").textContent = w.ssid ? [`Wi-Fi${w.radio && /ax/.test(w.radio) ? " 6" : ""}`, w.signal != null ? `${w.signal}% signal` : "", w.rx ? `${Math.round(w.rx)} Mb/s link` : ""].filter(Boolean).join(" · ") : "Wired or offline";
    const n = NET.dn.length; if (n < 2) return;
    const max = Math.max(1, ...NET.dn, ...NET.up) * 1.15;
    const pts = (arr) => arr.map((v, i) => `${((i + 60 - n) / 59 * 300).toFixed(1)},${(100 - v / max * 96).toFixed(1)}`);
    const d = pts(NET.dn), u = pts(NET.up);
    $("#hl-dl").setAttribute("points", d.join(" "));
    $("#hl-ul").setAttribute("points", u.join(" "));
    $("#hl-da").setAttribute("d", `M${d[0].split(",")[0]},100 L${d.join(" L")} L300,100Z`);
  }
  Hd.wifi = (m) => { S.wifi = m; if (pid === "health") renderNet(); };

  const APP_COLS = ["#ff9f0a", "#0a84ff", "#30d158", "#bf5af2", "#ff375f", "#64d2ff", "#ffd60a", "#5e5ce6", "#ff6961"];
  const hueOf = (name) => APP_COLS[[...name].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7) % APP_COLS.length];
  const fmtMem = (mb) => (mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb} MB`);
  Hd.procs = (m) => {
    const box = $("#hl-list");
    if (box.querySelector(".holding")) return;   // don't redraw under a finger
    box.innerHTML = (m.list || []).map((p) => `<div class="hl-row">
      <span class="hl-ico" style="background:${hueOf(p.name)}">${esc(p.name.slice(0, 1))}</span>
      <span class="hl-nm"><b>${esc(p.name)}${p.n > 1 ? ` <i>· ${p.n}</i>` : ""}</b><small>${fmtMem(p.mem)} · CPU ${p.cpu}%</small></span>
      <button class="hl-end" data-exe="${esc(p.exe.join(","))}"><span>End</span></button></div>`).join("")
      || `<div class="hl-empty">Nothing heavy running.</div>`;
  };
  function holdButton(sel, ms, fire) {
    let t = null, el = null;
    const stop = () => { clearTimeout(t); if (el) el.classList.remove("holding"); el = null; };
    document.addEventListener("pointerdown", (e) => {
      const b = e.target.closest(sel); if (!b) return;
      el = b; b.classList.add("holding"); buzz();
      t = setTimeout(() => { const x = el; stop(); if (x) { buzz(); fire(x); } }, ms);
    });
    ["pointerup", "pointercancel", "pointerleave"].forEach((ev) => document.addEventListener(ev, (e) => { if (el && (ev !== "pointerleave" || e.target === el)) stop(); }));
  }
  holdButton(".hl-end", 800, (b) => { b.closest(".hl-row").classList.add("gone"); send({ a: "kill", exe: b.dataset.exe.split(",") }); });

  let procsT = null;
  pageHooks.push((id) => {
    clearInterval(procsT);
    if (id === "health") {
      send({ a: "procs", now: true }); renderNet(); renderQuota();
      procsT = setInterval(() => send({ a: "procs" }), 10000);
    }
  });
  const hhmm = (ts) => fmtHM(new Date(ts * 1000));
  function renderQuota() {
    const q = S.quota;
    const kv = $("#hl-kv");
    if (!q) { kv.innerHTML = `<div class="hl-empty">Waiting for usage…</div>`; return; }
    const ses = (q.limits || []).find((l) => l.k === "session"), wk = (q.limits || []).find((l) => l.k === "weekly");
    $("#hl-plan").textContent = q.plan || "";
    const pct = ses ? ses.pct : null;
    setTxt($("#hl-pct"), pct != null ? `${pct}%` : "--");
    const col = pct == null ? "#8e8e93" : pct >= 90 ? "#ff453a" : pct >= 70 ? "#d97757" : "#d97757";
    gRing("#hl-r1", pct || 0, col);
    gRing("#hl-r2", wk ? wk.pct : 0, "#8e8e93");
    const rows = [];
    if (ses && ses.reset) rows.push(["Resets", hhmm(ses.reset)]);
    if (wk) rows.push(["Weekly", `${wk.pct}%`]);
    if (ses && ses.reset && ses.pct > 0) {
      const now = Date.now() / 1000, start = ses.reset - 5 * 3600, el = now - start;
      if (el > 600) {
        const full = now + (100 - ses.pct) / (ses.pct / el);
        rows.push(["At this pace", full < ses.reset ? `<span class="c-or">full ~${hhmm(full)}</span>` : `<span class="c-gr">lasts the session</span>`]);
      }
    }
    kv.innerHTML = rows.map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join("")
      + (q.err ? `<div class="hl-err">${esc(q.err)}</div>` : "");
  }
  Hd.quota = (m) => { S.quota = m; if (pid === "health") renderQuota(); };

  /* =========================================================================
     Focus: pomodoro (shared), checklist (shared), day progress, stopwatch, battery
     ========================================================================= */
  const FC_T = { work: "Focus", short: "Short break", long: "Long break", idle: "Focus" };
  function renderFocusTimer() {
    if (!FC) return;
    const left = fcLeft(), total = (FC.mode === "idle" ? FC.len.work : FC.len[FC.mode] || 25) * 60;
    setTxt($("#fc-time"), mmss(left));
    const brk = FC.mode === "short" || FC.mode === "long";
    gRing("#fc-rv", FC.mode === "idle" ? 0 : clamp(100 - left / total * 100, 0, 100), brk ? "#30d158" : "#bf5af2");
    $("#fc-ring").classList.toggle("brk", brk);
  }
  function renderFocus() {
    if (!FC) return;
    const brk = FC.mode === "short" || FC.mode === "long";
    $("#fc-mode").textContent = FC.mode === "work" ? `Focus · ${FC.round} of ${FC.rounds}` : FC_T[FC.mode];
    const endTs = FC.paused ? null : FC.end;
    $("#fc-sub").textContent = FC.mode === "idle" ? `${FC.len.work} min focus, ${FC.len.short} min break` : FC.paused ? "Paused" : brk ? `Back at ${hhmm(endTs)}` : `Break at ${hhmm(endTs)}`;
    const B = (cmd, txt, cls = "") => `<button class="${cls}" data-fc="${cmd}">${txt}</button>`;
    $("#fc-btns").innerHTML = FC.mode === "idle" ? B("start", "Start focus", "pri")
      : (FC.paused ? B("resume", "Resume", "pri") : B("pause", "Pause", "pri")) + B("skip", brk ? "Skip break" : "Skip") + (FC.paused ? B("stop", "Stop") : B("add5", "+5 min"));
    renderFocusTimer();
    const items = FC.todo || [];
    $("#fc-todoh").textContent = `Today · ${items.filter((i) => i.done).length} of ${items.length}`;
    $("#fc-clear").hidden = !items.some((i) => i.done);
    $("#fc-items").innerHTML = items.map((i) => `<button class="fc-it${i.done ? " done" : ""}" data-id="${esc(i.id)}"><span class="ck">${i.done ? svg("check") : ""}</span><span class="tx">${esc(i.t)}</span></button>`).join("")
      || `<div class="hl-empty">Nothing yet. Add something below.</div>`;
  }
  Hd.focus = (m) => { FC = m; renderFocus(); islandUpdate(); };
  $("#fc-btns").addEventListener("click", (e) => { const b = e.target.closest("[data-fc]"); if (!b) return; buzz(); send({ a: "focus", cmd: b.dataset.fc }); });
  $("#fc-clear").addEventListener("click", () => { buzz(); send({ a: "focus", cmd: "clear" }); });
  $("#fc-add").addEventListener("submit", (e) => {
    e.preventDefault(); const v = $("#fc-in").value.trim(); if (!v) return;
    buzz(); send({ a: "focus", cmd: "add", text: v }); $("#fc-in").value = ""; $("#fc-in").blur();
  });
  (() => { // tap = tick, hold = remove
    let t = null, held = false;
    const box = $("#fc-items");
    box.addEventListener("pointerdown", (e) => {
      const it = e.target.closest(".fc-it"); if (!it) return; held = false;
      t = setTimeout(() => { held = true; buzz(); it.classList.add("gone"); send({ a: "focus", cmd: "del", id: it.dataset.id }); toast("Removed", "xmark"); }, 650);
    });
    ["pointerup", "pointercancel", "pointerleave"].forEach((ev) => box.addEventListener(ev, () => clearTimeout(t)));
    box.addEventListener("click", (e) => {
      const it = e.target.closest(".fc-it"); if (!it || held) return;
      buzz(); it.classList.toggle("done"); send({ a: "focus", cmd: "toggle", id: it.dataset.id });
    });
  })();
  function isoWeek(d) { const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())); const day = t.getUTCDay() || 7; t.setUTCDate(t.getUTCDate() + 4 - day); const y = new Date(Date.UTC(t.getUTCFullYear(), 0, 1)); return Math.ceil(((t - y) / 864e5 + 1) / 7); }
  function renderDay() {
    const d = new Date(), h = d.getHours() + d.getMinutes() / 60;
    $("#fc-wd").textContent = DF.wd.format(d);
    setTxt($("#fc-dp"), `${Math.floor(h / 24 * 100)}%`);
    $("#fc-hours").innerHTML = Array.from({ length: 24 }, (_, i) => `<i class="${i < Math.floor(h) ? "on" : i === Math.floor(h) ? "now" : ""}"></i>`).join("");
    const wk = ((d.getDay() + 6) % 7 + h / 24) / 7 * 100;
    const y0 = new Date(d.getFullYear(), 0, 1), y1 = new Date(d.getFullYear() + 1, 0, 1);
    $("#fc-wy").textContent = `Week ${isoWeek(d)} · ${Math.floor(wk)}% · Year ${Math.floor((d - y0) / (y1 - y0) * 100)}%`;
  }
  const SW = LS.get("sw", { run: false, t0: 0, acc: 0 });
  const swNow = () => SW.acc + (SW.run ? Date.now() - SW.t0 : 0);
  function renderSW() {
    const ms = swNow(), s = Math.floor(ms / 1000);
    $("#fc-swt").innerHTML = `${s >= 3600 ? `${Math.floor(s / 3600)}:` : ""}${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}<i>.${Math.floor(ms / 100) % 10}</i>`;
    $("#fc-sws").textContent = SW.run ? "Running · tap to stop" : ms ? "Stopped · hold to reset" : "Tap to start · hold to reset";
    $("#fc-sw").classList.toggle("run", SW.run);
  }
  (() => {
    const b = $("#fc-sw"); let t = null, held = false;
    b.addEventListener("pointerdown", () => { held = false; t = setTimeout(() => { held = true; buzz(); Object.assign(SW, { run: false, t0: 0, acc: 0 }); LS.set("sw", SW); renderSW(); }, 650); });
    ["pointerup", "pointercancel", "pointerleave"].forEach((ev) => b.addEventListener(ev, () => clearTimeout(t)));
    b.addEventListener("click", () => {
      if (held) return; buzz();
      if (SW.run) { SW.acc += Date.now() - SW.t0; SW.run = false; } else { SW.t0 = Date.now(); SW.run = true; }
      LS.set("sw", SW); renderSW();
    });
  })();
  (async () => {
    try {
      if (!navigator.getBattery) throw 0;
      const b = await navigator.getBattery();
      const r = () => { setTxt($("#fc-batv"), `${Math.round(b.level * 100)}%`); $("#fc-bats").innerHTML = b.charging ? `<span class="c-gr">${svg("bolt")} Charging</span>` : "On battery"; };
      b.addEventListener("levelchange", r); b.addEventListener("chargingchange", r); r();
    } catch (e) { $("#fc-batl").textContent = "This screen"; $("#fc-bats").textContent = "Battery isn't shared by this browser"; }
  })();
  pageHooks.push((id) => { if (id === "focus") { renderFocus(); renderDay(); renderSW(); } });

  /* =========================================================================
     Meeting mode
     ========================================================================= */
  function renderMeet() {
    const c = CTX.call, muted = !!(S.vol && S.vol.mic);
    $("#p-meet").classList.toggle("idle", !c);
    $("#mt-app").textContent = c ? c.app : "Call";
    const title = c && c.title ? c.title.replace(/\s*[|·-]\s*(Microsoft Teams|Zoom( Workplace| Meeting)?|Discord|Google Chrome|Microsoft Edge|Slack)\s*$/i, "").trim() : "";
    $("#mt-title").textContent = c ? title || "Call in progress" : "No call right now";
    $("#mt-sub").textContent = c ? (c.cam ? "Camera is on" : "Camera off") : "This page opens by itself when a call starts";
    const mb = $("#mt-mute");
    mb.classList.toggle("muted", muted);
    mb.innerHTML = svg(muted ? "micoff" : "mic");
    $("#mt-state").textContent = muted ? "Muted" : "Mic on";
    $("#mt-camic").classList.toggle("on", !!(c && c.cam));
    $("#mt-cams").textContent = c && c.cam ? "On" : "Off";
    renderMeetTimer();
  }
  function renderMeetTimer() {
    const c = CTX.call;
    if (!c) { setTxt($("#mt-timer"), "--:--"); return; }
    const s = Math.max(0, Math.floor(Date.now() / 1000 - c.since));
    setTxt($("#mt-timer"), s >= 3600 ? `${Math.floor(s / 3600)}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}` : mmss(s));
  }
  { const hv = Hd.vol; Hd.vol = (m) => { hv(m); if (pid === "meet") renderMeet(); }; }
  $("#mt-mute").addEventListener("click", () => {
    buzz(); S.vol = Object.assign({}, S.vol, { mic: !(S.vol && S.vol.mic) }); renderMeet(); send({ a: "mic" });
  });
  document.addEventListener("click", (e) => { const b = e.target.closest("[data-call]"); if (b) { buzz(); send({ a: "call", cmd: b.dataset.call }); } });
  holdButton("#mt-leave", 900, () => send({ a: "call", cmd: "leave" }));
  pageHooks.push((id) => { if (id === "meet") renderMeet(); });

  /* one slow ticker for the clock-like bits */
  setInterval(() => {
    if (pid === "focus") { renderFocusTimer(); renderSW(); if (new Date().getSeconds() === 0) renderDay(); }
    if (pid === "meet") renderMeetTimer();
    if (FC && FC.mode !== "idle" && ISL.cur && ISL.cur.id === "focus") islandUpdate();
  }, 250);

  /* =========================================================================
     PC notifications + webhooks (Room page)
     ========================================================================= */
  const NOTE_COLS = { whatsapp: "#25d366", discord: "#5865f2", outlook: "#0a84ff", mail: "#0a84ff", teams: "#5b5fc7",
    "microsoft teams": "#5b5fc7", telegram: "#2aabee", gmail: "#ea4335", slack: "#e01e5a", messenger: "#0a84ff",
    instagram: "#e1306c", steam: "#1b2838", webhook: "#8e8e93", calendar: "#ff453a" };
  function noteCol(app) { const k = (app || "").toLowerCase(); return NOTE_COLS[k] || Object.entries(NOTE_COLS).find(([n]) => k.includes(n))?.[1] || hueOf(app || "?"); }
  Hd.note = (m) => {
    if (m.buzz !== false) buzz(30);
    ISL.queue = ISL.queue.filter((q) => q.id !== "note");
    islandQueue({ id: "note", n: m });
  };
  Hd.goto = (m) => {
    const id = m.page; if (!SECS[id]) return;
    if (PV[id] === "auto") autoPage(id, true);
    requestAnimationFrame(() => go(id));
  };
  const COLV = { orange: "var(--orange)", blue: "var(--blue)", green: "var(--green)", purple: "var(--purple)", red: "var(--red)",
    pink: "var(--pink)", cyan: "var(--cyan)", yellow: "var(--yellow)", teal: "var(--teal)", indigo: "var(--indigo)" };
  const ago = (ts) => { const s = Math.max(0, Date.now() / 1000 - ts); return s < 60 ? `${Math.round(s)} s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`; };
  const fmtVal = (v) => (typeof v === "boolean" ? (v ? "On" : "Off") : typeof v === "number" ? (Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("en-US") : String(Math.round(v * 10) / 10)) : String(v ?? "--"));
  function spark(hist) {
    if (!hist || hist.length < 2) return "";
    const mn = Math.min(...hist), mx = Math.max(...hist), r = mx - mn || 1;
    return hist.map((v, i) => `${(i / (hist.length - 1) * 300).toFixed(1)},${(54 - (v - mn) / r * 48).toFixed(1)}`).join(" ");
  }
  function renderRoom() {
    const h = S.hooks || {}, vals = h.values || [], box = $("#rm-grid");
    const hk = (S.hello && S.hello.hook) || {};
    const base = `http://${h.lan || hk.lan || "PC-IP"}:${h.port || hk.port || 8765}`, key = h.key || hk.key || "KEY";
    if (!vals.length) {
      box.className = "rm empty";
      box.innerHTML = `<div class="w rm-help"><div class="hl-lbl">Room · webhooks</div>
        <b class="rm-h">Send anything to this page</b>
        <p>From an ESP32, Home Assistant or a script on your network:</p>
        <code>POST ${esc(base)}/hook/value?key=${esc(key)}<br>{"id":"room","label":"Room","value":27.4,"unit":"°","sub":"Humidity 68%"}</code>
        <p>Quick test in a browser: <code>${esc(base)}/hook/value?key=${esc(key)}&amp;id=room&amp;value=27.4&amp;unit=°</code></p>
        <p>Pop a notification: <code>/hook/notify?key=…&amp;title=Door&amp;body=Opened</code> · Siri Shortcuts: <code>/api/do?key=…&amp;do=lock</code></p></div>`;
      return;
    }
    const big = vals.find((v) => typeof v.value === "number" && (v.hist || []).length > 2);
    const rest = vals.filter((v) => v !== big).slice(0, big ? 4 : 6);
    box.className = `rm${big ? " has-big" : ""}`;
    const tile = (v) => {
      const col = COLV[v.color] || "";
      const on = v.value === true;
      const sw = v.action ? `<span class="rm-sw${on ? " on" : ""}"><i></i></span>` : "";
      return `<button class="w rm-t${typeof v.value === "boolean" ? " bool" : ""}${on ? " on" : ""}" data-hook="${esc(v.id)}" ${v.action ? "" : "disabled"} style="${col ? `--rc:${col}` : ""}">
        <div class="hl-lbl">${esc(v.label)}</div>
        <div class="rm-v"><div><b>${esc(fmtVal(v.value))}</b>${v.unit && typeof v.value === "number" ? `<span>${esc(v.unit)}</span>` : ""}
        <small>${esc(v.sub || ago(v.ts))}</small></div>${sw}</div></button>`;
    };
    let html = "";
    if (big) {
      const col = COLV[big.color] || "var(--orange)";
      html += `<div class="w rm-big" style="--rc:${col}"><div class="hl-lbl">${esc(big.label)}</div>
        <div class="rm-bv"><b>${esc(fmtVal(big.value))}</b><span>${esc(big.unit || "")}</span></div>
        <div class="rm-sub">${esc(big.sub || "")}</div>
        <svg class="rm-sp" viewBox="0 0 300 58" preserveAspectRatio="none"><polyline points="${spark(big.hist)}" fill="none" stroke="${col}" stroke-width="2.4" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>
        <div class="rm-foot"><span>${big.hist.length} readings</span><span>${ago(big.ts)}</span></div></div>`;
    }
    html += rest.map(tile).join("");
    box.innerHTML = html;
  }
  Hd.hooks = (m) => {
    S.hooks = m;
    autoPage("room", (m.values || []).length > 0);
    if (pid === "room") renderRoom();
  };
  pageHooks.push((id) => { if (id === "room") renderRoom(); });
  $("#rm-grid").addEventListener("click", (e) => {
    const b = e.target.closest("[data-hook]"); if (!b || b.disabled) return;
    buzz(); b.classList.toggle("on"); send({ a: "hook_toggle", id: b.dataset.hook });
  });

  /* toast */
  let toastT = null;
  function toast(msg, icon = "check", err = false) {
    const t = $("#toast");
    $("#toast-ic").innerHTML = svg(icon); $("#toast-t").textContent = msg;
    t.classList.toggle("err", !!err); t.classList.add("on");
    clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("on"), 1700);
  }
  Hd.toast = (m) => toast(m.msg, m.err ? "xmark" : m.icon || "check", m.err);

  /* =========================================================================
     drive: Forza telemetry, CarPlay Ultra style
     ========================================================================= */
  const FZ = { d: null, live: false, lastLive: 0, prevPage: null, auto: false, rpm: 0, kmh: 0, maxRpm: 0, ord: null, name: undefined, trail: [], tick: 0 };
  const CLS = [[500, "D", "#5ac8fa"], [600, "C", "#e6b800"], [700, "B", "#ff9f0a"], [800, "A", "#ff453a"], [900, "S1", "#bf5af2"], [998, "S2", "#0a84ff"]];
  const clsOf = (pi) => { for (const [t, n, c] of CLS) if (pi <= t) return [n, c]; return ["X", "#30d158"]; };
  const gearTxt = (g) => (g === 0 ? "R" : g >= 11 || g == null ? "N" : String(g));
  const setTxt = (el, v) => { if (el._v !== v) { el._v = v; el.textContent = v; } };
  const SHIFT = $$("#shift i");
  const GAUGE = {};
  function buildGauge(id, max, step, div, redFrom) {
    const el = $(`#${id} svg`), cx = 100, cy = 100, R = 86, A0 = 150, SW = 240;
    const pt = (a, r) => [cx + r * Math.cos((a * Math.PI) / 180), cy + r * Math.sin((a * Math.PI) / 180)];
    const arc = (a0, a1, r) => { const [x0, y0] = pt(a0, r), [x1, y1] = pt(a1, r); return `M${x0.toFixed(2)} ${y0.toFixed(2)}A${r} ${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`; };
    const ang = (v) => A0 + (SW * clamp(v, 0, max)) / max;
    let h = `<defs><radialGradient id="${id}-bg" cx="50%" cy="42%" r="62%"><stop offset="0" stop-color="#232327"/><stop offset="1" stop-color="#0b0b0d"/></radialGradient></defs>`;
    h += `<circle cx="100" cy="100" r="98" fill="url(#${id}-bg)"/><circle cx="100" cy="100" r="98" fill="none" stroke="rgba(255,255,255,.06)"/>`;
    h += `<path d="${arc(A0, A0 + SW, R)}" class="gv-track"/>`;
    if (redFrom != null) h += `<path d="${arc(ang(redFrom), A0 + SW, R)}" class="gv-red"/>`;
    h += `<path id="${id}-val" d="${arc(A0, A0 + SW, R)}" pathLength="100" class="gv-val" style="stroke-dasharray:0 100"/>`;
    for (let v = 0; v <= max + 1e-6; v += step / 2) {
      const major = Math.abs(v / step - Math.round(v / step)) < 1e-6, a = ang(v), red = redFrom != null && v >= redFrom - 1e-6 ? " red" : "";
      const [x0, y0] = pt(a, R - 9), [x1, y1] = pt(a, R - (major ? 17 : 13));
      h += `<line x1="${x0.toFixed(2)}" y1="${y0.toFixed(2)}" x2="${x1.toFixed(2)}" y2="${y1.toFixed(2)}" class="${major ? "gt-maj" : "gt-min"}${red}"/>`;
      if (major) { const [lx, ly] = pt(a, R - 28); h += `<text x="${lx.toFixed(1)}" y="${(ly + 4).toFixed(1)}" class="gt-lbl${red}">${div ? v / div : v}</text>`; }
    }
    h += `<g id="${id}-ndl" class="gv-ndl"><line x1="${cx + R - 30}" y1="100" x2="${cx + R + 3}" y2="100"/></g>`;
    el.innerHTML = h;
    GAUGE[id] = { max, ang, val: $(`#${id}-val`), ndl: $(`#${id}-ndl`) };
    setGauge(id, 0);
  }
  function setGauge(id, v) {
    const g = GAUGE[id];
    g.val.style.strokeDasharray = `${(clamp(v / g.max, 0, 1) * 100).toFixed(2)} 100`;
    g.ndl.setAttribute("transform", `rotate(${g.ang(v).toFixed(2)} 100 100)`);
  }
  buildGauge("g-speed", 360, 40, 0, null);
  buildGauge("g-rpm", 8000, 1000, 1000, 7200);

  function carInfo(m) {
    FZ.ord = m.ord; FZ.name = m.name; FZ.car = m.car ? m.car.full : null;
    const [c, col] = clsOf(m.pi);
    const b = $("#clsb"); b.style.setProperty("--cc", col); $("b", b).textContent = c; $("i", b).textContent = m.pi;
    $("#dtb").textContent = ["FWD", "RWD", "AWD"][m.dt] || "--";
    const n = $("#cwc-name"), car = !m.name && m.car;
    $(".cwc-lbl").textContent = car ? `${car.year} · ${car.make}` : "Car";
    n.textContent = m.name || (car ? car.model : "Tap to name this car");
    n.classList.toggle("unk", !m.name && !car);
    $("#cwc-id").textContent = car ? "" : `#${m.ord} · ${m.cyl ? `${m.cyl} cyl` : "EV"}`;
  }
  Hd.fz = (m) => {
    const cp = $("#cp");
    if (!m.live) { FZ.live = false; cp.classList.remove("live", "paused"); return; }
    FZ.live = true; FZ.d = m; FZ.lastLive = Date.now();
    cp.classList.add("live"); cp.classList.toggle("paused", !m.on);
    if (m.max > 0 && Math.abs(m.max - FZ.maxRpm) > 50) {
      FZ.maxRpm = m.max;
      buildGauge("g-rpm", Math.ceil(m.max / 1000) * 1000, 1000, 1000, m.max * 0.9);
    }
    if (m.ord !== FZ.ord || m.name !== FZ.name || (m.car ? m.car.full : null) !== FZ.car) carInfo(m);
    if (m.on && !FZ.auto) {
      FZ.auto = true;
      const auto = !(S.hello && S.hello.forza && S.hello.forza.auto === false);
      if (auto) autoEnter("drive");
    }
  };
  Hd.fzapp = (m) => $("#fz-run").classList.toggle("on", !!m.running);
  function driveIdleCheck() {
    if (!FZ.live && FZ.auto && Date.now() - FZ.lastLive > 20000) {
      autoExit("drive");
      FZ.auto = false;
    }
  }
  function renderDrive(dt) {
    const d = FZ.d, k = Math.min(1, dt * 18);
    FZ.rpm += (d.rpm - FZ.rpm) * k; FZ.kmh += (d.kmh - FZ.kmh) * k;
    setGauge("g-speed", FZ.kmh); setGauge("g-rpm", FZ.rpm);
    setTxt($("#g-kmh"), String(Math.round(FZ.kmh)));
    setTxt($("#g-rpmv"), (FZ.rpm / 1000).toFixed(1));
    const pct = FZ.rpm / (d.max || 8000);
    const g = $("#g-rpm"); g.classList.toggle("red", pct >= 0.9); g.classList.toggle("hot", pct >= 0.8 && pct < 0.9);
    const flash = pct >= 0.955 && d.on;
    $("#shift").classList.toggle("flash", flash);
    if (!flash) {
      const on = clamp(Math.floor(((pct - 0.7) / 0.25) * 12), 0, 12);
      SHIFT.forEach((el, i) => { const c = i < on ? (i < 4 ? "g" : i < 8 ? "y" : "r") : ""; if (el.className !== c) el.className = c; });
    }
    const gear = $("#gear"); setTxt(gear, gearTxt(d.gear)); gear.classList.toggle("sp", flash);
    $("#cp-glow").style.setProperty("--glow", flash ? 0.3 : pct > 0.85 ? ((pct - 0.85) * 2).toFixed(2) : 0);
    $("#pb-thr").style.width = `${(d.thr / 2.55).toFixed(1)}%`;
    $("#pb-brk").style.width = `${(d.brk / 2.55).toFixed(1)}%`;
    FZ.tick++;
    if (FZ.tick % 4 === 0) {
      setTxt($("#cwc-hp"), String(d.hp)); setTxt($("#cwc-nm"), String(d.nm));
      setTxt($("#cwc-boost"), Math.max(0, d.boost).toFixed(1));
    }
    const gx = (clamp(d.gx, -1.5, 1.5) / 1.5) * 45, gy = (-clamp(d.gz, -1.5, 1.5) / 1.5) * 45;
    const dot = $("#gm-dot"); dot.setAttribute("cx", gx.toFixed(1)); dot.setAttribute("cy", gy.toFixed(1));
    if (FZ.tick % 2 === 0) {
      FZ.trail.push(`${gx.toFixed(1)},${gy.toFixed(1)}`);
      if (FZ.trail.length > 26) FZ.trail.shift();
      $("#gm-trail").setAttribute("points", FZ.trail.join(" "));
    }
    if (FZ.tick % 12 === 0) {
      $$("#tires div").forEach((el, i) => {
        const t = d.tt[i];
        el.style.setProperty("--tc", t < 65 ? "#64d2ff" : t <= 105 ? "#30d158" : t <= 120 ? "#ff9f0a" : "#ff453a");
        setTxt(el.firstElementChild, `${t}°`);
        el.classList.toggle("slip", (d.slip[i] || 0) > 1);
      });
    }
  }
  // dock
  document.addEventListener("click", (e) => {
    const f = e.target.closest("[data-fz]");
    if (f) { buzz(); send({ a: "forza", v: f.dataset.fz }); return; }
    const g = e.target.closest("[data-go]");
    if (g) { buzz(); go(g.dataset.go); }
  });
  (() => {
    const b = $("#fz-quit"); let t = null, fired = false, quitAt = 0;
    b.addEventListener("pointerdown", () => {
      fired = false; b.classList.add("holding");
      t = setTimeout(() => {
        fired = true; b.classList.remove("holding"); buzz();
        const force = Date.now() - quitAt < 20000; quitAt = Date.now();
        send({ a: "forza", v: force ? "kill" : "quit" });
      }, 1000);
    });
    const end = () => { clearTimeout(t); b.classList.remove("holding"); };
    ["pointerup", "pointerleave", "pointercancel"].forEach((ev) => b.addEventListener(ev, end));
    b.addEventListener("click", () => { if (!fired) toast("Hold to quit Forza", "power"); });
  })();
  // name this car
  function carSheet(open) {
    const sh = $("#carsheet");
    if (open) { sh.hidden = false; requestAnimationFrame(() => sh.classList.add("on")); setTimeout(() => $("#car-input").focus(), 150); }
    else { sh.classList.remove("on"); $("#car-input").blur(); setTimeout(() => { sh.hidden = true; }, 300); }
  }
  $("#cw-car").addEventListener("click", () => {
    if (!FZ.d) { toast("Start driving in Forza first", "car"); return; }
    $("#car-input").value = FZ.d.name || (FZ.d.car ? FZ.d.car.full : "");
    const [c] = clsOf(FZ.d.pi);
    $("#car-note").textContent = `Car ID #${FZ.d.ord} · ${c} ${FZ.d.pi} · ${["FWD", "RWD", "AWD"][FZ.d.dt] || ""} · ${FZ.d.cyl ? `${FZ.d.cyl} cyl` : "EV"}`;
    carSheet(true);
  });
  $("#car-cancel").addEventListener("click", () => carSheet(false));
  $("#carsheet").addEventListener("click", (e) => { if (e.target.id === "carsheet") carSheet(false); });
  const saveCar = () => {
    if (!FZ.d) return carSheet(false);
    const name = $("#car-input").value.trim();
    send({ a: "carname", ord: FZ.d.ord, name });
    FZ.d.name = name || null; carInfo(FZ.d); carSheet(false);
  };
  $("#car-save").addEventListener("click", saveCar);
  $("#car-input").addEventListener("keydown", (e) => { if (e.key === "Enter") saveCar(); });

  /* =========================================================================
     frame loop
     ========================================================================= */
  let lastF = performance.now(), bgAcc = 0, lastSecShown = -1;
  function frame(t) {
    const dt = Math.min(0.1, (t - lastF) / 1000); lastF = t;
    if (t - AUDIO.at > 400) for (let i = 0; i < 24; i++) AUDIO.t[i] *= 0.9;
    const k = Math.min(1, dt * 16);
    for (let i = 0; i < 24; i++) AUDIO.s[i] += (AUDIO.t[i] - AUDIO.s[i]) * k;
    AUDIO.bass = (AUDIO.s[0] + AUDIO.s[1] + AUDIO.s[2] + AUDIO.s[3]) / 400;

    if (M.active) {
      const p = curPos();
      if (pid === "music") {
        const fr = M.dur > 0 ? p / M.dur : 0;
        $("#np-fill").style.width = `${(fr * 100).toFixed(3)}%`;
        const sec = Math.floor(p);
        if (sec !== lastSecShown) { lastSecShown = sec; renderProgress(p); }
      }
      if (pid === "music" || ambOn) lyricsTick(p);
    }
    if (ISL.mode !== "hidden") waveTick(t);
    if (ambOn) document.documentElement.style.setProperty("--bass", AUDIO.bass.toFixed(3));

    bgAcc += dt;
    if ((pid === "music" || ambOn) && bgAcc >= 1 / 30) {
      BG.t += bgAcc * (M.playing ? 1 : 0.25); BG.step();
      BG.draw(ambOn ? $("#amb-bg") : $("#np-bg"));
      bgAcc = 0;
    }
    if (pid === "music" && $(".np-r").classList.contains("nolyr")) drawSpec();
    if (pid === "home" && clockStyle === "analog") drawAnalog();
    if (pid === "drive") {
      if (FZ.live && FZ.d) renderDrive(dt);
      const pf = R.on ? (R.d.dur > 0 ? rPos() / R.d.dur : 0) : (M.active && M.dur > 0 ? curPos() / M.dur : 0);
      $("#cwr-fill").style.width = `${(pf * 100).toFixed(2)}%`;
    }
    if (Q.open && R.on) {
      const d = R.d.dur || 0, p = rPos();
      $("#qs-fill").style.width = `${(d > 0 ? p / d * 100 : 0).toFixed(2)}%`;
      $("#qs-cur").textContent = fmtT(p); $("#qs-rem").textContent = d > 0 ? `-${fmtT(d - p)}` : "";
    }
    requestAnimationFrame(frame);
  }

  /* =========================================================================
     screen care: wake lock, fullscreen, pixel shift
     ========================================================================= */
  async function wake() { try { if ("wakeLock" in navigator && document.visibilityState === "visible") await navigator.wakeLock.request("screen"); } catch (e) {} }
  document.addEventListener("visibilitychange", wake);
  let fsTried = false;
  document.addEventListener("pointerup", () => {
    if (fsTried) return; fsTried = true;
    const standalone = matchMedia("(display-mode: fullscreen), (display-mode: standalone)").matches;
    if (!standalone && document.documentElement.requestFullscreen && !document.fullscreenElement) {
      document.documentElement.requestFullscreen({ navigationUI: "hide" }).catch(() => {});
    }
    wake();
  });
  setInterval(() => {
    const x = Math.round(Math.random() * 4 - 2), y = Math.round(Math.random() * 4 - 2);
    $("#root").style.transform = `translate(${x}px,${y}px)`;
  }, 150000);

  /* =========================================================================
     boot
     ========================================================================= */
  paintIcons();
  renderVol();
  tickClock();
  (document.fonts ? document.fonts.ready : Promise.resolve()).then(() => { fitMarquees(); renderF1(); });
  connect();
  wake();
  secondLoop();
  requestAnimationFrame(frame);
  window.__dd = { go, S, M, Hd, setAmbient, islandQueue };
})();
