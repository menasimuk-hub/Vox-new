import * as React from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { useBillingSubscriptionCancellation } from "@/lib/queries";
import { StatusBadge, type BadgeTone } from "@/components/status-badge";

type CancellationPayload = {
  status?: string;
  effective_subscription_status?: string;
  cancellation_type?: string | null;
  cancellation_reason?: string | null;
  requested_at?: string | null;
  effective_at?: string | null;
  current_period_end?: string | null;
  requested_refund_type?: string | null;
  calculated_unused_value_display?: string | null;
  can_request_cancellation?: boolean;
  refund_review?: { review_status?: string } | null;
  policy_notes?: { open_invoices_block_wallet_credit?: boolean };
};

function fmtDate(iso?: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { dateStyle: "medium" });
}

function cancellationLabel(status?: string) {
  const s = String(status || "none").toLowerCase();
  if (s === "scheduled") return "Scheduled to cancel";
  if (s === "cancelled") return "Cancelled";
  if (s === "requested") return "Cancellation requested";
  if (s === "reversed") return "Active";
  return "Active";
}

function cancellationBadgeTone(status: string, cancelled: boolean): BadgeTone {
  if (cancelled) return "archived";
  if (status === "scheduled" || status === "requested") return "scheduled";
  return "live";
}

function cancellationBadgeLabel(status: string, cancelled: boolean) {
  if (cancelled) return "Cancelled";
  if (status === "scheduled" || status === "requested") return "Scheduled";
  return "Active";
}

export function SubscriptionCancellationCard({ planName }: { planName?: string | null }) {
  const cancelQ = useBillingSubscriptionCancellation();
  const [open, setOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [reason, setReason] = React.useState("");
  const [refundPref, setRefundPref] = React.useState("none");

  const data = (cancelQ.data || {}) as CancellationPayload;
  const status = String(data.status || "none").toLowerCase();
  const scheduled = status === "scheduled" || status === "requested";
  const cancelled = status === "cancelled" || data.effective_subscription_status === "cancelled";
  const canCancel = Boolean(data.can_request_cancellation) && !cancelled;

  const submit = async () => {
    setBusy(true);
    try {
      await apiFetch("/billing/subscription/cancellation", {
        method: "POST",
        body: JSON.stringify({
          cancellation_type: "period_end",
          reason: reason.trim() || null,
          requested_refund_type: refundPref,
        }),
      });
      toast.success("Cancellation scheduled for end of billing period");
      setOpen(false);
      await cancelQ.refetch();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not request cancellation");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Card>
        <CardHeader className="pb-2">
          <CardDescription>Subscription</CardDescription>
          <CardTitle className="flex flex-wrap items-center gap-2 text-lg">
            {cancellationLabel(status)}
            <StatusBadge
              tone={cancellationBadgeTone(status, cancelled)}
              label={cancellationBadgeLabel(status, cancelled)}
            />
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {planName ? <p>Plan: <strong>{planName}</strong></p> : null}
          {scheduled ? (
            <p className="text-muted-foreground">
              Your subscription stays active until <strong>{fmtDate(data.effective_at || data.current_period_end)}</strong>.
              Future renewals will stop after that date.
            </p>
          ) : cancelled ? (
            <p className="text-muted-foreground">Your subscription has ended.</p>
          ) : (
            <p className="text-muted-foreground">
              Cancel at period end to keep access until your current billing period ends. No automatic bank or card refund.
            </p>
          )}
          {data.calculated_unused_value_display && scheduled ? (
            <p className="text-muted-foreground">
              Estimated unused value: <strong>{data.calculated_unused_value_display}</strong> (subject to review).
            </p>
          ) : null}
          {data.refund_review?.review_status === "pending" ? (
            <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-100">
              Refund review pending — our team will contact you if a payment-method refund applies.
            </p>
          ) : null}
          {canCancel ? (
            <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
              Request cancellation
            </Button>
          ) : null}
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Request subscription cancellation</DialogTitle>
            <DialogDescription>
              Your plan{planName ? ` (${planName})` : ""} remains active until{" "}
              <strong>{fmtDate(data.current_period_end)}</strong>. Future renewals stop after that date.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 text-sm">
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              <li>Service stays active until the end of your current billing period.</li>
              <li>No automatic refund to your bank or card.</li>
              <li>Any approved remaining value may be added to your wallet.</li>
              <li>Refunds to your original payment method are subject to review.</li>
            </ul>
            <div className="space-y-2">
              <Label htmlFor="cancel-reason">Reason (optional)</Label>
              <Textarea id="cancel-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={3} />
            </div>
            <div className="space-y-2">
              <Label>Unused value preference</Label>
              <RadioGroup value={refundPref} onValueChange={setRefundPref}>
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="none" id="refund-none" />
                  <Label htmlFor="refund-none" className="font-normal">No compensation requested</Label>
                </div>
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="wallet_credit" id="refund-wallet" />
                  <Label htmlFor="refund-wallet" className="font-normal">Add remaining value to wallet (if approved)</Label>
                </div>
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="payment_method_refund" id="refund-bank" />
                  <Label htmlFor="refund-bank" className="font-normal">Request review for refund to original payment method</Label>
                </div>
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="either" id="refund-either" />
                  <Label htmlFor="refund-either" className="font-normal">Either wallet credit or payment-method refund (admin decides)</Label>
                </div>
              </RadioGroup>
            </div>
            {data.policy_notes?.open_invoices_block_wallet_credit ? (
              <p className="text-xs text-amber-700 dark:text-amber-300">
                Open invoices must be resolved before wallet credit can be issued.
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)} disabled={busy}>
              Keep subscription
            </Button>
            <Button type="button" variant="destructive" onClick={() => void submit()} disabled={busy}>
              {busy ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
              Cancel at period end
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
