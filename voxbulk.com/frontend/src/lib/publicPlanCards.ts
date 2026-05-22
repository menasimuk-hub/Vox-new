import { fetchPublicPlans } from "@/lib/retoverApi";

export type PublicPlanRow = {
  id?: string;
  code: string;
  name: string;
  price_gbp_pence?: number;
  description?: string | null;
  features_json?: string | null;
  calls_included?: number;
  whatsapp_included?: number;
  sms_included?: number;
  overage_per_min_pence?: number;
  trial_days_default?: number;
  sort_order?: number;
};

export type MarketingPlanCard = {
  code: string;
  name: string;
  who: string;
  base: string;
  incl: string;
  extra: string;
  calls: string;
  trial: string;
  featured: boolean;
  features: string[];
  cta: string;
  ctaStyle: "primary" | "outline";
  signupHref: string;
};

const FALLBACK_PLANS: MarketingPlanCard[] = [
  {
    code: "solo",
    name: "Solo",
    who: "1–2 dentists",
    base: "£99",
    incl: "Includes 1 dentist",
    extra: "+ £49/mo per extra dentist",
    calls: "100 calls included",
    trial: "14-day free trial",
    featured: false,
    features: [
      "1 branch",
      "WhatsApp messaging",
      "Cancellation recovery",
      "Basic dashboard",
      "Dentally integration",
      "Email support",
    ],
    cta: "Start free trial",
    ctaStyle: "outline",
    signupHref: "/signin?mode=signup",
  },
  {
    code: "practice",
    name: "Practice",
    who: "3–6 dentists · Most popular",
    base: "£199",
    incl: "Includes 3 dentists",
    extra: "+ £49/mo per extra dentist",
    calls: "200 calls included",
    trial: "14-day free trial",
    featured: true,
    features: [
      "Up to 3 branches",
      "WhatsApp messaging",
      "No-show follow-up",
      "Full dashboard + PDF reports",
      "Team up to 10",
      "Priority support",
      "Dentally integration",
    ],
    cta: "Start free trial",
    ctaStyle: "primary",
    signupHref: "/signin?mode=signup",
  },
  {
    code: "group",
    name: "Group",
    who: "7+ dentists · Multi-site",
    base: "£399",
    incl: "Includes 7 dentists",
    extra: "+ £49/mo per extra dentist",
    calls: "400 calls included",
    trial: "30-day free trial",
    featured: false,
    features: [
      "Unlimited branches",
      "Custom call scripts",
      "Advanced analytics",
      "Account manager",
      "SLA guarantee",
      "API access",
    ],
    cta: "Book a demo",
    ctaStyle: "outline",
    signupHref: "#demo",
  },
];

function fmtGbp(pence: number): string {
  const pounds = Number(pence || 0) / 100;
  return pounds % 1 === 0 ? `£${pounds.toFixed(0)}` : `£${pounds.toFixed(2)}`;
}

function parseFeatures(plan: PublicPlanRow): string[] {
  try {
    const parsed = JSON.parse(plan.features_json || "[]");
    if (Array.isArray(parsed) && parsed.length) {
      return parsed.map(String);
    }
  } catch {
    /* ignore */
  }
  const out: string[] = [];
  if (plan.calls_included) out.push(`${plan.calls_included} AI calls / month`);
  if (plan.whatsapp_included) out.push(`${plan.whatsapp_included} WhatsApp / month`);
  if (plan.sms_included) out.push(`${plan.sms_included} SMS / month`);
  if (plan.overage_per_min_pence) {
    out.push(`${fmtGbp(plan.overage_per_min_pence)}/min overage after included usage`);
  }
  return out.length ? out : ["Recovery queue", "WhatsApp reminders", "Usage wallet"];
}

export function mapPublicPlanToCard(plan: PublicPlanRow, index: number, total: number): MarketingPlanCard {
  const trialDays = Number(plan.trial_days_default || 0);
  const featured = total >= 3 ? index === 1 : index === 0;
  const calls = Number(plan.calls_included || 0);
  const wa = Number(plan.whatsapp_included || 0);
  const sms = Number(plan.sms_included || 0);
  const parts: string[] = [];
  if (calls) parts.push(`${calls} calls`);
  if (wa) parts.push(`${wa} WhatsApp`);
  if (sms) parts.push(`${sms} SMS`);

  return {
    code: plan.code,
    name: plan.name,
    who: (plan.description || plan.code || "").trim() || "Monthly subscription",
    base: fmtGbp(Number(plan.price_gbp_pence || 0)),
    incl: parts.length ? `Includes ${parts.join(" · ")}` : "Monthly platform access",
    extra:
      plan.overage_per_min_pence && Number(plan.overage_per_min_pence) > 0
        ? `Overage ${fmtGbp(Number(plan.overage_per_min_pence))}/min after included usage`
        : "Transparent overage billing",
    calls: calls ? `${calls} calls included` : "Usage-based calling",
    trial: trialDays > 0 ? `${trialDays}-day free trial` : "No setup fee",
    featured,
    features: parseFeatures(plan),
    cta: trialDays > 0 ? "Start free trial" : "Get started",
    ctaStyle: featured ? "primary" : "outline",
    signupHref: "/signin?mode=signup",
  };
}

export function mapPublicPlansToCards(rows: PublicPlanRow[]): MarketingPlanCard[] {
  const sorted = [...rows].sort(
    (a, b) =>
      Number(a.sort_order ?? 100) - Number(b.sort_order ?? 100) ||
      Number(a.price_gbp_pence || 0) - Number(b.price_gbp_pence || 0),
  );
  if (!sorted.length) return FALLBACK_PLANS;
  return sorted.map((plan, index) => mapPublicPlanToCard(plan, index, sorted.length));
}

export async function loadMarketingPlanCards(): Promise<MarketingPlanCard[]> {
  try {
    const rows = (await fetchPublicPlans()) as PublicPlanRow[];
    return mapPublicPlansToCards(Array.isArray(rows) ? rows : []);
  } catch {
    return FALLBACK_PLANS;
  }
}

export function overageFootnote(cards: MarketingPlanCard[], rows: PublicPlanRow[]): string {
  const overageRates = [...new Set(rows.map((r) => Number(r.overage_per_min_pence || 0)).filter((n) => n > 0))];
  if (overageRates.length) {
    const bits = overageRates.map((p) => fmtGbp(p)).join(" – ");
    return `Overage calls billed at ${bits}/min after included usage · WhatsApp & SMS counted against plan allowances`;
  }
  return "Overage calls: £0.18 · WhatsApp conversations: £0.08 · Extra branch: £49/mo";
}
