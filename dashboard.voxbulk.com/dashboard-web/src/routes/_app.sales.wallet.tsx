import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { Wallet, DollarSign, Building2, Tag } from "lucide-react";

import { apiFetch } from "@/lib/api";
import { requireSalesRep } from "@/lib/guards/settings-route";
import "@/styles/sales-portal.css";

export const Route = createFileRoute("/_app/sales/wallet")({
  head: () => ({ meta: [{ title: "Wallet — Sales" }] }),
  beforeLoad: () => requireSalesRep(),
  component: SalesWallet,
});

type Stats = {
  wallet: {
    active_companies: number;
    codes_used: number;
    revenue_minor: number;
    commission_minor: number;
    commission_paid_minor: number;
    commission_pending_minor: number;
  };
};

function money(minor?: number) {
  const n = Number(minor || 0) / 100;
  return `£${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function SalesWallet() {
  const [stats, setStats] = React.useState<Stats | null>(null);

  React.useEffect(() => {
    void (async () => {
      try {
        const res = await apiFetch<{ stats: Stats }>("/sales/dashboard");
        setStats(res.stats);
      } catch {
        /* surfaced as empty state */
      }
    })();
  }, []);

  return (
    <div className="salesPortal salesPortal--embedded">
      <div className="sp-app">
        <div className="sp-simple">
          <h2>
            <Wallet size={20} /> Wallet
          </h2>
          <p>Revenue from your customers and your commission.</p>
          <div className="sp-kpi-grid">
            <div className="sp-kpi">
              <div className="label">
                <DollarSign size={14} /> Customer revenue
              </div>
              <div className="value">{money(stats?.wallet.revenue_minor)}</div>
            </div>
            <div className="sp-kpi">
              <div className="label">
                <Building2 size={14} /> Active companies
              </div>
              <div className="value">{stats?.wallet.active_companies ?? 0}</div>
            </div>
            <div className="sp-kpi">
              <div className="label">
                <Tag size={14} /> Codes used
              </div>
              <div className="value">{stats?.wallet.codes_used ?? 0}</div>
            </div>
            <div className="sp-kpi">
              <div className="label">
                <Wallet size={14} /> Commission
              </div>
              <div className="value">{money(stats?.wallet.commission_minor)}</div>
              <div className="sub">{money(stats?.wallet.commission_pending_minor)} pending</div>
            </div>
          </div>
          <h4 style={{ margin: "20px 0 12px", fontWeight: 600 }}>Commission breakdown</h4>
          <div className="sp-company">
            <span className="name">Paid out</span>
            <span>{money(stats?.wallet.commission_paid_minor)}</span>
          </div>
          <div className="sp-company">
            <span className="name">Pending</span>
            <span>{money(stats?.wallet.commission_pending_minor)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
