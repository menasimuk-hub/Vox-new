import * as React from "react";

import { cn } from "@/lib/utils";

import {
  IntegrationStatusPill,
  type IntegrationStatus,
} from "@/components/integrations/integration-status-pill";
import { integrationStatusFor } from "@/components/integrations/integration-status";
import { ProviderLogo } from "@/components/integrations/provider-logo";

export type IntegrationView = {
  key: string;
  group: "booking" | "crm" | "ats";
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
  return integrationStatusFor(view);
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
    status === "setup_needed"
      ? "Paste your booking page URL to finish setup"
      : view.connected && view.connected_account
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
        "group flex w-full overflow-hidden rounded-lg border text-left transition-colors",
        isActive
          ? "border-foreground/15 bg-accent/40 shadow-sm"
          : "border-border bg-card hover:border-border hover:bg-accent/30",
      )}
    >
      <div className="aspect-square w-20 shrink-0 border-r border-border/60 sm:w-[5.5rem]">
        <ProviderLogo
          variant="tile"
          iconSlug={view.icon_slug}
          providerKey={view.key}
          label={view.label}
        />
      </div>
      <div className="flex min-h-20 min-w-0 flex-1 flex-col justify-center gap-1 px-3 py-2 sm:min-h-[5.5rem]">
        <div className="flex items-start justify-between gap-2">
          <span className="text-sm font-semibold leading-snug">{view.label}</span>
          <IntegrationStatusPill status={status} />
        </div>
        <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">{subline}</p>
      </div>
    </button>
  );
}
