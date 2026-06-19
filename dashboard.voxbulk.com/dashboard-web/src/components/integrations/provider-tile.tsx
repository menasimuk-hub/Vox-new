import * as React from "react";
import {
  Building2,
  Calendar,
  CalendarCheck,
  CalendarClock,
  CalendarRange,
  PlugZap,
} from "lucide-react";

import { cn } from "@/lib/utils";

import {
  IntegrationStatusPill,
  type IntegrationStatus,
} from "@/components/integrations/integration-status-pill";

export type IntegrationView = {
  key: string;
  group: "booking" | "crm";
  label: string;
  short_description: string;
  icon_slug: string;
  platform_ready: boolean;
  visible_to_orgs: boolean;
  connected: boolean;
  connected_account: string | null;
  connected_at: string | null;
  last_check_ok: boolean | null;
  last_check_at: string | null;
  blocked_reason: string | null;
  actions: {
    connect_url?: string;
    disconnect_url: string;
    test_url: string;
    connect_token_url?: string;
  };
  extra: Record<string, unknown>;
};

const ICON_BY_SLUG: Record<string, React.ComponentType<{ className?: string; strokeWidth?: number }>> = {
  calendly: CalendarCheck,
  cal_com: CalendarRange,
  google_calendar: Calendar,
  microsoft_calendar: CalendarClock,
  hubspot: Building2,
};

function statusFor(view: IntegrationView): IntegrationStatus {
  if (!view.platform_ready) return "disabled";
  if (view.last_check_ok === false) return "error";
  if (view.connected) return "connected";
  return "not_connected";
}

type Props = {
  view: IntegrationView;
  active?: boolean;
  onOpen: (view: IntegrationView) => void;
};

export function ProviderTile({ view, active, onOpen }: Props) {
  const Icon = ICON_BY_SLUG[view.icon_slug] || PlugZap;
  const status = statusFor(view);
  const isActive = Boolean(active) || view.connected;
  const subline =
    view.connected && view.connected_account
      ? view.connected_account
      : view.blocked_reason
        ? view.blocked_reason
        : view.short_description;

  return (
    <button
      type="button"
      onClick={() => onOpen(view)}
      title={view.label}
      className={cn(
        "group flex h-full w-full flex-col items-start gap-2.5 rounded-md border p-3.5 text-left transition-colors",
        isActive
          ? "border-foreground/15 bg-accent/40 shadow-sm"
          : "border-border bg-card hover:border-border hover:bg-accent/30",
      )}
    >
      <div className="flex w-full items-start gap-3">
        <span
          className={cn(
            "grid size-9 shrink-0 place-items-center rounded-md border transition-colors",
            isActive
              ? "border-border bg-background text-foreground"
              : "border-border/60 bg-muted/40 text-foreground/80 group-hover:border-border group-hover:text-foreground",
          )}
        >
          <Icon className="size-4" strokeWidth={1.75} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-sm font-medium leading-tight">{view.label}</span>
            <IntegrationStatusPill status={status} />
          </div>
          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{subline}</p>
        </div>
      </div>
    </button>
  );
}
