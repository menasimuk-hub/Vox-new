import { redirect } from "@tanstack/react-router";

import { apiFetch } from "@/lib/api";
import { canManageOrgSettings, isBillingOnlyRole } from "@/lib/org-roles";

type MeRole = {
  role?: string | null;
  tenant_role?: string | null;
};

export async function requireOrgSettingsAccess() {
  const me = await apiFetch<MeRole>("/auth/me");
  const role = me.role ?? me.tenant_role;
  if (!canManageOrgSettings(role)) {
    throw redirect({ to: "/settings/profile" });
  }
}

export async function requireBillingOnlyHome() {
  const me = await apiFetch<MeRole>("/auth/me");
  const role = me.role ?? me.tenant_role;
  if (isBillingOnlyRole(role)) {
    throw redirect({ to: "/account/billing" });
  }
}

export async function requireNonBillingOnlySettings() {
  const me = await apiFetch<MeRole>("/auth/me");
  const role = me.role ?? me.tenant_role;
  if (isBillingOnlyRole(role)) {
    throw redirect({ to: "/account/billing" });
  }
}
