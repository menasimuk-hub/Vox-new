import { createFileRoute, Link } from "@tanstack/react-router";
import { Download, QrCode } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch, downloadAuthenticatedFile } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";

type LeadRow = {
  id: string;
  created_at?: string | null;
  detected_language?: string | null;
  country_hint?: string | null;
  visitor_phone?: string | null;
  name?: string | null;
  company?: string | null;
  interest?: string | null;
  buying_timeline?: string | null;
  lead_score?: string | null;
  booth_name?: string | null;
  booth_code?: string | null;
  offer_sent_at?: string | null;
  follow_up_status?: string | null;
};

export const Route = createFileRoute("/_app/expo/leads")({
  head: () => ({ meta: [{ title: "Expo leads — VoxBulk" }] }),
  validateSearch: (search: Record<string, unknown>) => ({
    booth_id: typeof search.booth_id === "string" ? search.booth_id : undefined,
  }),
  component: ExpoLeads,
});

function ExpoLeads() {
  const { booth_id: initialBoothId } = Route.useSearch();
  const [boothId, setBoothId] = React.useState(initialBoothId || "all");
  const [score, setScore] = React.useState("all");

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

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="VoxBulk Expo"
        title="Lead results"
        description="Filter and export exhibition leads captured via WhatsApp or web."
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
          className="h-9 rounded-md border bg-background px-3 text-sm"
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
          className="h-9 rounded-md border bg-background px-3 text-sm"
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
        <Skeleton className="h-24 rounded-xl" />
      ) : summary ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Kpi title="Scans" value={summary.scans} />
          <Kpi title="Completed leads" value={summary.completed_leads} />
          <Kpi title="Hot / Warm / Cold" value={`${summary.hot} / ${summary.warm} / ${summary.cold}`} />
          <Kpi title="Offers sent" value={summary.offers_sent} />
        </div>
      ) : null}

      {leadsQ.isLoading ? (
        <Skeleton className="h-96 rounded-xl" />
      ) : leadsQ.isError ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-destructive">
            {leadsQ.error instanceof Error ? leadsQ.error.message : "Unable to load leads."}
          </CardContent>
        </Card>
      ) : (
        <div className="overflow-x-auto rounded-xl border">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Timestamp</th>
                <th className="px-3 py-2">Language</th>
                <th className="px-3 py-2">Phone</th>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Company</th>
                <th className="px-3 py-2">Interest</th>
                <th className="px-3 py-2">Timeline</th>
                <th className="px-3 py-2">Score</th>
                <th className="px-3 py-2">Booth</th>
                <th className="px-3 py-2">Offer</th>
                <th className="px-3 py-2">Follow-up</th>
              </tr>
            </thead>
            <tbody>
              {leads.length === 0 ? (
                <tr>
                  <td colSpan={11} className="px-3 py-8 text-center text-muted-foreground">
                    No leads yet — share your Expo QR at the stand.
                  </td>
                </tr>
              ) : (
                leads.map((lead) => (
                  <tr key={lead.id} className="border-t">
                    <td className="px-3 py-2 whitespace-nowrap">{formatTs(lead.created_at)}</td>
                    <td className="px-3 py-2">{lead.detected_language || lead.country_hint || "—"}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{lead.visitor_phone || "—"}</td>
                    <td className="px-3 py-2">{lead.name || "—"}</td>
                    <td className="px-3 py-2">{lead.company || "—"}</td>
                    <td className="px-3 py-2 max-w-[220px] truncate" title={lead.interest || ""}>
                      {lead.interest || "—"}
                    </td>
                    <td className="px-3 py-2">{lead.buying_timeline || "—"}</td>
                    <td className="px-3 py-2">
                      <ScoreBadge score={lead.lead_score} />
                    </td>
                    <td className="px-3 py-2">{lead.booth_code || lead.booth_name || "—"}</td>
                    <td className="px-3 py-2">{lead.offer_sent_at ? "Yes" : "No"}</td>
                    <td className="px-3 py-2">{lead.follow_up_status || "none"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Kpi({ title, value }: { title: string; value: number | string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{title}</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">
          {typeof value === "number" ? value.toLocaleString() : value}
        </p>
      </CardContent>
    </Card>
  );
}

function ScoreBadge({ score }: { score?: string | null }) {
  const s = String(score || "").toLowerCase();
  if (!s) return <span className="text-muted-foreground">—</span>;
  const variant = s === "hot" ? "default" : s === "warm" ? "secondary" : "outline";
  return <Badge variant={variant}>{s.toUpperCase()}</Badge>;
}

function formatTs(value?: string | null) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString("en-GB", {
      day: "2-digit",
      month: "2-digit",
      year: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
}
