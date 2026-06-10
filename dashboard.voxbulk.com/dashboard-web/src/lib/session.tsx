import * as React from "react";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";



import { toast } from "sonner";



import { apiFetch, ApiError, getAccessToken, logoutDashboard, redirectToSignIn } from "@/lib/api";
import {
  consumeAuthHandoffFromHash,
  hasAuthHandoffInHash,
  storeAuthHandoffFromHash,
  stripAuthHashFromUrl,
} from "@/lib/auth-handoff";
import { notifyInterviewLaunch } from "@/lib/interviewLaunchFeedback";

import {

  clearBillingQuery,

  clearBillingReturnState,

  completeGoCardlessOrderPayment,
  completeGoCardlessMandateUpdate,
  completeGoCardlessSubscription,
  GC_ORDER_ID_KEY,
  readBillingReturnParams,
  resolveRedirectFlowId,
  startGoCardlessOrderPayment,
  startPaidInterviewOrder,
  startPaidSurveyOrder,
} from "@/lib/billing/gocardless";

import type { BillingSubscription, Organisation, UserProfile } from "@/lib/types/api";



export type SessionState = {

  profile: UserProfile;

  org: Organisation | null;

  subscription: BillingSubscription | null;

};



const SessionCtx = React.createContext<{

  session: SessionState | null;

  loading: boolean;

  error: string;

  refetch: () => void;

}>({

  session: null,

  loading: true,

  error: "",

  refetch: () => {},

});



async function loadSession(): Promise<SessionState> {

  const [profile, org, subscription] = await Promise.all([

    apiFetch<UserProfile>("/auth/me"),

    apiFetch<Organisation>("/organisations/me").catch(() => null),

    apiFetch<BillingSubscription>("/billing/subscription").catch(() => null),

  ]);

  return { profile, org, subscription };

}



function isAuthSessionFailure(err: unknown) {

  if (err instanceof ApiError) {

    return err.status === 401 || err.status === 403;

  }

  return false;

}



function GoCardlessReturnHandler({ onComplete }: { onComplete: () => void }) {

  const ran = React.useRef(false);
  const navigate = useNavigate();

  React.useEffect(() => {

    if (ran.current) return;

    const params = readBillingReturnParams();

    if (!params?.billing && !params?.orderBilling) return;

    ran.current = true;



    if (params?.orderBilling === "cancelled") {

      clearBillingReturnState("order");

      clearBillingQuery();

      toast.message("Payment cancelled");

      return;

    }



    if (params?.billing === "cancelled") {

      clearBillingReturnState("subscription");

      clearBillingQuery();

      toast.message("Payment setup cancelled");

      return;

    }

    if (params?.billing === "mandate_cancelled") {
      clearBillingReturnState("mandate");
      clearBillingQuery();
      toast.message("Direct Debit update cancelled — your existing mandate is unchanged.");
      return;
    }

    if (params?.billing === "mandate_success") {
      const redirectFlowId = resolveRedirectFlowId(params, "mandate");
      if (!redirectFlowId) {
        toast.error("Direct Debit update completed but checkout session was not found.");
        clearBillingQuery();
        return;
      }
      void (async () => {
        try {
          await completeGoCardlessMandateUpdate(redirectFlowId);
          clearBillingReturnState("mandate");
          clearBillingQuery();
          toast.success("Direct Debit details updated successfully.");
          onComplete();
        } catch (e) {
          toast.error(e instanceof Error ? e.message : "Could not complete Direct Debit update");
        }
      })();
      return;
    }



    if (params?.billing === "error" || params?.orderBilling === "error") {

      clearBillingQuery();

      toast.error("Payment return failed. Please try again.");

      return;

    }



    if (params?.orderBilling === "success") {

      const redirectFlowId = resolveRedirectFlowId(params, "order");
      const paidOrderId = params.orderId || (() => {
        try {
          return (sessionStorage.getItem(GC_ORDER_ID_KEY) || "").trim();
        } catch {
          return "";
        }
      })();
      clearBillingReturnState("order");
      clearBillingQuery();

      if (!redirectFlowId) {
        toast.error("Payment completed but checkout session was not found.");
        return;
      }
      void (async () => {
        try {
          const result = await completeGoCardlessOrderPayment(redirectFlowId);
          const order = result?.order;
          const resolvedOrderId = String(order?.id || paidOrderId || "");

          if (order?.payment_status === "approved" && resolvedOrderId) {
            if (order.service_code === "interview") {
              try {
                const launched = await startPaidInterviewOrder(resolvedOrderId);
                const emailN = Number(launched?.invites?.email_sent ?? 0);
                const waN = Number(launched?.invites?.whatsapp_sent ?? 0);
                if (launched?.ok === false || emailN < 1) {
                  notifyInterviewLaunch(launched);
                  toast.success("Payment approved.");
                  const errs = Array.isArray(launched?.invites?.errors)
                    ? launched!.invites!.errors!.filter(Boolean)
                    : [];
                  const detail =
                    errs[0] ||
                    launched?.message ||
                    (waN > 0
                      ? "WhatsApp was sent but invite email was not — open the interview and tap Launch or Resend."
                      : "Launch failed — open the interview and tap Launch.");
                  toast.error(detail);
                  void navigate({
                    to: "/interviews/new",
                    search: { order_id: resolvedOrderId },
                  });
                  return;
                }
                notifyInterviewLaunch(launched);
                void navigate({
                  to: "/interviews/new",
                  search: { order_id: resolvedOrderId },
                });
              } catch (launchErr) {
                toast.success("Payment approved.");
                toast.error(
                  launchErr instanceof Error
                    ? launchErr.message
                    : "Payment succeeded but launch failed — open your interview and tap Launch.",
                );
                void navigate({
                  to: "/interviews/new",
                  search: { order_id: resolvedOrderId },
                });
              }
            } else if (order?.service_code === "survey") {
              try {
                const launched = await startPaidSurveyOrder(resolvedOrderId, "now");
                toast.success(launched.message || "Payment approved — survey launched.");
                void navigate({
                  to: "/surveys/results",
                  search: { orderId: resolvedOrderId },
                  replace: true,
                });
              } catch (launchErr) {
                toast.success("Payment approved.");
                toast.error(
                  launchErr instanceof Error
                    ? launchErr.message
                    : "Payment succeeded but launch failed — open your survey and try again.",
                );
                void navigate({
                  to: "/surveys/results",
                  search: { orderId: resolvedOrderId },
                  replace: true,
                });
              }
            } else {
              toast.success("Payment approved — campaign is ready.");
            }
          } else {
            toast.success("GoCardless payment completed.");
          }

          onComplete();
        } catch (e) {
          toast.error(e instanceof Error ? e.message : "Could not complete GoCardless payment");
        }
      })();

      return;
    }



    if (params?.billing !== "success") return;

    const redirectFlowId = resolveRedirectFlowId(params, "subscription");

    if (!redirectFlowId) {

      toast.error("Payment completed but checkout session was not found.");

      clearBillingQuery();

      return;

    }

    void (async () => {

      try {

        await completeGoCardlessSubscription(redirectFlowId);

        clearBillingReturnState("subscription");

        clearBillingQuery();

        toast.success("Subscription activated successfully.");

        onComplete();

      } catch (e) {

        toast.error(e instanceof Error ? e.message : "Could not complete GoCardless checkout");

      }

    })();

  }, [onComplete]);

  return null;

}



export function SessionProvider({ children }: { children: React.ReactNode }) {

  const [token, setToken] = React.useState(() => {
    if (typeof window === "undefined") return "";
    const handoffToken = storeAuthHandoffFromHash();
    if (handoffToken) return handoffToken;
    return getAccessToken();
  });

  const qc = useQueryClient();

  React.useLayoutEffect(() => {
    if (hasAuthHandoffInHash()) {
      consumeAuthHandoffFromHash();
    } else if (window.location.hash.includes("access_token")) {
      stripAuthHashFromUrl();
    }
    setToken(getAccessToken());
  }, []);

  React.useEffect(() => {
    const sync = () => setToken(getAccessToken());
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);



  const q = useQuery({

    queryKey: ["session", token],

    queryFn: loadSession,

    enabled: Boolean(token),

    retry: false,

    staleTime: 60_000,

  });



  React.useEffect(() => {
    if (token || hasAuthHandoffInHash()) return;
    redirectToSignIn();
  }, [token]);



  React.useEffect(() => {

    if (q.error && "status" in (q.error as object) && (q.error as { status?: number }).status === 401) {

      logoutDashboard();

    }

  }, [q.error]);



  const value = React.useMemo(

    () => ({

      session: q.data ?? null,

      loading: Boolean(token) && q.isLoading,

      error: q.error instanceof Error ? q.error.message : "",

      refetch: () => void q.refetch(),

    }),

    [q.data, q.error, q.isLoading, q.refetch, token],

  );



  const onBillingComplete = React.useCallback(() => {

    void q.refetch();

    void qc.invalidateQueries({ queryKey: ["service-orders"] });

    void qc.invalidateQueries({ queryKey: ["interview-draft"] });

  }, [q, qc]);



  if (!token && !hasAuthHandoffInHash()) return null;

  if (!token) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <div className="max-w-sm text-center">
          <h2 className="text-lg font-semibold tracking-tight">Signing you in…</h2>
          <p className="mt-2 text-sm text-muted-foreground">Finishing login handoff.</p>
        </div>
      </div>
    );
  }



  if (value.loading) {

    return (

      <div className="flex min-h-screen items-center justify-center bg-background px-4">

        <div className="max-w-sm text-center">

          <h2 className="text-lg font-semibold tracking-tight">Loading your dashboard…</h2>

          <p className="mt-2 text-sm text-muted-foreground">Checking your VoxBulk session.</p>

        </div>

      </div>

    );

  }



  if (value.error && !value.session && isAuthSessionFailure(q.error)) {

    return (

      <div className="flex min-h-screen items-center justify-center bg-background px-4">

        <div className="max-w-sm text-center">

          <h2 className="text-lg font-semibold tracking-tight">Session expired</h2>

          <p className="mt-2 text-sm text-muted-foreground">Sign in again to continue.</p>

          <div className="mt-6 flex flex-wrap justify-center gap-2">

            <button

              type="button"

              className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"

              onClick={() => redirectToSignIn()}

            >

              Go to sign in

            </button>

            <button

              type="button"

              className="inline-flex items-center justify-center rounded-md border border-input px-4 py-2 text-sm font-medium"

              onClick={() => logoutDashboard()}

            >

              Log out

            </button>

          </div>

        </div>

      </div>

    );

  }



  return (

    <SessionCtx.Provider value={value}>

      <GoCardlessReturnHandler onComplete={onBillingComplete} />

      {children}

    </SessionCtx.Provider>

  );

}



export function useSession() {

  return React.useContext(SessionCtx);

}



export function initialsFromName(name?: string | null) {

  const parts = String(name || "")

    .trim()

    .split(/\s+/)

    .filter(Boolean);

  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();

  return String(name || "VB")

    .slice(0, 2)

    .toUpperCase();

}

