import { isRedirect, redirect } from "@tanstack/react-router";

import { apiFetch } from "@/lib/api";
import { requireCampaignAccess } from "@/lib/guards/campaign-route";
import { showRecoveryModules } from "@/lib/feature-flags";
import { fromAllowedApi, fromEnabledApi, visibleFrom, type ServiceKey } from "@/lib/services";
import type { Organisation } from "@/lib/types/api";

type AppointmentSettings = { setup_complete?: boolean };

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

/** Appointments module — includes reminder sequences (legacy follow_up compat). */
export async function requireAppointmentsModule() {
  await requireCampaignAccess();
  const org = await apiFetch<Organisation>("/organisations/me");
  const allowed = fromAllowedApi(org.allowed_services);
  const enabled = fromEnabledApi(org.enabled_services);
  const visible = visibleFrom(allowed, enabled);
  if (!visible.appointments && !(showRecoveryModules && visible.followup)) {
    throw redirect({ to: "/" });
  }
}

/** Appointments routes — enable check + auto-open setup wizard until complete. */
export async function requireAppointmentsRoute(location: { pathname: string }) {
  await requireEnabledService("appointments");
  const path = String(location.pathname || "");
  if (path.includes("/appointments/setup")) return;

  try {
    const settings = await apiFetch<AppointmentSettings>("/appointments/settings");
    if (!settings.setup_complete) {
      throw redirect({ to: "/appointments/setup" });
    }
  } catch (e) {
    if (isRedirect(e)) throw e;
  }
}
