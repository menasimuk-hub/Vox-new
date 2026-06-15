/** Organisation role helpers — keep in sync with voxbulk-api/app/services/org_rbac.py */

export const ORG_ROLES = ["owner", "manager", "accountant", "member", "receptionist"] as const;
export type OrgRole = (typeof ORG_ROLES)[number];

export function normalizeOrgRole(role?: string | null): OrgRole {
  const r = String(role || "member").trim().toLowerCase();
  return (ORG_ROLES as readonly string[]).includes(r) ? (r as OrgRole) : "member";
}

export function canManageTeam(role?: string | null) {
  const r = normalizeOrgRole(role);
  return r === "owner" || r === "manager";
}

export function canAccessBilling(role?: string | null) {
  const r = normalizeOrgRole(role);
  return r === "owner" || r === "manager" || r === "accountant";
}

export function canLaunchCampaigns(role?: string | null) {
  const r = normalizeOrgRole(role);
  return r === "owner" || r === "manager" || r === "member" || r === "receptionist";
}
