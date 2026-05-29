import * as React from "react";
import { Link } from "@tanstack/react-router";
import { ArrowLeft, CalendarClock, Download, FileText, Filter, Mail, MessageCircle, Play, Search, Send, UserCheck } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { downloadAuthenticatedFile } from "@/lib/api";
import { orderTab, orderToCampaign } from "@/lib/mappers/orders";
import { useInterviewResults, useSaveInterviewShortlist, useSendInterviewScheduling, useServiceOrders } from "@/lib/queries";
import type { CampaignTone } from "@/lib/types/campaign";
import type { ServiceOrder } from "@/lib/types/api";
import { AtsScore } from "@/components/ats-score";
import { InterviewRecordingPlayer } from "@/components/interview-recording-player";
import { InterviewTranscriptDialog } from "@/components/interview-transcript-dialog";

export type CandidateRow = {
  id: string;
  name: string;
  phone?: string;
  email?: string;
  duration?: string;
  duration_label?: string;
  score?: number;
  recommendation?: string;
  sentiment?: string;
  status?: string;
  scheduledAt?: string;
  transcript_preview?: string | null;
  recording_play_url?: string | null;
  ats_score?: number | null;
  ats_status?: string | null;
  ats_label?: string | null;
};

function fmtSchedule(iso?: string | null) {
  if (!iso) return "Pending";
  try {
    return new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

function isLiveOrder(order: ServiceOrder | undefined, tone: CampaignTone) {
  if (order?.is_finished) return false;
  if (order?.status === "running" || order?.status === "scheduled") return true;
  return tone === "live" || tone === "scheduled" || tone === "paused";
}

export function InterviewCampaignResultsPage({ orderId }: { orderId: string }) {
  const [open, setOpen] = React.useState<string | null>(null);
  const [transcriptOpen, setTranscriptOpen] = React.useState(false);
  const [sendOpen, setSendOpen] = React.useState(false);
  const [selectedRows, setSelectedRows] = React.useState<Record<string, boolean>>({});

  const ordersQ = useServiceOrders("interview");
  const rawOrder = (ordersQ.data || []).find((o) => o.id === orderId);
  const current = rawOrder ? orderToCampaign(rawOrder, "interview") : null;
  const isLive = isLiveOrder(rawOrder, current?.status || "quoted");

  const resultsQ = useInterviewResults(orderId);
  const results = resultsQ.data || {};
  const orderMeta = (results.order || {}) as Record<string, unknown>;
  const kpis = (results.kpis || {}) as Record<string, unknown>;
  const apiCandidates = (results.candidates || []) as Record<string, unknown>[];
  const campaignId = String(orderMeta.campaign_id || rawOrder?.campaign_id || "—");

  const rowsForSort: CandidateRow[] = React.useMemo(() => {
    if (isLive) {
      return apiCandidates.map((c) => ({
        id: String(c.id || c.name),
        name: String(c.name || "Candidate"),
        phone: String(c.phone || ""),
        email: String(c.email || ""),
        status: String(c.status || "Pending"),
        scheduledAt: fmtSchedule(String(c.scheduling_sent_at || orderMeta.scheduled_start_at || "")),
        ats_score: c.ats_score != null ? Number(c.ats_score) : null,
        ats_status: String(c.ats_status || ""),
        ats_label: String(c.ats_label || ""),
      }));
    }
    return apiCandidates.map((c) => ({
      id: String(c.id || c.name),
      name: String(c.name || "Candidate"),
      phone: String(c.phone || ""),
      email: String(c.email || ""),
      duration: String(c.duration_label || c.duration || "—"),
      duration_label: String(c.duration_label || ""),
      score: Number(c.score || 0),
      recommendation: String(c.recommendation || "—"),
      sentiment: String(c.sentiment || "—"),
      transcript_preview: (c.transcript_preview as string | null) ?? null,
      recording_play_url: (c.recording_play_url as string | null) ?? null,
      ats_score: c.ats_score != null ? Number(c.ats_score) : null,
      ats_status: String(c.ats_status || ""),
      ats_label: String(c.ats_label || ""),
    }));
  }, [apiCandidates, isLive, orderMeta.scheduled_start_at]);

  const candSort = useTableSort(rowsForSort as Record<string, unknown>[]);
  const allSelected = rowsForSort.length > 0 && rowsForSort.every((r) => selectedRows[r.id]);

  const toggleAll = () => {
    if (allSelected) {
      setSelectedRows({});
      return;
    }
    const next: Record<string, boolean> = {};
    rowsForSort.forEach((r) => {
      next[r.id] = true;
    });
    setSelectedRows(next);
  };

  React.useEffect(() => {
    setSelectedRows({});
    setOpen(null);
  }, [orderId]);

  const exportResults = async (kind: "pdf" | "csv") => {
    try {
      const ext = kind === "pdf" ? "pdf" : "csv";
      await downloadAuthenticatedFile(
        `/service-orders/${encodeURIComponent(orderId)}/interview-results/export.${ext}`,
        `interview-results-${campaignId !== "—" ? campaignId : orderId.slice(0, 8)}.${ext}`,
      );
      toast.success(`${kind.toUpperCase()} downloaded`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    }
  };

  if (ordersQ.isLoading || !current) {
    return (
      <div className="flex w-full flex-col gap-6">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!rawOrder) {
    return (
      <div className="flex w-full flex-col gap-6">
        <PageHeader eyebrow="Campaign" title="Not found" description="This interview campaign could not be loaded." />
        <Button asChild variant="outline"><Link to="/interviews">Back to interviews</Link></Button>
      </div>
    );
  }

  const selectedCount = Object.values(selectedRows).filter(Boolean).length;
  const candidateOpen = open ? rowsForSort.find((c) => c.id === open) : null;

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Campaign results"
        title={current.name}
        description={`${campaignId} · ${isLive ? "Live campaign — track call progress." : "Candidate transcripts, scores, and AI recommendations."}`}
        actions={
          <>
            <Button variant="ghost" className="gap-1.5" asChild>
              <Link to="/interviews"><ArrowLeft className="size-4" /> Back</Link>
            </Button>
            {!isLive && (
              <>
                <Button variant="outline" className="gap-1.5" onClick={() => void exportResults("pdf")}><Download className="size-4" /> Export PDF</Button>
                <Button variant="outline" className="gap-1.5" onClick={() => void exportResults("csv")}><Download className="size-4" /> Export CSV</Button>
              </>
            )}
          </>
        }
      />

      {isLive && (
        <Card>
          <CardContent className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4 text-sm">
            <LiveMeta label="Campaign ID" value={campaignId} />
            <LiveMeta label="Schedule start" value={fmtSchedule(String(orderMeta.scheduled_start_at || rawOrder?.scheduled_start_at || ""))} />
            <LiveMeta label="Schedule end" value={fmtSchedule(String(orderMeta.scheduled_end_at || rawOrder?.scheduled_end_at || ""))} />
            <LiveMeta label="Candidates" value={String(orderMeta.recipient_count || rawOrder?.recipient_count || apiCandidates.length)} />
          </CardContent>
        </Card>
      )}

      {!isLive && (
        <div className="grid gap-4 md:grid-cols-4">
          {resultsQ.isLoading ? (
            Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)
          ) : (
            <>
              <ResultKpi label="Campaign ID" value={campaignId} sub="tracking reference" />
              <ResultKpi label="Completed calls" value={String(kpis.reached ?? apiCandidates.length)} sub={`${kpis.reach_rate_pct ?? 100}% reached`} />
              <ResultKpi label="Recommended advance" value={String(kpis.recommended_advance ?? 0)} sub="AI shortlist" />
              <ResultKpi label="Avg duration" value={String(kpis.avg_duration_label ?? "—")} sub="per call" />
            </>
          )}
        </div>
      )}

      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-3 p-3">
          <label className="flex items-center gap-2 pl-2 text-xs text-muted-foreground">
            <Checkbox checked={allSelected} onCheckedChange={toggleAll} />
            Select all
          </label>
          <div className="flex flex-wrap gap-2">
            <div className="relative"><Search className="absolute left-2 top-2 size-4 text-muted-foreground" /><Input placeholder="Search candidate" className="h-8 w-44 pl-8 text-xs" /></div>
            <Button size="sm" variant="outline" className="gap-1.5"><Filter className="size-3.5" /> Filter</Button>
            {!isLive && (
              <Button size="sm" className="gap-1.5" disabled={selectedCount === 0} onClick={() => setSendOpen(true)}>
                <Send className="size-3.5" /> Send booking link {selectedCount > 0 && `(${selectedCount})`}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <Card>
          <CardContent className="px-0">
            {resultsQ.isLoading ? (
              <div className="space-y-2 p-6"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-full" /></div>
            ) : rowsForSort.length === 0 ? (
              <p className="p-8 text-center text-sm text-muted-foreground">No candidates yet for this campaign.</p>
            ) : (
              <Table>
                <TableHeader><TableRow>
                  <TableHead className="w-8 pl-4"></TableHead>
                  <SortHeader label="Name" sortKey="name" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} />
                  {isLive ? (
                    <>
                      <SortHeader label="Scheduled" sortKey="scheduledAt" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} />
                      <SortHeader label="Contact" sortKey="phone" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} />
                      <SortHeader label="Status" sortKey="status" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} />
                      <TableHead>ATS</TableHead>
                    </>
                  ) : (
                    <>
                      <SortHeader label="Duration" sortKey="duration" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} />
                      <TableHead>ATS</TableHead>
                      <SortHeader label="Score" sortKey="score" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} />
                      <SortHeader label="Recommendation" sortKey="recommendation" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} />
                      <SortHeader label="Sentiment" sortKey="sentiment" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} />
                    </>
                  )}
                  <TableHead className="pr-4 text-right"></TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {candSort.sorted.map((c: CandidateRow) => (
                    <TableRow key={c.id} className="cursor-pointer" onClick={() => setOpen(c.id)}>
                      <TableCell className="pl-4">
                        <Checkbox checked={!!selectedRows[c.id]} onCheckedChange={(v) => setSelectedRows((s) => ({ ...s, [c.id]: !!v }))} onClick={(e) => e.stopPropagation()} />
                      </TableCell>
                      <TableCell className="font-medium">{c.name}</TableCell>
                      {isLive ? (
                        <>
                          <TableCell className="text-xs"><span className="inline-flex items-center gap-1.5"><CalendarClock className="size-3.5 text-muted-foreground" />{c.scheduledAt}</span></TableCell>
                          <TableCell className="text-xs text-muted-foreground">{c.phone}</TableCell>
                          <TableCell className="text-xs capitalize">{c.status}</TableCell>
                          <TableCell><AtsScore score={c.ats_score} status={c.ats_status} label={c.ats_label} /></TableCell>
                        </>
                      ) : (
                        <>
                          <TableCell className="text-xs tabular-nums">{c.duration}</TableCell>
                          <TableCell><AtsScore score={c.ats_score} status={c.ats_status} label={c.ats_label} /></TableCell>
                          <TableCell><ScoreBar score={c.score || 0} /></TableCell>
                          <TableCell className="text-sm">{c.recommendation}</TableCell>
                          <TableCell className="text-sm">{c.sentiment}</TableCell>
                        </>
                      )}
                      <TableCell className="pr-4 text-right">
                        {!isLive && (
                          <Button size="icon" variant="ghost" aria-label="Play recording" onClick={(e) => { e.stopPropagation(); setOpen(c.id); }}>
                            <Play className="size-4" />
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        {open && isLive && candidateOpen && (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">{candidateOpen.name}</CardTitle>
              <Button size="sm" variant="ghost" onClick={() => setOpen(null)}>Close</Button>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="rounded-lg border border-border bg-muted/40 p-3">
                <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground"><CalendarClock className="size-3.5" /> Scheduled</div>
                <p className="mt-1 text-base font-semibold">{candidateOpen.scheduledAt}</p>
              </div>
              <div className="pt-1"><AtsScore score={candidateOpen.ats_score} status={candidateOpen.ats_status} label={candidateOpen.ats_label} /></div>
            </CardContent>
          </Card>
        )}

        {open && !isLive && candidateOpen && (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">{candidateOpen.name}</CardTitle>
              <Button size="sm" variant="ghost" onClick={() => setOpen(null)}>Close</Button>
            </CardHeader>
            <CardContent className="space-y-3">
              <InterviewRecordingPlayer playPath={candidateOpen.recording_play_url} durationLabel={candidateOpen.duration_label || candidateOpen.duration} />
              <Button variant="outline" size="sm" className="w-full gap-1.5" onClick={() => setTranscriptOpen(true)}>
                <FileText className="size-3.5" /> Open transcript
              </Button>
              <div className="rounded-lg border border-success/30 bg-success/10 p-3">
                <div className="flex items-start gap-2">
                  <UserCheck className="mt-0.5 size-4 text-success" />
                  <div>
                    <p className="text-sm font-medium">AI recommendation</p>
                    <p className="mt-1 text-xs text-muted-foreground">{candidateOpen.recommendation} — {candidateOpen.sentiment}</p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      <SendBookingDialog
        open={sendOpen}
        onOpenChange={setSendOpen}
        count={selectedCount}
        orderId={orderId}
        recipientIds={Object.entries(selectedRows).filter(([, v]) => v).map(([id]) => id)}
      />
      <InterviewTranscriptDialog open={transcriptOpen} onOpenChange={setTranscriptOpen} orderId={orderId} recipientId={open} candidateName={candidateOpen?.name} />
    </div>
  );
}

function LiveMeta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="mt-1 font-medium">{value}</p>
    </div>
  );
}

function SendBookingDialog({ open, onOpenChange, count, orderId, recipientIds }: { open: boolean; onOpenChange: (v: boolean) => void; count: number; orderId: string; recipientIds: string[] }) {
  const [channel, setChannel] = React.useState<"email" | "whatsapp" | "both">("both");
  const shortlistM = useSaveInterviewShortlist(orderId);
  const sendM = useSendInterviewScheduling(orderId);
  const [busy, setBusy] = React.useState(false);
  const channels = channel === "both" ? ["whatsapp", "email"] : channel === "whatsapp" ? ["whatsapp"] : ["email"];

  const onSend = async () => {
    if (recipientIds.length === 0) return;
    setBusy(true);
    try {
      await shortlistM.mutateAsync(recipientIds);
      const res = await sendM.mutateAsync({ recipient_ids: recipientIds, channels });
      const wa = Number((res as Record<string, unknown>).whatsapp_sent || 0);
      const em = Number((res as Record<string, unknown>).email_sent || 0);
      if (wa + em > 0) toast.success(`Sent ${wa} WhatsApp and ${em} email invite(s)`);
      else toast.error("Nothing was sent");
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Send failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Send booking links</DialogTitle>
          <DialogDescription>Each candidate gets a unique link to book a slot in your calling window.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-3 gap-2">
          <ChannelOption icon={<Mail className="size-4" />} label="Email" active={channel === "email"} onClick={() => setChannel("email")} />
          <ChannelOption icon={<MessageCircle className="size-4" />} label="WhatsApp" active={channel === "whatsapp"} onClick={() => setChannel("whatsapp")} />
          <ChannelOption icon={<Send className="size-4" />} label="Both" active={channel === "both"} onClick={() => setChannel("both")} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button onClick={() => void onSend()} disabled={count === 0 || busy}>{busy ? "Sending…" : `Send to ${count}`}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ChannelOption({ icon, label, active, onClick }: { icon: React.ReactNode; label: string; active: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className={"flex flex-col items-center gap-1 rounded-md border p-3 text-xs " + (active ? "border-primary bg-primary/10" : "border-border")}>
      {icon}<span>{label}</span>
    </button>
  );
}

function ScoreBar({ score }: { score: number }) {
  const tone = score >= 80 ? "bg-success" : score >= 60 ? "bg-warning" : "bg-destructive";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 rounded-full bg-border"><div className={`h-full rounded-full ${tone}`} style={{ width: `${score}%` }} /></div>
      <span className="w-7 text-right text-xs tabular-nums">{score}</span>
    </div>
  );
}

function ResultKpi({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <Card><CardContent className="p-4">
      <p className="text-xs uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight font-mono">{value}</p>
      <p className="text-xs text-muted-foreground">{sub}</p>
    </CardContent></Card>
  );
}

void orderTab;
