/** Shared AI Demo dashboard highlight + pointer helpers. */

const PULSE_MS = 1800;
const POINTER_ID = "voxbulk-ai-demo-pointer";
const STYLE_ID = "voxbulk-ai-demo-highlight-style";

export type DemoHighlightOptions = {
  targetElementId?: string | null;
  pointer?: boolean;
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
  0% { box-shadow: 0 0 0 0 rgba(30, 111, 217, 0.55); }
  70% { box-shadow: 0 0 0 14px rgba(30, 111, 217, 0); }
  100% { box-shadow: 0 0 0 0 rgba(30, 111, 217, 0); }
}
.highlight-pulse {
  outline: 2px solid rgba(30, 111, 217, 0.85) !important;
  outline-offset: 3px;
  animation: voxDemoPulse 1.6s ease-out 1;
  border-radius: 8px;
  position: relative;
  z-index: 5;
}
#${POINTER_ID} {
  position: fixed;
  width: 28px;
  height: 28px;
  margin-left: -4px;
  margin-top: -4px;
  border-radius: 50%;
  border: 2px solid #1e6fd9;
  background: rgba(30, 111, 217, 0.18);
  pointer-events: none;
  z-index: 9999;
  transition: left 0.45s ease, top 0.45s ease, opacity 0.25s ease;
  box-shadow: 0 0 0 6px rgba(30, 111, 217, 0.12);
}
#${POINTER_ID}::after {
  content: "";
  position: absolute;
  left: 10px;
  top: 10px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #1e6fd9;
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
    (document.querySelector(`[data-demo-target="${raw.replace(/"/g, '\\"')}"]`) as HTMLElement | null) ||
    document.getElementById(raw)
  );
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
  tip.style.left = `${Math.round(rect.left + Math.min(rect.width * 0.7, rect.width - 8))}px`;
  tip.style.top = `${Math.round(rect.top + Math.min(rect.height * 0.55, rect.height - 8))}px`;
  window.setTimeout(() => {
    const node = document.getElementById(POINTER_ID);
    if (node) node.style.opacity = "0";
  }, PULSE_MS + 400);
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
    el.scrollIntoView({ behavior: "smooth", block: "center" });
  } catch {
    /* ignore */
  }
  el.classList.remove("highlight-pulse");
  // reflow so animation restarts
  void el.offsetWidth;
  el.classList.add("highlight-pulse");
  window.setTimeout(() => el.classList.remove("highlight-pulse"), PULSE_MS);
  if (opts.pointer) placePointer(el);
  return true;
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
