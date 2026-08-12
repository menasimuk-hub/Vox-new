/** Shared AI Demo dashboard highlight + pointer helpers. */

const RETRY_MS = 120;
const RETRY_MAX = 40; // ~4.8s wait for route paint
const POINTER_ID = "voxbulk-ai-demo-pointer";
const SPOTLIGHT_ID = "voxbulk-ai-demo-spotlight";
const LABEL_ID = "voxbulk-ai-demo-label";
const STYLE_ID = "voxbulk-ai-demo-highlight-style";

export type DemoHighlightIntent = "view" | "click";

export type DemoHighlightOptions = {
  targetElementId?: string | null;
  pointer?: boolean;
  label?: string | null;
  /** Soft-fail missing targets in production; warn in dev/test. */
  warnMissing?: boolean;
  /** view = info box (no click CTA). click = "Click here" until they tap. */
  intent?: DemoHighlightIntent;
  /** Keep the spotlight until the visitor clicks (coach mode). */
  persistUntilClick?: boolean;
  onClicked?: (targetElementId: string) => void;
};

export function inferDemoHighlightIntent(targetElementId?: string | null): DemoHighlightIntent {
  const tid = String(targetElementId || "").trim().toLowerCase();
  if (!tid) return "view";
  if (tid.startsWith("nav-") || tid.startsWith("results-tab") || tid === "results-location-select") return "click";
  if (tid.startsWith("packages-tab-") || tid === "wizard-next") return "click";
  return "view";
}

let driverHandle: { destroy: () => void } | null = null;
let clickBoundEl: HTMLElement | null = null;
let clickBoundHandler: ((ev: Event) => void) | null = null;
let highlightEpoch = 0;

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
  0% { box-shadow: 0 0 0 0 rgba(36, 48, 86, 0.45); }
  70% { box-shadow: 0 0 0 16px rgba(36, 48, 86, 0); }
  100% { box-shadow: 0 0 0 0 rgba(36, 48, 86, 0); }
}
.highlight-pulse {
  outline: 2px solid #243056 !important;
  outline-offset: 4px;
  animation: voxDemoPulse 1.8s ease-out 2;
  border-radius: 12px;
  position: relative;
  z-index: 60 !important;
}
#${SPOTLIGHT_ID} {
  position: fixed;
  pointer-events: none;
  z-index: 55;
  transition: opacity 0.2s ease;
}
#${POINTER_ID} {
  position: fixed;
  width: 28px;
  height: 28px;
  margin-left: -4px;
  margin-top: -4px;
  border-radius: 50%;
  border: 2px solid #243056;
  background: rgba(36, 48, 86, 0.16);
  pointer-events: none;
  z-index: 70;
  box-shadow: 0 0 0 6px rgba(36, 48, 86, 0.12);
}
#${POINTER_ID}::after {
  content: "";
  position: absolute;
  left: 8px;
  top: 8px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #243056;
}
#${LABEL_ID} {
  position: fixed;
  z-index: 10001;
  max-width: min(280px, 72vw);
  padding: 12px 14px;
  border-radius: 16px;
  background: #fbf8f3;
  color: #2a241c;
  font: 600 13px/1.4 inherit, ui-sans-serif, system-ui, sans-serif;
  border: 1px solid rgba(36, 48, 86, 0.12);
  box-shadow: 0 14px 40px rgba(36, 48, 86, 0.16);
  pointer-events: auto;
}
#${LABEL_ID} .vox-demo-chip {
  display: inline-flex;
  align-items: center;
  background: #243056;
  color: #fbf8f3;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 4px 9px;
  border-radius: 999px;
  margin-bottom: 8px;
}
#${LABEL_ID} .vox-demo-title {
  display: block;
  font-size: 14px;
  font-weight: 700;
  color: #243056;
  letter-spacing: -0.01em;
}
#${LABEL_ID} .vox-demo-next {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-top: 10px;
  background: #243056;
  color: #fbf8f3;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 8px 14px;
  border-radius: 999px;
  border: none;
  cursor: pointer;
}
#${LABEL_ID} .vox-demo-hint {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  font-weight: 500;
  color: #5c534a;
  line-height: 1.35;
}
body.voxbulk-demo-click .driver-overlay {
  /* click mode: allow tapping the highlighted control */
}
.voxbulk-demo-popover {
  background: #fbf8f3 !important;
  color: #2a241c !important;
  border: 1px solid rgba(36, 48, 86, 0.12) !important;
  border-radius: 16px !important;
  box-shadow: 0 14px 40px rgba(36, 48, 86, 0.16) !important;
  padding: 12px 14px 14px !important;
  max-width: min(280px, 72vw) !important;
  font-family: inherit !important;
}
.voxbulk-demo-popover .driver-popover-title {
  font-size: 14px !important;
  font-weight: 700 !important;
  letter-spacing: -0.01em !important;
  text-transform: none !important;
  color: #243056 !important;
  margin-bottom: 2px !important;
  line-height: 1.3 !important;
}
.voxbulk-demo-popover-click .driver-popover-title {
  display: inline-flex !important;
  align-items: center !important;
  width: auto !important;
  background: #243056 !important;
  color: #fbf8f3 !important;
  font-size: 10px !important;
  font-weight: 700 !important;
  letter-spacing: 0.08em !important;
  text-transform: uppercase !important;
  padding: 4px 9px !important;
  border-radius: 999px !important;
  margin-bottom: 8px !important;
}
.voxbulk-demo-popover .driver-popover-description {
  font-size: 13px !important;
  font-weight: 600 !important;
  line-height: 1.4 !important;
  color: #2a241c !important;
}
.voxbulk-demo-popover-view .driver-popover-description {
  display: block !important;
  font-weight: 500 !important;
  color: #5c534a !important;
  margin-top: 6px !important;
}
.voxbulk-demo-popover-click .driver-popover-description {
  display: block !important;
}
.voxbulk-demo-popover .driver-popover-arrow-side-left .driver-popover-arrow,
.voxbulk-demo-popover .driver-popover-arrow-side-right .driver-popover-arrow,
.voxbulk-demo-popover .driver-popover-arrow-side-top .driver-popover-arrow,
.voxbulk-demo-popover .driver-popover-arrow-side-bottom .driver-popover-arrow {
  border-color: #fbf8f3 !important;
}
.voxbulk-demo-popover-click .driver-popover-footer,
.voxbulk-demo-popover-click .driver-popover-close-btn,
.voxbulk-demo-popover-click .driver-popover-navigation-btns,
.voxbulk-demo-popover-click .driver-popover-progress-text,
.voxbulk-demo-popover .driver-popover-close-btn,
.voxbulk-demo-popover .driver-popover-progress-text {
  display: none !important;
}
.voxbulk-demo-popover-view .driver-popover-footer {
  display: flex !important;
  justify-content: flex-end !important;
  margin-top: 12px !important;
  padding-top: 0 !important;
  border-top: none !important;
}
.voxbulk-demo-popover-view .driver-popover-navigation-btns {
  display: flex !important;
  gap: 8px !important;
}
.voxbulk-demo-popover-view .driver-popover-next-btn {
  background: #243056 !important;
  color: #fbf8f3 !important;
  border: none !important;
  border-radius: 999px !important;
  padding: 8px 16px !important;
  font-size: 12px !important;
  font-weight: 700 !important;
  letter-spacing: 0.04em !important;
  text-transform: uppercase !important;
  cursor: pointer !important;
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
  veil.style.opacity = "1";
  veil.style.background = "transparent";
  veil.style.boxShadow = `0 0 0 9999px rgba(26, 39, 68, 0.38)`;
  veil.style.top = `${top}px`;
  veil.style.left = `${left}px`;
  veil.style.width = `${rect.width + pad * 2}px`;
  veil.style.height = `${rect.height + pad * 2}px`;
  veil.style.borderRadius = "14px";
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

const VIEW_NEXT_HINT = "Click Next when you are ready — so we do not rush to the next topic.";

function placeLabel(el: HTMLElement, opts: DemoHighlightOptions) {
  ensureHighlightStyles();
  const intent = opts.intent || inferDemoHighlightIntent(opts.targetElementId);
  const text = String(opts.label || "").trim() || (intent === "click" ? "This control" : "This area");
  let node = document.getElementById(LABEL_ID);
  if (!node) {
    node = document.createElement("div");
    node.id = LABEL_ID;
    document.body.appendChild(node);
  }
  node.replaceChildren();
  if (intent === "click") {
    const chip = document.createElement("span");
    chip.className = "vox-demo-chip";
    chip.textContent = "Click here";
    node.appendChild(chip);
  }
  const title = document.createElement("span");
  title.className = "vox-demo-title";
  title.textContent = text;
  node.appendChild(title);
  if (intent === "view") {
    const hint = document.createElement("span");
    hint.className = "vox-demo-hint";
    hint.textContent = VIEW_NEXT_HINT;
    node.appendChild(hint);
    const next = document.createElement("button");
    next.type = "button";
    next.className = "vox-demo-next";
    next.textContent = "Next";
    next.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const id = String(opts.targetElementId || "").trim();
      clearDemoHighlight();
      if (id) opts.onClicked?.(id);
    });
    node.appendChild(next);
  }
  const rect = el.getBoundingClientRect();
  const preferBelow = rect.bottom + 96 < window.innerHeight;
  const top = preferBelow ? rect.bottom + 12 : Math.max(8, rect.top - 96);
  const left = Math.min(Math.max(8, rect.left), window.innerWidth - 240);
  node.style.opacity = "1";
  node.style.top = `${Math.round(top)}px`;
  node.style.left = `${Math.round(left)}px`;
}

function expandNavForTarget(el: HTMLElement) {
  const group = el.closest("[data-demo-nav-group]") as HTMLElement | null;
  if (!group) return;
  const closed = group.querySelector<HTMLElement>("[data-state='closed']") || group.closest("[data-state='closed']");
  if (!closed) return;
  const trigger = group.querySelector<HTMLElement>("[data-sidebar='group-label']");
  trigger?.click();
}

function unbindClick() {
  if (clickBoundEl && clickBoundHandler) {
    clickBoundEl.removeEventListener("click", clickBoundHandler, true);
  }
  clickBoundEl = null;
  clickBoundHandler = null;
}

function setDemoBodyMode(intent: DemoHighlightIntent | null) {
  if (typeof document === "undefined") return;
  document.body.classList.remove("voxbulk-demo-view", "voxbulk-demo-click");
  if (intent) document.body.classList.add(`voxbulk-demo-${intent}`);
}

export function clearDemoHighlight() {
  highlightEpoch += 1;
  unbindClick();
  try {
    driverHandle?.destroy();
  } catch {
    /* ignore */
  }
  driverHandle = null;
  setDemoBodyMode(null);
  document.querySelectorAll(".driver-overlay, .driver-popover, .driver-active").forEach((n) => {
    try {
      n.remove();
    } catch {
      /* ignore */
    }
  });
  document.getElementById(SPOTLIGHT_ID)?.remove();
  document.getElementById(POINTER_ID)?.remove();
  document.getElementById(LABEL_ID)?.remove();
}

function bindClickOnce(el: HTMLElement, id: string, opts: DemoHighlightOptions) {
  unbindClick();
  clickBoundHandler = () => {
    unbindClick();
    clearDemoHighlight();
    opts.onClicked?.(id);
  };
  clickBoundEl = el;
  el.addEventListener("click", clickBoundHandler, true);
}

function fallbackHighlight(el: HTMLElement, opts: DemoHighlightOptions) {
  const intent = opts.intent || inferDemoHighlightIntent(opts.targetElementId);
  ensureHighlightStyles();
  el.classList.remove("highlight-pulse");
  void el.offsetWidth;
  el.classList.add("highlight-pulse");
  placeSpotlight(el);
  if (intent === "click" && opts.pointer !== false) placePointer(el);
  placeLabel(el, { ...opts, intent });
}

async function highlightWithDriver(el: HTMLElement, opts: DemoHighlightOptions, epoch: number) {
  const intent = opts.intent || inferDemoHighlightIntent(opts.targetElementId);
  const [{ driver }] = await Promise.all([
    import("driver.js"),
    import("driver.js/dist/driver.css"),
  ]);
  if (epoch !== highlightEpoch) return;
  try {
    driverHandle?.destroy();
  } catch {
    /* ignore */
  }
  if (epoch !== highlightEpoch) return;
  ensureHighlightStyles();
  setDemoBodyMode(intent);
  const label = String(opts.label || "").trim();
  const targetId = String(opts.targetElementId || "").trim();
  const finishViewNext = () => {
    clearDemoHighlight();
    if (targetId) opts.onClicked?.(targetId);
  };
  const inst = driver({
    overlayColor: "#1a2744",
    overlayOpacity: 0.42,
    stagePadding: 8,
    stageRadius: 14,
    popoverOffset: 14,
    popoverClass: `voxbulk-demo-popover voxbulk-demo-popover-${intent}`,
    allowClose: false,
    disableActiveInteraction: intent === "view",
    showButtons: intent === "view" ? ["next"] : [],
    nextBtnText: "Next",
    overlayClickBehavior: intent === "click" ? "close" : () => undefined,
    onDestroyed: () => {
      if (driverHandle === inst) driverHandle = null;
    },
  });
  inst.highlight({
    element: el,
    popover: {
      title: intent === "click" ? "Click here" : label || "Look here",
      description:
        intent === "click"
          ? label || "Tap this"
          : VIEW_NEXT_HINT,
      showButtons: intent === "view" ? ["next"] : [],
      nextBtnText: "Next",
      side: "right",
      align: "start",
      onNextClick: intent === "view" ? finishViewNext : undefined,
    },
  });
  driverHandle = inst;
  const watch = () => {
    if (epoch !== highlightEpoch || driverHandle !== inst) return;
    if (!el.isConnected) {
      clearDemoHighlight();
      return;
    }
    window.requestAnimationFrame(watch);
  };
  window.requestAnimationFrame(watch);
}

export function applyDemoHighlight(opts: DemoHighlightOptions) {
  if (typeof document === "undefined") return false;
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
  const intent = opts.intent || inferDemoHighlightIntent(id);
  const clickMode = intent === "click";
  expandNavForTarget(el);
  try {
    el.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
  } catch {
    /* ignore */
  }
  clearDemoHighlight();
  const epoch = highlightEpoch;
  setDemoBodyMode(intent);
  if (clickMode) bindClickOnce(el, id, opts);
  void highlightWithDriver(el, { ...opts, intent }, epoch).catch(() => {
    if (epoch !== highlightEpoch) return;
    fallbackHighlight(el, { ...opts, intent });
  });
  // VIEW waits for Next; CLICK waits for the highlighted control.
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
