import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { Handshake, Trophy, DollarSign, Star, TrendingUp } from "lucide-react";

import { apiFetch } from "@/lib/api";
import { requireSalesRep } from "@/lib/guards/settings-route";
import "@/styles/sales-portal.css";

export const Route = createFileRoute("/_app/sales/deals")({
  head: () => ({ meta: [{ title: "Won deals — Sales" }] }),
  beforeLoad: () => requireSalesRep(),
  component: SalesDeals,
});

type Stats = {
  won_deals: { count: number; total_value_minor: number; companies: { name: string; org_id?: string | null }[] };
  wallet: { active_companies: number };
  visited_count: number;
};

function money(minor?: number) {
  const n = Number(minor || 0) / 100;
  return `£${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function SalesDeals() {
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
            <Handshake size={20} /> Won deals
          </h2>
          <p>Closed and won deals with company &amp; package details.</p>
          <div className="sp-kpi-grid">
            <div className="sp-kpi">
              <div className="label">
                <Trophy size={14} /> Deals won
              </div>
              <div className="value">{stats?.won_deals.count ?? 0}</div>
            </div>
            <div className="sp-kpi">
              <div className="label">
                <DollarSign size={14} /> Total value
              </div>
              <div className="value">{money(stats?.won_deals.total_value_minor)}</div>
            </div>
            <div className="sp-kpi">
              <div className="label">
                <Star size={14} /> Active companies
              </div>
              <div className="value">{stats?.wallet.active_companies ?? 0}</div>
            </div>
            <div className="sp-kpi">
              <div className="label">
                <TrendingUp size={14} /> Visited
              </div>
              <div className="value">{stats?.visited_count ?? 0}</div>
            </div>
          </div>
          <h4 style={{ margin: "20px 0 12px", fontWeight: 600 }}>Company &amp; package details</h4>
          {(stats?.won_deals.companies || []).length === 0 ? (
            <p>No won deals yet. Deals appear here once a customer signs up with your promo code.</p>
          ) : (
            (stats?.won_deals.companies || []).map((c, i) => (
              <div className="sp-company" key={i}>
                <span className="name">{c.name}</span>
                <span className="pkg">{c.org_id ? "Converted" : "Pending"}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
