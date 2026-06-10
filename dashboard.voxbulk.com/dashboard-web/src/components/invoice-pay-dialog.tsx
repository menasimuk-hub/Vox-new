import * as React from "react";
import { CreditCard, Landmark, Loader2, Wallet } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { apiFetch } from "@/lib/api";
import { usePayInvoice } from "@/lib/queries";
import type { Invoice, InvoicePaymentContext } from "@/lib/types/api";

declare global {
  interface Window {
    Stripe?: (key: string) => StripeJs;
  }
}

type StripeJs = {
  elements: (opts: { clientSecret: string }) => StripeElements;
  confirmPayment: (opts: {
    elements: StripeElements;
    redirect: "if_required";
  }) => Promise<{ error?: { message?: string }; paymentIntent?: { id: string; status: string } }>;
};
type StripeElements = { create: (kind: string, opts?: Record<string, unknown>) => { mount: (el: HTMLElement) => void; destroy: () => void } };

const loadedScripts: Record<string, Promise<void>> = {};
function loadScript(src: string): Promise<void> {
  if (!loadedScripts[src]) {
    loadedScripts[src] = new Promise<void>((resolve, reject) => {
      const tag = document.createElement("script");
      tag.src = src;
      tag.async = true;
      tag.onload = () => resolve();
      tag.onerror = () => reject(new Error(`Failed to load ${src}`));
      document.head.appendChild(tag);
    });
  }
  return loadedScripts[src];
}

type Props = {
  invoice: Invoice | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPaid?: () => void;
};

export function InvoicePayDialog({ invoice, open, onOpenChange, onPaid }: Props) {
  const payM = usePayInvoice();
  const ctx = (invoice?.payment_context || {}) as InvoicePaymentContext;
  const available = ctx.available_methods || ctx.methods?.filter((m) => m.available !== false) || [];

  const [step, setStep] = React.useState<"choose" | "card">("choose");
  const [busy, setBusy] = React.useState(false);
  const [cardReady, setCardReady] = React.useState(false);
  const mountRef = React.useRef<HTMLDivElement | null>(null);
  const stripeRef = React.useRef<{ stripe: StripeJs; elements: StripeElements; intentId: string } | null>(null);
  const cleanupRef = React.useRef<(() => void) | null>(null);

  React.useEffect(() => {
    if (!open) {
      setStep("choose");
      setCardReady(false);
      cleanupRef.current?.();
      cleanupRef.current = null;
      stripeRef.current = null;
    }
  }, [open]);

  const payWalletOrDd = async (method: string) => {
    if (!invoice?.id) return;
    setBusy(true);
    try {
      const res = await payM.mutateAsync({ invoiceId: invoice.id, method });
      if (method === "direct_debit" || res.method === "direct_debit") {
        toast.success("Direct Debit collection started", {
          description: "Payment completes in 3–5 working days.",
        });
      } else {
        toast.success("Invoice paid");
      }
      onOpenChange(false);
      onPaid?.();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Payment failed");
    } finally {
      setBusy(false);
    }
  };

  const startCard = async () => {
    if (!invoice?.id) return;
    setBusy(true);
    try {
      const intent = await apiFetch<{
        client_secret?: string;
        publishable_key?: string;
        payment_intent_id?: string;
      }>(`/billing/invoices/${encodeURIComponent(invoice.id)}/pay/card/intent`, { method: "POST", body: "{}" });
      if (!intent.client_secret || !intent.publishable_key || !intent.payment_intent_id) {
        throw new Error("Card payments are not configured.");
      }
      await loadScript("https://js.stripe.com/v3");
      if (!window.Stripe) throw new Error("Stripe.js failed to load");
      const stripe = window.Stripe(intent.publishable_key);
      const elements = stripe.elements({ clientSecret: intent.client_secret });
      const paymentElement = elements.create("payment", { layout: "tabs" });
      if (mountRef.current) {
        mountRef.current.innerHTML = "";
        paymentElement.mount(mountRef.current);
      }
      stripeRef.current = { stripe, elements, intentId: intent.payment_intent_id };
      cleanupRef.current = () => paymentElement.destroy();
      setStep("card");
      setCardReady(true);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not start card payment");
    } finally {
      setBusy(false);
    }
  };

  const confirmCard = async () => {
    const s = stripeRef.current;
    if (!invoice?.id || !s) return;
    setBusy(true);
    try {
      const result = await s.stripe.confirmPayment({ elements: s.elements, redirect: "if_required" });
      if (result.error) {
        toast.error(result.error.message || "Card payment failed");
        setBusy(false);
        return;
      }
      await apiFetch(`/billing/invoices/${encodeURIComponent(invoice.id)}/pay/card/confirm`, {
        method: "POST",
        body: JSON.stringify({ payment_intent_id: result.paymentIntent?.id || s.intentId }),
      });
      toast.success("Invoice paid by card");
      onOpenChange(false);
      onPaid?.();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not confirm payment");
    } finally {
      setBusy(false);
    }
  };

  const methodIcon = (method: string) => {
    if (method === "wallet") return <Wallet className="size-4" />;
    if (method === "direct_debit") return <Landmark className="size-4" />;
    return <CreditCard className="size-4" />;
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Pay invoice · {invoice?.invoice_number || invoice?.id?.slice(0, 8)}</DialogTitle>
          <DialogDescription>{invoice?.description || "Choose how to settle this invoice."}</DialogDescription>
        </DialogHeader>

        {step === "choose" ? (
          <div className="space-y-4 text-sm">
            <div className="rounded-lg border border-border p-3">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Amount due</span>
                <span className="font-semibold tabular-nums">{ctx.amount_due_display || invoice?.total_gbp}</span>
              </div>
              <div className="mt-2 flex justify-between text-xs text-muted-foreground">
                <span>Wallet available</span>
                <span>{ctx.wallet_balance_display || "—"}</span>
              </div>
              {ctx.wallet_shortfall_display ? (
                <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
                  Wallet is short by {ctx.wallet_shortfall_display}. Partial wallet payment is not supported — pay the full
                  amount by card or Direct Debit.
                </p>
              ) : null}
              <div className="mt-2 grid gap-1 text-xs text-muted-foreground">
                <span>Card: {ctx.card_available ? "Available (Stripe)" : "Not configured"}</span>
                <span>Direct Debit: {ctx.mandate_active ? "Active mandate" : "No active mandate"}</span>
              </div>
            </div>

            {!ctx.payable ? (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs">
                {(ctx.next_steps || []).map((stepText) => (
                  <p key={stepText}>{stepText}</p>
                ))}
              </div>
            ) : available.length === 0 ? (
              <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive">
                No payment methods are available for this invoice. Contact support or{" "}
                <Link to="/account/packages" className="underline">
                  set up billing
                </Link>
                .
              </div>
            ) : (
              <div className="grid gap-2">
                {available.map((method) => {
                  const m = String(method.method || "");
                  return (
                    <Button
                      key={m}
                      variant={m === "wallet" ? "default" : "outline"}
                      className="h-auto flex-col items-start gap-1 py-3 text-left"
                      disabled={busy || payM.isPending}
                      onClick={() => {
                        if (m === "card") void startCard();
                        else void payWalletOrDd(m === "direct_debit_retry" ? "direct_debit" : m);
                      }}
                    >
                      <span className="flex items-center gap-2 font-medium">
                        {methodIcon(m)}
                        {String(method.label || m)}
                      </span>
                      {method.outcome_label ? (
                        <span className="text-xs font-normal text-muted-foreground">{String(method.outcome_label)}</span>
                      ) : null}
                    </Button>
                  );
                })}
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <div ref={mountRef} className="min-h-[10rem]" />
            {!cardReady ? (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Preparing secure card payment…
              </p>
            ) : null}
          </div>
        )}

        <DialogFooter className="gap-2 sm:justify-between">
          {step === "card" ? (
            <>
              <Button
                variant="ghost"
                disabled={busy}
                onClick={() => {
                  cleanupRef.current?.();
                  setStep("choose");
                  setCardReady(false);
                }}
              >
                Back
              </Button>
              <Button disabled={busy || !cardReady} onClick={() => void confirmCard()}>
                {busy ? <Loader2 className="size-4 animate-spin" /> : null}
                Pay {ctx.amount_due_display || ""} by card
              </Button>
            </>
          ) : (
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              Cancel
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
