import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/account/smart-card/packages")({
  validateSearch: (search: Record<string, unknown>) => ({
    billing: typeof search.billing === "string" ? search.billing : undefined,
    payment_intent: typeof search.payment_intent === "string" ? search.payment_intent : undefined,
    payment_intent_client_secret:
      typeof search.payment_intent_client_secret === "string"
        ? search.payment_intent_client_secret
        : undefined,
    redirect_flow_id: typeof search.redirect_flow_id === "string" ? search.redirect_flow_id : undefined,
  }),
  beforeLoad: ({ search }) => {
    throw redirect({
      to: "/account/packages",
      search: {
        tab: "smartCard",
        billing: search.billing,
        payment_intent: search.payment_intent,
        payment_intent_client_secret: search.payment_intent_client_secret,
        redirect_flow_id: search.redirect_flow_id,
      },
    });
  },
});
