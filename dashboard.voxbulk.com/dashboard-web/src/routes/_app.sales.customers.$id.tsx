import * as React from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ChevronLeft, CheckCircle2, Circle, Flag } from "lucide-react";

import { apiFetch } from "@/lib/api";
import { requireSalesRep } from "@/lib/guards/settings-route";
import { CustomerEditor, type SalesCustomer } from "@/components/sales/CustomerEditor";
import "@/styles/sales-portal.css";

type TimelineEntry = { key: string; label: string; at: string | null };
type CustomerDetail = SalesCustomer & { timeline?: TimelineEntry[] };

export const Route = createFileRoute("/_app/sales/customers/$id")({
  head: () => ({ meta: [{ title: "Customer — Sales" }] }),
  beforeLoad: () => requireSalesRep(),
  validateSearch: (search: Record<string, unknown>): { edit?: boolean } => ({
    edit: search.edit === true || search.edit === "true",
  }),
  component: SalesCustomerDetail,
});

const STAGE_LABELS: Record<string, string> = {
  lead: "Lead",
  contacted: "Contacted",
  demoed: "Demoed",
  interested: "Interested",
  won: "Won",
};

function fmt(at: string | null): string {
  if (!at) return "Pending";
  try {
    return new Date(at).toLocaleString();
  } catch {
    return at;
  }
}

function SalesCustomerDetail() {
  const { id } = Route.useParams();
  const [detail, setDetail] = React.useState<CustomerDetail | null>(null);

  const load = React.useCallback(async () => {
    try {
      const res = await apiFetch<{ customer: CustomerDetail }>(`/sales/customers/${id}`);
      setDetail(res.customer);
    } catch {
      /* surfaced via editor toast / empty state */
    }
  }, [id]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const stage = detail?.stage || detail?.status || "lead";
  const timeline = detail?.timeline || [];

  return (
    <div className="salesPortal salesPortal--embedded">
      <div className="sp-app">
        <div className="sp-track-head">
          <Link to="/sales" className="sp-back" title="Back to my customers">
            <ChevronLeft size={16} /> My customers
          </Link>
          {detail ? (
            <div className="sp-track-title">
              <h2>{detail.company_name || detail.full_name || "Customer"}</h2>
              <span className={`sp-stage stage-${stage}`}>{STAGE_LABELS[stage] || stage}</span>
              {detail.interested ? (
                <span className="sp-flag" title="Offer sent — interested">
                  <Flag size={11} /> Interested
                </span>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="sp-funnel">
          {timeline.map((step) => {
            const reached = Boolean(step.at);
            return (
              <div key={step.key} className={`sp-funnel-step ${reached ? "done" : ""}`}>
                <span className="sp-funnel-ico">
                  {reached ? <CheckCircle2 size={18} /> : <Circle size={18} />}
                </span>
                <div className="sp-funnel-body">
                  <div className="sp-funnel-label">{step.label}</div>
                  <div className="sp-funnel-at">{fmt(step.at)}</div>
                </div>
              </div>
            );
          })}
        </div>

        <CustomerEditor customerId={id} onChanged={() => void load()} />
      </div>
    </div>
  );
}
