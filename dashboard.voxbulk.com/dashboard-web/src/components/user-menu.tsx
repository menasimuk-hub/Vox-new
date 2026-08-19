import { Building2, Check, ChevronDown, Home, LogOut, Star } from "lucide-react";
import type { MouseEvent } from "react";
import { toast } from "sonner";

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
import { normalizeOrgRole } from "@/lib/org-roles";
import { useMyOrganisations, useOrganisation, useSetPreferredOrganisation, useSwitchOrganisation } from "@/lib/queries";
import { initialsFromName, useSession } from "@/lib/session";
import { useOrgLogoPreview } from "@/lib/use-org-logo";

function roleLabel(role: string) {
  const labels: Record<string, string> = {
    owner: "Owner",
    manager: "Manager",
    accountant: "Accountant",
    member: "Member",
  };
  return labels[role] || role;
}

export function UserMenu() {
  const { session } = useSession();
  const orgsQ = useMyOrganisations();
  const orgQ = useOrganisation();
  const switchM = useSwitchOrganisation();
  const preferredM = useSetPreferredOrganisation();

  const orgs = orgsQ.data?.organisations ?? [];
  const activeId = orgsQ.data?.active_org_id || session?.org?.id;
  const activeOrg = orgs.find((o) => o.org_id === activeId);
  const orgName = activeOrg?.name || session?.org?.name || session?.org?.display_name || "Company";
  const email = session?.profile?.email || "";
  const role = normalizeOrgRole(session?.profile?.role);
  const avatar = initialsFromName(orgName || email || "U");
  const orgLogo = useOrgLogoPreview(orgQ.data?.logo_url || session?.org?.logo_url);
  const showSwitcher = orgs.length > 1;

  const setMain = (orgId: string, isMain: boolean, e: MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    preferredM.mutate(isMain ? null : orgId, {
      onSuccess: () => {
        toast.success(isMain ? "Main company cleared" : "Main company saved — used when you sign in");
      },
      onError: (err) => {
        toast.error(err instanceof Error ? err.message : "Could not update main company");
      },
    });
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          className="h-9 gap-2 px-1.5 sm:px-2"
          aria-label="Account and company menu"
        >
          {orgLogo ? (
            <img
              src={orgLogo}
              alt=""
              className="size-8 shrink-0 rounded-full object-cover bg-white ring-1 ring-border sm:size-9"
            />
          ) : (
            <span className="grid size-8 place-items-center rounded-full bg-accent text-accent-foreground text-xs font-semibold sm:size-9">
              {avatar}
            </span>
          )}
          <span className="hidden max-w-[120px] flex-col items-start text-left leading-tight md:flex">
            <span className="truncate text-xs font-medium">{orgName}</span>
            <span className="truncate text-[10px] text-muted-foreground capitalize">{roleLabel(role)}</span>
          </span>
          <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel className="font-normal">
          <p className="truncate text-sm font-medium">{email || "Signed in"}</p>
          <p className="truncate text-xs text-muted-foreground">
            Viewing {orgName} · {roleLabel(role)}
          </p>
        </DropdownMenuLabel>
        {showSwitcher ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="text-xs text-muted-foreground">
              Switch company · star = main on login
            </DropdownMenuLabel>
            {orgs.map((org) => {
              const OrgIcon = org.is_owner ? Home : Building2;
              const isMain = Boolean(org.is_main);
              return (
                <DropdownMenuItem
                  key={org.org_id}
                  disabled={switchM.isPending}
                  className="gap-1"
                  onClick={() => {
                    if (org.org_id !== activeId) switchM.mutate(org.org_id);
                  }}
                >
                  <OrgIcon className="size-4 shrink-0 opacity-70" />
                  <span className="min-w-0 flex-1 truncate">{org.name}</span>
                  {isMain ? (
                    <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-primary">
                      Main
                    </span>
                  ) : null}
                  <span className="text-[10px] capitalize text-muted-foreground">{org.role}</span>
                  <button
                    type="button"
                    title={isMain ? "Clear main company" : "Set as main company"}
                    aria-label={isMain ? "Clear main company" : "Set as main company"}
                    className="rounded p-0.5 hover:bg-muted"
                    disabled={preferredM.isPending}
                    onClick={(e) => setMain(org.org_id, isMain, e)}
                  >
                    <Star
                      className={`size-3.5 ${isMain ? "fill-amber-400 text-amber-500" : "text-muted-foreground"}`}
                    />
                  </button>
                  {org.org_id === activeId ? <Check className="size-4 text-primary" /> : null}
                </DropdownMenuItem>
              );
            })}
          </>
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
