/** Shared AI Demo dashboard highlight + pointer helpers. */

const PULSE_MS = 3200;
const RETRY_MS = 120;
const RETRY_MAX = 40; // ~4.8s wait for route paint
const POINTER_ID = "voxbulk-ai-demo-pointer";
const SPOTLIGHT_ID = "voxbulk-ai-demo-spotlight";
const LABEL_ID = "voxbulk-ai-demo-label";
const STYLE_ID = "voxbulk-ai-demo-highlight-style";

export type DemoHighlightOptions = {
  targetElementId?: string | null;
  pointer?: boolean;
  label?: string | null;
  /** Soft-fail missing targets in production; warn in dev/test. */
  warnMissing?: boolean;
};

export function pricingTabForService(serviceSlug: string | null | undefined): string {
  const s = String(serviceSlug || "")
    .trim()
    .toLowerCase()
    .replace(/-/g, "_")
    .replace(/\s+/g, "_");
  if (s === "feedback" || s === "customer_feedback") return "feedback";
  if (s === "expo" || s === "voxbulk_expo" || s === "booth") return "expo";
  if (s === "smart_card" || s === "smartcard" || s === "smart_card_qr") return "smartCard";
  if (
    s === "recruitment" ||
    s === "surveys" ||
    s === "interview" ||
    s === "interviews" ||
    s === "ai_interview" ||
    s === "core" ||
    s === "platform"
  ) {
    return "core";
  }
  return "core";
}

export function openPricingTabPath(serviceSlug: string | null | undefined): string {
  return `/account/packages?tab=${pricingTabForService(serviceSlug)}`;
}

function ensureHighlightStyles() {
  if (typeof document === "undefined") return;
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
@keyframes voxDemoPulse {
  0% { box-shadow: 0 0 0 0 rgba(30, 111, 217, 0.65); }
  70% { box-shadow: 0 0 0 18px rgba(30, 111, 217, 0); }
  100% { box-shadow: 0 0 0 0 rgba(30, 111, 217, 0); }
}
.highlight-pulse {
  outline: 3px solid #1e6fd9 !important;
  outline-offset: 4px;
  animation: voxDemoPulse 1.8s ease-out 2;
  border-radius: 10px;
  position: relative;
  z-index: 60 !important;
}
#${SPOTLIGHT_ID} {
  position: fixed;
  inset: 0;
  background: rgba(10, 22, 40, 0.45);
  pointer-events: none;
  z-index: 55;
  transition: opacity 0.2s ease;
}
#${POINTER_ID} {
  position: fixed;
  width: 34px;
  height: 34px;
  margin-left: -6px;
  margin-top: -6px;
  border-radius: 50%;
  border: 3px solid #1e6fd9;
  background: rgba(30, 111, 217, 0.22);
  pointer-events: none;
  z-index: 70;
  transition: left 0.35s ease, top 0.35s ease, opacity 0.25s ease;
  box-shadow: 0 0 0 8px rgba(30, 111, 217, 0.15);
}
#${POINTER_ID}::after {
  content: "";
  position: absolute;
  left: 11px;
  top: 11px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #1e6fd9;
}
#${LABEL_ID} {
  position: fixed;
  z-index: 71;
  max-width: min(280px, 70vw);
  padding: 8px 12px;
  border-radius: 10px;
  background: #0a1628;
  color: #fff;
  font: 600 13px/1.35 system-ui, sans-serif;
  box-shadow: 0 10px 30px rgba(10,22,40,0.35);
  pointer-events: none;
  transition: opacity 0.2s ease;
}
#${LABEL_ID}::before {
  content: "Click here";
  display: block;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #8ec5ff;
  margin-bottom: 2px;
}
`;
  document.head.appendChild(style);
}

function resolveTarget(targetElementId: string): HTMLElement | null {
  const raw = String(targetElementId || "").trim();
  if (!raw || typeof document === "undefined") return null;
  if (raw.startsWith("#") || raw.startsWith("[") || raw.startsWith(".")) {
    try {
      return document.querySelector(raw) as HTMLElement | null;
    } catch {
      return null;
    }
  }
  return (
    (document.querySelector(`[data-demo-target="${raw.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"]`) as HTMLElement | null) ||
    document.getElementById(raw)
  );
}

function clearOverlaysSoon() {
  window.setTimeout(() => {
    document.getElementById(SPOTLIGHT_ID)?.remove();
    const tip = document.getElementById(POINTER_ID);
    if (tip) tip.style.opacity = "0";
    const label = document.getElementById(LABEL_ID);
    if (label) label.style.opacity = "0";
  }, PULSE_MS);
}

function placeSpotlight(el: HTMLElement) {
  ensureHighlightStyles();
  let veil = document.getElementById(SPOTLIGHT_ID);
  if (!veil) {
    veil = document.createElement("div");
    veil.id = SPOTLIGHT_ID;
    document.body.appendChild(veil);
  }
  const rect = el.getBoundingClientRect();
  const pad = 10;
  const top = Math.max(0, rect.top - pad);
  const left = Math.max(0, rect.left - pad);
  const right = Math.max(0, window.innerWidth - rect.right - pad);
  const bottom = Math.max(0, window.innerHeight - rect.bottom - pad);
  veil.style.opacity = "1";
  veil.style.clipPath = `inset(${top}px ${right}px ${bottom}px ${left}px round 12px)`;
  // invert via mask: use box-shadow hole technique instead of clipPath inset hole
  veil.style.clipPath = "none";
  veil.style.background = "transparent";
  veil.style.boxShadow = `0 0 0 9999px rgba(10, 22, 40, 0.48)`;
  veil.style.top = `${top}px`;
  veil.style.left = `${left}px`;
  veil.style.width = `${rect.width + pad * 2}px`;
  veil.style.height = `${rect.height + pad * 2}px`;
  veil.style.borderRadius = "12px";
  veil.style.inset = "auto";
}

function placePointer(el: HTMLElement) {
  ensureHighlightStyles();
  let tip = document.getElementById(POINTER_ID);
  if (!tip) {
    tip = document.createElement("div");
    tip.id = POINTER_ID;
    document.body.appendChild(tip);
  }
  const rect = el.getBoundingClientRect();
  tip.style.opacity = "1";
  tip.style.left = `${Math.round(rect.left + Math.min(rect.width * 0.72, Math.max(rect.width - 12, 12)))}px`;
  tip.style.top = `${Math.round(rect.top + Math.min(rect.height * 0.55, Math.max(rect.height - 12, 12)))}px`;
}

function placeLabel(el: HTMLElement, label?: string | null) {
  ensureHighlightStyles();
  const text = String(label || "").trim() || "This control";
  let node = document.getElementById(LABEL_ID);
  if (!node) {
    node = document.createElement("div");
    node.id = LABEL_ID;
    document.body.appendChild(node);
  }
  // Keep ::before "Click here"; put detail in textContent after a span
  node.replaceChildren();
  const detail = document.createElement("span");
  detail.textContent = text;
  node.appendChild(detail);
  const rect = el.getBoundingClientRect();
  const preferBelow = rect.bottom + 56 < window.innerHeight;
  const top = preferBelow ? rect.bottom + 12 : Math.max(8, rect.top - 56);
  const left = Math.min(Math.max(8, rect.left), window.innerWidth - 220);
  node.style.opacity = "1";
  node.style.top = `${Math.round(top)}px`;
  node.style.left = `${Math.round(left)}px`;
}

export function applyDemoHighlight(opts: DemoHighlightOptions) {
  if (typeof document === "undefined") return false;
  ensureHighlightStyles();
  const id = String(opts.targetElementId || "").trim();
  if (!id) return false;
  const el = resolveTarget(id);
  if (!el) {
    const warn =
      opts.warnMissing !== false &&
      (import.meta.env?.DEV || import.meta.env?.MODE === "test" || import.meta.env?.MODE === "development");
    if (warn) {
      console.warn(`[ai-demo] no matching target_element_id in DOM: ${id}`);
    }
    return false;
  }
  try {
    el.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
  } catch {
    /* ignore */
  }
  el.classList.remove("highlight-pulse");
  void el.offsetWidth;
  el.classList.add("highlight-pulse");
  window.setTimeout(() => el.classList.remove("highlight-pulse"), PULSE_MS);
  placeSpotlight(el);
  if (opts.pointer !== false) placePointer(el);
  placeLabel(el, opts.label);
  clearOverlaysSoon();
  return true;
}

/** Wait for route paint / lazy pages, then spotlight. */
export function scheduleDemoHighlight(opts: DemoHighlightOptions, delayMs = 250): void {
  if (typeof window === "undefined") return;
  let tries = 0;
  const run = () => {
    if (applyDemoHighlight({ ...opts, warnMissing: tries >= RETRY_MAX - 1 })) return;
    tries += 1;
    if (tries < RETRY_MAX) window.setTimeout(run, RETRY_MS);
  };
  window.setTimeout(run, Math.max(0, delayMs));
}

export function parseDemoRoute(route: string): { pathname: string; search: Record<string, string> } {
  const raw = String(route || "").trim();
  if (!raw) return { pathname: "/", search: {} };
  const [pathname, qs = ""] = raw.split("?");
  const search: Record<string, string> = {};
  if (qs) {
    new URLSearchParams(qs).forEach((value, key) => {
      search[key] = value;
    });
  }
  return { pathname: pathname.startsWith("/") ? pathname : `/${pathname}`, search };
}
