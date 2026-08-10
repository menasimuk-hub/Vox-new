/** Onboarding + marketing service catalog for public signup wizard. */

import type { ProductVisibilityPayload } from "@/lib/product-visibility";

export type OnboardingProductId =
  | "recruitment"
  | "surveys"
  | "feedback"
  | "expo"
  | "smart_card";

/** Backend enabled_services / allowed_services keys. */
export type BackendServiceKey =
  | "interview"
  | "survey"
  | "customer_feedback"
  | "feedback_campaigns"
  | "expo"
  | "smart_card"
  | "appointments"
  | "recovery"
  | "follow_up"
  | "campaigns";

/** @deprecated Use OnboardingProductId — kept for any older imports. */
export type MarketingServiceId = OnboardingProductId;

export type OnboardingProduct = {
  id: OnboardingProductId;
  label: string;
  desc: string;
  visibilityKey: string;
  /** Primary org module keys toggled when this card is selected. */
  backendKeys: BackendServiceKey[];
};

export const ONBOARDING_PRODUCTS: OnboardingProduct[] = [
  {
    id: "recruitment",
    label: "Recruitment & AI interviews",
    desc: "Screen candidates by voice, score fit, and speed up hiring.",
    visibilityKey: "interview",
    backendKeys: ["interview", "recovery"],
  },
  {
    id: "surveys",
    label: "WhatsApp & AI surveys",
    desc: "Run WhatsApp or voice surveys with high open rates.",
    visibilityKey: "survey",
    backendKeys: ["survey"],
  },
  {
    id: "feedback",
    label: "Customer Feedback",
    desc: "QR and WhatsApp feedback for venues, with follow-up.",
    visibilityKey: "customer_feedback",
    backendKeys: ["customer_feedback"],
  },
  {
    id: "expo",
    label: "VoxBulk Expo",
    desc: "Booth QR and WhatsApp lead capture for events.",
    visibilityKey: "expo",
    backendKeys: ["expo"],
  },
  {
    id: "smart_card",
    label: "Smart Card",
    desc: "Digital business cards with lead capture for teams.",
    visibilityKey: "smart_card",
    backendKeys: ["smart_card"],
  },
];

/** Legacy alias — same product cards. */
export const MARKETING_SERVICES = ONBOARDING_PRODUCTS.map((p) => ({
  id: p.id,
  label: p.label,
  desc: p.desc,
  backendKey: p.backendKeys[0] as BackendServiceKey,
}));

function isVisibilityKeyEnabled(vis: ProductVisibilityPayload | null | undefined, key: string): boolean {
  if (!vis?.enabled_keys?.length) return true;
  return vis.enabled_keys.includes(key);
}

function isOrgAllowed(allowed: Record<string, boolean> | null | undefined, keys: BackendServiceKey[]): boolean {
  if (!allowed) return true;
  // Visible if any mapped backend key is not explicitly denied.
  return keys.some((k) => allowed[k] !== false);
}

/**
 * Products shown on signup: platform-active (product visibility) and not org-denied.
 * Expo stays visible for self-serve opt-in even when not yet granted.
 */
export function activeOnboardingProducts(
  vis?: ProductVisibilityPayload | null,
  allowed?: Record<string, boolean> | null,
): OnboardingProduct[] {
  return ONBOARDING_PRODUCTS.filter((p) => {
    if (!isVisibilityKeyEnabled(vis, p.visibilityKey)) return false;
    if (p.id === "expo") return true;
    return isOrgAllowed(allowed, p.backendKeys);
  });
}

/** @deprecated Prefer activeOnboardingProducts(vis, allowed). */
export function allowedMarketingServices(allowed?: Record<string, boolean> | null) {
  return activeOnboardingProducts(null, allowed);
}

export function selectionToEnabledServices(
  selected: OnboardingProductId[],
  allowed?: Record<string, boolean> | null,
  available?: OnboardingProduct[],
): Record<string, boolean> {
  const catalog = available?.length ? available : ONBOARDING_PRODUCTS;
  const out: Record<string, boolean> = {
    interview: false,
    survey: false,
    customer_feedback: false,
    feedback_campaigns: false,
    expo: false,
    smart_card: false,
    appointments: false,
    recovery: false,
    follow_up: false,
    campaigns: false,
  };

  for (const product of catalog) {
    if (!selected.includes(product.id)) continue;
    for (const key of product.backendKeys) {
      if (product.id !== "expo" && allowed && allowed[key] === false) continue;
      out[key] = true;
    }
  }

  if (!Object.values(out).some(Boolean)) {
    const first = catalog[0];
    if (first) {
      for (const key of first.backendKeys) out[key] = true;
    }
  }
  return out;
}

/** @deprecated Prefer selectionToEnabledServices. */
export function marketingSelectionToEnabled(
  selected: OnboardingProductId[],
  allowed?: Record<string, boolean> | null,
): Record<string, boolean> {
  return selectionToEnabledServices(selected, allowed);
}
