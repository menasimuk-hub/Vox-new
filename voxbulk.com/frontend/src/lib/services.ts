export type MarketingServiceId =
  | "recruitment"
  | "ai_interviews"
  | "whatsapp_surveys"
  | "ai_calling"
  | "ats"
  | "customer_success"
  | "voxbulk_expo";

export type BackendServiceKey = "interview" | "survey" | "recovery" | "follow_up" | "expo";

/** Opt-in products that should stay visible in onboarding even when not yet admin-granted. */
const ONBOARDING_ALWAYS_VISIBLE: ReadonlySet<MarketingServiceId> = new Set(["voxbulk_expo"]);

export const MARKETING_SERVICES: {
  id: MarketingServiceId;
  label: string;
  desc: string;
  backendKey: BackendServiceKey;
}[] = [
  { id: "ai_interviews", label: "AI interview screening", desc: "Score skills, comms and fit", backendKey: "interview" },
  { id: "whatsapp_surveys", label: "WhatsApp surveys", desc: "98% open rates, instant replies", backendKey: "survey" },
  { id: "ai_calling", label: "AI calling survey", desc: "Voice agents on autopilot", backendKey: "survey" },
  { id: "ats", label: "ATS & CV scanning", desc: "Bulk parsing, ranking, scoring", backendKey: "interview" },
  { id: "recruitment", label: "Recruitment automation", desc: "CV screening, scheduling, hiring", backendKey: "recovery" },
  { id: "customer_success", label: "Customer success", desc: "Onboarding, check-ins, retention", backendKey: "follow_up" },
  { id: "voxbulk_expo", label: "VoxBulk Expo", desc: "Booth QR & WhatsApp lead capture", backendKey: "expo" },
];

export function allowedMarketingServices(allowed?: Record<string, boolean> | null) {
  if (!allowed) return MARKETING_SERVICES;
  return MARKETING_SERVICES.filter(
    (s) => ONBOARDING_ALWAYS_VISIBLE.has(s.id) || allowed[s.backendKey] !== false,
  );
}

export function marketingSelectionToEnabled(
  selected: MarketingServiceId[],
  allowed?: Record<string, boolean> | null,
): Record<BackendServiceKey, boolean> {
  const out: Record<BackendServiceKey, boolean> = {
    interview: false,
    survey: false,
    recovery: false,
    follow_up: false,
    expo: false,
  };
  for (const svc of MARKETING_SERVICES) {
    if (!selected.includes(svc.id)) continue;
    // Expo is self-serve during company setup — still send enable even if not yet granted.
    if (svc.id !== "voxbulk_expo" && allowed && allowed[svc.backendKey] === false) continue;
    out[svc.backendKey] = true;
  }
  if (!Object.values(out).some(Boolean)) {
    const first = allowedMarketingServices(allowed)[0];
    if (first) out[first.backendKey] = true;
  }
  return out;
}
