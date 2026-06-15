import { redirect } from "@tanstack/react-router";

import { apiFetch } from "@/lib/api";
import { canAccessBilling } from "@/lib/org-roles";

type MeRole = {
  role?: string | null;
  tenant_role?: string | null;
};

export async function requireBillingAccess() {
  const me = await apiFetch<MeRole>("/auth/me");
  const role = me.role ?? me.tenant_role;
  if (!canAccessBilling(role)) {
    throw redirect({ to: "/" });
  }
}
