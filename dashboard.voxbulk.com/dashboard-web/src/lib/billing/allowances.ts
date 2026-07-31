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
  product: "core" | "feedback" | "smart_card";
  title: string;
  tintClass: string;
  ringClass: string;
  badgeClass: string;
  usageLink: string;
  packagesLink: string;
  packagesSearch?: Record<string, string>;
};

export const PRODUCT_PANEL_META: Record<"core" | "feedback" | "smart_card", ProductPanelMeta> = {
  core: {
    product: "core",
    title: "Core platform",
    tintClass: "border-sky-200 bg-sky-50/80 dark:border-sky-900/40 dark:bg-sky-950/30",
    ringClass: "ring-sky-200/70 dark:ring-sky-800/40",
    badgeClass: "bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-200",
    usageLink: "/account/usage",
    packagesLink: "/account/packages",
    packagesSearch: { tab: "core" },
  },
  feedback: {
    product: "feedback",
    title: "Customer Feedback",
    tintClass: "border-emerald-200 bg-emerald-50/80 dark:border-emerald-900/40 dark:bg-emerald-950/30",
    ringClass: "ring-emerald-200/70 dark:ring-emerald-800/40",
    badgeClass: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200",
    usageLink: "/account/usage",
    packagesLink: "/account/feedback/packages",
  },
  smart_card: {
    product: "smart_card",
    title: "Smart Card QR",
    tintClass: "border-violet-200 bg-violet-50/80 dark:border-violet-900/40 dark:bg-violet-950/30",
    ringClass: "ring-violet-200/70 dark:ring-violet-800/40",
    badgeClass: "bg-violet-100 text-violet-800 dark:bg-violet-900/50 dark:text-violet-200",
    usageLink: "/account/usage",
    packagesLink: "/account/smart-card/packages",
  },
};

export type AllowanceIconMap = Record<string, LucideIcon>;
