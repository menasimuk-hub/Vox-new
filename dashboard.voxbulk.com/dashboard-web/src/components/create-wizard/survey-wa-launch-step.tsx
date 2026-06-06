import { CalendarClock, Repeat, Rocket, Send } from "lucide-react";

import { Summary } from "@/components/create-wizard/summary";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export type SurveyWaLaunchStepProps = {
  launchMode: "now" | "schedule" | "recurring";
  setLaunchMode: (v: "now" | "schedule" | "recurring") => void;
  scheduleAt: string;
  setScheduleAt: (v: string) => void;
  recurringInterval: string;
  setRecurringInterval: (v: string) => void;
  firstDeliveryAt: string;
  setFirstDeliveryAt: (v: string) => void;
  consent: boolean;
  setConsent: (v: boolean) => void;
  contactsCount: number;
  packageId: string;
  setPackageId: (v: string) => void;
  packages: Array<Record<string, unknown>>;
  packagesLoading: boolean;
  typeCount: number;
  onLaunch: () => void;
  launchPending?: boolean;
};

export function SurveyWaLaunchStep({
  launchMode,
  setLaunchMode,
  scheduleAt,
  setScheduleAt,
  recurringInterval,
  setRecurringInterval,
  firstDeliveryAt,
  setFirstDeliveryAt,
  consent,
  setConsent,
  contactsCount,
  packageId,
  setPackageId,
  packages,
  packagesLoading,
  typeCount,
  onLaunch,
  launchPending,
}: SurveyWaLaunchStepProps) {
  const canLaunch =
    consent &&
    (launchMode === "now" ||
      (launchMode === "schedule" && !!scheduleAt) ||
      (launchMode === "recurring" && !!firstDeliveryAt));

  const modeSummary =
    launchMode === "now"
      ? "Send now"
      : launchMode === "schedule"
        ? `Scheduled · ${scheduleAt || "—"}`
        : `Recurring · ${recurringInterval.replace("-", " ")} starting ${firstDeliveryAt || "—"}`;

  return (
    <Card className="animate-scale-in">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Rocket className="size-4 text-primary" /> Step 6 · Launch your survey
        </CardTitle>
        <CardDescription>Choose when to send and confirm consent.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <RadioGroup
          value={launchMode}
          onValueChange={(v) => setLaunchMode(v as "now" | "schedule" | "recurring")}
          className="grid gap-3 sm:grid-cols-3"
        >
          <label
            className={cn(
              "flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition",
              launchMode === "now" ? "border-primary bg-primary/5 ring-1 ring-primary/30" : "border-border bg-background hover:border-primary/40",
            )}
          >
            <RadioGroupItem value="now" className="mt-0.5" />
            <div>
              <p className="flex items-center gap-2 text-sm font-semibold">
                <Send className="size-4 text-primary" /> Send now
              </p>
              <p className="text-xs text-muted-foreground">Begin delivery as soon as you launch.</p>
            </div>
          </label>
          <label
            className={cn(
              "flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition",
              launchMode === "schedule"
                ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                : "border-border bg-background hover:border-primary/40",
            )}
          >
            <RadioGroupItem value="schedule" className="mt-0.5" />
            <div className="w-full">
              <p className="flex items-center gap-2 text-sm font-semibold">
                <CalendarClock className="size-4 text-primary" /> Schedule
              </p>
              <p className="mb-2 text-xs text-muted-foreground">Pick a date and time to send.</p>
              {launchMode === "schedule" && (
                <Input type="datetime-local" value={scheduleAt} onChange={(e) => setScheduleAt(e.target.value)} />
              )}
            </div>
          </label>
          <label
            className={cn(
              "flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition",
              launchMode === "recurring"
                ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                : "border-border bg-background hover:border-primary/40",
            )}
          >
            <RadioGroupItem value="recurring" className="mt-0.5" />
            <div className="w-full">
              <p className="flex items-center gap-2 text-sm font-semibold">
                <Repeat className="size-4 text-primary" /> Recurring
              </p>
              <p className="mb-2 text-xs text-muted-foreground">Send on a repeating schedule.</p>
              {launchMode === "recurring" && (
                <div className="mt-2 space-y-2 animate-fade-in">
                  <div className="space-y-1">
                    <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Frequency</Label>
                    <Select value={recurringInterval} onValueChange={setRecurringInterval}>
                      <SelectTrigger className="h-8">
                        <SelectValue placeholder="Select frequency" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="1-week">Every 1 week</SelectItem>
                        <SelectItem value="2-weeks">Every 2 weeks</SelectItem>
                        <SelectItem value="3-weeks">Every 3 weeks</SelectItem>
                        <SelectItem value="1-month">Every 1 month</SelectItem>
                        <SelectItem value="3-months">Every 3 months</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">First run date</Label>
                    <Input
                      type="datetime-local"
                      value={firstDeliveryAt}
                      onChange={(e) => setFirstDeliveryAt(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                </div>
              )}
            </div>
          </label>
        </RadioGroup>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-1.5">
            <Label className="text-xs">Package</Label>
            {packagesLoading ? (
              <Skeleton className="h-10 w-full" />
            ) : (
              <Select value={packageId} onValueChange={setPackageId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select package" />
                </SelectTrigger>
                <SelectContent>
                  {packages.map((p) => (
                    <SelectItem key={String(p.id || p.rule_id)} value={String(p.id || p.rule_id)}>
                      {String(p.label || p.name || p.bundle_size || "Package")}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
        </div>

        <label
          className={cn(
            "flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition",
            consent ? "border-primary bg-primary/5" : "border-warning/50 bg-warning/5",
          )}
        >
          <Checkbox checked={consent} onCheckedChange={(v) => setConsent(!!v)} className="mt-0.5" />
          <div>
            <p className="text-sm font-medium">I confirm my contact list has valid WhatsApp opt-in consent.</p>
            <p className="text-xs text-muted-foreground">Required before launch — protects your account and your contacts.</p>
          </div>
        </label>

        <div className="grid gap-2 sm:grid-cols-3">
          <Summary label="Contacts" value={`${contactsCount}`} />
          <Summary label="Mode" value={modeSummary} />
          <Summary label="Estimated cost" value={`£${(contactsCount * 0.18 * Math.max(1, typeCount)).toFixed(2)}`} />
        </div>

        <div className="flex justify-end">
          <Button size="lg" className="gap-1.5" disabled={!canLaunch || launchPending} onClick={onLaunch}>
            <Rocket className="size-4" />{" "}
            {launchPending
              ? "Launching…"
              : launchMode === "now"
                ? "Launch now"
                : launchMode === "schedule"
                  ? "Schedule launch"
                  : "Activate recurring"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
