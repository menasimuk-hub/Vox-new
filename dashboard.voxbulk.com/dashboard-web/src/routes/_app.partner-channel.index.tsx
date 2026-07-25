import * as React from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Building2, Copy, DollarSign, Percent, Send, Tag, Wallet } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import { requirePartnerChannel } from "@/lib/guards/settings-route";

export const Route = createFileRoute("/_app/partner-channel/")({
  head: () => ({ meta: [{ title: "Partner overview — VoxBulk" }] }),
  beforeLoad: () => requirePartnerChannel(),
  component: PartnerChannelOverview,
});

type Stats = {
  commission_pct?: number;
  wallet: {
    active_companies: number;
    codes_used: number;
    revenue_minor: number;
    commission_minor: number;
    commission_paid_minor: number;
    commission_pending_minor: number;
  };
};

type Rep = {
  promo_code?: string;
  company_name?: string | null;
  name?: string;
  commission_pct?: number;
};

function money(minor?: number) {
  const n = Number(minor || 0) / 100;
  return `£${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function PartnerChannelOverview() {
  const [stats, setStats] = React.useState<Stats | null>(null);
  const [rep, setRep] = React.useState<Rep | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [copied, setCopied] = React.useState(false);

  React.useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const [dash, me] = await Promise.all([
          apiFetch<{ stats: Stats }>("/sales/dashboard"),
          apiFetch<{ rep: Rep }>("/sales/me"),
        ]);
        setStats(dash.stats);
        setRep(me.rep);
      } catch {
        setStats(null);
        setRep(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const pct = Number(rep?.commission_pct ?? stats?.commission_pct ?? 15);
  const promo = rep?.promo_code || "";

  const copyPromo = async () => {
    if (!promo) return;
    try {
      await navigator.clipboard.writeText(promo);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Partner Channel Sales"
        title="Overview"
        description={`${rep?.company_name || rep?.name || "Your partner account"} — track customers who sign up with your promo code.`}
        actions={
          <>
            <Button asChild variant="outline" className="gap-1.5">
              <Link to="/partner-channel/wallet">
                <Wallet className="size-4" />
                Wallet
              </Link>
            </Button>
            <Button asChild className="gap-1.5">
              <Link to="/partner-channel/send-offer">
                <Send className="size-4" />
                Send offer
              </Link>
            </Button>
          </>
        }
      />

      <Card className="border-primary/15 bg-gradient-to-br from-primary/[0.04] via-card to-card">
        <CardContent className="flex flex-wrap items-center justify-between gap-4 p-6">
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">Your promo code</p>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <span className="font-mono text-2xl font-semibold tracking-wide">{loading ? "…" : promo || "—"}</span>
              {promo ? (
                <Button type="button" variant="outline" size="sm" className="h-8" onClick={() => void copyPromo()}>
                  <Copy className="mr-1.5 h-3.5 w-3.5" />
                  {copied ? "Copied" : "Copy"}
                </Button>
              ) : null}
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              Earn <span className="font-medium text-foreground">{pct}%</span> commission on every paid subscription
              invoice attributed to this code.
            </p>
          </div>
          <Tag className="hidden size-10 text-primary/40 sm:block" />
        </CardContent>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi
          icon={<Building2 className="size-4" />}
          label="Active companies"
          value={loading ? "…" : String(stats?.wallet.active_companies ?? 0)}
        />
        <Kpi
          icon={<Tag className="size-4" />}
          label="Codes used"
          value={loading ? "…" : String(stats?.wallet.codes_used ?? 0)}
        />
        <Kpi
          icon={<DollarSign className="size-4" />}
          label="Customer revenue"
          value={loading ? "…" : money(stats?.wallet.revenue_minor)}
        />
        <Kpi
          icon={<Percent className="size-4" />}
          label="Total commission"
          value={loading ? "…" : money(stats?.wallet.commission_minor)}
          hint={`${money(stats?.wallet.commission_pending_minor)} pending`}
        />
      </div>
    </div>
  );
}

function Kpi({
  icon,
  label,
  value,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          {icon}
          {label}
        </div>
        <div className="mt-2 text-2xl font-semibold tracking-tight tabular-nums">{value}</div>
        {hint ? <div className="mt-1 text-xs text-muted-foreground">{hint}</div> : null}
      </CardContent>
    </Card>
  );
}
