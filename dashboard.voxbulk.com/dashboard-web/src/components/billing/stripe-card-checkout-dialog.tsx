import * as React from "react";
import { CreditCard, Loader2 } from "lucide-react";
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
import { loadScript, type StripeElementsCheckout } from "@/lib/billing/subscription-payment";

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
    confirmParams?: { return_url?: string };
  }) => Promise<{ error?: { message?: string }; paymentIntent?: { id: string; status: string } }>;
};

type StripePaymentElement = {
  mount: (el: HTMLElement) => void;
  destroy: () => void;
  on: (event: string, handler: () => void) => void;
};

type StripeElements = {
  create: (kind: string, opts?: Record<string, unknown>) => StripePaymentElement;
};

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  session: StripeElementsCheckout | null;
  title?: string;
  description?: string;
  onPaid: (paymentIntentId: string) => void | Promise<void>;
};

/**
 * Subscription Stripe checkout — mounts Payment Element then confirms.
 * Uses a callback ref so we wait until Radix Dialog has painted the mount node
 * (otherwise the effect runs with mountRef=null and stays on “Loading…” forever).
 */
export function StripeCardCheckoutDialog({
  open,
  onOpenChange,
  session,
  title = "Pay with card",
  description = "Enter your card details to activate the subscription. Your card is saved for renewals.",
  onPaid,
}: Props) {
  const [ready, setReady] = React.useState(false);
  const [paying, setPaying] = React.useState(false);
  const [mountEl, setMountEl] = React.useState<HTMLDivElement | null>(null);
  const stripeRef = React.useRef<{ stripe: StripeJs; elements: StripeElements; intentId: string } | null>(
    null,
  );
  const cleanupRef = React.useRef<(() => void) | null>(null);
  const sessionKey = session
    ? `${session.payment_intent_id}:${session.client_secret.slice(0, 24)}`
    : "";

  const mountRefCb = React.useCallback((node: HTMLDivElement | null) => {
    setMountEl(node);
  }, []);

  React.useEffect(() => {
    if (!open || !session || !mountEl) {
      setReady(false);
      return;
    }

    let cancelled = false;
    let readyFallbackTimer: number | undefined;
    setReady(false);
    cleanupRef.current?.();
    cleanupRef.current = null;
    stripeRef.current = null;

    void (async () => {
      try {
        await loadScript("https://js.stripe.com/v3");
        if (cancelled || !window.Stripe) {
          if (!cancelled) throw new Error("Stripe.js failed to load");
          return;
        }
        const stripe = window.Stripe(session.publishable_key);
        const elements = stripe.elements({ clientSecret: session.client_secret });
        const paymentElement = elements.create("payment", {
          layout: "tabs",
          wallets: { applePay: "never", googlePay: "never" },
        });
        if (cancelled || !mountEl.isConnected) return;
        mountEl.innerHTML = "";
        paymentElement.on("ready", () => {
          if (!cancelled) setReady(true);
        });
        paymentElement.mount(mountEl);
        stripeRef.current = { stripe, elements, intentId: session.payment_intent_id };
        cleanupRef.current = () => {
          try {
            paymentElement.destroy();
          } catch {
            /* ignore */
          }
        };
        // Fallback if ready event is slow/missing in some browsers.
        readyFallbackTimer = window.setTimeout(() => {
          if (!cancelled) setReady(true);
        }, 2500);
      } catch (e) {
        if (!cancelled) {
          toast.error(e instanceof Error ? e.message : "Could not load Stripe");
          onOpenChange(false);
        }
      }
    })();

    return () => {
      cancelled = true;
      if (readyFallbackTimer) window.clearTimeout(readyFallbackTimer);
      cleanupRef.current?.();
      cleanupRef.current = null;
      stripeRef.current = null;
    };
  }, [open, sessionKey, mountEl, session, onOpenChange]);

  React.useEffect(() => {
    if (!open) {
      setPaying(false);
      setReady(false);
    }
  }, [open]);

  const pay = async () => {
    const ctx = stripeRef.current;
    const active = session;
    if (!ctx || !active) return;
    setPaying(true);
    try {
      const result = await ctx.stripe.confirmPayment({
        elements: ctx.elements,
        redirect: "if_required",
        confirmParams: { return_url: active.return_url },
      });
      if (result.error) {
        toast.error(result.error.message || "Payment failed");
        setPaying(false);
        return;
      }
      const intentId = result.paymentIntent?.id || ctx.intentId;
      await onPaid(intentId);
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Payment failed");
    } finally {
      setPaying(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="top-[4dvh] flex max-h-[min(92dvh,40rem)] w-[calc(100%-2rem)] translate-y-0 flex-col gap-0 overflow-hidden p-0 sm:top-[50%] sm:max-w-md sm:-translate-y-1/2">
        <DialogHeader className="shrink-0 space-y-1 border-b px-6 py-4">
          <DialogTitle className="flex items-center gap-2">
            <CreditCard className="size-5 text-primary" />
            {title}
          </DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-6 py-4">
          <div ref={mountRefCb} className="min-h-[180px]" />
          {!ready ? (
            <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Loading secure card form…
            </div>
          ) : null}
        </div>

        <DialogFooter className="shrink-0 border-t px-6 py-4">
          <Button type="button" variant="outline" disabled={paying} onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" disabled={!ready || paying} onClick={() => void pay()}>
            {paying ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" />
                Paying…
              </>
            ) : (
              "Pay now"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
