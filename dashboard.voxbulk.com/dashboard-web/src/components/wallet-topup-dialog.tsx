import * as React from "react";
import { CreditCard, Loader2, Wallet } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { redirectToAirwallexHostedCheckout } from "@/lib/billing/airwallex-hpp";

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
    confirmParams?: Record<string, unknown>;
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
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Pre-filled amount in minor units (e.g. wallet shortfall before a launch). */
  initialAmountMinor?: number;
  onToppedUp?: () => void;
};

export function WalletTopupDialog({ open, onOpenChange, initialAmountMinor, onToppedUp }: Props) {
  const optionsQ = useWalletTopupOptions();
  const intentM = useWalletTopupIntent();
  const confirmM = useWalletTopupConfirm();

  const options = optionsQ.data;
  const currency = String(options?.currency || "GBP");
  const symbol = { GBP: "£", USD: "$", CAD: "CA$", AUD: "A$" }[currency] || currency;
  const minMinor = Number(options?.min_amount_minor || 500);

  const [amount, setAmount] = React.useState("50");
  const [provider, setProvider] = React.useState<string | null>(null);
  const [paying, setPaying] = React.useState(false);
  const [paymentReady, setPaymentReady] = React.useState(false);
  const mountRef = React.useRef<HTMLDivElement | null>(null);
  const stripeRef = React.useRef<{ stripe: StripeJs; elements: StripeElements; intentId: string } | null>(null);
  const cleanupRef = React.useRef<(() => void) | null>(null);

  React.useEffect(() => {
    if (open && initialAmountMinor && initialAmountMinor > 0) {
      setAmount((Math.ceil(initialAmountMinor / 100)).toString());
    }
    if (!open) {
      setProvider(null);
      setPaymentReady(false);
      cleanupRef.current?.();
      cleanupRef.current = null;
      stripeRef.current = null;
    }
  }, [open, initialAmountMinor]);

  const amountMinor = Math.round(Number(amount || 0) * 100);

  const startPayment = async (providerId: string) => {
    if (amountMinor < minMinor) {
      toast.error(`Minimum top-up is ${options?.min_amount_display || "5.00"}`);
      return;
    }
    setProvider(providerId);
    setPaymentReady(false);
    try {
      const intent = await intentM.mutateAsync({ provider: providerId, amount_minor: amountMinor });
      if (providerId === "stripe") {
        if (!intent.publishable_key || !intent.client_secret || !intent.payment_intent_id) {
          throw new Error("Stripe is not configured. Ask support to enable Stripe in admin integrations.");
        }
        await loadScript("https://js.stripe.com/v3");
        if (!window.Stripe) throw new Error("Stripe.js failed to load");
        const stripe = window.Stripe(String(intent.publishable_key));
        const elements = stripe.elements({ clientSecret: intent.client_secret });
        const paymentElement = elements.create("payment", {
          layout: "tabs",
          wallets: { applePay: "never", googlePay: "never" },
        });
        if (mountRef.current) {
          mountRef.current.innerHTML = "";
          paymentElement.mount(mountRef.current);
        }
        stripeRef.current = { stripe, elements, intentId: intent.payment_intent_id };
        cleanupRef.current = () => paymentElement.destroy();
        setPaymentReady(true);
      } else if (providerId === "airwallex") {
        if (!intent.payment_intent_id || !intent.client_secret) {
          throw new Error("Airwallex is not configured.");
        }
        onOpenChange(false);
        await redirectToAirwallexHostedCheckout({
          intent_id: intent.payment_intent_id,
          client_secret: intent.client_secret,
          currency: intent.currency,
          environment: String((intent as Record<string, unknown>).environment || "demo"),
          pending: { flow: "wallet", payment_intent_id: intent.payment_intent_id },
          returnPath: `${window.location.pathname}${window.location.search}`,
        });
        return;
      }
    } catch (e) {
      setProvider(null);
      toast.error(e instanceof Error ? e.message : "Could not start payment");
    }
  };

  const finishPayment = async (providerId: string, intentId: string) => {
    try {
      const res = await confirmM.mutateAsync({ provider: providerId, payment_intent_id: intentId });
      if (res.credited || res.duplicate) {
        toast.success(`Wallet topped up — ${String(res.wallet_balance_display || res.wallet_balance_gbp || "")}`);
        onOpenChange(false);
        onToppedUp?.();
      } else {
        toast.message("Payment is still processing", {
          description: "Your wallet will be credited as soon as the payment settles.",
        });
        onOpenChange(false);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not verify payment");
    } finally {
      setPaying(false);
    }
  };

  const payWithStripe = async () => {
    const ctx = stripeRef.current;
    if (!ctx) return;
    setPaying(true);
    try {
      const result = await ctx.stripe.confirmPayment({ elements: ctx.elements, redirect: "if_required" });
      if (result.error) {
        toast.error(result.error.message || "Payment failed");
        setPaying(false);
        return;
      }
      await finishPayment("stripe", result.paymentIntent?.id || ctx.intentId);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Payment failed");
      setPaying(false);
    }
  };

  const providers = options?.providers || [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="top-[4dvh] flex max-h-[min(92dvh,36rem)] w-[calc(100%-2rem)] translate-y-0 flex-col gap-0 overflow-hidden p-0 sm:top-[50%] sm:max-w-md sm:-translate-y-1/2">
        <DialogHeader className="shrink-0 space-y-1 border-b px-6 py-4">
          <DialogTitle className="flex items-center gap-2">
            <Wallet className="size-5 text-primary" /> Top up wallet
          </DialogTitle>
          <DialogDescription>
            Balance: {String(options?.wallet_balance_display || "—")} · paid by card, credited instantly.
          </DialogDescription>
        </DialogHeader>

        {!provider ? (
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-4">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Amount ({symbol})</label>
              <Input
                type="number"
                min={minMinor / 100}
                step={5}
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </div>
            <div className="flex flex-wrap gap-2">
              {(options?.suggested_amounts || []).slice(0, 4).map((t) => {
                const minor = Number(t.total_credit_pence || t.credit_pence || 0);
                if (!minor) return null;
                return (
                  <Button key={String(t.id)} variant="outline" size="sm" onClick={() => setAmount(String(minor / 100))}>
                    {String(t.total_credit_display || t.credit_display || `${symbol}${(minor / 100).toFixed(0)}`)}
                  </Button>
                );
              })}
            </div>
            {optionsQ.isLoading ? (
              <p className="text-sm text-muted-foreground">Loading payment methods…</p>
            ) : providers.length === 0 ? (
              <p className="text-sm text-destructive">
                Card payments are not configured yet. Contact support to top up your wallet.
              </p>
            ) : (
              <div className="grid gap-2">
                {providers.map((p) => (
                  <Button
                    key={p.id}
                    className="w-full justify-start gap-2"
                    variant="default"
                    disabled={intentM.isPending || amountMinor < minMinor}
                    onClick={() => void startPayment(p.id)}
                  >
                    {intentM.isPending && provider === p.id ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <CreditCard className="size-4" />
                    )}
                    Pay {symbol}{(amountMinor / 100).toFixed(2)} with {p.label}
                  </Button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <>
            <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
              <div ref={mountRef} className="min-h-[8rem] [&_.StripeElement]:max-w-full" />
              {!paymentReady && (
                <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" /> Preparing secure payment…
                </p>
              )}
            </div>
            <div className="flex shrink-0 items-center justify-between gap-2 border-t bg-background px-6 py-4">
              <Button variant="ghost" disabled={paying} onClick={() => { cleanupRef.current?.(); cleanupRef.current = null; setProvider(null); setPaymentReady(false); }}>
                Back
              </Button>
              {provider === "stripe" && paymentReady ? (
                <Button disabled={paying} onClick={() => void payWithStripe()}>
                  {paying ? <Loader2 className="size-4 animate-spin" /> : null}
                  Pay {symbol}{(amountMinor / 100).toFixed(2)}
                </Button>
              ) : null}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
