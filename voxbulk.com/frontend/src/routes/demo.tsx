import { Outlet, createFileRoute } from "@tanstack/react-router";

/** Layout so `/demo` (request form) and `/demo/session` + `/demo/resend` coexist. */
export const Route = createFileRoute("/demo")({
  component: () => <Outlet />,
});
