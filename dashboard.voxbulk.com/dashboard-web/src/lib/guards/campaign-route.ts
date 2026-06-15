import { redirect } from "@tanstack/react-router";

import { apiFetch } from "@/lib/api";
import { canLaunchCampaigns } from "@/lib/org-roles";

type MeRole = {
  role?: string | null;
  tenant_role?: string | null;
};

export async function requireCampaignAccess() {
  const me = await apiFetch<MeRole>("/auth/me");
  const role = me.role ?? me.tenant_role;
  if (!canLaunchCampaigns(role)) {
    throw redirect({ to: "/account/billing" });
  }
}
