import { createFileRoute } from "@tanstack/react-router";

import { IntegrationsSettingsPage } from "@/components/integrations-settings-page";
import { requireOrgSettingsAccess } from "@/lib/guards/settings-route";

const integrationsSearch = (s: Record<string, unknown>) => ({
  scheduling: typeof s.scheduling === "string" ? s.scheduling : undefined,
  provider: typeof s.provider === "string" ? s.provider : undefined,
  message: typeof s.message === "string" ? s.message : undefined,
  hubspot: typeof s.hubspot === "string" ? s.hubspot : undefined,
});

export const Route = createFileRoute("/_app/settings/integrations")({
  head: () => ({ meta: [{ title: "Integrations — VoxBulk" }] }),
  validateSearch: integrationsSearch,
  beforeLoad: () => requireOrgSettingsAccess(),
  component: IntegrationsSettingsRoute,
});

function IntegrationsSettingsRoute() {
  const search = Route.useSearch();
  return <IntegrationsSettingsPage search={search} />;
}
