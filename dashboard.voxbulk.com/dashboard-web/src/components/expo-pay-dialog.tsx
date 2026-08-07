import * as React from "react";
import { CheckCircle2, CreditCard, Loader2, Rocket } from "lucide-react";
import { toast } from "sonner";

import { PromoCodeRedeem } from "@/components/billing/promo-code-redeem";
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
import { formatExpoDay, formatExpoWindow } from "@/lib/expo-qr";

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

type BoothPaySnapshot = {
  activated_at?: string | null;
  expires_at?: string | null;
  is_live?: boolean;
  is_before_start?: boolean;
  is_paid?: boolean;
  payment_status?: string;
  paid_at?: string | null;
};

type PayOptions = {
  ok?: boolean;
  amount_minor?: number;
  amount_display?: string;
  currency?: string;
  is_paid?: boolean;
  payment_status?: string;
  providers?: Array<{ id: string; label: string; publishable_key?: string }>;
  quote?: {
    total_display?: string;
    amount_note?: string;
    discount_applied?: boolean;
    discount_display?: string | null;
    vat_display?: string | null;
    net_display?: string;
    catalog_display?: string;
    promo_code?: string | null;
    promo_label?: string | null;
    trial_days?: number;
    after_trial_display?: string | null;
    total_minor?: number;
  };
  booth?: BoothPaySnapshot;
};

type PaidResult = {
  booth?: Record<string, unknown>;
  amountLabel: string;
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
  const [paidResult, setPaidResult] = React.useState<PaidResult | null>(null);
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

  const loadOptions = React.useCallback(async () => {
    if (!boothId) return;
    setLoadingOptions(true);
    try {
      const res = await apiFetch<PayOptions>(`/expo/booths/${encodeURIComponent(boothId)}/pay/options`);
      setOptions(res);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not load payment options");
      onOpenChange(false);
    } finally {
      setLoadingOptions(false);
    }
  }, [boothId, onOpenChange]);

  React.useEffect(() => {
    if (!open || !boothId) {
      reset();
      setOptions(null);
      setPaidResult(null);
      zeroPriceActivateRef.current = false;
      return;
    }
    void loadOptions();
  }, [open, boothId, reset, loadOptions]);

  React.useEffect(() => {
    if (!open) reset();
  }, [open, reset]);

  const amountLabel = options?.quote?.total_display || options?.amount_display || "—";
  const windowLabel = formatExpoWindow(options?.booth?.activated_at, options?.booth?.expires_at);
  const startLabel = formatExpoDay(options?.booth?.activated_at);

  const showPaidSuccess = (booth?: Record<string, unknown>, paidAmount?: string) => {
    const label = paidAmount || amountLabel;
    setPaidResult({ booth, amountLabel: label });
    reset();
    const live = Boolean(booth?.is_live ?? options?.booth?.is_live);
    const activated = booth?.activated_at || options?.booth?.activated_at;
    const ends = booth?.expires_at || options?.booth?.expires_at;
    const win = formatExpoWindow(
      activated != null ? String(activated) : null,
      ends != null ? String(ends) : null,
    );
    toast.success(live ? "Payment received — booth is live" : "Payment received", {
      description: win
        ? `Package window ${win}${live ? "" : " · goes live on start date"}`
        : undefined,
    });
  };

  const dismissPaidSuccess = () => {
    const booth = paidResult?.booth;
    setPaidResult(null);
    onOpenChange(false);
    onPaid?.(booth);
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
        showPaidSuccess(res.booth, amountLabel);
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
        amount_minor?: number;
        booth?: Record<string, unknown>;
      }>(`/expo/booths/${encodeURIComponent(boothId)}/pay/intent`, {
        method: "POST",
        body: JSON.stringify({ provider: providerId }),
      });
      if (
        intent.paid ||
        intent.provider === "free" ||
        intent.provider === "signup_trial" ||
        intent.provider === "promo_discount"
      ) {
        showPaidSuccess(intent.booth, amountLabel === "—" ? "£0" : amountLabel);
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
    if (!open || !boothId || loadingOptions || !options || paidResult) return;
    if (options.is_paid) return;
    if (Number(options.amount_minor || 0) > 0) return;
    if (zeroPriceActivateRef.current || provider || intentPending || paying) return;
    zeroPriceActivateRef.current = true;
    void startPayment("free");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, boothId, loadingOptions, options, provider, intentPending, paying, paidResult]);

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
  const paidBooth = (paidResult?.booth || {}) as BoothPaySnapshot;
  const paidWindow =
    formatExpoWindow(
      paidBooth.activated_at != null ? String(paidBooth.activated_at) : options?.booth?.activated_at,
      paidBooth.expires_at != null ? String(paidBooth.expires_at) : options?.booth?.expires_at,
    ) || windowLabel;
  const paidLive = Boolean(paidBooth.is_live ?? options?.booth?.is_live);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && paidResult) {
          dismissPaidSuccess();
          return;
        }
        onOpenChange(next);
      }}
    >
      <DialogContent className="top-[4dvh] flex max-h-[min(92dvh,36rem)] w-[calc(100%-2rem)] translate-y-0 flex-col gap-0 overflow-hidden p-0 sm:top-[50%] sm:max-w-md sm:-translate-y-1/2">
        <DialogHeader className="shrink-0 space-y-1 border-b px-6 py-4">
          <DialogTitle className="flex items-center gap-2">
            {paidResult ? (
              <>
                <CheckCircle2 className="size-5 text-emerald-600" /> Payment received
              </>
            ) : (
              <>
                <Rocket className="size-5 text-primary" /> Pay Expo package
              </>
            )}
          </DialogTitle>
          <DialogDescription>
            {paidResult
              ? boothName
                ? `${boothName} is paid.`
                : "Your Expo package is paid."
              : `${boothName ? `${boothName} · ` : ""}${amountLabel}. Live exhibition only after payment.`}
          </DialogDescription>
        </DialogHeader>

        {paidResult ? (
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-4">
            <div className="rounded-xl border border-emerald-300/70 bg-emerald-50/80 p-4 text-sm dark:border-emerald-800 dark:bg-emerald-950/40">
              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800 dark:text-emerald-300">
                Amount paid
              </p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-foreground">
                {paidResult.amountLabel}
              </p>
              <div className="mt-3 space-y-1.5 border-t border-emerald-200/80 pt-3 dark:border-emerald-800">
                <div className="flex justify-between gap-3">
                  <span className="text-muted-foreground">Starts</span>
                  <span className="font-medium tabular-nums">
                    {formatExpoDay(
                      paidBooth.activated_at != null
                        ? String(paidBooth.activated_at)
                        : options?.booth?.activated_at,
                    ) || "—"}
                  </span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-muted-foreground">Ends</span>
                  <span className="font-medium tabular-nums">
                    {formatExpoDay(
                      paidBooth.expires_at != null ? String(paidBooth.expires_at) : options?.booth?.expires_at,
                    ) || "—"}
                  </span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-muted-foreground">Status</span>
                  <span className="font-medium">
                    {paidLive ? "Live now" : `Goes live ${formatExpoDay(paidBooth.activated_at != null ? String(paidBooth.activated_at) : options?.booth?.activated_at) || "on start date"}`}
                  </span>
                </div>
              </div>
              {paidWindow ? (
                <p className="mt-3 text-xs text-muted-foreground">Package window: {paidWindow}</p>
              ) : null}
            </div>
            <Button className="w-full" onClick={dismissPaidSuccess}>
              Continue to QR code
            </Button>
          </div>
        ) : !provider ? (
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
            ) : (
              <>
                <div className="space-y-1.5 rounded-lg border bg-muted/30 p-3 text-sm">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-muted-foreground">Package price</span>
                    <span className="tabular-nums font-medium">
                      {options?.quote?.catalog_display || options?.amount_display || "—"}
                    </span>
                  </div>
                  <div className="flex items-start justify-between gap-3">
                    <span className="text-muted-foreground">Promo</span>
                    <span className="max-w-[60%] text-right text-emerald-700 dark:text-emerald-400">
                      {options?.quote?.discount_applied
                        ? [
                            options.quote.promo_code ? `Promo ${options.quote.promo_code}` : "Promo",
                            options.quote.promo_label ||
                              (options.quote.discount_display ? `−${options.quote.discount_display}` : null),
                          ]
                            .filter(Boolean)
                            .join(" · ")
                        : "No promo applied"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-t pt-2">
                    <span className="font-medium">Total due today</span>
                    <span className="text-lg font-semibold tabular-nums">{amountLabel}</span>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-t pt-2">
                    <span className="text-muted-foreground">Live window</span>
                    <span className="max-w-[60%] text-right font-medium tabular-nums">
                      {windowLabel || (startLabel ? `From ${startLabel}` : "Set on booth")}
                    </span>
                  </div>
                  {options?.quote?.amount_note ? (
                    <p className="text-xs text-muted-foreground">{options.quote.amount_note}</p>
                  ) : null}
                </div>
                <PromoCodeRedeem
                  serviceHint="Expo"
                  compact
                  onRedeemed={() => {
                    void loadOptions();
                  }}
                />
                {providers.length === 0 ? (
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
                        Pay {amountLabel} with card
                      </Button>
                    ))}
                  </div>
                )}
              </>
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
