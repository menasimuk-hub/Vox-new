import { createFileRoute, Link, useNavigate, useParams } from "@tanstack/react-router";
import * as React from "react";
import { Play, Pause, Pencil, Copy, Trash2, Square, FileBarChart, Coins } from "lucide-react";

import { SurveyIdentityHeader } from "@/components/survey-identity-header";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { PaymentModal } from "@/components/modals";
import { gocardlessAvailable, startGoCardlessOrderPayment } from "@/lib/billing/gocardless";
import { useSession } from "@/lib/session";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { orderToCampaign } from "@/lib/mappers/orders";
import { useDeleteOrder, usePatchServiceOrder, useServiceOrder } from "@/lib/queries";

export const Route = createFileRoute("/_app/surveys/$id")({
  component: SurveyDetail,
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

function SurveyDetail() {
  const { id } = useParams({ from: "/_app/surveys/$id" });
  const navigate = useNavigate();
  const { session } = useSession();

  React.useEffect(() => {
    void navigate({ to: "/surveys/new", search: { order_id: id }, replace: true });
  }, [id, navigate]);
  const orderQ = useServiceOrder(id);
  const patchM = usePatchServiceOrder();
  const deleteM = useDeleteOrder();
  const gcReady = gocardlessAvailable(session?.subscription as Record<string, unknown> | null);

  const order = orderQ.data;
  const c = order ? orderToCampaign(order, "survey") : null;

  const [del, setDel] = React.useState(false);
  const [pay, setPay] = React.useState(false);
  const [payBusy, setPayBusy] = React.useState(false);
  const [title, setTitle] = React.useState("");
  const [startAt, setStartAt] = React.useState("");
  const [endAt, setEndAt] = React.useState("");

  React.useEffect(() => {
    if (!order) return;
    setTitle(order.title || "");
    setStartAt(toLocalInput(order.scheduled_start_at));
    setEndAt(toLocalInput(order.scheduled_end_at));
  }, [order]);

  const onSave = async () => {
    try {
      await patchM.mutateAsync({
        orderId: id,
        body: { title, scheduled_start_at: startAt || null, scheduled_end_at: endAt || null },
      });
      toast.success("Survey updated");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Save failed");
    }
  };

  const onDelete = async () => {
    try {
      await deleteM.mutateAsync(id);
      toast.success("Survey deleted");
      setDel(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    }
  };

  if (orderQ.isLoading) {
    return <div className="p-8"><Skeleton className="h-40 w-full" /></div>;
  }

  if (!order || !c) {
    return <p className="p-8 text-sm text-muted-foreground">Survey not found.</p>;
  }

  const quote = String((order as Record<string, unknown>).quote_total_display || order.quote_total_gbp || "—");

  const onPaySurvey = async () => {
    if (!gcReady) {
      toast.error("GoCardless checkout is not configured");
      return;
    }
    setPayBusy(true);
    try {
      await startGoCardlessOrderPayment(id);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not start GoCardless checkout");
      setPayBusy(false);
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Survey detail"
        title={c.name}
        description={
          (
            <div className="space-y-2">
              <SurveyIdentityHeader
                surveyName={c.name}
                surveyId={c.surveyId || order.campaign_id || order.survey_id}
                channel={c.surveyChannel}
                compact
              />
              <span className="flex items-center gap-2 text-sm text-muted-foreground">
                <StatusBadge tone={c.status} /> · {c.responses}/{c.target} responses
              </span>
            </div>
          ) as unknown as string
        }
        actions={
          <>
            <Button variant="ghost" asChild><Link to="/surveys">← Back</Link></Button>
            <Button variant="outline" asChild><Link to="/surveys/results" search={{ orderId: id }}><FileBarChart className="mr-1.5 size-4" /> View report</Link></Button>
          </>
        }
      />

      <div className="flex flex-wrap gap-2">
        {c.status === "awaiting-payment" || c.status === "quoted" ? (
          <Button className="gap-1.5" onClick={() => setPay(true)}><Coins className="size-4" /> Pay</Button>
        ) : null}
        <Button variant="outline" className="gap-1.5"><Play className="size-4" /> Start survey</Button>
        <Button variant="outline" className="gap-1.5"><Pencil className="size-4" /> Edit</Button>
        <Button variant="outline" className="gap-1.5"><Copy className="size-4" /> Duplicate</Button>
        {c.status === "live" ? (
          <Button variant="outline" className="gap-1.5"><Pause className="size-4" /> Pause</Button>
        ) : (
          <Button variant="outline" className="gap-1.5"><Play className="size-4" /> Resume</Button>
        )}
        <Button variant="outline" className="gap-1.5"><Square className="size-4" /> Stop</Button>
        <Button variant="ghost" className="ml-auto gap-1.5 text-destructive hover:text-destructive" onClick={() => setDel(true)}><Trash2 className="size-4" /> Delete</Button>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Inline edit</CardTitle></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <Field label="Title"><Input value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
          <Field label="Start"><Input type="datetime-local" value={startAt} onChange={(e) => setStartAt(e.target.value)} /></Field>
          <Field label="End"><Input type="datetime-local" value={endAt} onChange={(e) => setEndAt(e.target.value)} /></Field>
          <div className="md:col-span-2 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => {
              setTitle(order.title || "");
              setStartAt(toLocalInput(order.scheduled_start_at));
              setEndAt(toLocalInput(order.scheduled_end_at));
            }}>Cancel</Button>
            <Button onClick={() => void onSave()} disabled={patchM.isPending}>{patchM.isPending ? "Saving…" : "Save changes"}</Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <DetailCard title="Setup">
          <DRow label="Contacts" value={`${c.target.toLocaleString()} recipients`} />
          <DRow label="Channel" value={String((order.config as Record<string, unknown> | undefined)?.delivery || "AI call / WhatsApp")} />
          <DRow label="Prompt status" value={<StatusBadge tone="approved-script" /> as unknown as string} />
        </DetailCard>
        <DetailCard title="Billing">
          <DRow label="Quote" value={quote} />
          <DRow label="Payment" value={<StatusBadge tone={c.status === "payment-failed" ? "payment-failed" : "awaiting-payment"} /> as unknown as string} />
          <DRow label="Status" value={order.payment_status || order.status} />
        </DetailCard>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Progress</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <ProgressRow label="Completion" value={c.completion} />
        </CardContent>
      </Card>

      <Dialog open={del} onOpenChange={setDel}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete survey?</DialogTitle>
            <DialogDescription>This cannot be undone.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDel(false)}>Cancel</Button>
            <Button variant="destructive" onClick={() => void onDelete()} disabled={deleteM.isPending}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <PaymentModal
        open={pay}
        onOpenChange={setPay}
        amount={quote}
        busy={payBusy}
        gcAvailable={gcReady}
        onPayGoCardless={() => void onPaySurvey()}
      />
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label className="text-xs">{label}</Label>{children}</div>;
}
function DetailCard({ title, children }: { title: string; children: React.ReactNode }) {
  return <Card><CardHeader><CardTitle className="text-base">{title}</CardTitle></CardHeader><CardContent className="space-y-2 text-sm">{children}</CardContent></Card>;
}
function DRow({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="flex items-center justify-between border-b border-border/60 py-1.5 last:border-0">
    <span className="text-muted-foreground">{label}</span><span className="font-medium">{value}</span>
  </div>;
}
function ProgressRow({ label, value }: { label: string; value: number }) {
  return <div>
    <div className="mb-1 flex justify-between text-xs"><span>{label}</span><span className="tabular-nums text-muted-foreground">{value}%</span></div>
    <Progress value={value} className="h-1.5" />
  </div>;
}
