import { createFileRoute, Link } from "@tanstack/react-router";
import { Send, ShieldCheck, CheckCircle2 } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useFeedbackPromoDashboard } from "@/lib/queries";

export const Route = createFileRoute("/_app/feedback/campaigns/")({
  head: () => ({ meta: [{ title: "Campaign dashboard — Customer feedback" }] }),
  component: FeedbackCampaignDashboard,
});

function FeedbackCampaignDashboard() {
  const dashQ = useFeedbackPromoDashboard();
  const totals = dashQ.data?.totals || { sent: 0, coming: 0, not_interested: 0 };
  const campaigns = dashQ.data?.campaigns || [];

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Add-on · Customer feedback"
        title="Campaign dashboard"
        description="Promo WhatsApp broadcasts — billed per send. Pay invoice before launch."
        actions={
          <Button asChild className="gap-1.5">
            <Link to="/feedback/campaigns/send"><Send className="size-4" /> Send campaign</Link>
          </Button>
        }
      />

      <div className="flex items-center gap-2 rounded-lg border border-success/30 bg-success/5 p-3 text-sm text-success">
        <ShieldCheck className="size-4" />
        <span><b>Admin-approved templates.</b> Send to your opt-in list and uploaded numbers. Pay invoice before launch.</span>
      </div>

      {dashQ.isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : (
        <div className="grid gap-3 md:grid-cols-4">
          <Kpi label="Total sent" value={totals.sent.toLocaleString()} />
          <Kpi label="Interested" value={totals.coming.toLocaleString()} tone="success" />
          <Kpi label="Not interested" value={totals.not_interested.toLocaleString()} tone="muted" />
          <Kpi label="Response rate" value={`${dashQ.data?.response_rate ?? 0}%`} sub={`${dashQ.data?.positive_rate ?? 0}% positive`} />
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          <div className="border-b border-border p-4">
            <h2 className="text-base font-semibold">Recent campaigns</h2>
            <p className="text-xs text-muted-foreground">Pay invoice → launch. Replies tracked when customers use quick-reply buttons.</p>
          </div>
          <div className="divide-y divide-border">
            {campaigns.length ? campaigns.map((c) => {
              const sent = Number(c.sent_count || 0);
              const yes = Number(c.yes_count || 0);
              const rate = sent ? ((yes / sent) * 100).toFixed(1) : "0.0";
              return (
                <div key={String(c.id)} className="grid items-center gap-3 p-4 md:grid-cols-[1.5fr_1fr_auto]">
                  <div>
                    <p className="font-medium">{String(c.template_name || "Campaign")}</p>
                    <p className="text-xs text-muted-foreground">{String(c.status)} · {Number(c.recipient_count || 0).toLocaleString()} recipients</p>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Sent {sent.toLocaleString()} · £{(Number(c.cost_minor || 0) / 100).toFixed(2)}
                  </div>
                  <Badge variant="outline" className="border-success/40 bg-success/10 text-success justify-self-end">
                    <CheckCircle2 className="mr-1 size-3" /> {rate}% interested
                  </Badge>
                </div>
              );
            }) : (
              <div className="p-6 text-sm text-muted-foreground">No campaigns yet. Send your first promo campaign.</div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function Kpi({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "success" | "muted" }) {
  const color = tone === "success" ? "text-success" : tone === "muted" ? "text-muted-foreground" : "text-primary";
  return (
    <Card><CardContent className="p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${color}`}>{value}</p>
      {sub ? <p className="text-[11px] text-muted-foreground">{sub}</p> : null}
    </CardContent></Card>
  );
}
