import { createFileRoute, Link, useParams } from "@tanstack/react-router";
import * as React from "react";
import { ExternalLink, Save } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { orderToCampaign } from "@/lib/mappers/orders";
import { isInterviewCampaignReadOnly, interviewCampaignReadOnlyLabel } from "@/lib/interview-campaign";
import { usePatchServiceOrder, useSaveInterviewDraft, useServiceOrder } from "@/lib/queries";

export const Route = createFileRoute("/_app/interviews/$orderId")({
  head: () => ({ meta: [{ title: "Manage interview — VoxBulk" }] }),
  component: InterviewManagePage,
});

function toLocalInput(iso?: string | null) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return "";
  }
}

function toIsoFromLocal(value?: string) {
  if (!value) return null;
  try {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return null;
    return d.toISOString();
  } catch {
    return null;
  }
}

function InterviewManagePage() {
  const { orderId } = useParams({ from: "/_app/interviews/$orderId" });
  const orderQ = useServiceOrder(orderId);
  const saveDraftM = useSaveInterviewDraft();
  const patchM = usePatchServiceOrder();

  const order = orderQ.data;
  const config = (order?.config || {}) as Record<string, unknown>;
  const campaign = order ? orderToCampaign(order, "interview") : null;
  const orderStatus = String(order?.status || "").toLowerCase();
  const readOnly = isInterviewCampaignReadOnly(orderStatus);
  const locked = ["running", "paused", "scheduled"].includes(orderStatus);

  const [title, setTitle] = React.useState("");
  const [role, setRole] = React.useState("");
  const [criteria, setCriteria] = React.useState("");
  const [systemPrompt, setSystemPrompt] = React.useState("");
  const [script, setScript] = React.useState("");
  const [startAt, setStartAt] = React.useState("");
  const [endAt, setEndAt] = React.useState("");

  React.useEffect(() => {
    if (!order) return;
    setTitle(String(order.title || config.position || config.role || ""));
    setRole(String(config.role || ""));
    setCriteria(String(config.criteria || config.screening_criteria || ""));
    setSystemPrompt(String(config.system_prompt || ""));
    setScript(String(config.approved_script || config.generated_script_draft || ""));
    setStartAt(toLocalInput(order.scheduled_start_at || (config.calling_window_start_at as string)));
    setEndAt(toLocalInput(order.scheduled_end_at || (config.calling_window_end_at as string)));
  }, [order, config.approved_script, config.calling_window_end_at, config.calling_window_start_at, config.criteria, config.generated_script_draft, config.position, config.role, config.screening_criteria, config.system_prompt]);

  const onSave = async () => {
    if (!order || readOnly) return;
    const bodyConfig = {
      ...config,
      role: role || title,
      position: title,
      criteria,
      screening_criteria: criteria,
      system_prompt: systemPrompt,
      approved_script: script,
      generated_script_draft: script,
      script_approved: Boolean(config.script_approved) || Boolean(script.trim()),
      calling_window_start_at: toIsoFromLocal(startAt),
      calling_window_end_at: toIsoFromLocal(endAt),
    };
    const patchBody = {
      title: title || order.title,
      scheduled_start_at: toIsoFromLocal(startAt),
      scheduled_end_at: toIsoFromLocal(endAt),
      config: bodyConfig,
    };
    try {
      if (locked) {
        await patchM.mutateAsync({ orderId, body: patchBody });
      } else {
        await saveDraftM.mutateAsync({
          order_id: orderId,
          title: patchBody.title,
          role: role || title,
          criteria,
          config: bodyConfig,
          scheduled_start_at: patchBody.scheduled_start_at,
          scheduled_end_at: patchBody.scheduled_end_at,
        });
        await patchM.mutateAsync({ orderId, body: patchBody });
      }
      toast.success("Interview updated");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save interview");
    }
  };

  if (orderQ.isLoading) {
    return (
      <div className="p-8">
        <Skeleton className="mb-4 h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!order || !campaign) {
    return (
      <div className="p-8 text-sm text-muted-foreground">
        Interview not found.{" "}
        <Link to="/interviews" className="text-primary underline">
          Back to interviews
        </Link>
      </div>
    );
  }

  const interviewNumber = order.campaign_id || order.reference_id || order.id.slice(0, 8);

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Interviews"
        title={campaign.name}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge tone={campaign.status} />
            <span className="font-mono text-xs text-muted-foreground">{interviewNumber}</span>
            <span className="text-muted-foreground">· {order.recipient_count ?? 0} candidates</span>
          </span> as unknown as string
        }
        actions={
          <>
            <Button variant="ghost" asChild>
              <Link to="/interviews">← Back</Link>
            </Button>
            <Button variant="outline" asChild>
              <Link to="/interviews/results/$orderId" params={{ orderId }}>
                View results
              </Link>
            </Button>
            {!readOnly && !locked ? (
              <Button variant="outline" asChild className="gap-1.5">
                <Link to="/interviews/new" search={{ order_id: orderId }}>
                  <ExternalLink className="size-4" /> Full setup wizard
                </Link>
              </Button>
            ) : null}
          </>
        }
      />

      {readOnly ? (
        <div className="rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
          {interviewCampaignReadOnlyLabel(orderStatus)}
        </div>
      ) : locked ? (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm text-amber-950 dark:text-amber-100">
          This interview is live — you can update the calling window, AI prompt, and interview questions. Candidate list and launch settings are locked.
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Interview settings</CardTitle>
          <CardDescription>Edit schedule, AI prompt, and interview questions. Changes apply to upcoming calls.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Interview name">
              <Input value={title} onChange={(e) => setTitle(e.target.value)} disabled={readOnly} />
            </Field>
            <Field label="Role">
              <Input value={role} onChange={(e) => setRole(e.target.value)} disabled={readOnly} placeholder="Job title for candidates" />
            </Field>
            <Field label="Calling start">
              <Input type="datetime-local" value={startAt} onChange={(e) => setStartAt(e.target.value)} disabled={readOnly} />
            </Field>
            <Field label="Calling end">
              <Input type="datetime-local" value={endAt} onChange={(e) => setEndAt(e.target.value)} disabled={readOnly} />
            </Field>
          </div>

          <Field label="Screening criteria">
            <Textarea
              rows={4}
              value={criteria}
              onChange={(e) => setCriteria(e.target.value)}
              disabled={readOnly}
              placeholder="What the AI should look for when scoring CVs and conducting interviews…"
            />
          </Field>

          <Field label="AI system prompt">
            <Textarea
              rows={5}
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              disabled={readOnly}
              placeholder="Instructions for how the AI agent should behave on the call…"
            />
          </Field>

          <Field label="Interview questions (script)">
            <Textarea
              rows={10}
              value={script}
              onChange={(e) => setScript(e.target.value)}
              disabled={readOnly}
              placeholder="Questions the AI will ask during the phone interview…"
            />
          </Field>

          {!readOnly ? (
            <div className="flex justify-end gap-2 border-t border-border pt-4">
              <Button
                variant="ghost"
                onClick={() => {
                  if (!order) return;
                  setTitle(String(order.title || ""));
                  setRole(String(config.role || ""));
                  setCriteria(String(config.criteria || config.screening_criteria || ""));
                  setSystemPrompt(String(config.system_prompt || ""));
                  setScript(String(config.approved_script || config.generated_script_draft || ""));
                  setStartAt(toLocalInput(order.scheduled_start_at));
                  setEndAt(toLocalInput(order.scheduled_end_at));
                }}
              >
                Reset
              </Button>
              <Button className="gap-1.5" onClick={() => void onSave()} disabled={saveDraftM.isPending || patchM.isPending}>
                <Save className="size-4" />
                {saveDraftM.isPending || patchM.isPending ? "Saving…" : "Save changes"}
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs font-medium">{label}</Label>
      {children}
    </div>
  );
}
