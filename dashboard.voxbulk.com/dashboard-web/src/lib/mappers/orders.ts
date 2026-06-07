import type { BadgeTone } from "@/components/status-badge";
import type { Campaign, CampaignTone, CampaignType } from "@/lib/types/campaign";
import type { ServiceOrder } from "@/lib/types/api";
import { firstStepLabelFromConfig, sanitizeStepLabelFromApi } from "@/lib/survey-step-labels";

function formatRelativeTime(iso?: string | null) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const diffMs = Date.now() - d.getTime();
    const mins = Math.round(diffMs / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.round(mins / 60);
    if (hrs < 48) return `${hrs}h ago`;
    return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
  } catch {
    return "—";
  }
}

export function orderProgress(order: ServiceOrder) {
  const target = Number(order.recipient_count || 0);
  const report = order.report || {};
  if (order.service_code === "survey") {
    const responses = Number(report.responded || report.completed || 0);
    const sent = Number(report.sent || report.reached || target);
    const denom = sent || target;
    return {
      responses,
      target: denom,
      completion: denom ? Math.round((responses / denom) * 100) : 0,
    };
  }
  const responses = Number(report.completed || report.interviewed || 0);
  return {
    responses,
    target,
    completion: target ? Math.round((responses / target) * 100) : 0,
  };
}

export function statusLabelToTone(label: string, order: ServiceOrder): CampaignTone {
  const l = String(label || order.status || "").toLowerCase();
  if (order.status === "running") return "live";
  if (order.status === "paused") return "paused";
  if (order.status === "scheduled") return "scheduled";
  if (order.is_archived || order.status === "archived") return "archived";
  if (order.is_finished || order.status === "completed") return "finished";
  if (order.payment_status === "rejected" || l.includes("failed")) return "payment-failed";
  if (order.payment_status === "pending_approval" || l.includes("awaiting") || l.includes("pending payment")) {
    return "awaiting-payment";
  }
  if (order.status === "quoted" || order.status === "draft" || l === "quoted") return "quoted";
  if (l === "live" || l === "running") return "live";
  return "quoted";
}

export function orderToCampaign(order: ServiceOrder, type: CampaignType): Campaign {
  const { responses, target, completion } = orderProgress(order);
  const rejectTitles = [order.title || "", String(order.config?.goal || "")].filter(Boolean);
  const step1 = (
    sanitizeStepLabelFromApi(String(order.first_step_name || ""), rejectTitles) ||
    firstStepLabelFromConfig(order.config, rejectTitles)
  ).trim();
  return {
    id: order.id,
    name: order.title || (type === "interview" ? "Interview task" : "Survey task"),
    subtitle: step1 ? step1 : undefined,
    type,
    status: statusLabelToTone(order.status_label || order.status, order),
    responses,
    target,
    completion,
    updatedAt: formatRelativeTime(order.updated_at || order.created_at),
  };
}

export function orderTab(order: ServiceOrder): "live" | "finished" | "archived" {
  if (order.is_archived || order.status === "archived") return "archived";
  if (order.is_finished) return "finished";
  if (order.is_live) return "live";
  return "live";
}

export function badgeToneFromStatus(status: string): BadgeTone {
  const map: Record<string, BadgeTone> = {
    paid: "completed",
    open: "live",
    void: "archived",
  };
  return map[String(status || "").toLowerCase()] || "finished";
}
