export type MarketingServiceId =
  | "recruitment"
  | "ai_interviews"
  | "whatsapp_surveys"
  | "ai_calling"
  | "ats"
  | "customer_success";

export type BackendServiceKey = "interview" | "survey" | "recovery" | "follow_up";

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
];

export function allowedMarketingServices(allowed?: Record<string, boolean> | null) {
  if (!allowed) return MARKETING_SERVICES;
  return MARKETING_SERVICES.filter((s) => allowed[s.backendKey] !== false);
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
  };
  for (const svc of MARKETING_SERVICES) {
    if (!selected.includes(svc.id)) continue;
    if (allowed && allowed[svc.backendKey] === false) continue;
    out[svc.backendKey] = true;
  }
  if (!Object.values(out).some(Boolean)) {
    const first = allowedMarketingServices(allowed)[0];
    if (first) out[first.backendKey] = true;
  }
  return out;
}
