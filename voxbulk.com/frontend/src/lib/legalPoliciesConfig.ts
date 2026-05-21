export const LEGAL_TAB_IDS = ["terms", "privacy", "cookies", "gdpr", "legal"] as const;

export type LegalTabId = (typeof LEGAL_TAB_IDS)[number];

export const LEGAL_TAB_LABELS: Record<LegalTabId, string> = {
  terms: "Terms & Conditions",
  privacy: "Privacy Policy",
  cookies: "Cookie Policy",
  gdpr: "GDPR",
  legal: "Legal",
};

export function isLegalTabId(value: unknown): value is LegalTabId {
  return typeof value === "string" && LEGAL_TAB_IDS.includes(value as LegalTabId);
}

export function legalPoliciesPublicUrl(tab: LegalTabId = "terms") {
  return `/legal-policies?tab=${tab}`;
}
