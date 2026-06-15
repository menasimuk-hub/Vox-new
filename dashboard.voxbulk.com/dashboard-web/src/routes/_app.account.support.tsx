import { createFileRoute, Outlet } from "@tanstack/react-router";

import { requireBillingAccess } from "@/lib/guards/billing-route";

export const Route = createFileRoute("/_app/account/support")({
  beforeLoad: () => requireBillingAccess(),
  component: () => <Outlet />,
});
