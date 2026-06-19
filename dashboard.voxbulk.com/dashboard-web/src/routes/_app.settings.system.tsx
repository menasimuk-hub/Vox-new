import { createFileRoute } from "@tanstack/react-router";

import { IntegrationsSettingsPage } from "@/components/integrations-settings-page";
import { requireOrgSettingsAccess } from "@/lib/guards/settings-route";

const integrationsSearch = (s: Record<string, unknown>) => {
  const tab = typeof s.tab === "string" ? s.tab : undefined;
  const microsoft = typeof s.microsoft_calendar === "string" ? s.microsoft_calendar : undefined;
  const scheduling = typeof s.scheduling === "string" ? s.scheduling : microsoft;
  const provider =
    typeof s.provider === "string"
      ? s.provider
      : microsoft
        ? "microsoft_calendar"
        : undefined;
  return {
    scheduling,
    provider,
    message: typeof s.message === "string" ? s.message : undefined,
    hubspot: typeof s.hubspot === "string" ? s.hubspot : undefined,
    tab: tab === "crm" || tab === "booking" ? tab : undefined,
  };
};

export const Route = createFileRoute("/_app/settings/system")({
  head: () => ({ meta: [{ title: "Integrations — VoxBulk" }] }),
  validateSearch: integrationsSearch,
  beforeLoad: () => requireOrgSettingsAccess(),
  component: SystemSettingsRoute,
});

/** Legacy URL kept for OAuth callbacks (`/settings/system?hubspot=connected`). */
function SystemSettingsRoute() {
  const search = Route.useSearch();
  return <IntegrationsSettingsPage search={search} />;
}
