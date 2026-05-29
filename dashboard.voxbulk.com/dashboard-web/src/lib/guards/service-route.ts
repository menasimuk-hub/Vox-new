import { redirect } from "@tanstack/react-router";

import { apiFetch } from "@/lib/api";
import { showRecoveryModules } from "@/lib/feature-flags";
import { enabledServicesFromApi, visibleFrom, type ServiceKey } from "@/lib/services";
import type { Organisation } from "@/lib/types/api";

export async function requireEnabledService(service: ServiceKey) {
  if (!showRecoveryModules && (service === "recovery" || service === "followup")) {
    throw redirect({ to: "/" });
  }

  const org = await apiFetch<Organisation>("/organisations/me");
  const allowed = enabledServicesFromApi(org.allowed_services ?? org.enabled_services);
  const enabled = enabledServicesFromApi(org.enabled_services);
  const visible = visibleFrom(allowed, enabled);
  if (!visible[service]) {
    throw redirect({ to: "/" });
  }
}
