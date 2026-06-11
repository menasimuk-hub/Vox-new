import { isInterviewCampaignReadOnly } from "@/lib/interview-campaign";

type UsageOrderRow = {
  order_id: string;
  service_code?: string | null;
  status?: string | null;
};

export function orderDetailLink(row: UsageOrderRow) {
  const serviceCode = String(row.service_code || "").toLowerCase();
  const orderId = row.order_id;
  if (!orderId) return null;

  if (serviceCode === "interview") {
    const readOnly = isInterviewCampaignReadOnly(row.status);
    if (readOnly) {
      return { to: "/interviews/$orderId" as const, params: { orderId } };
    }
    return { to: "/interviews/new" as const, search: { order_id: orderId } };
  }

  if (serviceCode === "survey") {
    return { to: "/surveys/new" as const, search: { order_id: orderId } };
  }

  return null;
}
