import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { requireAppointmentsModule } from "@/lib/guards/service-route";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";

const DEFAULT_STEPS = [
  { id: "s1", when: "72h before", default: true },
  { id: "s2", when: "48h before", default: true },
  { id: "s3", when: "24h before", default: true },
  { id: "s4", when: "2h before", default: true },
  { id: "s5", when: "After no-show", default: true },
];

type ReminderStep = {
  id: string;
  when: string;
  message: string;
  enabled: boolean;
};

export const Route = createFileRoute("/_app/follow-up")({
  beforeLoad: requireAppointmentsModule,
  head: () => ({ meta: [{ title: "Reminder sequences — VoxBulk" }] }),
  component: ReminderSequencesPage,
});

function ReminderSequencesPage() {
  const queryClient = useQueryClient();
  const settingsQ = useQuery({
    queryKey: ["appointments", "settings"],
    queryFn: () =>
      apiFetch<{ reminder_sequence_json?: ReminderStep[] }>("/appointments/settings"),
  });

  const [steps, setSteps] = React.useState<ReminderStep[]>(
    DEFAULT_STEPS.map((s) => ({
      id: s.id,
      when: s.when,
      enabled: s.default,
      message: `Hi {first_name}, just a reminder of your appointment ${s.when}. Reply Y to confirm, R to reschedule.`,
    })),
  );

  React.useEffect(() => {
    const raw = settingsQ.data?.reminder_sequence_json;
    if (Array.isArray(raw) && raw.length > 0) {
      setSteps(
        raw.map((r, i) => ({
          id: String(r.id ?? `s${i + 1}`),
          when: String(r.when ?? DEFAULT_STEPS[i]?.when ?? "24h before"),
          message: String(r.message ?? ""),
          enabled: r.enabled !== false,
        })),
      );
    }
  }, [settingsQ.data]);

  const saveMut = useMutation({
    mutationFn: () =>
      apiFetch("/appointments/settings", {
        method: "PATCH",
        body: JSON.stringify({ reminder_sequence_json: steps }),
      }),
    onSuccess: () => {
      toast.success("Reminder sequence saved");
      void queryClient.invalidateQueries({ queryKey: ["appointments", "settings"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Appointments"
        title="Reminder sequences"
        description="WhatsApp appointment reminders, fully editable."
      />
      <div className="flex flex-col gap-3">
        {steps.map((s, i) => (
          <Card key={s.id}>
            <CardContent className="flex flex-col gap-3 p-4 md:flex-row md:items-start">
              <div className="flex items-center gap-3 md:w-48">
                <div className="grid size-7 place-items-center rounded-full bg-primary/15 text-xs font-semibold text-primary">
                  {i + 1}
                </div>
                <Select
                  value={s.when}
                  onValueChange={(when) =>
                    setSteps((prev) => prev.map((row) => (row.id === s.id ? { ...row, when } : row)))
                  }
                >
                  <SelectTrigger className="h-8 w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["72h before", "48h before", "24h before", "12h before", "2h before", "After no-show"].map((w) => (
                      <SelectItem key={w} value={w}>{w}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex-1">
                <Textarea
                  rows={2}
                  value={s.message}
                  onChange={(e) =>
                    setSteps((prev) =>
                      prev.map((row) => (row.id === s.id ? { ...row, message: e.target.value } : row)),
                    )
                  }
                />
              </div>
              <Switch
                checked={s.enabled}
                onCheckedChange={(enabled) =>
                  setSteps((prev) => prev.map((row) => (row.id === s.id ? { ...row, enabled } : row)))
                }
              />
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="flex justify-end">
        <Button disabled={saveMut.isPending} onClick={() => saveMut.mutate()}>
          Save sequence
        </Button>
      </div>
    </div>
  );
}
