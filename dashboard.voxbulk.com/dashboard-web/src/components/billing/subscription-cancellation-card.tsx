import * as React from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useQuery, useQueryClient } from "@tanstack/react-query";

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
import { REFUND_TIMING_BANK, REFUND_TIMING_PROCESSING } from "@/lib/billing/refund-timing";
import { queryKeys } from "@/lib/queries";
import { StatusBadge, type BadgeTone } from "@/components/status-badge";
import { cn } from "@/lib/utils";

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
  calculated_unused_value_pence?: number | null;
  billing_interval?: string | null;
  can_request_cancellation?: boolean;
  can_reverse_cancellation?: boolean;
  refund_review?: { review_status?: string } | null;
  policy_notes?: {
    open_invoices_block_wallet_credit?: boolean;
    yearly_refund_rule?: string | null;
  };
};

function fmtDate(iso?: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { dateStyle: "medium" });
}

function cancellationStatusBadge(status: string, cancelled: boolean): { tone: BadgeTone; label: string } | null {
  if (cancelled) return { tone: "archived", label: "Cancelled" };
  if (status === "scheduled" || status === "requested") return { tone: "scheduled", label: "Scheduled" };
  return null;
}

function useInvalidateBillingQueries() {
  const qc = useQueryClient();
  return React.useCallback(async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: queryKeys.billingSubscriptionCancellation }),
      qc.invalidateQueries({ queryKey: queryKeys.billingSubscription }),
      qc.invalidateQueries({ queryKey: queryKeys.billingWallet }),
      qc.invalidateQueries({ queryKey: queryKeys.billingRequests }),
      qc.invalidateQueries({ queryKey: ["billing", "wallet", "transactions"] }),
    ]);
  }, [qc]);
}

type CancellationService = "voxbulk" | "feedback" | "smart_card";

function cancellationConfig(service: CancellationService) {
  if (service === "feedback") {
    return {
      queryKey: queryKeys.feedbackSubscriptionCancellation,
      getPath: "/customer-feedback/subscription/cancellation",
      postPath: "/customer-feedback/subscription/cancellation",
      reversePath: "/customer-feedback/subscription/cancellation/reverse",
      refundPrefs: ["none", "payment_method_refund"] as const,
      invalidate: async (qc: ReturnType<typeof useQueryClient>) => {
        await Promise.all([
          qc.invalidateQueries({ queryKey: queryKeys.feedbackSubscriptionCancellation }),
          qc.invalidateQueries({ queryKey: queryKeys.feedbackSubscription }),
          qc.invalidateQueries({ queryKey: queryKeys.feedbackPackages }),
          qc.invalidateQueries({ queryKey: queryKeys.billingSubscriptionsSummary }),
        ]);
      },
    };
  }
  if (service === "smart_card") {
    return {
      queryKey: queryKeys.smartCardSubscriptionCancellation,
      getPath: "/smart-card/billing/cancellation",
      postPath: "/smart-card/billing/cancellation",
      reversePath: "/smart-card/billing/cancellation/reverse",
      refundPrefs: ["none", "payment_method_refund"] as const,
      invalidate: async (qc: ReturnType<typeof useQueryClient>) => {
        await Promise.all([
          qc.invalidateQueries({ queryKey: queryKeys.smartCardSubscriptionCancellation }),
          qc.invalidateQueries({ queryKey: queryKeys.billingSubscriptionsSummary }),
          qc.invalidateQueries({ queryKey: ["smart-card"] }),
        ]);
      },
    };
  }
  return {
    queryKey: queryKeys.billingSubscriptionCancellation,
    getPath: "/billing/subscription/cancellation",
    postPath: "/billing/subscription/cancellation",
    reversePath: "/billing/subscription/cancellation/reverse",
    refundPrefs: ["none", "wallet_credit", "payment_method_refund", "either"] as const,
    invalidate: async (qc: ReturnType<typeof useQueryClient>) => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: queryKeys.billingSubscriptionCancellation }),
        qc.invalidateQueries({ queryKey: queryKeys.billingSubscription }),
        qc.invalidateQueries({ queryKey: queryKeys.billingWallet }),
        qc.invalidateQueries({ queryKey: queryKeys.billingRequests }),
        qc.invalidateQueries({ queryKey: queryKeys.billingSubscriptionsSummary }),
        qc.invalidateQueries({ queryKey: ["billing", "wallet", "transactions"] }),
      ]);
    },
  };
}

function useSubscriptionCancellationState(service: CancellationService = "voxbulk") {
  const config = cancellationConfig(service);
  const qc = useQueryClient();
  const cancelQ = useQuery({
    queryKey: config.queryKey,
    queryFn: () => apiFetch(config.getPath),
    refetchOnMount: "always",
  });
  const invalidateBilling = React.useCallback(async () => {
    await config.invalidate(qc);
  }, [config, qc]);
  const [open, setOpen] = React.useState(false);
  const [reverseOpen, setReverseOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [reason, setReason] = React.useState("");
  const [refundPref, setRefundPref] = React.useState("payment_method_refund");

  const data = (cancelQ.data || {}) as CancellationPayload;
  const unusedPence = Number(data.calculated_unused_value_pence || 0);
  const defaultRefundPref =
    unusedPence > 0 && config.refundPrefs.includes("payment_method_refund")
      ? "payment_method_refund"
      : config.refundPrefs.includes("none")
        ? "none"
        : config.refundPrefs[0];

  React.useEffect(() => {
    if (!open) return;
    setRefundPref(defaultRefundPref);
  }, [open, defaultRefundPref]);

  const status = String(data.status || "none").toLowerCase();
  const scheduled = status === "scheduled" || status === "requested";
  const cancelled = status === "cancelled" || data.effective_subscription_status === "cancelled";
  const canCancel = Boolean(data.can_request_cancellation) && !cancelled;
  const canReverse = Boolean(data.can_reverse_cancellation) && scheduled && !cancelled;

  const submit = async () => {
    setBusy(true);
    try {
      await apiFetch(config.postPath, {
        method: "POST",
        body: JSON.stringify({
          cancellation_type: "period_end",
          reason: reason.trim() || null,
          requested_refund_type: refundPref,
        }),
      });
      toast.success("Cancellation scheduled for end of billing period");
      setOpen(false);
      await invalidateBilling();
      await cancelQ.refetch();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not request cancellation");
    } finally {
      setBusy(false);
    }
  };

  const reverseCancellation = async () => {
    setBusy(true);
    try {
      await apiFetch(config.reversePath, { method: "POST", body: "{}" });
      toast.success("Cancellation removed — your subscription will continue");
      setReverseOpen(false);
      await invalidateBilling();
      await cancelQ.refetch();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not remove cancellation");
    } finally {
      setBusy(false);
    }
  };

  return {
    cancelQ,
    data,
    status,
    scheduled,
    cancelled,
    canCancel,
    canReverse,
    open,
    setOpen,
    reverseOpen,
    setReverseOpen,
    busy,
    reason,
    setReason,
    refundPref,
    setRefundPref,
    refundPrefs: config.refundPrefs,
    submit,
    reverseCancellation,
  };
}

function CancellationDialog({
  planName,
  state,
}: {
  planName?: string | null;
  state: ReturnType<typeof useSubscriptionCancellationState>;
}) {
  const { data, open, setOpen, busy, reason, setReason, refundPref, setRefundPref, refundPrefs, submit } = state;
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Are you sure you want to cancel?</DialogTitle>
          <DialogDescription>
            Your plan{planName ? ` (${planName})` : ""} stays active until{" "}
            <strong>{fmtDate(data.current_period_end)}</strong>. After that date access ends and no further
            renewals are charged.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 text-sm">
          {data.calculated_unused_value_display ? (
            <p className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
              Estimated unused value:{" "}
              <strong className="text-foreground">{data.calculated_unused_value_display}</strong>
              {String(data.billing_interval || "").toLowerCase() === "yearly" ? (
                <> — yearly: amount paid minus (months used × monthly price); yearly discount is not kept on months already used.</>
              ) : (
                <> (remaining days in this billing period).</>
              )}
            </p>
          ) : null}
          <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
            <li>You keep access until the end of the current billing period.</li>
            <li>No next payment will be taken after that date.</li>
            <li>If you request a refund for unused prepaid time, our team reviews it before any money is returned.</li>
            <li>{REFUND_TIMING_PROCESSING}</li>
            <li>{REFUND_TIMING_BANK}</li>
          </ul>
          <div className="space-y-2">
            <Label htmlFor="cancel-reason">Reason (optional)</Label>
            <Textarea id="cancel-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={3} />
          </div>
          <div className="space-y-2">
            <Label>Unused value preference</Label>
            <RadioGroup value={refundPref} onValueChange={setRefundPref}>
              {refundPrefs.includes("payment_method_refund") ? (
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="payment_method_refund" id="refund-bank" />
                  <Label htmlFor="refund-bank" className="font-normal">
                    Request refund of unused value to original payment method
                  </Label>
                </div>
              ) : null}
              {refundPrefs.includes("wallet_credit") ? (
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="wallet_credit" id="refund-wallet" />
                  <Label htmlFor="refund-wallet" className="font-normal">Add remaining value to wallet (if approved)</Label>
                </div>
              ) : null}
              {refundPrefs.includes("either") ? (
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="either" id="refund-either" />
                  <Label htmlFor="refund-either" className="font-normal">Either wallet credit or payment-method refund (admin decides)</Label>
                </div>
              ) : null}
              <div className="flex items-center gap-2">
                <RadioGroupItem value="none" id="refund-none" />
                <Label htmlFor="refund-none" className="font-normal">No refund — keep access until period end only</Label>
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
            Never mind
          </Button>
          <Button type="button" variant="destructive" onClick={() => void submit()} disabled={busy}>
            {busy ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
            Confirm cancellation
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ReverseCancellationDialog({
  state,
}: {
  state: ReturnType<typeof useSubscriptionCancellationState>;
}) {
  const { reverseOpen, setReverseOpen, busy, reverseCancellation } = state;
  return (
    <Dialog open={reverseOpen} onOpenChange={setReverseOpen}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Keep your subscription?</DialogTitle>
          <DialogDescription>
            This removes your scheduled cancellation. Your plan will renew as normal at the end of the billing period.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => setReverseOpen(false)} disabled={busy}>
            Cancel
          </Button>
          <Button type="button" onClick={() => void reverseCancellation()} disabled={busy}>
            {busy ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
            Keep subscription
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function SubscriptionCancellationBar({
  planName,
  className,
  service = "voxbulk",
}: {
  planName?: string | null;
  className?: string;
  service?: CancellationService;
}) {
  const state = useSubscriptionCancellationState(service);
  const { data, status, scheduled, cancelled, canCancel, canReverse, setOpen, setReverseOpen, cancelQ } = state;
  const cancellationBadge = cancellationStatusBadge(status, cancelled);

  if (cancelQ.isLoading) return null;

  return (
    <>
      <div
        className={cn(
          "flex flex-col gap-4 rounded-lg border border-border bg-muted/20 p-4 sm:flex-row sm:items-center sm:justify-between",
          className,
        )}
      >
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold">Subscription cancellation</p>
            {cancellationBadge ? <StatusBadge tone={cancellationBadge.tone} label={cancellationBadge.label} /> : null}
          </div>
          {scheduled ? (
            <>
              <p className="text-sm text-muted-foreground">
                Active until <strong className="text-foreground">{fmtDate(data.effective_at || data.current_period_end)}</strong>.
                No further payments after that date.
              </p>
              <p className="text-xs text-muted-foreground">
                Change your mind? You can keep your subscription before our team finalises any refund.
              </p>
            </>
          ) : cancelled ? (
            <p className="text-sm text-muted-foreground">Your subscription has ended.</p>
          ) : (
            <p className="text-sm text-muted-foreground">
              Cancel at period end to keep access until your billing period ends. No next payment will be charged.
            </p>
          )}
          {data.refund_review?.review_status === "pending" ? (
            <p className="text-xs text-amber-700 dark:text-amber-300">
              Refund review pending — {REFUND_TIMING_PROCESSING} {REFUND_TIMING_BANK}
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {canReverse ? (
            <Button type="button" variant="default" className="shrink-0" onClick={() => setReverseOpen(true)}>
              Keep subscription
            </Button>
          ) : null}
          {canCancel ? (
            <Button type="button" variant="outline" className="shrink-0" onClick={() => setOpen(true)}>
              Cancel subscription
            </Button>
          ) : null}
        </div>
      </div>
      <CancellationDialog planName={planName} state={state} />
      <ReverseCancellationDialog state={state} />
    </>
  );
}

/** Compact cancel / keep controls for product billing cards. */
export function ProductCancellationActions({
  planName,
  service = "voxbulk",
  enabled = true,
}: {
  planName?: string | null;
  service?: CancellationService;
  /** False for PAYG / no plan — hide controls. */
  enabled?: boolean;
}) {
  const state = useSubscriptionCancellationState(service);
  const { data, scheduled, cancelled, canCancel, canReverse, setOpen, setReverseOpen, cancelQ } = state;

  if (!enabled || cancelQ.isLoading || cancelled) return null;
  if (!canCancel && !canReverse && !scheduled) return null;

  return (
    <>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {canReverse ? (
          <Button type="button" size="sm" variant="secondary" onClick={() => setReverseOpen(true)}>
            Keep subscription
          </Button>
        ) : null}
        {canCancel ? (
          <Button type="button" size="sm" variant="outline" onClick={() => setOpen(true)}>
            Cancel subscription
          </Button>
        ) : null}
        {scheduled && !canReverse ? (
          <span className="text-xs text-muted-foreground">
            Ends {fmtDate(data.effective_at || data.current_period_end)} · no next payment
          </span>
        ) : null}
      </div>
      <CancellationDialog planName={planName} state={state} />
      <ReverseCancellationDialog state={state} />
    </>
  );
}

/** @deprecated Use SubscriptionCancellationBar on the billing page */
export function SubscriptionCancellationCard({ planName }: { planName?: string | null }) {
  const state = useSubscriptionCancellationState();
  const { status, scheduled, cancelled, canCancel, canReverse, setOpen, setReverseOpen } = state;
  const cancellationBadge = cancellationStatusBadge(status, cancelled);

  return (
    <>
      <Card>
        <CardHeader className="pb-2">
          <CardDescription>Subscription</CardDescription>
          <CardTitle className="flex flex-wrap items-center gap-2 text-lg">
            {scheduled ? "Scheduled to cancel" : cancelled ? "Cancelled" : "Subscription"}
            {cancellationBadge ? <StatusBadge tone={cancellationBadge.tone} label={cancellationBadge.label} /> : null}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {planName ? <p>Plan: <strong>{planName}</strong></p> : null}
          <div className="flex flex-wrap gap-2">
            {canReverse ? (
              <Button type="button" size="sm" onClick={() => setReverseOpen(true)}>
                Keep subscription
              </Button>
            ) : null}
            {canCancel ? (
              <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
                Request cancellation
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>
      <CancellationDialog planName={planName} state={state} />
      <ReverseCancellationDialog state={state} />
    </>
  );
}
