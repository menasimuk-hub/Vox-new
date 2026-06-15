import { redirect } from "@tanstack/react-router";

import { apiFetch } from "@/lib/api";
import { requireCampaignAccess } from "@/lib/guards/campaign-route";
import { showRecoveryModules } from "@/lib/feature-flags";
import { fromAllowedApi, fromEnabledApi, visibleFrom, type ServiceKey } from "@/lib/services";
import type { Organisation } from "@/lib/types/api";

export async function requireEnabledService(service: ServiceKey) {
  await requireCampaignAccess();

  if (!showRecoveryModules && (service === "recovery" || service === "followup")) {
    throw redirect({ to: "/" });
  }

  const org = await apiFetch<Organisation>("/organisations/me");
  const allowed = fromAllowedApi(org.allowed_services);
  const enabled = fromEnabledApi(org.enabled_services);
  const visible = visibleFrom(allowed, enabled);
  if (!visible[service]) {
    throw redirect({ to: "/" });
  }
}
