import * as React from "react";
import type { LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type ServiceTint = {
  panel: string;
  ring: string;
  icon: string;
  chip: string;
  soft: string;
};

export const SERVICE_TINTS = {
  core: {
    panel: "border-sky-200 bg-sky-50/80 dark:border-sky-900/50 dark:bg-sky-950/30",
    ring: "ring-sky-200/80 dark:ring-sky-800/40",
    icon: "text-sky-600 dark:text-sky-400",
    chip: "bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-200",
    soft: "border-sky-200/80 bg-sky-50 dark:border-sky-800 dark:bg-sky-950/40",
  },
  feedback: {
    panel: "border-emerald-200 bg-emerald-50/80 dark:border-emerald-900/50 dark:bg-emerald-950/30",
    ring: "ring-emerald-200/80 dark:ring-emerald-800/40",
    icon: "text-emerald-600 dark:text-emerald-400",
    chip: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200",
    soft: "border-emerald-200/80 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/40",
  },
  smartCard: {
    panel: "border-violet-200 bg-violet-50/80 dark:border-violet-900/50 dark:bg-violet-950/30",
    ring: "ring-violet-200/80 dark:ring-violet-800/40",
    icon: "text-violet-600 dark:text-violet-400",
    chip: "bg-violet-100 text-violet-800 dark:bg-violet-900/50 dark:text-violet-200",
    soft: "border-violet-200/80 bg-violet-50 dark:border-violet-800 dark:bg-violet-950/40",
  },
  expo: {
    panel: "border-cyan-200 bg-cyan-50/80 dark:border-cyan-900/50 dark:bg-cyan-950/30",
    ring: "ring-cyan-200/80 dark:ring-cyan-800/40",
    icon: "text-cyan-600 dark:text-cyan-400",
    chip: "bg-cyan-100 text-cyan-800 dark:bg-cyan-900/50 dark:text-cyan-200",
    soft: "border-cyan-200/80 bg-cyan-50 dark:border-cyan-800 dark:bg-cyan-950/40",
  },
} as const satisfies Record<string, ServiceTint>;

type Props = {
  tint: ServiceTint;
  icon: LucideIcon;
  title: string;
  blurb?: string;
  badge?: string;
  children: React.ReactNode;
  className?: string;
};

export function ServicePackageShell({ tint, icon: Icon, title, blurb, badge, children, className }: Props) {
  return (
    <div className={cn("space-y-6 rounded-2xl border p-4 ring-1 sm:p-6", tint.panel, tint.ring, className)}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <div className={cn("grid size-16 place-items-center rounded-2xl bg-background shadow-sm", tint.icon)}>
            <Icon className="size-9" strokeWidth={1.75} />
          </div>
          <div>
            <p className="text-lg font-semibold tracking-tight">{title}</p>
            {blurb ? <p className="mt-0.5 max-w-xl text-sm text-muted-foreground">{blurb}</p> : null}
          </div>
        </div>
        {badge ? (
          <Badge variant="outline" className={cn("border-transparent text-xs", tint.chip)}>
            {badge}
          </Badge>
        ) : null}
      </div>
      {children}
    </div>
  );
}
