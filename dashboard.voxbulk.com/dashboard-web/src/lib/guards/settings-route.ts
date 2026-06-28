import { redirect } from "@tanstack/react-router";

import { apiFetch } from "@/lib/api";
import { canManageOrgSettings, isBillingOnlyRole } from "@/lib/org-roles";

type MeRole = {
  role?: string | null;
  tenant_role?: string | null;
  is_sales_rep?: boolean;
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
  // Salesmen now use the full dashboard, so they stay on the home route.
  if (me.is_sales_rep) return;
  const role = me.role ?? me.tenant_role;
  if (isBillingOnlyRole(role)) {
    throw redirect({ to: "/account/billing" });
  }
}

export async function requireSalesRep() {
  try {
    const me = await apiFetch<MeRole>("/auth/me");
    if (!me?.is_sales_rep) throw redirect({ to: "/" });
  } catch (e) {
    if (e && typeof e === "object" && "to" in (e as Record<string, unknown>)) throw e;
    throw redirect({ to: "/login" });
  }
}

export async function requireNonBillingOnlySettings() {
  const me = await apiFetch<MeRole>("/auth/me");
  const role = me.role ?? me.tenant_role;
  if (isBillingOnlyRole(role)) {
    throw redirect({ to: "/account/billing" });
  }
}
