import type { FeedbackSubscription } from "@/lib/queries";

export function feedbackWebMode(sub?: FeedbackSubscription | null): "shared" | "none" | "separate" {
  const mode = String(sub?.web_mode || "").toLowerCase();
  if (mode === "shared" || mode === "none" || mode === "separate") return mode;
  const web = Number(sub?.web_units_included ?? 0);
  if (web < 0) return "shared";
  if (web === 0) return "none";
  return "separate";
}

export function feedbackRemainingSummary(sub?: FeedbackSubscription | null): string {
  const mode = feedbackWebMode(sub);
  if (mode === "shared") {
    const remaining = Math.max(0, Number(sub?.survey_units_remaining ?? sub?.wa_units_remaining ?? 0));
    return `${remaining.toLocaleString()} surveys remaining this month (WhatsApp or web)`;
  }
  if (mode === "none") {
    const remaining = Math.max(0, Number(sub?.wa_units_remaining ?? 0));
    return `${remaining.toLocaleString()} WhatsApp surveys remaining this month`;
  }
  const waRem = Math.max(0, Number(sub?.wa_units_remaining ?? 0));
  const webRem = Math.max(0, Number(sub?.web_units_remaining ?? 0));
  return `${waRem.toLocaleString()} WA · ${webRem.toLocaleString()} web remaining this month`;
}
