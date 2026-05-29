import { createFileRoute, Outlet } from "@tanstack/react-router";

import { requireRecoveryModules } from "@/lib/guards/recovery-route";

export const Route = createFileRoute("/_app/recovery")({
  beforeLoad: requireRecoveryModules,
  component: () => <Outlet />,
});
