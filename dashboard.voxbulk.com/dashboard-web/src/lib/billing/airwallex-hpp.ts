export const AWX_PENDING_KEY = "voxbulk_awx_pending";

export type AirwallexPending = {
  flow: "wallet" | "invoice" | "subscription";
  payment_intent_id: string;
  invoice_id?: string;
};

const loadedScripts: Record<string, Promise<void>> = {};

function loadScript(src: string): Promise<void> {
  if (!loadedScripts[src]) {
    loadedScripts[src] = new Promise<void>((resolve, reject) => {
      const tag = document.createElement("script");
      tag.src = src;
      tag.async = true;
      tag.onload = () => resolve();
      tag.onerror = () => reject(new Error(`Failed to load ${src}`));
      document.head.appendChild(tag);
    });
  }
  return loadedScripts[src];
}

type AirwallexRedirectJs = {
  init: (opts: { env: string; origin: string }) => void;
  redirectToCheckout: (opts: Record<string, unknown>) => void;
};

declare global {
  interface Window {
    Airwallex?: AirwallexRedirectJs;
  }
}

export function storeAirwallexPending(pending: AirwallexPending) {
  sessionStorage.setItem(AWX_PENDING_KEY, JSON.stringify(pending));
}

export function readAirwallexPending(): AirwallexPending | null {
  try {
    const raw = sessionStorage.getItem(AWX_PENDING_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AirwallexPending;
    if (!parsed?.payment_intent_id || !parsed?.flow) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function clearAirwallexPending() {
  try {
    sessionStorage.removeItem(AWX_PENDING_KEY);
  } catch {
    /* ignore */
  }
}

export function airwallexReturnUrl(outcome: "success" | "cancelled", returnPath = "/account/billing") {
  const url = new URL(returnPath, window.location.origin);
  url.searchParams.set("billing", outcome === "success" ? "airwallex_success" : "airwallex_cancelled");
  return url.href;
}

export async function redirectToAirwallexHostedCheckout(opts: {
  intent_id: string;
  client_secret: string;
  currency: string;
  environment: string;
  pending: AirwallexPending;
  returnPath?: string;
}) {
  await loadScript("https://checkout.airwallex.com/assets/elements.bundle.min.js");
  const awx = window.Airwallex;
  if (!awx?.redirectToCheckout) {
    throw new Error("Airwallex hosted checkout is not available");
  }
  storeAirwallexPending(opts.pending);
  const env = String(opts.environment || "demo");
  const returnPath = opts.returnPath || "/account/billing";
  awx.init({ env, origin: window.location.origin });
  awx.redirectToCheckout({
    env,
    mode: "payment",
    currency: opts.currency,
    intent_id: opts.intent_id,
    client_secret: opts.client_secret,
    successUrl: airwallexReturnUrl("success", returnPath),
    cancelUrl: airwallexReturnUrl("cancelled", returnPath),
  });
}
