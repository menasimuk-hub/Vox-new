import type { ServiceOrder } from "@/lib/types/api";

export type OrderPayAction = "launch" | "topup" | "wait" | "none";

export type OrderPayButton = {
  label: string;
  hint: string;
  action: OrderPayAction;
  disabled?: boolean;
};

function quoteDisplay(order: ServiceOrder): string {
  return String(order.quote_total_gbp || "—");
}

export function orderHasPayableQuote(order: ServiceOrder | null | undefined): boolean {
  if (!order) return false;
  const paymentStatus = String(order.payment_status || "unpaid").toLowerCase();
  if (paymentStatus === "approved" || paymentStatus === "pending_approval") return false;
  const quotePence = Number(order.quote_total_pence ?? 0);
  return quotePence > 0;
}

export function orderPayButton(order: ServiceOrder | null | undefined): OrderPayButton {
  if (!order) {
    return { label: "Pay", hint: "", action: "none" };
  }

  const paymentStatus = String(order.payment_status || "unpaid").toLowerCase();
  const workflow = String(order.workflow_state || order.status || "draft").toLowerCase();
  const quote = quoteDisplay(order);
  const quotePence = Number(order.quote_total_pence ?? 0);

  if (paymentStatus === "pending_approval") {
    return {
      label: "Awaiting approval",
      hint: "Your payment is pending admin approval before you can launch.",
      action: "wait",
      disabled: true,
    };
  }

  if (paymentStatus === "approved" || workflow === "launch_ready") {
    return {
      label: "Launch campaign",
      hint: "Payment is complete — open launch to send.",
      action: "launch",
    };
  }

  if ((workflow === "quoted" || paymentStatus === "unpaid") && quotePence <= 0) {
    return {
      label: "Launch campaign",
      hint: "No payment required — open launch when you are ready.",
      action: "launch",
    };
  }

  if (workflow === "quoted" || paymentStatus === "unpaid") {
    return {
      label: `Pay quote · ${quote}`,
      hint: "Review the quote and pay from your package allowance, wallet, or Direct Debit at launch.",
      action: "launch",
    };
  }

  if (quotePence <= 0) {
    return {
      label: "Launch campaign",
      hint: "No payment required — open launch when you are ready.",
      action: "launch",
    };
  }

  return {
    label: `Pay to launch · ${quote}`,
    hint: "Payment is required before this campaign can go live.",
    action: "launch",
  };
}

export function invoiceStatusLabel(status?: string | null): string {
  const st = String(status || "issued").toLowerCase();
  const map: Record<string, string> = {
    due: "Payment due",
    issued: "Issued",
    open: "Open",
    paid: "Paid",
    collecting: "Direct Debit collecting",
    pending: "Payment pending",
    failed: "Payment failed",
    past_due: "Past due",
    disputed: "Disputed",
    refunded: "Refunded",
    void: "Void",
    cancelled: "Cancelled",
  };
  return map[st] || st.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
