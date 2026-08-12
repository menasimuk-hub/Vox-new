export type DemoHighlightIntent = "view" | "click";

const CLICK_PREFIXES = ["nav-", "results-", "packages-", "wizard-next"];

export function inferDemoHighlightIntent(target: string | null | undefined): DemoHighlightIntent {
  const id = String(target || "").trim().toLowerCase();
  if (!id) return "view";
  if (CLICK_PREFIXES.some((p) => id.startsWith(p))) return "click";
  return "view";
}

export function parseDemoRoute(route: string): { pathname: string; search: Record<string, string> } {
  const raw = String(route || "/").trim() || "/";
  try {
    const url = new URL(raw, "https://dashboard.voxbulk.com");
    const search: Record<string, string> = {};
    url.searchParams.forEach((v, k) => {
      search[k] = v;
    });
    return { pathname: url.pathname || "/", search };
  } catch {
    return { pathname: raw.startsWith("/") ? raw : `/${raw}`, search: {} };
  }
}

type HighlightOpts = {
  targetElementId: string | null;
  pointer?: boolean;
  label?: string | null;
  warnMissing?: boolean;
  intent?: DemoHighlightIntent;
  persistUntilClick?: boolean;
  showNext?: boolean;
  onClicked?: (target: string) => void;
};

const CHIP_ID = "voxbulk-demo-coach-chip";
const OUTLINE_CLASS = "voxbulk-demo-outline";
const STYLE_ID = "voxbulk-demo-outline-style";
const TAB_ROW_Y = 140;
const CHIP_MAX_W = 240;

let chipEl: HTMLDivElement | null = null;
let outlinedEl: HTMLElement | null = null;
let clickCleanup: (() => void) | null = null;
let retryTimer: number | null = null;
let retryGeneration = 0;
let chipReposition: (() => void) | null = null;

function ensureOutlineStyle() {
  if (typeof document === "undefined") return;
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .${OUTLINE_CLASS} {
      outline: 2px solid #1e3a5f !important;
      outline-offset: 4px !important;
      border-radius: 10px;
    }
  `;
  document.head.appendChild(style);
}

function stripDriverLeftovers() {
  if (typeof document === "undefined") return;
  document.querySelectorAll(".driver-overlay, .driver-popover, .driver-active-element").forEach((n) => {
    try {
      n.remove();
    } catch {
      /* ignore */
    }
  });
  document.body.classList.remove("driver-active");
  document.documentElement.classList.remove("driver-active");
}

function removeChip() {
  try {
    chipEl?.remove();
  } catch {
    /* ignore */
  }
  chipEl = null;
}

function clearOutline() {
  try {
    outlinedEl?.classList.remove(OUTLINE_CLASS);
  } catch {
    /* ignore */
  }
  outlinedEl = null;
}

export function clearDemoHighlight() {
  retryGeneration += 1;
  if (retryTimer != null) {
    window.clearTimeout(retryTimer);
    retryTimer = null;
  }
  clickCleanup?.();
  clickCleanup = null;
  if (chipReposition) {
    window.removeEventListener("resize", chipReposition);
    window.removeEventListener("scroll", chipReposition, true);
    chipReposition = null;
  }
  stripDriverLeftovers();
  removeChip();
  clearOutline();
}

function findTarget(id: string): HTMLElement | null {
  if (!id || typeof document === "undefined") return null;
  return document.querySelector(`[data-demo-target="${CSS.escape(id)}"]`);
}

function placeChip(chip: HTMLDivElement, target: HTMLElement) {
  const rect = target.getBoundingClientRect();
  const chipH = chip.offsetHeight || 72;
  const chipW = Math.min(CHIP_MAX_W, chip.offsetWidth || CHIP_MAX_W);
  const spaceBelow = window.innerHeight - rect.bottom;
  const inTabRow = rect.top < TAB_ROW_Y;
  const preferBelow = spaceBelow >= chipH + 12 || inTabRow;
  let top = preferBelow ? rect.bottom + 8 : rect.top - chipH - 8;
  if (top < 8) top = 8;
  if (top + chipH > window.innerHeight - 8) top = Math.max(8, window.innerHeight - chipH - 8);
  let left = rect.left;
  if (left + chipW > window.innerWidth - 8) left = Math.max(8, window.innerWidth - chipW - 8);
  if (left < 8) left = 8;
  chip.style.top = `${Math.round(top)}px`;
  chip.style.left = `${Math.round(left)}px`;
}

function bindClick(el: HTMLElement, targetId: string, onClicked?: (t: string) => void) {
  clickCleanup?.();
  const handler = () => {
    clickCleanup?.();
    clickCleanup = null;
    onClicked?.(targetId);
  };
  el.addEventListener("click", handler, { once: true, capture: true });
  clickCleanup = () => el.removeEventListener("click", handler, true);
}

function applyOutlineAndChip(opts: HighlightOpts, el: HTMLElement) {
  ensureOutlineStyle();
  stripDriverLeftovers();
  clearOutline();
  removeChip();
  el.classList.add(OUTLINE_CLASS);
  outlinedEl = el;
  try {
    el.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
  } catch {
    /* ignore */
  }

  const intent = opts.intent || inferDemoHighlightIntent(opts.targetElementId);
  const showNext = opts.showNext === true && intent === "view";
  const label = String(opts.label || opts.targetElementId || "").trim() || (intent === "click" ? "Click here" : "Look here");

  const chip = document.createElement("div");
  chip.id = CHIP_ID;
  chip.setAttribute("data-demo-chip", intent);
  chip.style.cssText = [
    "position:fixed",
    `max-width:${CHIP_MAX_W}px`,
    "z-index:70",
    "pointer-events:none",
    "border-radius:12px",
    "border:1px solid #e8dfd2",
    "background:#f7f1e8",
    "color:#1e3a5f",
    "box-shadow:0 8px 24px rgba(30,58,95,0.16)",
    "padding:8px 10px",
    "font:600 12px/1.35 ui-sans-serif,system-ui,sans-serif",
  ].join(";");

  const title = document.createElement("div");
  title.textContent = intent === "click" ? "Click here" : label;
  title.style.cssText = "font-weight:700;letter-spacing:0.01em;";
  chip.appendChild(title);

  if (intent === "click" && label && label.toLowerCase() !== "click here") {
    const sub = document.createElement("div");
    sub.textContent = label;
    sub.style.cssText = "margin-top:2px;font-weight:600;font-size:11px;color:#5c5346;";
    chip.appendChild(sub);
  }

  if (showNext) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = "Next";
    btn.style.cssText = [
      "margin-top:8px",
      "pointer-events:auto",
      "cursor:pointer",
      "border:0",
      "border-radius:999px",
      "background:#1e3a5f",
      "color:#f7f1e8",
      "font:700 11px/1 ui-sans-serif,system-ui,sans-serif",
      "padding:7px 14px",
    ].join(";");
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      opts.onClicked?.(String(opts.targetElementId || ""));
    });
    chip.appendChild(btn);
  }

  document.body.appendChild(chip);
  chipEl = chip;
  placeChip(chip, el);
  const reposition = () => {
    if (chipEl && outlinedEl) placeChip(chipEl, outlinedEl);
  };
  chipReposition = reposition;
  window.addEventListener("resize", reposition);
  window.addEventListener("scroll", reposition, true);

  if (intent === "click") {
    bindClick(el, String(opts.targetElementId || ""), opts.onClicked);
  }
}

/**
 * Keep retrying until `[data-demo-target]` exists. Cancel only when a newer
 * highlight is scheduled (generation bump) — no fixed give-up timer.
 */
export function scheduleDemoHighlight(opts: HighlightOpts, delayMs = 0) {
  const id = String(opts.targetElementId || "").trim();
  if (!id) return;
  retryGeneration += 1;
  const gen = retryGeneration;
  if (retryTimer != null) {
    window.clearTimeout(retryTimer);
    retryTimer = null;
  }
  clickCleanup?.();
  clickCleanup = null;

  const attempt = () => {
    if (gen !== retryGeneration) return;
    const el = findTarget(id);
    if (el) {
      applyOutlineAndChip(opts, el);
      return;
    }
    if (opts.warnMissing) {
      /* keep waiting — route/DOM may still be painting */
    }
    retryTimer = window.setTimeout(attempt, 180);
  };

  retryTimer = window.setTimeout(attempt, Math.max(0, delayMs));
}
