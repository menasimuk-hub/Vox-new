import { useNavigate } from "@tanstack/react-router";
import {
  ArrowRight,
  HeartPulse,
  MessageSquareText,
  Megaphone,
  PhoneCall,
  QrCode,
} from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { showRecoveryModules } from "@/lib/feature-flags";
import { useServices, type ServiceKey } from "@/lib/services";
import { cn } from "@/lib/utils";

type PickerService = {
  key: ServiceKey;
  label: string;
  desc: string;
  icon: React.ComponentType<{ className?: string }>;
  to: string;
  search?: Record<string, unknown>;
  tint: string;
};

const PICKER_SERVICES: PickerService[] = [
  {
    key: "interviews",
    label: "Interview campaign",
    desc: "AI phone screening for candidates at scale.",
    icon: PhoneCall,
    to: "/interviews/new",
    search: { new: true },
    tint: "from-blue-500/20 to-blue-500/0",
  },
  {
    key: "surveys",
    label: "WhatsApp / voice survey",
    desc: "Send a structured survey to a contact list.",
    icon: MessageSquareText,
    to: "/surveys/new",
    tint: "from-violet-500/20 to-violet-500/0",
  },
  {
    key: "feedback",
    label: "Customer feedback (QR)",
    desc: "Print a QR — customers scan and the survey starts.",
    icon: QrCode,
    to: "/feedback/new",
    tint: "from-emerald-500/20 to-emerald-500/0",
  },
  {
    key: "recovery",
    label: "Recovery campaign",
    desc: "No-show recovery, recalls, emergency rebooks.",
    icon: HeartPulse,
    to: "/recovery",
    tint: "from-rose-500/20 to-rose-500/0",
  },
  {
    key: "campaigns",
    label: "Broadcast campaign",
    desc: "WhatsApp template broadcasts to your audience.",
    icon: Megaphone,
    to: "/campaigns/new",
    tint: "from-amber-500/20 to-amber-500/0",
  },
];

export function NewCampaignPicker({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const navigate = useNavigate();
  const { visible } = useServices();

  const services = PICKER_SERVICES.filter((s) => {
    if (!showRecoveryModules && (s.key === "recovery" || s.key === "followup")) return false;
    return true;
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>What kind of campaign?</DialogTitle>
          <DialogDescription>Pick a service to start. You can change details later.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          {services.map((s) => {
            const on = visible[s.key];
            const Icon = s.icon;
            return (
              <button
                key={s.key}
                type="button"
                disabled={!on}
                onClick={() => {
                  onOpenChange(false);
                  void navigate({ to: s.to, search: s.search });
                }}
                className={cn(
                  "group relative overflow-hidden rounded-xl border border-border bg-card p-4 text-left transition",
                  on
                    ? "hover:-translate-y-0.5 hover:border-primary/50 hover:shadow-md"
                    : "cursor-not-allowed opacity-50",
                )}
              >
                <div className={cn("pointer-events-none absolute inset-0 bg-gradient-to-br opacity-60", s.tint)} />
                <div className="relative flex items-start gap-3">
                  <span className="grid size-10 place-items-center rounded-lg bg-background/80 text-primary ring-1 ring-border">
                    <Icon className="size-5" />
                  </span>
                  <div className="flex-1">
                    <p className="font-medium">{s.label}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">{s.desc}</p>
                    {!on ? (
                      <p className="mt-2 text-[10px] uppercase tracking-wider text-muted-foreground">
                        Not enabled — open Settings → Services
                      </p>
                    ) : null}
                  </div>
                  <ArrowRight className="size-4 opacity-0 transition group-hover:opacity-100" />
                </div>
              </button>
            );
          })}
        </div>
        <div className="flex justify-end">
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
