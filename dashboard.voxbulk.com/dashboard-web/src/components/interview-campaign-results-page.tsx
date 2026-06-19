import * as React from "react";
import { Link } from "@tanstack/react-router";
import { ArrowLeft, Activity, CalendarClock, Download, FileText, Filter, Play, Search, Send, UserCheck } from "lucide-react";
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
import { downloadAuthenticatedFile, openAuthenticatedHtmlInTab } from "@/lib/api";
import { orderTab, orderToCampaign } from "@/lib/mappers/orders";
import { isInterviewCampaignReadOnly, interviewCampaignReadOnlyLabel, candidateAllowsResendBookingInvite } from "@/lib/interview-campaign";
import { useInterviewResults, useHubSpotStatus, useSaveInterviewShortlist, useSendInterviewScheduling, useServiceOrders, useSchedulingStatus, useStopInterviewCampaign } from "@/lib/queries";
import type { CampaignTone } from "@/lib/types/campaign";
import type { ServiceOrder } from "@/lib/types/api";
import { AtsScore } from "@/components/ats-score";
import { InterviewRecordingPlayer } from "@/components/interview-recording-player";
import { InterviewTranscriptDialog } from "@/components/interview-transcript-dialog";
import { CandidateActivityDialog, activityStatusLabel, activityStatusTone } from "@/components/candidate-activity-dialog";
import { CandidateContactDialog } from "@/components/candidate-contact-dialog";

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
  bookingStatus?: string;
  bookingTime?: string;
  booked_start_at?: string | null;
  invite_email_sent_at?: string | null;
  invite_email_failed?: string | null;
  outreach_email?: string;
  activity_status?: string;
  has_interview_report?: boolean;
  transcript_preview?: string | null;
  recording_play_url?: string | null;
  ats_score?: number | null;
  ats_status?: string | null;
  ats_label?: string | null;
};

const BOOKING_TZ = "Europe/London";

function parseUtc(iso?: string | null) {
  const raw = String(iso || "").trim();
  if (!raw) return new Date(NaN);
  if (!/[zZ]|[+-]\d{2}:\d{2}$/.test(raw)) return new Date(`${raw}Z`);
  return new Date(raw);
}

function fmtSchedule(iso?: string | null) {
  if (!iso) return "—";
  try {
    return parseUtc(iso).toLocaleString("en-GB", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: BOOKING_TZ,
      timeZoneName: "short",
    });
  } catch {
    return iso;
  }
}

function liveBookingDisplay(candidate: {
  booked_start_at?: string | null;
  activity_status?: string;
  invite_email_sent_at?: string | null;
}) {
  const status = String(candidate.activity_status || "").toLowerCase();
  if (candidate.booked_start_at && !["booking_cancelled"].includes(status)) {
    return {
      statusLabel: status === "booked_waiting" || status === "booked" ? "Booked" : activityStatusLabel(status),
      timeLabel: fmtSchedule(candidate.booked_start_at),
      tone: activityStatusTone(status),
    };
  }
  if (status === "booking_cancelled") {
    return { statusLabel: "Booking cancelled", timeLabel: "—", tone: activityStatusTone(status) };
  }
  if (["booking_email_sent", "awaiting_booking"].includes(status) || candidate.invite_email_sent_at) {
    return { statusLabel: "Waiting for booking", timeLabel: "—", tone: activityStatusTone("awaiting_booking") };
  }
  if (status === "calling") {
    return { statusLabel: "Calling now", timeLabel: "—", tone: activityStatusTone(status) };
  }
  if (status === "pending") {
    return { statusLabel: "Pending", timeLabel: "—", tone: activityStatusTone(status) };
  }
  return {
    statusLabel: activityStatusLabel(status),
    timeLabel: "—",
    tone: activityStatusTone(status),
  };
}

function isLiveOrder(order: ServiceOrder | undefined, tone: CampaignTone) {
  if (order?.is_live === true) return true;
  if (order?.is_finished === true) return false;
  if (order?.status === "running" || order?.status === "scheduled" || order?.status === "paused") return true;
  return tone === "live" || tone === "scheduled" || tone === "paused";
}

export function InterviewCampaignResultsPage({ orderId }: { orderId: string }) {
  const [open, setOpen] = React.useState<string | null>(null);
  const [activityCandidate, setActivityCandidate] = React.useState<CandidateRow | null>(null);
  const [contactCandidate, setContactCandidate] = React.useState<CandidateRow | null>(null);
  const [transcriptOpen, setTranscriptOpen] = React.useState(false);
  const [sendOpen, setSendOpen] = React.useState(false);
  const [selectedRows, setSelectedRows] = React.useState<Record<string, boolean>>({});

  const ordersQ = useServiceOrders("interview");
  const rawOrder = (ordersQ.data || []).find((o) => o.id === orderId);
  const current = rawOrder ? orderToCampaign(rawOrder, "interview") : null;
  const isLive = isLiveOrder(rawOrder, current?.status || "quoted");

  const resultsQ = useInterviewResults(orderId);
  const schedulingQ = useSchedulingStatus();
  const scheduling = (schedulingQ.data || {}) as Record<string, unknown>;
  const calendarReady = scheduling.human_scheduling_ready === true;
  const providerLabel = String(scheduling.provider_label || scheduling.provider || "").trim();
  const connectedAccount = String(scheduling.connected_account || scheduling.owner_name || "").trim();
  const bookingDisplay =
    calendarReady && providerLabel
      ? connectedAccount
        ? `${providerLabel} · ${connectedAccount}`
        : providerLabel
      : scheduling.legacy_unsupported_provider
        ? "Reconnect required (unsupported provider)"
        : "Not connected";
  const stopM = useStopInterviewCampaign();
  const [stopOpen, setStopOpen] = React.useState(false);
  const [stopConfirmText, setStopConfirmText] = React.useState("");
  const [stopError, setStopError] = React.useState("");
  const stopConfirmed = stopConfirmText.trim().toUpperCase() === "STOP";
  const results = resultsQ.data || {};
  const orderMeta = (results.order || {}) as Record<string, unknown>;
  const kpis = (results.kpis || {}) as Record<string, unknown>;
  const apiCandidates = (results.candidates || []) as Record<string, unknown>[];
  const campaignId = String(orderMeta.campaign_id || rawOrder?.campaign_id || "—");

  const rowsForSort: CandidateRow[] = React.useMemo(() => {
    if (isLive) {
      return apiCandidates.map((c) => {
        const booked_start_at = c.booked_start_at ? String(c.booked_start_at) : null;
        const invite_email_sent_at = c.invite_email_sent_at ? String(c.invite_email_sent_at) : null;
        const activity_status = String(c.activity_status || "");
        const booking = liveBookingDisplay({ booked_start_at, activity_status, invite_email_sent_at });
        return {
          id: String(c.id || c.name),
          name: String(c.name || "Candidate"),
          phone: String(c.phone || ""),
          email: String(c.outreach_email || c.email || ""),
          outreach_email: c.outreach_email ? String(c.outreach_email) : undefined,
          status: String(c.status || "Pending"),
          bookingStatus: booking.statusLabel,
          bookingTime: booking.timeLabel,
          scheduledAt: booking.timeLabel,
          booked_start_at,
          invite_email_sent_at,
          invite_email_failed: c.invite_email_failed ? String(c.invite_email_failed) : undefined,
          activity_status,
          ats_score: c.ats_score != null ? Number(c.ats_score) : null,
          ats_status: String(c.ats_status || ""),
          ats_label: String(c.ats_label || ""),
        };
      });
    }
    return apiCandidates.map((c) => ({
      id: String(c.id || c.name),
      name: String(c.name || "Candidate"),
      phone: String(c.phone || ""),
      email: String(c.outreach_email || c.email || ""),
      outreach_email: c.outreach_email ? String(c.outreach_email) : undefined,
      invite_email_failed: c.invite_email_failed ? String(c.invite_email_failed) : undefined,
      duration: String(c.duration_label || c.duration || "—"),
      duration_label: String(c.duration_label || ""),
      score: c.score != null ? Number(c.score) : null,
      recommendation: String(c.recommendation || "—"),
      sentiment: String(c.sentiment || "—"),
      has_interview_report: Boolean(c.has_interview_report),
      transcript_preview: (c.transcript_preview as string | null) ?? null,
      recording_play_url: (c.recording_play_url as string | null) ?? null,
      ats_score: c.ats_score != null ? Number(c.ats_score) : null,
      ats_status: String(c.ats_status || ""),
      ats_label: String(c.ats_label || ""),
    }));
  }, [apiCandidates, isLive]);

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

  const downloadReport = async (recipientId: string, kind: "html" | "pdf") => {
    try {
      const path =
        kind === "pdf"
          ? `/service-orders/${encodeURIComponent(orderId)}/recipients/${encodeURIComponent(recipientId)}/interview-candidate-report.pdf`
          : `/service-orders/${encodeURIComponent(orderId)}/recipients/${encodeURIComponent(recipientId)}/interview-candidate-report.html`;
      if (kind === "html") {
        await openAuthenticatedHtmlInTab(path);
        toast.success("Report opened in new tab");
      } else {
        await downloadAuthenticatedFile(path, `interview-report-${recipientId}.pdf`);
        toast.success("PDF downloaded");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Report failed");
    }
  };

  const onStopCampaign = async () => {
    if (!stopConfirmed) return;
    setStopError("");
    try {
      await stopM.mutateAsync({ orderId, reason: "Stopped by user from results" });
      toast.success("Interview stopped");
      setStopOpen(false);
      setStopConfirmText("");
    } catch (e) {
      const message = e instanceof Error ? e.message : "Stop failed";
      setStopError(message);
      toast.error(message);
    }
  };

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
  const campaignReadOnly = isInterviewCampaignReadOnly(rawOrder?.status) || rawOrder?.is_finished === true;
  const candidateOpen = open ? rowsForSort.find((c) => c.id === open) : null;
  const resendBookingInviteForOpen = candidateAllowsResendBookingInvite({
    orderStatus: rawOrder?.status,
    activityStatus: candidateOpen?.activity_status,
    recipientStatus: candidateOpen?.status,
    interviewCompleted: ["interview_completed", "report_ready"].includes(
      String(candidateOpen?.activity_status || "").toLowerCase(),
    ),
  });

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
            {isLive ? (
              <Button variant="destructive" className="gap-1.5" onClick={() => setStopOpen(true)}>
                Stop campaign
              </Button>
            ) : (
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
              <ResultKpi label="Calls attempted" value={String(kpis.attempted ?? kpis.called ?? 0)} sub={`${kpis.reach_rate_pct ?? 0}% completed`} />
              <ResultKpi label="Completed calls" value={String(kpis.reached ?? 0)} sub="Answered & screened" />
              <ResultKpi label="No answer / failed" value={String((kpis.no_answer ?? 0) + (kpis.failed ?? 0))} sub="Attempted but not completed" />
              <ResultKpi label="Recommended advance" value={String(kpis.recommended_advance ?? 0)} sub="After AI interview" />
              <ResultKpi label="Avg duration" value={String(kpis.avg_duration_label ?? "—")} sub="per call" />
            </>
          )}
        </div>
      )}

      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-3 p-3">
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 pl-2 text-xs text-muted-foreground">
              <Checkbox checked={allSelected} onCheckedChange={toggleAll} />
              Select all
            </label>
            <span
              className={
                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] " +
                (calendarReady
                  ? "border-success/40 bg-success/10 text-foreground"
                  : "border-warning/40 bg-warning/10 text-muted-foreground")
              }
              title={calendarReady ? `Booking via ${bookingDisplay}` : "Connect a booking provider in Settings → Integrations"}
            >
              <CalendarClock className="size-3.5 shrink-0" />
              Booking: {bookingDisplay}
              {!calendarReady ? (
                <Link to="/settings/integrations" className="ml-1 font-medium text-primary underline-offset-2 hover:underline">
                  Integrations
                </Link>
              ) : null}
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            <div className="relative w-full min-w-0 sm:w-44"><Search className="absolute left-2 top-2 size-4 text-muted-foreground" /><Input placeholder="Search candidate" className="h-8 w-full pl-8 text-xs" /></div>
            <Button size="sm" variant="outline" className="gap-1.5"><Filter className="size-3.5" /> Filter</Button>
            {!isLive && (
              <Button
                size="sm"
                className="gap-1.5"
                disabled={selectedCount === 0 || !calendarReady}
                title={
                  selectedCount === 0
                    ? "Select candidates first"
                    : !calendarReady
                      ? scheduling.legacy_unsupported_provider
                        ? "Your previous calendar provider is no longer supported — reconnect in Settings → Integrations"
                        : "Connect a booking provider in Settings → Integrations"
                      : providerLabel
                        ? `Via ${providerLabel}${connectedAccount ? ` (${connectedAccount})` : ""}`
                        : undefined
                }
                onClick={() => setSendOpen(true)}
              >
                <Send className="size-3.5" />
                <span className="flex flex-col items-start leading-tight">
                  <span>Send booking link {selectedCount > 0 && `(${selectedCount})`}</span>
                  {calendarReady && providerLabel ? (
                    <span className="text-[10px] font-normal opacity-80">Via {providerLabel}</span>
                  ) : null}
                </span>
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,360px)]">
        <Card>
          <CardContent className="px-0">
            {resultsQ.isLoading ? (
              <div className="space-y-2 p-6"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-full" /></div>
            ) : rowsForSort.length === 0 ? (
              <p className="p-8 text-center text-sm text-muted-foreground">No candidates yet for this campaign.</p>
            ) : (
              <div className="table-scroll">
              <Table>
                <TableHeader><TableRow>
                  <TableHead className="w-8 pl-4"></TableHead>
                  <SortHeader label="Name" sortKey="name" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} />
                  {isLive ? (
                    <>
                      <SortHeader label="Booking" sortKey="bookingStatus" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} />
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
                      <TableCell className="font-medium">
                        <button
                          type="button"
                          className="text-left font-medium text-primary underline-offset-2 hover:underline"
                          title={c.id}
                          onClick={(e) => {
                            e.stopPropagation();
                            setContactCandidate(c);
                          }}
                        >
                          {c.name}
                        </button>
                      </TableCell>
                      {isLive ? (
                        <>
                          <TableCell className="text-xs">
                            <StatusBadge tone={activityStatusTone(c.activity_status)}>{c.bookingStatus}</StatusBadge>
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">{c.phone}</TableCell>
                          <TableCell className="text-xs">
                            {c.activity_status === "booking_cancelled" ? (
                              <span className="font-medium text-destructive">Booking cancelled</span>
                            ) : (
                              <span className="capitalize">{String(c.activity_status || c.status || "pending").replace(/_/g, " ")}</span>
                            )}
                          </TableCell>
                          <TableCell><AtsScore score={c.ats_score} status={c.ats_status} label={c.ats_label} /></TableCell>
                        </>
                      ) : (
                        <>
                          <TableCell className="text-xs tabular-nums">{c.duration}</TableCell>
                          <TableCell><AtsScore score={c.ats_score} status={c.ats_status} label={c.ats_label} /></TableCell>
                          <TableCell><ScoreBar score={c.has_interview_report ? (c.score || 0) : 0} /></TableCell>
                          <TableCell className="text-sm">{c.has_interview_report ? c.recommendation : "Awaiting interview"}</TableCell>
                          <TableCell className="text-sm">{c.has_interview_report ? c.sentiment : "—"}</TableCell>
                        </>
                      )}
                      <TableCell className="pr-4 text-right">
                        {isLive ? (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="gap-1.5"
                            onClick={(e) => {
                              e.stopPropagation();
                              setActivityCandidate(c);
                            }}
                          >
                            <Activity className="size-4" /> Activity
                          </Button>
                        ) : (
                          <div className="inline-flex gap-1">
                            <Button
                              size="sm"
                              variant="ghost"
                              className="gap-1.5"
                              onClick={(e) => {
                                e.stopPropagation();
                                setActivityCandidate(c);
                              }}
                            >
                              <Activity className="size-4" /> Activity
                            </Button>
                            {c.has_interview_report && (c.status === "completed" || c.activity_status === "report_ready") && (
                              <>
                                <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); void downloadReport(c.id, "html"); }}>Report</Button>
                                <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); void downloadReport(c.id, "pdf"); }}>PDF</Button>
                              </>
                            )}
                            {c.has_interview_report ? (
                              <Button size="icon" variant="ghost" aria-label="Play recording" onClick={(e) => { e.stopPropagation(); setOpen(c.id); }}>
                                <Play className="size-4" />
                              </Button>
                            ) : (
                              <span className="px-2 text-xs text-muted-foreground">No interview yet</span>
                            )}
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              </div>
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
                <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground">
                  <CalendarClock className="size-3.5" /> Booking status
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <StatusBadge tone={activityStatusTone(candidateOpen.activity_status)}>
                    {candidateOpen.bookingStatus}
                  </StatusBadge>
                </div>
                {candidateOpen.booked_start_at ? (
                  <p className="mt-2 text-base font-semibold tabular-nums">{candidateOpen.bookingTime} UK</p>
                ) : (
                  <p className="mt-2 text-sm text-muted-foreground">
                    {candidateOpen.bookingStatus === "Waiting for booking"
                      ? "Invite sent — waiting for the candidate to pick a slot."
                      : "No interview slot booked yet."}
                  </p>
                )}
              </div>
              <div className="rounded-lg border border-border bg-muted/40 p-3 space-y-2">
                <div>
                  <p className="text-xs uppercase tracking-wider text-muted-foreground">Email</p>
                  <p className="mt-1 font-medium break-all">{candidateOpen.email || "—"}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wider text-muted-foreground">Phone</p>
                  <p className="mt-1 font-medium">{candidateOpen.phone || "—"}</p>
                </div>
              </div>
              <div className="pt-1"><AtsScore score={candidateOpen.ats_score} status={candidateOpen.ats_status} label={candidateOpen.ats_label} /></div>
              <p className="text-xs text-muted-foreground">
                {resendBookingInviteForOpen
                  ? "Click the candidate name for contact details and resend invite. Use Activity for the full timeline."
                  : candidateOpen?.has_interview_report || candidateOpen?.activity_status === "report_ready"
                    ? "Click the candidate name for contact details. The AI interview is complete — resend invite is not available."
                    : "Click the candidate name for contact details. Resend invite is available after you launch the campaign."}
              </p>
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
              {candidateOpen.has_interview_report ? (
                <>
                  <InterviewRecordingPlayer playPath={candidateOpen.recording_play_url} durationLabel={candidateOpen.duration_label || candidateOpen.duration} />
                  <Button variant="outline" size="sm" className="w-full gap-1.5" onClick={() => setTranscriptOpen(true)}>
                    <FileText className="size-3.5" /> Open transcript
                  </Button>
                  <Button variant="outline" size="sm" className="w-full gap-1.5" onClick={() => void downloadReport(candidateOpen.id, "html")}>
                    <FileText className="size-3.5" /> Full report
                  </Button>
                  <Button variant="outline" size="sm" className="w-full gap-1.5" onClick={() => void downloadReport(candidateOpen.id, "pdf")}>
                    <Download className="size-3.5" /> Report PDF
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
                </>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Interview not completed yet. Results and reports appear here after the AI phone call finishes.
                </p>
              )}
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
      <CandidateContactDialog
        open={contactCandidate != null}
        onOpenChange={(next) => {
          if (!next) setContactCandidate(null);
        }}
        orderId={orderId}
        readOnly={campaignReadOnly}
        allowResendBookingInvite={!campaignReadOnly && resendBookingInviteForOpen}
        candidate={contactCandidate}
      />
      <CandidateActivityDialog
        open={activityCandidate != null}
        onOpenChange={(next) => {
          if (!next) setActivityCandidate(null);
        }}
        orderId={orderId}
        recipientId={activityCandidate?.id ?? null}
        candidateName={activityCandidate?.name}
      />

      <Dialog
        open={stopOpen}
        onOpenChange={(open) => {
          setStopOpen(open);
          if (!open) {
            setStopConfirmText("");
            setStopError("");
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Stop interview campaign</DialogTitle>
            <DialogDescription>
              Pending AI calls will stop. Booked candidates keep their slots until cancelled individually.
            </DialogDescription>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">Type <strong>STOP</strong> to confirm.</p>
          <Input
            value={stopConfirmText}
            onChange={(e) => {
              setStopConfirmText(e.target.value);
              if (stopError) setStopError("");
            }}
            placeholder="STOP"
            onKeyDown={(e) => {
              if (e.key === "Enter" && stopConfirmed && !stopM.isPending) void onStopCampaign();
            }}
          />
          {stopError ? <p className="text-sm text-destructive">{stopError}</p> : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => { setStopOpen(false); setStopConfirmText(""); setStopError(""); }}>Cancel</Button>
            <Button variant="destructive" disabled={!stopConfirmed || stopM.isPending} onClick={() => void onStopCampaign()}>
              {stopM.isPending ? "Stopping…" : "Stop campaign"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
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
  const shortlistM = useSaveInterviewShortlist(orderId);
  const sendM = useSendInterviewScheduling(orderId);
  const schedulingQ = useSchedulingStatus();
  const hubspotQ = useHubSpotStatus();
  const [busy, setBusy] = React.useState(false);
  const scheduling = (schedulingQ.data || {}) as Record<string, unknown>;
  const hubspot = (hubspotQ.data || {}) as Record<string, unknown>;
  const calendarReady = scheduling.human_scheduling_ready === true;
  const hubspotReady = hubspot.connected === true;
  const providerLabel = String(scheduling.provider_label || scheduling.provider || "booking provider").trim();
  const connectedAccount = String(scheduling.connected_account || scheduling.owner_name || "").trim();
  const legacyUnsupported = Boolean(scheduling.legacy_unsupported_provider);

  const onSend = async () => {
    if (recipientIds.length === 0) return;
    setBusy(true);
    try {
      await shortlistM.mutateAsync(recipientIds);
      const res = await sendM.mutateAsync({ recipient_ids: recipientIds, channels: ["email"] });
      const em = Number((res as Record<string, unknown>).email_sent || 0);
      const hs = Number((res as Record<string, unknown>).hubspot_synced || 0);
      const sentProvider = String((res as Record<string, unknown>).provider_label || providerLabel || "").trim();
      const errs = (res as Record<string, unknown>).errors;
      if (em > 0) {
        toast.success(
          `Sent ${em} email${em === 1 ? "" : "s"} via ${sentProvider || "your booking provider"}${hs > 0 ? ` · ${hs} synced to HubSpot` : ""}`,
        );
      } else if (Array.isArray(errs) && errs.length) {
        toast.error(String(errs[0]));
      } else {
        toast.error("Nothing was sent");
      }
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
          <DialogTitle>Send human interview links</DialogTitle>
          <DialogDescription>
            Each shortlisted candidate receives an email with a booking link from your connected calendar provider.
            {hubspotReady ? " Connected HubSpot contacts will be updated automatically." : ""}
          </DialogDescription>
        </DialogHeader>
        {calendarReady ? (
          <p className="rounded-md border border-success/40 bg-success/10 p-3 text-sm">
            <strong>Sending via {providerLabel}</strong>
            {connectedAccount ? ` (${connectedAccount})` : ""}
          </p>
        ) : legacyUnsupported ? (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-muted-foreground">
            Your previous calendar provider is no longer supported. Reconnect in{" "}
            <Link to="/settings/integrations" className="font-medium text-foreground underline-offset-2 hover:underline">
              Settings → Integrations
            </Link>
            .
          </p>
        ) : (
          <p className="rounded-md border border-warning/40 bg-warning/10 p-3 text-sm text-muted-foreground">
            Connect a booking provider in{" "}
            <Link to="/settings/integrations" className="font-medium text-foreground underline-offset-2 hover:underline">
              Settings → Integrations
            </Link>{" "}
            before sending.
          </p>
        )}
        {!hubspotReady ? (
          <p className="rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
            Optional: connect HubSpot in{" "}
            <Link to="/settings/integrations" className="text-primary underline-offset-2 hover:underline">
              Settings → Integrations
            </Link>{" "}
            to sync shortlisted candidates to your CRM.
          </p>
        ) : null}
        <p className="rounded-md border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
          Human interview links are sent by <strong>email only</strong> from {providerLabel}.
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button onClick={() => void onSend()} disabled={count === 0 || busy || !calendarReady}>{busy ? "Sending…" : `Send email to ${count}`}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
