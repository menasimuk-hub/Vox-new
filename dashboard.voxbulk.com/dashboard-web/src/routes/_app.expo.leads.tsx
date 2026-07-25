import { createFileRoute, Link } from "@tanstack/react-router";
import {
  Download,
  Flame,
  Mail,
  Phone,
  QrCode,
  Snowflake,
  Thermometer,
  Trash2,
  Building2,
  User,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch, buildAuthHeaders, downloadAuthenticatedFile, getApiBaseUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

type LeadAnswer = {
  question_key?: string;
  question_label?: string;
  question_prompt?: string;
  answer_text?: string | null;
  original_text?: string | null;
  answer_text_en?: string | null;
  answer_source?: string | null;
  step_order?: number;
};

type LeadRow = {
  id: string;
  created_at?: string | null;
  detected_language?: string | null;
  country_hint?: string | null;
  visitor_phone?: string | null;
  visitor_email?: string | null;
  name?: string | null;
  company?: string | null;
  interest?: string | null;
  buying_timeline?: string | null;
  lead_score?: string | null;
  booth_name?: string | null;
  booth_code?: string | null;
  offer_sent_at?: string | null;
  follow_up_status?: string | null;
  assets_sent?: string[];
  consent_acknowledged?: boolean;
  business_card_url?: string | null;
  answers?: LeadAnswer[];
};

export const Route = createFileRoute("/_app/expo/leads")({
  head: () => ({ meta: [{ title: "Expo leads — VoxBulk" }] }),
  validateSearch: (search: Record<string, unknown>) => ({
    booth_id: typeof search.booth_id === "string" ? search.booth_id : undefined,
  }),
  component: ExpoLeads,
});

function ExpoLeads() {
  const queryClient = useQueryClient();
  const { booth_id: initialBoothId } = Route.useSearch();
  const [boothId, setBoothId] = React.useState(initialBoothId || "all");
  const [score, setScore] = React.useState("all");
  const [selected, setSelected] = React.useState<LeadRow | null>(null);
  const [deleteTarget, setDeleteTarget] = React.useState<LeadRow | null>(null);
  const [deleting, setDeleting] = React.useState(false);

  React.useEffect(() => {
    if (initialBoothId) setBoothId(initialBoothId);
  }, [initialBoothId]);

  const boothsQ = useQuery({
    queryKey: ["expo", "booths"],
    queryFn: () => apiFetch<{ items: { id: string; name: string }[] }>("/expo/booths"),
  });

  const filters = {
    ...(boothId !== "all" ? { booth_id: boothId } : {}),
    ...(score !== "all" ? { score } : {}),
  };
  const qs = new URLSearchParams(filters).toString();

  const summaryQ = useQuery({
    queryKey: ["expo", "summary", boothId],
    queryFn: () =>
      apiFetch<{
        scans: number;
        sessions_started: number;
        completed_leads: number;
        hot: number;
        warm: number;
        cold: number;
        offers_sent: number;
      }>(`/expo/results/summary${boothId !== "all" ? `?booth_id=${boothId}` : ""}`),
  });

  const leadsQ = useQuery({
    queryKey: ["expo", "leads", boothId, score],
    queryFn: () => apiFetch<{ items: LeadRow[] }>(`/expo/results/leads${qs ? `?${qs}` : ""}`),
  });

  const detailQ = useQuery({
    queryKey: ["expo", "lead", selected?.id],
    enabled: Boolean(selected?.id),
    queryFn: () => apiFetch<{ item: LeadRow }>(`/expo/results/leads/${selected!.id}`),
  });

  const detail = detailQ.data?.item || selected;
  const [cardSrc, setCardSrc] = React.useState<string | null>(null);

  React.useEffect(() => {
    let revoked: string | null = null;
    let cancelled = false;
    setCardSrc(null);
    const path = detail?.business_card_url;
    if (!path) return;
    (async () => {
      try {
        const base = getApiBaseUrl().replace(/\/+$/, "");
        const res = await fetch(`${base}${path}`, { headers: buildAuthHeaders() });
        if (!res.ok) return;
        const blob = await res.blob();
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        revoked = url;
        setCardSrc(url);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [detail?.business_card_url, detail?.id]);

  const summary = summaryQ.data;
  const leads = leadsQ.data?.items || [];

  async function handleExport() {
    try {
      await downloadAuthenticatedFile(
        `/expo/results/export.csv${boothId !== "all" ? `?booth_id=${boothId}` : ""}`,
        "expo-leads.csv",
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await apiFetch(`/expo/results/leads/${deleteTarget.id}`, { method: "DELETE" });
      toast.success("Lead deleted");
      if (selected?.id === deleteTarget.id) setSelected(null);
      setDeleteTarget(null);
      await queryClient.invalidateQueries({ queryKey: ["expo"] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not delete lead");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="VoxBulk Expo"
        title="Lead results"
        description="Exhibition leads from WhatsApp and web — filter, open a lead, export, or delete."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" className="gap-1.5" onClick={() => void handleExport()}>
              <Download className="size-4" /> Export CSV
            </Button>
            <Button asChild variant="outline" size="sm" className="gap-1.5">
              <Link to="/expo">
                <QrCode className="size-4" /> Saved booths
              </Link>
            </Button>
          </div>
        }
      />

      <div className="flex flex-wrap gap-3">
        <select
          className="h-9 rounded-lg border bg-background px-3 text-sm shadow-sm"
          value={boothId}
          onChange={(e) => setBoothId(e.target.value)}
        >
          <option value="all">All booths</option>
          {(boothsQ.data?.items || []).map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
        <select
          className="h-9 rounded-lg border bg-background px-3 text-sm shadow-sm"
          value={score}
          onChange={(e) => setScore(e.target.value)}
        >
          <option value="all">All scores</option>
          <option value="hot">Hot</option>
          <option value="warm">Warm</option>
          <option value="cold">Cold</option>
        </select>
      </div>

      {summaryQ.isLoading ? (
        <Skeleton className="h-28 rounded-2xl" />
      ) : summary ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Kpi
            title="Scans"
            value={summary.scans}
            accent="from-sky-500/15 to-sky-500/5"
            icon={<QrCode className="size-4 text-sky-600" />}
          />
          <Kpi
            title="Completed leads"
            value={summary.completed_leads}
            accent="from-emerald-500/15 to-emerald-500/5"
            icon={<User className="size-4 text-emerald-600" />}
          />
          <Kpi
            title="Hot / Warm / Cold"
            value={`${summary.hot} / ${summary.warm} / ${summary.cold}`}
            accent="from-amber-500/15 to-orange-500/5"
            icon={<Flame className="size-4 text-orange-600" />}
          />
          <Kpi
            title="Offers sent"
            value={summary.offers_sent}
            accent="from-violet-500/15 to-violet-500/5"
            icon={<Mail className="size-4 text-violet-600" />}
          />
        </div>
      ) : null}

      {leadsQ.isLoading ? (
        <Skeleton className="h-96 rounded-2xl" />
      ) : leadsQ.isError ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-destructive">
            {leadsQ.error instanceof Error ? leadsQ.error.message : "Unable to load leads."}
          </CardContent>
        </Card>
      ) : (
        <div className="overflow-hidden rounded-2xl border bg-card shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b bg-muted/40 text-[11px] uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Lead</th>
                  <th className="px-4 py-3 font-medium">Interest</th>
                  <th className="px-4 py-3 font-medium">Score</th>
                  <th className="px-4 py-3 font-medium">Booth</th>
                  <th className="px-4 py-3 font-medium">When</th>
                  <th className="px-4 py-3 font-medium text-right"> </th>
                </tr>
              </thead>
              <tbody>
                {leads.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-12 text-center text-muted-foreground">
                      No leads yet — share your Expo QR at the stand.
                    </td>
                  </tr>
                ) : (
                  leads.map((lead) => (
                    <tr
                      key={lead.id}
                      className="cursor-pointer border-t transition hover:bg-muted/30"
                      onClick={() => setSelected(lead)}
                    >
                      <td className="px-4 py-3">
                        <p className="font-medium text-foreground">{lead.name || "Unknown"}</p>
                        <p className="text-xs text-muted-foreground">
                          {[lead.company, lead.visitor_phone].filter(Boolean).join(" · ") || "—"}
                        </p>
                      </td>
                      <td className="max-w-[220px] truncate px-4 py-3 text-muted-foreground" title={lead.interest || ""}>
                        {lead.interest || "—"}
                      </td>
                      <td className="px-4 py-3">
                        <ScoreBadge score={lead.lead_score} />
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{lead.booth_code || lead.booth_name || "—"}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">{formatTs(lead.created_at)}</td>
                      <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-8 text-muted-foreground hover:text-destructive"
                          onClick={() => setDeleteTarget(lead)}
                          aria-label="Delete lead"
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <Sheet open={selected != null} onOpenChange={(open) => !open && setSelected(null)}>
        <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
          {detail ? (
            <>
              <SheetHeader className="space-y-3 border-b pb-4 text-left">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <SheetTitle className="text-xl">{detail.name || "Lead"}</SheetTitle>
                    <SheetDescription className="mt-1 flex flex-wrap items-center gap-2">
                      <ScoreBadge score={detail.lead_score} />
                      <span>{detail.booth_name || detail.booth_code || "Booth"}</span>
                    </SheetDescription>
                  </div>
                </div>
              </SheetHeader>
              <div className="mt-6 space-y-5">
                {cardSrc ? (
                  <div>
                    <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                      Business card
                    </p>
                    <img
                      src={cardSrc}
                      alt="Business card"
                      className="mt-2 w-full rounded-lg border object-contain bg-muted/30"
                    />
                  </div>
                ) : detail.business_card_url && detailQ.isLoading ? (
                  <Skeleton className="h-40 w-full rounded-lg" />
                ) : null}
                <DetailRow icon={<Building2 className="size-4" />} label="Company" value={detail.company} />
                <DetailRow icon={<Phone className="size-4" />} label="Phone" value={detail.visitor_phone} />
                <DetailRow icon={<Mail className="size-4" />} label="Email" value={detail.visitor_email} />
                <DetailRow label="Interest" value={detail.interest} />
                <DetailRow label="Timeline" value={detail.buying_timeline} />
                <DetailRow label="Language" value={detail.detected_language || detail.country_hint} />
                <DetailRow label="Offer sent" value={detail.offer_sent_at ? formatTs(detail.offer_sent_at) : "No"} />
                <DetailRow label="Follow-up" value={detail.follow_up_status || "none"} />
                <DetailRow label="Captured" value={formatTs(detail.created_at)} />
                {detail.assets_sent && detail.assets_sent.length > 0 ? (
                  <div>
                    <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Assets sent</p>
                    <ul className="mt-1 space-y-1 text-sm">
                      {detail.assets_sent.map((a) => (
                        <li key={a} className="rounded-md bg-muted/50 px-2 py-1">
                          {a}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {(detail.answers || []).length > 0 ? (
                  <div className="space-y-3">
                    <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                      Questions &amp; answers
                    </p>
                    {(detail.answers || []).map((a, i) => {
                      const original = (a.original_text || a.answer_text || "").trim();
                      const english = (a.answer_text_en || a.answer_text || "").trim();
                      const showBoth =
                        original &&
                        english &&
                        original.toLowerCase() !== english.toLowerCase();
                      return (
                        <div key={`${a.question_key}-${i}`} className="rounded-lg border bg-muted/20 p-3 text-sm">
                          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                            {a.question_label || a.question_key || "Question"}
                            {a.answer_source === "voice" ? " · Voice" : null}
                          </p>
                          {a.question_prompt ? (
                            <p className="mt-1 text-[13px] font-medium text-foreground">{a.question_prompt}</p>
                          ) : null}
                          {showBoth ? (
                            <div className="mt-2 space-y-2">
                              <div>
                                <p className="text-[10px] text-muted-foreground">Original answer</p>
                                <p className="whitespace-pre-wrap">{original}</p>
                              </div>
                              <div>
                                <p className="text-[10px] text-muted-foreground">English translation</p>
                                <p className="whitespace-pre-wrap">{english}</p>
                              </div>
                            </div>
                          ) : (
                            <p className="mt-1 whitespace-pre-wrap">{english || original || "—"}</p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : detailQ.isLoading ? (
                  <Skeleton className="h-24 w-full rounded-lg" />
                ) : null}
                <Button
                  variant="destructive"
                  className="w-full gap-1.5"
                  onClick={() => {
                    setDeleteTarget(detail);
                  }}
                >
                  <Trash2 className="size-4" /> Delete lead
                </Button>
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>

      <AlertDialog open={deleteTarget != null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this lead?</AlertDialogTitle>
            <AlertDialogDescription>
              Removes {deleteTarget?.name || "this lead"} and their Expo session answers. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={deleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={(e) => {
                e.preventDefault();
                void confirmDelete();
              }}
            >
              {deleting ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function Kpi({
  title,
  value,
  accent,
  icon,
}: {
  title: string;
  value: number | string;
  accent: string;
  icon: React.ReactNode;
}) {
  return (
    <Card className={cn("overflow-hidden border-0 shadow-sm ring-1 ring-border/60")}>
      <CardContent className={cn("bg-gradient-to-br p-4", accent)}>
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{title}</p>
          <div className="grid size-8 place-items-center rounded-lg bg-background/80 shadow-sm">{icon}</div>
        </div>
        <p className="mt-2 text-2xl font-semibold tracking-tight tabular-nums">
          {typeof value === "number" ? value.toLocaleString() : value}
        </p>
      </CardContent>
    </Card>
  );
}

function DetailRow({
  label,
  value,
  icon,
}: {
  label: string;
  value?: string | null;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex gap-3">
      {icon ? <div className="mt-0.5 text-muted-foreground">{icon}</div> : null}
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className="mt-0.5 text-sm text-foreground">{value || "—"}</p>
      </div>
    </div>
  );
}

function ScoreBadge({ score }: { score?: string | null }) {
  const s = String(score || "").toLowerCase();
  if (!s) return <span className="text-muted-foreground">—</span>;
  if (s === "hot") {
    return (
      <Badge className="gap-1 bg-orange-600 hover:bg-orange-600">
        <Flame className="size-3" /> HOT
      </Badge>
    );
  }
  if (s === "warm") {
    return (
      <Badge variant="secondary" className="gap-1 text-amber-800">
        <Thermometer className="size-3" /> WARM
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1">
      <Snowflake className="size-3" /> COLD
    </Badge>
  );
}

function formatTs(value?: string | null) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
}
