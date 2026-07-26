import * as React from "react";
import { CreditCard, Loader2, Rocket } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { redirectToAirwallexHostedCheckout } from "@/lib/billing/airwallex-hpp";
import { apiFetch } from "@/lib/api";

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
type StripeElements = {
  create: (kind: string, opts?: Record<string, unknown>) => { mount: (el: HTMLElement) => void; destroy: () => void };
};

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

type PayOptions = {
  ok?: boolean;
  amount_minor?: number;
  amount_display?: string;
  currency?: string;
  is_paid?: boolean;
  payment_status?: string;
  providers?: Array<{ id: string; label: string; publishable_key?: string }>;
  booth?: {
    activated_at?: string | null;
    is_live?: boolean;
    is_before_start?: boolean;
  };
};

type Props = {
  boothId: string | null;
  boothName?: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPaid?: (booth?: Record<string, unknown>) => void;
};

export function ExpoPayDialog({ boothId, boothName, open, onOpenChange, onPaid }: Props) {
  const [options, setOptions] = React.useState<PayOptions | null>(null);
  const [loadingOptions, setLoadingOptions] = React.useState(false);
  const [provider, setProvider] = React.useState<string | null>(null);
  const [intentPending, setIntentPending] = React.useState(false);
  const [paying, setPaying] = React.useState(false);
  const [paymentReady, setPaymentReady] = React.useState(false);
  const mountRef = React.useRef<HTMLDivElement | null>(null);
  const stripeRef = React.useRef<{ stripe: StripeJs; elements: StripeElements; intentId: string } | null>(null);
  const cleanupRef = React.useRef<(() => void) | null>(null);
  const zeroPriceActivateRef = React.useRef(false);

  const reset = React.useCallback(() => {
    cleanupRef.current?.();
    cleanupRef.current = null;
    stripeRef.current = null;
    setProvider(null);
    setPaymentReady(false);
    setIntentPending(false);
    setPaying(false);
  }, []);

  React.useEffect(() => {
    if (!open || !boothId) {
      reset();
      setOptions(null);
      zeroPriceActivateRef.current = false;
      return;
    }
    let cancelled = false;
    setLoadingOptions(true);
    void (async () => {
      try {
        const res = await apiFetch<PayOptions>(`/expo/booths/${encodeURIComponent(boothId)}/pay/options`);
        if (!cancelled) setOptions(res);
      } catch (e) {
        if (!cancelled) {
          toast.error(e instanceof Error ? e.message : "Could not load payment options");
          onOpenChange(false);
        }
      } finally {
        if (!cancelled) setLoadingOptions(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, boothId, onOpenChange, reset]);

  React.useEffect(() => {
    if (!open) reset();
  }, [open, reset]);

  const paidToast = (booth?: Record<string, unknown>) => {
    const activated = booth?.activated_at || options?.booth?.activated_at;
    const live = Boolean(booth?.is_live ?? options?.booth?.is_live);
    if (live) {
      toast.success("Paid — Expo booth is live");
      return;
    }
    const startLabel = activated
      ? new Date(String(activated)).toLocaleDateString("en-GB", {
          day: "numeric",
          month: "short",
          year: "numeric",
        })
      : "your start date";
    toast.success(`Paid — goes live on ${startLabel}`);
  };

  const finishPayment = async (providerId: string, intentId: string) => {
    if (!boothId) return;
    try {
      const res = await apiFetch<{
        paid?: boolean;
        duplicate?: boolean;
        booth?: Record<string, unknown>;
        status?: string;
      }>(`/expo/booths/${encodeURIComponent(boothId)}/pay/confirm`, {
        method: "POST",
        body: JSON.stringify({ provider: providerId, payment_intent_id: intentId }),
      });
      if (res.paid || res.duplicate) {
        paidToast(res.booth);
        onOpenChange(false);
        onPaid?.(res.booth);
      } else {
        toast.message("Payment is still processing", {
          description: "Your booth will unlock as soon as the payment settles.",
        });
        onOpenChange(false);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not verify payment");
    } finally {
      setPaying(false);
    }
  };

  const startPayment = async (providerId: string) => {
    if (!boothId) return;
    setProvider(providerId);
    setPaymentReady(false);
    setIntentPending(true);
    try {
      const intent = await apiFetch<{
        provider?: string;
        paid?: boolean;
        client_secret?: string;
        publishable_key?: string;
        payment_intent_id?: string;
        currency?: string;
        environment?: string;
        booth?: Record<string, unknown>;
      }>(`/expo/booths/${encodeURIComponent(boothId)}/pay/intent`, {
        method: "POST",
        body: JSON.stringify({ provider: providerId }),
      });
      if (intent.paid || intent.provider === "free" || intent.provider === "signup_trial") {
        paidToast(intent.booth);
        onOpenChange(false);
        onPaid?.(intent.booth);
        return;
      }
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
          currency: String(intent.currency || options?.currency || "GBP"),
          environment: String(intent.environment || "demo"),
          pending: {
            flow: "expo",
            payment_intent_id: intent.payment_intent_id,
            booth_id: boothId,
          },
          returnPath: `${window.location.pathname}${window.location.search}`,
        });
      }
    } catch (e) {
      setProvider(null);
      toast.error(e instanceof Error ? e.message : "Could not start payment");
    } finally {
      setIntentPending(false);
    }
  };

  // Zero-price packages (incl. silent signup trial): activate without card UI.
  React.useEffect(() => {
    if (!open || !boothId || loadingOptions || !options) return;
    if (options.is_paid) return;
    if (Number(options.amount_minor || 0) > 0) return;
    if (zeroPriceActivateRef.current || provider || intentPending || paying) return;
    zeroPriceActivateRef.current = true;
    void startPayment("free");
    // startPayment is stable enough for one-shot £0 activate; omit from deps to avoid loops.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, boothId, loadingOptions, options, provider, intentPending, paying]);

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
  const amountLabel = options?.amount_display || "—";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="top-[4dvh] flex max-h-[min(92dvh,36rem)] w-[calc(100%-2rem)] translate-y-0 flex-col gap-0 overflow-hidden p-0 sm:top-[50%] sm:max-w-md sm:-translate-y-1/2">
        <DialogHeader className="shrink-0 space-y-1 border-b px-6 py-4">
          <DialogTitle className="flex items-center gap-2">
            <Rocket className="size-5 text-primary" /> Pay Expo package
          </DialogTitle>
          <DialogDescription>
            {boothName ? `${boothName} · ` : ""}
            {amountLabel}. Design and preview tests work unpaid; live exhibition starts after payment.
          </DialogDescription>
        </DialogHeader>

        {!provider ? (
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-4">
            {loadingOptions ? (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Loading payment methods…
              </p>
            ) : options?.is_paid ? (
              <p className="text-sm text-muted-foreground">This booth is already paid.</p>
            ) : Number(options?.amount_minor || 0) <= 0 ? (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Activating package…
              </p>
            ) : providers.length === 0 ? (
              <p className="text-sm text-destructive">
                Card payments are not configured yet. Contact support to pay for your Expo package.
              </p>
            ) : (
              <div className="grid gap-2">
                {providers.map((p) => (
                  <Button
                    key={p.id}
                    className="w-full justify-start gap-2"
                    disabled={intentPending}
                    onClick={() => void startPayment(p.id)}
                  >
                    {intentPending && provider === p.id ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <CreditCard className="size-4" />
                    )}
                    Pay with {p.label}
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
              <Button
                variant="ghost"
                disabled={paying}
                onClick={() => {
                  cleanupRef.current?.();
                  cleanupRef.current = null;
                  setProvider(null);
                  setPaymentReady(false);
                }}
              >
                Back
              </Button>
              {provider === "stripe" && paymentReady ? (
                <Button disabled={paying} onClick={() => void payWithStripe()}>
                  {paying ? <Loader2 className="size-4 animate-spin" /> : null}
                  Pay {amountLabel}
                </Button>
              ) : null}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
