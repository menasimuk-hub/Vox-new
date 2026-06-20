import * as React from "react";
import { Loader2, Play, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useCrmDealStages,
  useCrmSurveyAutomation,
  usePatchCrmSurveyAutomation,
  useTestCrmSurveyAutomation,
} from "@/lib/queries";

type Props = {
  orderId: string;
};

export function CrmSurveyAutomationCard({ orderId }: Props) {
  const statusQ = useCrmSurveyAutomation(orderId);
  const stagesQ = useCrmDealStages(Boolean(statusQ.data?.crm_connected));
  const patchM = usePatchCrmSurveyAutomation();
  const testM = useTestCrmSurveyAutomation();

  const status = statusQ.data;
  const [stageIds, setStageIds] = React.useState<string[]>([]);
  const [delayHours, setDelayHours] = React.useState(24);
  const [consent, setConsent] = React.useState(false);
  const [testRows, setTestRows] = React.useState<Array<Record<string, unknown>>>([]);

  React.useEffect(() => {
    if (!status) return;
    setStageIds(Array.isArray(status.stage_ids) ? status.stage_ids.map(String) : []);
    setDelayHours(Number(status.delay_hours || 24));
    setConsent(status.consent_acknowledged === true);
  }, [status]);

  const toggleStage = (id: string) => {
    setStageIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const onSave = async (enabled?: boolean) => {
    try {
      await patchM.mutateAsync({
        orderId,
        body: {
          enabled: enabled ?? status?.enabled,
          stage_ids: stageIds,
          delay_hours: delayHours,
          consent_acknowledged: consent,
        },
      });
      toast.success(enabled === false ? "CRM automation disabled" : "CRM automation saved");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save CRM automation");
    }
  };

  const onTest = async () => {
    try {
      const result = await testM.mutateAsync(orderId);
      setTestRows(Array.isArray(result.rows) ? result.rows : []);
      toast.success(
        `Test complete — ${result.would_schedule ?? 0} would send, ${result.would_skip ?? 0} skipped`,
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Test failed");
    }
  };

  if (statusQ.isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading CRM automation…
        </CardContent>
      </Card>
    );
  }

  if (!status?.crm_connected) {
    return null;
  }

  const blocked = status.subscription_eligible === false;
  const stages = stagesQ.data?.stages ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">CRM deal automation</CardTitle>
        <CardDescription>
          When a deal moves to a selected stage in {String(status.provider || "your CRM")}, send this survey after a
          delay. Subscription required — uses this survey&apos;s WhatsApp or AI call channel.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {blocked ? (
          <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-100">
            {status.subscription_block_reason ||
              "An active subscription is required for CRM deal automation."}
          </p>
        ) : null}

        <div className="space-y-2">
          <Label>Deal stages</Label>
          {stagesQ.isLoading ? (
            <p className="text-sm text-muted-foreground">Loading stages…</p>
          ) : stages.length ? (
            <div className="max-h-40 space-y-2 overflow-y-auto rounded-md border p-3">
              {stages.map((stage) => {
                const id = String(stage.id || "");
                const label = [stage.pipeline_name, stage.name].filter(Boolean).join(" · ");
                return (
                  <label key={id} className="flex cursor-pointer items-center gap-2 text-sm">
                    <Checkbox checked={stageIds.includes(id)} onCheckedChange={() => toggleStage(id)} />
                    <span>{label || id}</span>
                  </label>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No deal stages returned from CRM.</p>
          )}
        </div>

        <div className="grid gap-2 sm:max-w-xs">
          <Label htmlFor="crm-delay-hours">Delay after stage change (hours)</Label>
          <Input
            id="crm-delay-hours"
            type="number"
            min={0}
            max={168}
            value={delayHours}
            onChange={(e) => setDelayHours(Number(e.target.value || 0))}
          />
        </div>

        <label className="flex items-start gap-2 text-sm">
          <Checkbox checked={consent} onCheckedChange={(v) => setConsent(v === true)} className="mt-0.5" />
          <span>
            I confirm contacts may receive this survey when their CRM deal reaches the selected stage(s), and I have
            appropriate consent to contact them.
          </span>
        </label>

        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" onClick={() => void onTest()} disabled={testM.isPending || !stageIds.length}>
            {testM.isPending ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
            Test (dry run)
          </Button>
          <Button type="button" onClick={() => void onSave(true)} disabled={patchM.isPending || blocked || !consent || !stageIds.length}>
            {patchM.isPending ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
            Enable automation
          </Button>
          {status.enabled ? (
            <Button type="button" variant="ghost" onClick={() => void onSave(false)} disabled={patchM.isPending}>
              Disable
            </Button>
          ) : null}
        </div>

        {status.enabled ? (
          <p className="text-xs text-muted-foreground">
            Active — queued {status.queued_count ?? 0}, sent {status.sent_count ?? 0}.
            {status.last_poll_summary ? ` Last poll: ${status.last_poll_summary}.` : null}
          </p>
        ) : null}

        {testRows.length ? (
          <div className="rounded-md border">
            <div className="border-b px-3 py-2 text-xs font-medium text-muted-foreground">Dry-run preview</div>
            <ul className="max-h-48 divide-y overflow-y-auto text-xs">
              {testRows.slice(0, 20).map((row, idx) => (
                <li key={`${row.deal_id}-${idx}`} className="px-3 py-2">
                  <span className="font-medium">{String(row.deal_title || row.deal_id || "Deal")}</span>
                  {" — "}
                  {String(row.action || "skip")}
                  {row.reason ? ` (${String(row.reason)})` : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
