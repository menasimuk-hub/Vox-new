import * as React from "react";

import { useQuery, useQueryClient } from "@tanstack/react-query";



import { toast } from "sonner";



import { apiFetch, getAccessToken, logoutDashboard, redirectToSignIn } from "@/lib/api";

import {

  clearBillingQuery,

  clearBillingReturnState,

  completeGoCardlessOrderPayment,

  completeGoCardlessSubscription,

  readBillingReturnParams,

  resolveRedirectFlowId,

  startPaidInterviewOrder,

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



function GoCardlessReturnHandler({ onComplete }: { onComplete: () => void }) {

  const ran = React.useRef(false);

  React.useEffect(() => {

    if (ran.current) return;

    const params = readBillingReturnParams();

    if (!params.billing && !params.orderBilling) return;

    ran.current = true;



    if (params.orderBilling === "cancelled") {

      clearBillingReturnState("order");

      clearBillingQuery();

      toast.message("Payment cancelled");

      return;

    }



    if (params.billing === "cancelled") {

      clearBillingReturnState("subscription");

      clearBillingQuery();

      toast.message("Payment setup cancelled");

      return;

    }



    if (params.billing === "error" || params.orderBilling === "error") {

      clearBillingQuery();

      toast.error("Payment return failed. Please try again.");

      return;

    }



    if (params.orderBilling === "success") {

      const redirectFlowId = resolveRedirectFlowId(params, "order");

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

          if (order?.payment_status === "approved" && order.id) {
            if (order.service_code === "interview") {
              const launched = await startPaidInterviewOrder(order.id);
              const wa = Number(launched?.invites?.whatsapp_sent || 0);
              toast.success(
                wa > 0
                  ? `Payment approved — WhatsApp booking invites sent to ${wa} candidate(s).`
                  : launched?.message || "Payment approved — candidates can book their interview slots.",
              );
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



    if (params.billing !== "success") return;

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

  const token = typeof window !== "undefined" ? getAccessToken() : "";

  const qc = useQueryClient();



  const q = useQuery({

    queryKey: ["session", token],

    queryFn: loadSession,

    enabled: Boolean(token),

    retry: false,

    staleTime: 60_000,

  });



  React.useEffect(() => {

    if (!token) redirectToSignIn();

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



  if (!token) return null;



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



  if (value.error && !value.session) {

    return (

      <div className="flex min-h-screen items-center justify-center bg-background px-4">

        <div className="max-w-sm text-center">

          <h2 className="text-lg font-semibold tracking-tight">Session error</h2>

          <p className="mt-2 text-sm text-muted-foreground">{value.error}</p>

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

