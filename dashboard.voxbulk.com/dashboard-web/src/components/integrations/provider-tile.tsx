import * as React from "react";

import { cn } from "@/lib/utils";

import {
  IntegrationStatusPill,
  type IntegrationStatus,
} from "@/components/integrations/integration-status-pill";
import { ProviderLogo } from "@/components/integrations/provider-logo";

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
        "group flex min-h-[8.5rem] w-full flex-col items-start gap-3 rounded-lg border p-5 text-left transition-colors",
        isActive
          ? "border-foreground/15 bg-accent/40 shadow-sm"
          : "border-border bg-card hover:border-border hover:bg-accent/30",
      )}
    >
      <div className="flex w-full items-start gap-4">
        <ProviderLogo
          iconSlug={view.icon_slug}
          providerKey={view.key}
          label={view.label}
          className={cn(
            "size-12 transition-colors",
            isActive ? "border-border" : "border-border/60 group-hover:border-border",
          )}
          imgClassName="max-h-9 max-w-9"
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <span className="text-base font-semibold leading-snug">{view.label}</span>
            <IntegrationStatusPill status={status} />
          </div>
          <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-muted-foreground">{subline}</p>
        </div>
      </div>
    </button>
  );
}
