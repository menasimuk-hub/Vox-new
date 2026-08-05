import { Outlet, createFileRoute } from "@tanstack/react-router";

/** Layout so `/expo` (marketing) and `/expo/$token` (scan app) coexist. */
export const Route = createFileRoute("/expo")({
  component: () => <Outlet />,
});
