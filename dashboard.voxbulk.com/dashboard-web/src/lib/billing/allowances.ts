import type { LucideIcon } from "lucide-react";

export type AllowanceRow = {
  product: "core" | "feedback" | string;
  key: string;
  label: string;
  used: number;
  included: number;
  remaining: number | null;
  unit: string;
  unlimited?: boolean;
  period_start?: string | null;
  period_end?: string | null;
  pct_used?: number;
  shared_pool?: boolean;
};

export type AllowanceAlert = {
  product?: string;
  key?: string;
  level: "warning" | "critical" | string;
  message: string;
  pct_used?: number;
};

export type BillingSnapshot = {
  has_core_subscription?: boolean;
  is_payg?: boolean;
  shared_package_pool?: boolean;
  value_pool_active?: boolean;
  package_used_display?: string;
  package_included_display?: string;
  package_remaining_display?: string;
  wallet_balance_display?: string;
  wallet_balance_pence?: number;
};

export function formatAllowancePeriod(start?: string | null, end?: string | null) {
  const fmt = (raw: string) => {
    const d = new Date(raw);
    return Number.isNaN(d.getTime())
      ? raw
      : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  };
  if (start && end) return `${fmt(start)} – ${fmt(end)}`;
  if (end) return `Until ${fmt(end)}`;
  if (start) return `From ${fmt(start)}`;
  return "";
}

export function formatRemaining(row: AllowanceRow) {
  if (row.unlimited) return "Unlimited";
  if (row.included <= 0) return "Pay per use";
  return String(row.remaining ?? Math.max(0, row.included - row.used));
}

export function groupAllowancesByProduct(allowances: AllowanceRow[]) {
  const core = allowances.filter((a) => a.product === "core");
  const feedback = allowances.filter((a) => a.product === "feedback");
  return { core, feedback };
}

export function corePanelKeys(sharedPool?: boolean) {
  if (sharedPool) return ["calls", "whatsapp"] as const;
  return ["calls", "whatsapp", "cv_scans"] as const;
}

export function pickAllowances(rows: AllowanceRow[], keys: readonly string[]) {
  return keys.map((k) => rows.find((r) => r.key === k)).filter(Boolean) as AllowanceRow[];
}

export type ProductPanelMeta = {
  product: "core" | "feedback";
  title: string;
  tintClass: string;
  ringClass: string;
  badgeClass: string;
  usageLink: string;
  packagesLink: string;
  packagesSearch?: Record<string, string>;
};

export const PRODUCT_PANEL_META: Record<"core" | "feedback", ProductPanelMeta> = {
  core: {
    product: "core",
    title: "Core platform",
    tintClass: "border-primary/20 bg-primary/5",
    ringClass: "ring-primary/20",
    badgeClass: "bg-primary/15 text-primary border-primary/30",
    usageLink: "/account/usage",
    packagesLink: "/account/packages",
    packagesSearch: { tab: "core" },
  },
  feedback: {
    product: "feedback",
    title: "Customer Feedback",
    tintClass: "border-success/20 bg-success/5",
    ringClass: "ring-success/20",
    badgeClass: "bg-success/15 text-success border-success/30",
    usageLink: "/account/usage",
    packagesLink: "/account/packages",
    packagesSearch: { tab: "feedback" },
  },
};

export type AllowanceIconMap = Record<string, LucideIcon>;
