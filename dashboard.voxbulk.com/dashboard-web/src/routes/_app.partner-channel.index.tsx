import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { Building2, DollarSign, Percent, Tag, Wallet } from "lucide-react";

import { apiFetch } from "@/lib/api";
import { requirePartnerChannel } from "@/lib/guards/settings-route";
import "@/styles/sales-portal.css";

export const Route = createFileRoute("/_app/partner-channel/")({
  head: () => ({ meta: [{ title: "Partner Channel Sales — VoxBulk" }] }),
  beforeLoad: () => requirePartnerChannel(),
  component: PartnerChannelHome,
});

type CommissionRow = {
  id: string;
  org_id?: string | null;
  org_name?: string | null;
  amount_minor: number;
  currency?: string;
  status: string;
  note?: string | null;
  created_at?: string | null;
};

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
  commissions?: CommissionRow[];
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

function PartnerChannelHome() {
  const [stats, setStats] = React.useState<Stats | null>(null);
  const [rep, setRep] = React.useState<Rep | null>(null);
  const [loading, setLoading] = React.useState(true);

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

  const commissions = stats?.commissions || [];
  const pct = Number(rep?.commission_pct ?? stats?.commission_pct ?? 15);

  return (
    <div className="salesPortal salesPortal--embedded">
      <div className="sp-app">
        <div className="sp-simple">
          <h2>
            <Wallet size={20} /> Partner Channel Sales
          </h2>
          <p>
            {rep?.company_name || rep?.name || "Your partner account"} — track attributed revenue and commission
            when customers pay with your promo code.
          </p>

          <div className="sp-kpi-grid" style={{ marginBottom: 8 }}>
            <div className="sp-kpi">
              <div className="label">
                <Tag size={14} /> Promo code
              </div>
              <div className="value" style={{ fontSize: "1.15rem", fontFamily: "ui-monospace, monospace" }}>
                {rep?.promo_code || "—"}
              </div>
              <div className="sub">{pct}% on every paid subscription</div>
            </div>
            <div className="sp-kpi">
              <div className="label">
                <Building2 size={14} /> Active companies
              </div>
              <div className="value">{loading ? "…" : (stats?.wallet.active_companies ?? 0)}</div>
            </div>
            <div className="sp-kpi">
              <div className="label">
                <Tag size={14} /> Codes used
              </div>
              <div className="value">{loading ? "…" : (stats?.wallet.codes_used ?? 0)}</div>
            </div>
            <div className="sp-kpi">
              <div className="label">
                <DollarSign size={14} /> Customer revenue
              </div>
              <div className="value">{loading ? "…" : money(stats?.wallet.revenue_minor)}</div>
            </div>
          </div>

          <div className="sp-kpi-grid">
            <div className="sp-kpi">
              <div className="label">
                <Percent size={14} /> Total commission
              </div>
              <div className="value">{loading ? "…" : money(stats?.wallet.commission_minor)}</div>
            </div>
            <div className="sp-kpi">
              <div className="label">
                <Wallet size={14} /> Pending
              </div>
              <div className="value">{loading ? "…" : money(stats?.wallet.commission_pending_minor)}</div>
            </div>
            <div className="sp-kpi">
              <div className="label">
                <Wallet size={14} /> Paid out
              </div>
              <div className="value">{loading ? "…" : money(stats?.wallet.commission_paid_minor)}</div>
            </div>
          </div>

          <h4 style={{ margin: "24px 0 12px", fontWeight: 600 }}>Commission ledger</h4>
          {loading ? (
            <p style={{ color: "#7a6b58" }}>Loading…</p>
          ) : commissions.length === 0 ? (
            <p style={{ color: "#7a6b58" }}>
              No commission yet. When a customer signs up with your promo code and pays a subscription invoice, it
              appears here.
            </p>
          ) : (
            <div className="sp-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Company</th>
                    <th>Amount</th>
                    <th>Status</th>
                    <th>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {commissions.map((c) => (
                    <tr key={c.id}>
                      <td>{c.org_name || c.org_id || "—"}</td>
                      <td>{money(c.amount_minor)}</td>
                      <td>
                        <span className={`sp-stage ${c.status === "paid" ? "stage-won" : "stage-interested"}`}>
                          {c.status}
                        </span>
                      </td>
                      <td>{c.created_at ? String(c.created_at).slice(0, 10) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
