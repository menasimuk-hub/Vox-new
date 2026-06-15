import { Link } from "@tanstack/react-router";
import { Building2, Check, ChevronDown, LogOut, Settings, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { logoutDashboard } from "@/lib/api";
import { canManageTeam, normalizeOrgRole } from "@/lib/org-roles";
import { useMyOrganisations, useSwitchOrganisation } from "@/lib/queries";
import { initialsFromName, useSession } from "@/lib/session";

function roleLabel(role: string) {
  const labels: Record<string, string> = {
    owner: "Owner",
    manager: "Manager",
    accountant: "Accountant",
    member: "Member",
    receptionist: "Receptionist",
  };
  return labels[role] || role;
}

export function UserMenu() {
  const { session } = useSession();
  const orgsQ = useMyOrganisations();
  const switchM = useSwitchOrganisation();

  const orgs = orgsQ.data?.organisations ?? [];
  const activeId = orgsQ.data?.active_org_id || session?.org?.id;
  const activeOrg = orgs.find((o) => o.org_id === activeId);
  const orgName = activeOrg?.name || session?.org?.name || session?.org?.display_name || "Company";
  const email = session?.profile?.email || "";
  const role = normalizeOrgRole(session?.profile?.role);
  const avatar = initialsFromName(orgName || email || "U");
  const showTeam = canManageTeam(role);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          className="h-9 gap-2 px-1.5 sm:px-2"
          aria-label="Account and company menu"
        >
          <span className="grid size-8 place-items-center rounded-full bg-accent text-accent-foreground text-xs font-semibold sm:size-9">
            {avatar}
          </span>
          <span className="hidden max-w-[120px] flex-col items-start text-left leading-tight md:flex">
            <span className="truncate text-xs font-medium">{orgName}</span>
            <span className="truncate text-[10px] text-muted-foreground capitalize">{roleLabel(role)}</span>
          </span>
          <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="font-normal">
          <p className="truncate text-sm font-medium">{email || "Signed in"}</p>
          <p className="truncate text-xs text-muted-foreground">
            Viewing {orgName} · {roleLabel(role)}
          </p>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-xs text-muted-foreground">Switch company</DropdownMenuLabel>
        {orgs.length === 0 ? (
          <DropdownMenuItem disabled className="text-xs text-muted-foreground">
            {orgsQ.isLoading ? "Loading…" : orgName}
          </DropdownMenuItem>
        ) : (
          orgs.map((org) => (
            <DropdownMenuItem
              key={org.org_id}
              disabled={switchM.isPending}
              onClick={() => {
                if (org.org_id !== activeId) switchM.mutate(org.org_id);
              }}
            >
              <Building2 className="mr-2 size-4 shrink-0 opacity-70" />
              <span className="flex-1 truncate">{org.name}</span>
              <span className="ml-2 text-[10px] capitalize text-muted-foreground">{org.role}</span>
              {org.org_id === activeId ? <Check className="ml-1 size-4 text-primary" /> : null}
            </DropdownMenuItem>
          ))
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/settings/profile" className="cursor-pointer">
            <Settings className="mr-2 size-4" />
            Organisation profile
          </Link>
        </DropdownMenuItem>
        {showTeam ? (
          <DropdownMenuItem asChild>
            <Link to="/settings/team" className="cursor-pointer">
              <Users className="mr-2 size-4" />
              Team members
            </Link>
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={() => logoutDashboard()}
          className="text-destructive focus:text-destructive"
        >
          <LogOut className="mr-2 size-4" />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
