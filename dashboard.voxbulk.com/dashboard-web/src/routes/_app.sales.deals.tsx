import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import {
  ArrowUpRight,
  CalendarDays,
  ChevronDown,
  ChevronUp,
  CircleDollarSign,
  DollarSign,
  Handshake,
  Minus,
  Search,
  Trophy,
  Wallet,
} from "lucide-react";

import { apiFetch } from "@/lib/api";
import { requireSalesRep } from "@/lib/guards/settings-route";
import "@/styles/sales-portal.css";

export const Route = createFileRoute("/_app/sales/deals")({
  head: () => ({ meta: [{ title: "Won deals — Sales" }] }),
  beforeLoad: () => requireSalesRep(),
  component: SalesDeals,
});

type CommissionLine = {
  id: string;
  amount_minor?: number;
  amount_display?: string | null;
  currency?: string | null;
  kind?: string | null;
  status?: string | null;
  note?: string | null;
  created_at?: string | null;
  invoice_id?: string | null;
};

type ExpectedCommission = {
  label?: string | null;
  kind?: string | null;
  status?: string | null;
  expected_at?: string | null;
  expected_date?: string | null;
  amount_minor?: number | null;
  amount_display?: string | null;
  currency?: string | null;
  note?: string | null;
};

type Company = {
  id?: string;
  name: string;
  contact_person?: string | null;
  email?: string | null;
  mobile?: string | null;
  org_id?: string | null;
  status?: string;
  plan_name?: string | null;
  plan_code?: string | null;
  service_kind?: string | null;
  billing_interval?: string | null;
  amount_minor?: number | null;
  currency?: string | null;
  amount_display?: string | null;
  subscription_status?: string | null;
  current_period_end?: string | null;
  created_at?: string | null;
  won_at?: string | null;
  offer_sent_at?: string | null;
  commission_total_minor?: number | null;
  commission_pending_minor?: number | null;
  commission_paid_minor?: number | null;
  commission_requested_minor?: number | null;
  commission_total_display?: string | null;
  commission_pending_display?: string | null;
  commission_paid_display?: string | null;
  commissions?: CommissionLine[];
  expected_commissions?: ExpectedCommission[];
  next_expected_commission?: ExpectedCommission | null;
};

type Stats = {
  won_deals: { count: number; total_value_minor: number; companies: Company[] };
  wallet: {
    active_companies: number;
    commission_minor?: number;
    commission_pending_minor?: number;
    commission_available_minor?: number;
    commission_paid_minor?: number;
    commission_requested_minor?: number;
    revenue_minor?: number;
    codes_used?: number;
  };
  visited_count: number;
  currency?: string;
};

function KpiDelta({ value, suffix = "" }: { value: number; suffix?: string }) {
  if (!Number.isFinite(value) || value === 0) {
    return (
      <span className="delta flat">
        <Minus size={12} /> 0{suffix}
      </span>
    );
  }
  const up = value > 0;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={`delta ${up ? "up" : "down"}`}>
      <Icon size={12} />
      {up ? "+" : ""}
      {value}
      {suffix}
    </span>
  );
}

const SYMBOLS: Record<string, string> = { GBP: "£", EUR: "€", USD: "$", CAD: "CA$", AUD: "A$" };

const KIND_LABELS: Record<string, string> = {
  one_time: "One-time bonus",
  month1: "Month 1",
  month2: "Month 2",
  monthly: "Monthly",
  monthly_2nd: "Month commission",
  yearly_1mo: "Yearly (1 mo)",
  percent_invoice: "Percent",
  fixed_invoice: "Fixed",
  partner_invoice: "Partner",
};

function money(minor?: number | null, currency = "GBP") {
  const n = Number(minor || 0) / 100;
  const sym = SYMBOLS[currency] || `${currency} `;
  return `${sym}${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function fmtDay(iso?: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 10);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function dayKey(iso?: string | null) {
  if (!iso) return "";
  return String(iso).slice(0, 10);
}

function SalesDeals() {
  const [stats, setStats] = React.useState<Stats | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [query, setQuery] = React.useState("");
  const [fromDate, setFromDate] = React.useState("");
  const [toDate, setToDate] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState<"all" | "with_commission" | "pending_commission">("all");
  const [expanded, setExpanded] = React.useState<Record<string, boolean>>({});
  const currency = stats?.currency || "GBP";

  React.useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const res = await apiFetch<{ stats: Stats }>("/sales/dashboard");
        setStats(res.stats);
      } catch {
        setStats(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const companies = stats?.won_deals.companies || [];

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    return companies.filter((c) => {
      if (q) {
        const hay = [
          c.name,
          c.contact_person,
          c.email,
          c.plan_name,
          c.plan_code,
          c.status,
          c.org_id,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!hay.includes(q)) return false;
      }
      const when = dayKey(c.won_at || c.created_at || c.offer_sent_at);
      if (fromDate && when && when < fromDate) return false;
      if (toDate && when && when > toDate) return false;
      if (fromDate && !when) return false;
      if (toDate && !when) return false;
      const pending = Number(c.commission_pending_minor || 0);
      const total = Number(c.commission_total_minor || 0);
      if (statusFilter === "with_commission" && total <= 0) return false;
      if (statusFilter === "pending_commission" && pending <= 0) return false;
      return true;
    });
  }, [companies, query, fromDate, toDate, statusFilter]);

  const filteredCommission = filtered.reduce((s, c) => s + Number(c.commission_total_minor || 0), 0);
  const filteredPending = filtered.reduce((s, c) => s + Number(c.commission_pending_minor || 0), 0);
  const filteredExpected = filtered.reduce((s, c) => {
    const lines = c.expected_commissions || [];
    if (lines.length) return s + lines.reduce((a, l) => a + Number(l.amount_minor || 0), 0);
    return s + Number(c.next_expected_commission?.amount_minor || 0);
  }, 0);
  const visited = Number(stats?.visited_count || 0);
  const won = Number(stats?.won_deals.count || 0);
  const conversionPct = visited > 0 ? Math.round((won / visited) * 1000) / 10 : 0;
  const availableMinor = Number(stats?.wallet.commission_available_minor || 0);
  const earnedMinor = Number(stats?.wallet.commission_minor || 0);
  const paidMinor = Number(stats?.wallet.commission_paid_minor || 0);
  const requestedMinor = Number(stats?.wallet.commission_requested_minor || 0);

  return (
    <div className="salesPortal salesPortal--embedded">
      <div className="sp-app">
        <div className="sp-simple">
          <h2>
            <Handshake size={20} /> Won deals
          </h2>
          <p>Closed customers with package, commission dates, and amounts — search and filter to stay organised.</p>

          <div className="sp-kpi-grid sp-kpi-grid--4">
            <div className="sp-kpi sp-kpi--compact">
              <div className="label">
                <span className="label-left">
                  <Trophy size={13} /> Deals won
                </span>
                <KpiDelta value={won} />
              </div>
              <div className="value">{loading ? "…" : won}</div>
              <div className="sub">{visited} visited · {conversionPct}% conv.</div>
            </div>
            <div className="sp-kpi sp-kpi--compact">
              <div className="label">
                <span className="label-left">
                  <DollarSign size={13} /> Revenue
                </span>
                <span className={`delta ${Number(stats?.won_deals.total_value_minor || 0) > 0 ? "up" : "flat"}`}>
                  {Number(stats?.won_deals.total_value_minor || 0) > 0 ? <ArrowUpRight size={12} /> : <Minus size={12} />}
                  closed
                </span>
              </div>
              <div className="value">{loading ? "…" : money(stats?.won_deals.total_value_minor, currency)}</div>
              <div className="sub">{stats?.wallet.active_companies ?? 0} active companies</div>
            </div>
            <div className="sp-kpi sp-kpi--compact">
              <div className="label">
                <span className="label-left">
                  <CircleDollarSign size={13} /> Commission
                </span>
                <span className={`delta ${earnedMinor > 0 ? "up" : "flat"}`}>
                  {earnedMinor > 0 ? <ArrowUpRight size={12} /> : <Minus size={12} />}
                  book
                </span>
              </div>
              <div className="value">{loading ? "…" : money(earnedMinor, currency)}</div>
              <div className="sub">
                Expected {money(filteredExpected, currency)}
                {filteredPending > 0 || requestedMinor > 0
                  ? ` · pending ${money(Math.max(filteredPending, requestedMinor), currency)}`
                  : ""}
              </div>
            </div>
            <div className="sp-kpi sp-kpi--compact">
              <div className="label">
                <span className="label-left">
                  <Wallet size={13} /> Available
                </span>
                <span className={`delta ${availableMinor > 0 ? "up" : "flat"}`}>
                  {availableMinor > 0 ? <ArrowUpRight size={12} /> : <Minus size={12} />}
                  ready
                </span>
              </div>
              <div className="value">{loading ? "…" : money(availableMinor, currency)}</div>
              <div className="sub">Paid out {money(paidMinor, currency)}</div>
            </div>
          </div>

          <div
            style={{
              display: "grid",
              gap: 10,
              marginTop: 18,
              padding: 14,
              borderRadius: 12,
              border: "1px solid var(--sp-border, #e5e7eb)",
              background: "var(--sp-card, #fff)",
            }}
          >
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "end" }}>
              <label style={{ flex: "1 1 220px", display: "grid", gap: 4, fontSize: 12 }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontWeight: 600 }}>
                  <Search size={14} /> Search
                </span>
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Company, contact, email, package…"
                  style={{ height: 36, borderRadius: 8, border: "1px solid #d1d5db", padding: "0 10px" }}
                />
              </label>
              <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontWeight: 600 }}>
                  <CalendarDays size={14} /> From
                </span>
                <input
                  type="date"
                  value={fromDate}
                  onChange={(e) => setFromDate(e.target.value)}
                  style={{ height: 36, borderRadius: 8, border: "1px solid #d1d5db", padding: "0 10px" }}
                />
              </label>
              <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
                <span style={{ fontWeight: 600 }}>To</span>
                <input
                  type="date"
                  value={toDate}
                  onChange={(e) => setToDate(e.target.value)}
                  style={{ height: 36, borderRadius: 8, border: "1px solid #d1d5db", padding: "0 10px" }}
                />
              </label>
              <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
                <span style={{ fontWeight: 600 }}>Commission</span>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
                  style={{ height: 36, borderRadius: 8, border: "1px solid #d1d5db", padding: "0 10px" }}
                >
                  <option value="all">All deals</option>
                  <option value="with_commission">Has commission</option>
                  <option value="pending_commission">Pending payout</option>
                </select>
              </label>
              {(query || fromDate || toDate || statusFilter !== "all") && (
                <button
                  type="button"
                  onClick={() => {
                    setQuery("");
                    setFromDate("");
                    setToDate("");
                    setStatusFilter("all");
                  }}
                  style={{
                    height: 36,
                    borderRadius: 8,
                    border: "1px solid #d1d5db",
                    background: "#f9fafb",
                    padding: "0 12px",
                    cursor: "pointer",
                  }}
                >
                  Clear
                </button>
              )}
            </div>
            <p style={{ margin: 0, fontSize: 12, color: "#6b7280" }}>
              Showing <strong>{filtered.length}</strong> of {companies.length} deals
              {filteredCommission > 0 ? ` · commission in view ${money(filteredCommission, currency)}` : ""}
            </p>
          </div>

          <h4 style={{ margin: "20px 0 12px", fontWeight: 600 }}>Company &amp; commission details</h4>

          {loading ? (
            <p>Loading won deals…</p>
          ) : companies.length === 0 ? (
            <p>No won deals yet. Deals appear here once a customer signs up with your promo code.</p>
          ) : filtered.length === 0 ? (
            <p>No deals match your search or date filters.</p>
          ) : (
            <div style={{ display: "grid", gap: 10 }}>
              {filtered.map((c, i) => {
                const key = String(c.id || c.org_id || `${c.name}-${i}`);
                const open = Boolean(expanded[key]);
                const packageLabel = c.plan_name || c.plan_code || "Package not set yet";
                const interval = c.billing_interval ? String(c.billing_interval) : "";
                const price = c.amount_display || (c.amount_minor != null ? money(c.amount_minor, c.currency || currency) : null);
                return (
                  <div
                    key={key}
                    style={{
                      border: "1px solid #e5e7eb",
                      borderRadius: 12,
                      background: "#fff",
                      overflow: "hidden",
                    }}
                  >
                    <button
                      type="button"
                      onClick={() => setExpanded((prev) => ({ ...prev, [key]: !open }))}
                      style={{
                        width: "100%",
                        display: "flex",
                        gap: 12,
                        alignItems: "flex-start",
                        textAlign: "left",
                        padding: "14px 16px",
                        border: 0,
                        background: "transparent",
                        cursor: "pointer",
                      }}
                    >
                      <span
                        style={{
                          display: "grid",
                          placeItems: "center",
                          width: 36,
                          height: 36,
                          borderRadius: 999,
                          background: "#ecfdf5",
                          color: "#047857",
                          flexShrink: 0,
                        }}
                        aria-hidden
                      >
                        <Trophy size={18} />
                      </span>
                      <span style={{ flex: 1, minWidth: 0 }}>
                        <span style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                          <strong style={{ fontSize: 15 }}>{c.name}</strong>
                          <span
                            style={{
                              fontSize: 11,
                              fontWeight: 600,
                              borderRadius: 999,
                              padding: "2px 8px",
                              background: "#ecfdf5",
                              color: "#065f46",
                            }}
                          >
                            {c.status || "Won"}
                          </span>
                        </span>
                        <span style={{ display: "block", marginTop: 4, fontSize: 13, color: "#374151" }}>
                          {packageLabel}
                          {interval ? ` · ${interval}` : ""}
                          {price ? ` · ${price}` : ""}
                        </span>
                        <span style={{ display: "block", marginTop: 4, fontSize: 12, color: "#6b7280" }}>
                          Won {fmtDay(c.won_at || c.created_at)}
                          {c.commission_total_display || Number(c.commission_total_minor || 0) > 0
                            ? ` · Earned ${c.commission_total_display || money(c.commission_total_minor, c.currency || currency)}`
                            : " · No commission earned yet"}
                          {Number(c.commission_pending_minor || 0) > 0
                            ? ` · ${c.commission_pending_display || money(c.commission_pending_minor, c.currency || currency)} pending payout`
                            : ""}
                        </span>
                        {c.next_expected_commission ? (
                          <span style={{ display: "block", marginTop: 4, fontSize: 12, color: "#047857", fontWeight: 600 }}>
                            Expected {fmtDay(c.next_expected_commission.expected_date || c.next_expected_commission.expected_at)}
                            {" · "}
                            {c.next_expected_commission.amount_display ||
                              money(c.next_expected_commission.amount_minor, c.next_expected_commission.currency || currency)}
                            {c.next_expected_commission.label ? ` · ${c.next_expected_commission.label}` : ""}
                          </span>
                        ) : null}
                      </span>
                      <span style={{ color: "#9ca3af", marginTop: 8 }}>
                        {open ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                      </span>
                    </button>

                    {open ? (
                      <div
                        style={{
                          borderTop: "1px solid #f3f4f6",
                          padding: "12px 16px 16px",
                          display: "grid",
                          gap: 12,
                          background: "#fafafa",
                        }}
                      >
                        <div
                          style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                            gap: 10,
                            fontSize: 12,
                          }}
                        >
                          <div>
                            <div style={{ color: "#6b7280" }}>Contact</div>
                            <div style={{ fontWeight: 600 }}>{c.contact_person || "—"}</div>
                          </div>
                          <div>
                            <div style={{ color: "#6b7280" }}>Email</div>
                            <div style={{ fontWeight: 600, wordBreak: "break-all" }}>{c.email || "—"}</div>
                          </div>
                          <div>
                            <div style={{ color: "#6b7280" }}>Mobile</div>
                            <div style={{ fontWeight: 600 }}>{c.mobile || "—"}</div>
                          </div>
                          <div>
                            <div style={{ color: "#6b7280" }}>Customer package</div>
                            <div style={{ fontWeight: 600 }}>{packageLabel}</div>
                          </div>
                          <div>
                            <div style={{ color: "#6b7280" }}>Billing</div>
                            <div style={{ fontWeight: 600 }}>
                              {[interval, price, c.subscription_status].filter(Boolean).join(" · ") || "—"}
                            </div>
                          </div>
                          <div>
                            <div style={{ color: "#6b7280" }}>Won / converted</div>
                            <div style={{ fontWeight: 600 }}>{fmtDay(c.won_at || c.created_at)}</div>
                          </div>
                          <div>
                            <div style={{ color: "#6b7280" }}>Offer sent</div>
                            <div style={{ fontWeight: 600 }}>{fmtDay(c.offer_sent_at)}</div>
                          </div>
                          <div>
                            <div style={{ color: "#6b7280" }}>Commission total</div>
                            <div style={{ fontWeight: 600 }}>
                              {c.commission_total_display || money(c.commission_total_minor, c.currency || currency)}
                            </div>
                          </div>
                          <div>
                            <div style={{ color: "#6b7280" }}>Paid to you</div>
                            <div style={{ fontWeight: 600 }}>
                              {c.commission_paid_display || money(c.commission_paid_minor, c.currency || currency)}
                            </div>
                          </div>
                          <div>
                            <div style={{ color: "#6b7280" }}>Pending</div>
                            <div style={{ fontWeight: 600 }}>
                              {c.commission_pending_display || money(c.commission_pending_minor, c.currency || currency)}
                            </div>
                          </div>
                          <div>
                            <div style={{ color: "#6b7280" }}>Next expected</div>
                            <div style={{ fontWeight: 600 }}>
                              {c.next_expected_commission
                                ? `${fmtDay(c.next_expected_commission.expected_date || c.next_expected_commission.expected_at)} · ${
                                    c.next_expected_commission.amount_display ||
                                    money(
                                      c.next_expected_commission.amount_minor,
                                      c.next_expected_commission.currency || currency,
                                    )
                                  }`
                                : "—"}
                            </div>
                          </div>
                          <div>
                            <div style={{ color: "#6b7280" }}>Customer renewal</div>
                            <div style={{ fontWeight: 600 }}>{fmtDay(c.current_period_end)}</div>
                          </div>
                        </div>

                        <div>
                          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>Expected commission</div>
                          {(c.expected_commissions || []).length === 0 ? (
                            <p style={{ margin: 0, fontSize: 12, color: "#6b7280" }}>
                              No further expected commission for this customer under your current tiers.
                            </p>
                          ) : (
                            <div style={{ display: "grid", gap: 6, marginBottom: 12 }}>
                              {(c.expected_commissions || []).map((line, idx) => (
                                <div
                                  key={`${line.kind || "exp"}-${idx}`}
                                  style={{
                                    display: "flex",
                                    flexWrap: "wrap",
                                    justifyContent: "space-between",
                                    gap: 8,
                                    fontSize: 12,
                                    padding: "8px 10px",
                                    borderRadius: 8,
                                    border: "1px solid #a7f3d0",
                                    background: "#ecfdf5",
                                  }}
                                >
                                  <div>
                                    <div style={{ fontWeight: 600 }}>{line.label || "Expected commission"}</div>
                                    <div style={{ color: "#065f46" }}>
                                      Expected date: {fmtDay(line.expected_date || line.expected_at)}
                                      {line.note ? ` · ${line.note}` : ""}
                                    </div>
                                  </div>
                                  <div style={{ textAlign: "right" }}>
                                    <div style={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                                      {line.amount_display || money(line.amount_minor, line.currency || currency)}
                                    </div>
                                    <div style={{ color: "#047857" }}>Expected value</div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>

                        <div>
                          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>Earned commission lines</div>
                          {(c.commissions || []).length === 0 ? (
                            <p style={{ margin: 0, fontSize: 12, color: "#6b7280" }}>
                              No commission accrued yet for this customer. Rows appear after their subscription invoice
                              is paid.
                            </p>
                          ) : (
                            <div style={{ display: "grid", gap: 6 }}>
                              {(c.commissions || []).map((line) => (
                                <div
                                  key={line.id}
                                  style={{
                                    display: "flex",
                                    flexWrap: "wrap",
                                    justifyContent: "space-between",
                                    gap: 8,
                                    fontSize: 12,
                                    padding: "8px 10px",
                                    borderRadius: 8,
                                    border: "1px solid #e5e7eb",
                                    background: "#fff",
                                  }}
                                >
                                  <div>
                                    <div style={{ fontWeight: 600 }}>
                                      {KIND_LABELS[String(line.kind || "")] || line.kind || "Commission"}
                                    </div>
                                    <div style={{ color: "#6b7280" }}>
                                      {fmtDay(line.created_at)}
                                      {line.note ? ` · ${line.note}` : ""}
                                    </div>
                                  </div>
                                  <div style={{ textAlign: "right" }}>
                                    <div style={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                                      {line.amount_display || money(line.amount_minor, line.currency || currency)}
                                    </div>
                                    <div style={{ color: "#6b7280", textTransform: "capitalize" }}>
                                      {line.status || "—"}
                                    </div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
