import * as React from "react";

import { cn } from "@/lib/utils";

export type IntegrationStatus = "connected" | "not_connected" | "error" | "disabled";

type Props = {
  status: IntegrationStatus;
  label?: string;
  className?: string;
};

const STATUS_TONE: Record<IntegrationStatus, string> = {
  connected: "bg-success/15 text-success",
  not_connected: "bg-muted text-muted-foreground",
  error: "bg-destructive/15 text-destructive",
  disabled: "bg-muted text-muted-foreground",
};

const STATUS_LABEL: Record<IntegrationStatus, string> = {
  connected: "Connected",
  not_connected: "Not connected",
  error: "Error",
  disabled: "Unavailable",
};

export function IntegrationStatusPill({ status, label, className }: Props) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        STATUS_TONE[status],
        className,
      )}
    >
      <span className={cn("size-1.5 rounded-full", status === "connected" ? "bg-success" : status === "error" ? "bg-destructive" : "bg-muted-foreground/60")} />
      {label || STATUS_LABEL[status]}
    </span>
  );
}
