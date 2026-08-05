import { Outlet, createFileRoute } from "@tanstack/react-router";

/** Layout so `/smart-card` (marketing) and `/smart-card/$token` (scan app) coexist. */
export const Route = createFileRoute("/smart-card")({
  component: () => <Outlet />,
});
