import { createFileRoute, Link, useParams } from "@tanstack/react-router";
import * as React from "react";
import { CheckCircle2, Lock, Pencil, Save } from "lucide-react";
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
import { extractQuestionsBlock, mergeQuestionsIntoScript, questionsMatchApproved } from "@/lib/interview-script";
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

  const fullScriptRef = React.useRef("");
  const approvedScriptRef = React.useRef("");

  const [title, setTitle] = React.useState("");
  const [questions, setQuestions] = React.useState("");
  const [startAt, setStartAt] = React.useState("");
  const [endAt, setEndAt] = React.useState("");
  const [questionsApproved, setQuestionsApproved] = React.useState(false);

  React.useEffect(() => {
    if (!order) return;
    const full = String(config.approved_script || config.generated_script_draft || "");
    const approved = String(config.approved_script || full);
    fullScriptRef.current = full;
    approvedScriptRef.current = approved;
    setTitle(String(order.title || config.position || config.role || ""));
    setQuestions(extractQuestionsBlock(full));
    setStartAt(toLocalInput(order.scheduled_start_at || (config.calling_window_start_at as string)));
    setEndAt(toLocalInput(order.scheduled_end_at || (config.calling_window_end_at as string)));
    const approvedOk =
      Boolean(config.script_approved) &&
      questionsMatchApproved(full, approved) &&
      extractQuestionsBlock(full).trim() === extractQuestionsBlock(approved).trim();
    setQuestionsApproved(approvedOk);
  }, [order, config.approved_script, config.calling_window_end_at, config.calling_window_start_at, config.generated_script_draft, config.position, config.role, config.script_approved]);

  const mergedScript = React.useMemo(
    () => mergeQuestionsIntoScript(fullScriptRef.current, questions),
    [questions],
  );

  const questionsDirty = React.useMemo(() => {
    const baseline = extractQuestionsBlock(approvedScriptRef.current || fullScriptRef.current);
    return questions.trim() !== baseline.trim();
  }, [questions]);

  const onApproveQuestions = () => {
    if (!questions.trim()) {
      toast.error("Add at least one interview question before approving");
      return;
    }
    fullScriptRef.current = mergedScript;
    approvedScriptRef.current = mergedScript;
    setQuestionsApproved(true);
    toast.success("Questions approved — save to apply to upcoming calls");
  };

  const onSave = async () => {
    if (!order || readOnly) return;
    if (questionsDirty && !questionsApproved) {
      toast.error("Approve your question changes before saving");
      return;
    }
    const nextScript = mergeQuestionsIntoScript(fullScriptRef.current, questions);
    fullScriptRef.current = nextScript;
    const bodyConfig = {
      ...config,
      role: title,
      position: title,
      approved_script: nextScript,
      generated_script_draft: nextScript,
      script_approved: questionsApproved && Boolean(nextScript.trim()),
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
          role: title,
          criteria: String(config.criteria || config.screening_criteria || ""),
          config: bodyConfig,
          scheduled_start_at: patchBody.scheduled_start_at,
          scheduled_end_at: patchBody.scheduled_end_at,
        });
        await patchM.mutateAsync({ orderId, body: patchBody });
      }
      approvedScriptRef.current = nextScript;
      toast.success("Interview updated — changes apply to future calls only");
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
            {!readOnly ? (
              <Button variant="outline" asChild className="gap-1.5">
                <Link to="/interviews/new" search={{ order_id: orderId }}>
                  <Pencil className="size-4" /> Edit
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
          Live interview — you can change the calling window and interview questions. Opening lines and disclosures are fixed by your AI agent. Updates apply to <strong>future calls only</strong>.
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Interview settings</CardTitle>
          <CardDescription>
            Edit the calling schedule and numbered questions. Opening disclosure and intro are handled automatically — not shown here.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Interview name">
              <Input value={title} onChange={(e) => setTitle(e.target.value)} disabled={readOnly} />
            </Field>
            <Field label="Interview reference">
              <Input value={String(interviewNumber)} readOnly disabled className="font-mono text-xs" />
            </Field>
            <Field label="Calling start">
              <Input type="datetime-local" value={startAt} onChange={(e) => setStartAt(e.target.value)} disabled={readOnly} />
            </Field>
            <Field label="Calling end">
              <Input type="datetime-local" value={endAt} onChange={(e) => setEndAt(e.target.value)} disabled={readOnly} />
            </Field>
          </div>

          <Field label="Interview questions">
            <Textarea
              rows={12}
              value={questions}
              onChange={(e) => {
                setQuestions(e.target.value);
                setQuestionsApproved(false);
              }}
              disabled={readOnly}
              placeholder={"1. Tell me about your experience with…\n2. How would you handle…\n3. …"}
              className="font-mono text-sm leading-relaxed"
            />
            <p className="text-[11px] text-muted-foreground">
              One question per line, numbered. Do not include opening disclosure or intro — those are set on the voice agent.
            </p>
          </Field>

          {!readOnly ? (
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
              <div className="text-xs text-muted-foreground">
                {questionsApproved && !questionsDirty ? (
                  <span className="inline-flex items-center gap-1 text-success">
                    <CheckCircle2 className="size-3.5" /> Questions approved
                  </span>
                ) : questionsDirty ? (
                  "Approve questions after editing so you confirm what the AI will ask."
                ) : (
                  "Review questions, approve, then save."
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  className="gap-1.5"
                  disabled={!questions.trim() || (questionsApproved && !questionsDirty)}
                  onClick={onApproveQuestions}
                >
                  {questionsApproved && !questionsDirty ? <Lock className="size-4" /> : <CheckCircle2 className="size-4" />}
                  {questionsApproved && !questionsDirty ? "Approved" : "Approve questions"}
                </Button>
                <Button
                  className="gap-1.5"
                  onClick={() => void onSave()}
                  disabled={saveDraftM.isPending || patchM.isPending || (questionsDirty && !questionsApproved)}
                >
                  <Save className="size-4" />
                  {saveDraftM.isPending || patchM.isPending ? "Saving…" : "Save changes"}
                </Button>
              </div>
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
