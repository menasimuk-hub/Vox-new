import * as React from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Building2, Copy, DollarSign, Percent, Send, Tag, Wallet } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
    <div className="mx-auto max-w-5xl space-y-6 p-4 md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {rep?.company_name || rep?.name || "Your partner account"} — track customers who sign up with your promo
            code.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <Link to="/partner-channel/wallet">
              <Wallet className="mr-1.5 h-4 w-4" />
              Wallet
            </Link>
          </Button>
          <Button asChild size="sm">
            <Link to="/partner-channel/send-offer">
              <Send className="mr-1.5 h-4 w-4" />
              Send offer
            </Link>
          </Button>
        </div>
      </div>

      <Card className="overflow-hidden border-primary/15 bg-gradient-to-br from-primary/[0.04] via-background to-background">
        <CardHeader className="pb-3">
          <CardDescription>Your promo code</CardDescription>
          <CardTitle className="flex flex-wrap items-center gap-3 font-mono text-2xl tracking-wide">
            <Tag className="h-5 w-5 text-primary" />
            {loading ? "…" : promo || "—"}
            {promo ? (
              <Button type="button" variant="outline" size="sm" className="h-8 font-sans" onClick={() => void copyPromo()}>
                <Copy className="mr-1.5 h-3.5 w-3.5" />
                {copied ? "Copied" : "Copy"}
              </Button>
            ) : null}
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Earn <span className="font-medium text-foreground">{pct}%</span> commission on every paid subscription
            invoice attributed to this code.
          </p>
        </CardHeader>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi
          icon={<Building2 className="h-4 w-4" />}
          label="Active companies"
          value={loading ? "…" : String(stats?.wallet.active_companies ?? 0)}
        />
        <Kpi
          icon={<Tag className="h-4 w-4" />}
          label="Codes used"
          value={loading ? "…" : String(stats?.wallet.codes_used ?? 0)}
        />
        <Kpi
          icon={<DollarSign className="h-4 w-4" />}
          label="Customer revenue"
          value={loading ? "…" : money(stats?.wallet.revenue_minor)}
        />
        <Kpi
          icon={<Percent className="h-4 w-4" />}
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
      <CardContent className="p-4">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          {icon}
          {label}
        </div>
        <div className="mt-2 text-2xl font-semibold tracking-tight">{value}</div>
        {hint ? <div className="mt-1 text-xs text-muted-foreground">{hint}</div> : null}
      </CardContent>
    </Card>
  );
}
