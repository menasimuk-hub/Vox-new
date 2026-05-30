import * as React from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import logoDark from "@/assets/logo-dark.png";
import logoLight from "@/assets/logo-light.png";
import iconDark from "@/assets/icon-dark.png";
import iconLight from "@/assets/icon-light.png";
import { useTheme } from "@/lib/theme";
import {
  LayoutDashboard, ChevronDown, LogOut,
  PhoneCall, FilePlus2, FolderOpen, BarChart3, FileBarChart,
  ClipboardList, MessageSquareText, ListChecks, FileText,
  HeartPulse, AlarmClockOff, Bell, Megaphone, Tag,
  CalendarClock, Repeat,
  Settings as SettingsIcon, Layers, User2, Cog, Users, Ban, History,
  Package, CreditCard, LifeBuoy,
} from "lucide-react";

import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent, SidebarGroupLabel,
  SidebarHeader, SidebarMenu, SidebarMenuButton, SidebarMenuItem,
  SidebarMenuSub, SidebarMenuSubButton, SidebarMenuSubItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useServices, type ServiceKey } from "@/lib/services";
import { logoutDashboard } from "@/lib/api";
import { isRecoveryServiceKey, showRecoveryModules } from "@/lib/feature-flags";
import { initialsFromName, useSession } from "@/lib/session";
import { useOrgLogoPreview } from "@/lib/use-org-logo";
import { useOrganisation } from "@/lib/queries";

type Item = {
  title: string;
  url: string;
  icon: React.ComponentType<{ className?: string }>;
  isActive?: (path: string) => boolean;
};
type Group = { key: ServiceKey | "settings" | "account" | "workspace"; label: string; items: Item[] };

function normalizePath(value: string) {
  const trimmed = value.replace(/\/+$/, "");
  return trimmed || "/";
}

const groups: Group[] = [
  { key: "workspace", label: "Workspace", items: [{ title: "Dashboard", url: "/", icon: LayoutDashboard }] },
  { key: "interviews", label: "Interviews", items: [
    { title: "Create new interview", url: "/interviews/new", icon: FilePlus2 },
    {
      title: "Saved interviews",
      url: "/interviews",
      icon: FolderOpen,
      isActive: (path) => normalizePath(path) === "/interviews",
    },
    {
      title: "Interview results",
      url: "/interviews/results",
      icon: BarChart3,
      isActive: (path) => {
        const p = normalizePath(path);
        return p === "/interviews/results" || p.startsWith("/interviews/results/");
      },
    },
    { title: "Reports", url: "/interviews/reports", icon: FileBarChart },
  ]},
  { key: "surveys", label: "Surveys", items: [
    { title: "Create new survey", url: "/surveys/new", icon: MessageSquareText },
    { title: "Saved surveys", url: "/surveys", icon: ListChecks },
    { title: "Survey results", url: "/surveys/results", icon: BarChart3 },
    { title: "Reports", url: "/surveys/reports", icon: FileText },
  ]},
  { key: "recovery", label: "Recovery", items: [
    { title: "Recovery queue", url: "/recovery", icon: HeartPulse },
    { title: "No-show follow-up", url: "/recovery/no-show", icon: AlarmClockOff },
    { title: "Emergency reschedule", url: "/recovery/emergency", icon: Bell },
    { title: "Recall campaigns", url: "/recovery/recall", icon: Megaphone },
    { title: "Offer campaigns", url: "/recovery/offers", icon: Tag },
  ]},
  { key: "followup", label: "Follow up", items: [
    { title: "Reminder sequences", url: "/follow-up", icon: Repeat },
  ]},
  { key: "settings", label: "Settings", items: [
    { title: "Services", url: "/settings/services", icon: Layers },
    { title: "Profile settings", url: "/settings/profile", icon: User2 },
    { title: "System settings", url: "/settings/system", icon: Cog },
    { title: "Team members", url: "/settings/team", icon: Users },
    { title: "Opt-out list", url: "/settings/opt-out", icon: Ban },
    { title: "Audit log", url: "/settings/audit", icon: History },
  ]},
  { key: "account", label: "Account", items: [
    { title: "Packages & pricing", url: "/account/packages", icon: Package },
    { title: "Billing", url: "/account/billing", icon: CreditCard },
    { title: "Support", url: "/account/support", icon: LifeBuoy },
  ]},
];

export function AppSidebar() {
  const path = useRouterState({ select: (r) => r.location.pathname });
  const { visible, loaded } = useServices();
  const { session } = useSession();
  const { isMobile, setOpenMobile } = useSidebar();
  const closeMobile = React.useCallback(() => {
    if (isMobile) setOpenMobile(false);
  }, [isMobile, setOpenMobile]);
  const orgQ = useOrganisation();
  const orgName = session?.org?.name || session?.org?.display_name || orgQ.data?.name || session?.profile?.email || "Your organisation";
  const planName = session?.subscription?.plan?.name || "Plan";
  const avatar = initialsFromName(orgName);
  const orgLogo = useOrgLogoPreview(orgQ.data?.logo_url);

  const visibleGroups = groups.filter((g) => {
    if (g.key === "workspace" || g.key === "settings" || g.key === "account") return true;
    if (!loaded) return false;
    if (!showRecoveryModules && isRecoveryServiceKey(g.key)) return false;
    return visible[g.key];
  });

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <BrandMark />
      </SidebarHeader>

      <SidebarContent>
        {visibleGroups.map((g) => <NavGroup key={g.key} group={g} path={path} onNavigate={closeMobile} />)}
      </SidebarContent>

      <SidebarFooter>
        <Link
          to="/account/billing"
          onClick={closeMobile}
          className="flex items-center gap-3 rounded-lg bg-sidebar-accent/70 p-2.5 text-sidebar-accent-foreground hover:bg-sidebar-accent group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:bg-transparent group-data-[collapsible=icon]:p-1"
        >
          {orgLogo ? (
            <img src={orgLogo} alt="" className="size-9 shrink-0 rounded-full object-cover bg-white ring-1 ring-sidebar-border" />
          ) : (
            <div className="grid size-9 shrink-0 place-items-center rounded-full bg-sidebar-primary text-sidebar-primary-foreground text-xs font-semibold">{avatar}</div>
          )}
          <div className="flex-1 min-w-0 group-data-[collapsible=icon]:hidden">
            <p className="truncate text-sm font-medium leading-tight">{orgName}</p>
            <p className="truncate text-[11px] text-muted-foreground">{planName}</p>
          </div>
        </Link>
        <button
          type="button"
          onClick={() => logoutDashboard()}
          className="mt-1 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-muted-foreground hover:bg-accent/60 hover:text-foreground group-data-[collapsible=icon]:justify-center"
        >
          <LogOut className="size-3.5" />
          <span className="group-data-[collapsible=icon]:hidden">Log out</span>
        </button>
      </SidebarFooter>
    </Sidebar>
  );
}
function BrandMark() {
  const { theme } = useTheme();
  const fullLogo = theme === "dark" ? logoLight : logoDark;
  const iconLogo = theme === "dark" ? iconLight : iconDark;
  return (
    <Link to="/" className="flex items-center px-2 py-2">
      <img
        src={fullLogo}
        alt="VoxBulk"
        className="h-8 w-auto object-contain group-data-[collapsible=icon]:hidden"
      />
      <img
        src={iconLogo}
        alt="VoxBulk"
        className="hidden size-8 object-contain group-data-[collapsible=icon]:block"
      />
    </Link>
  );
}


function NavGroup({ group, path, onNavigate }: { group: Group; path: string; onNavigate?: () => void }) {
  const itemActive = (item: Item) =>
    item.isActive ? item.isActive(path) : normalizePath(path) === normalizePath(item.url);
  const hasActive = group.items.some((i) => itemActive(i));
  const [open, setOpen] = React.useState(hasActive || group.items.length === 1);

  React.useEffect(() => { if (hasActive) setOpen(true); }, [hasActive]);

  // Single-item groups render flat
  if (group.items.length === 1) {
    const item = group.items[0];
    return (
      <SidebarGroup>
        <SidebarGroupContent>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton asChild isActive={itemActive(item)} tooltip={item.title}>
                <Link to={item.url} onClick={onNavigate}>
                  <item.icon />
                  <span>{item.title}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>
    );
  }

  const HeadIcon = headIcon(group.key);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <SidebarGroup>
        <CollapsibleTrigger asChild>
          <SidebarGroupLabel className="group/label flex w-full cursor-pointer items-center justify-between hover:text-foreground">
            <span className="flex items-center gap-2">
              <HeadIcon className="size-3.5" />
              {group.label}
            </span>
            <ChevronDown className="size-3.5 transition-transform data-[state=closed]:-rotate-90 group-data-[state=closed]/label:-rotate-90" />
          </SidebarGroupLabel>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuSub>
                {group.items.map((item) => (
                  <SidebarMenuSubItem key={item.title}>
                    <SidebarMenuSubButton asChild isActive={itemActive(item)}>
                      <Link to={item.url} onClick={onNavigate}>
                        <item.icon className="size-3.5" />
                        <span>{item.title}</span>
                      </Link>
                    </SidebarMenuSubButton>
                  </SidebarMenuSubItem>
                ))}
              </SidebarMenuSub>
            </SidebarMenu>
          </SidebarGroupContent>
        </CollapsibleContent>
      </SidebarGroup>
    </Collapsible>
  );
}

function headIcon(key: Group["key"]) {
  switch (key) {
    case "interviews": return PhoneCall;
    case "surveys": return ClipboardList;
    case "recovery": return HeartPulse;
    case "followup": return CalendarClock;
    case "settings": return SettingsIcon;
    case "account": return User2;
    default: return LayoutDashboard;
  }
}
