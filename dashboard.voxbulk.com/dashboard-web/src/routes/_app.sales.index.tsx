import * as React from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Users, Trash2, UserPlus, Activity, Flag } from "lucide-react";

import { apiFetch } from "@/lib/api";
import { requireSalesRep } from "@/lib/guards/settings-route";
import type { SalesCustomer } from "@/components/sales/CustomerEditor";
import "@/styles/sales-portal.css";

export const Route = createFileRoute("/_app/sales/")({
  head: () => ({ meta: [{ title: "My customers — Sales" }] }),
  beforeLoad: () => requireSalesRep(),
  component: SalesCustomers,
});

const STAGE_LABELS: Record<string, string> = {
  lead: "Lead",
  contacted: "Contacted",
  demoed: "Demoed",
  interested: "Interested",
  won: "Won",
};

function SalesCustomers() {
  const [customers, setCustomers] = React.useState<SalesCustomer[]>([]);
  const [toast, setToast] = React.useState<{ msg: string; err?: boolean } | null>(null);

  const flash = (msg: string, err = false) => {
    setToast({ msg, err });
    window.setTimeout(() => setToast(null), 4000);
  };

  const loadAll = React.useCallback(async () => {
    try {
      const custRes = await apiFetch<{ items: SalesCustomer[] }>("/sales/customers");
      setCustomers(custRes.items || []);
    } catch (e: any) {
      flash(e?.message || "Failed to load customers", true);
    }
  }, []);

  React.useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const deleteCustomer = async (c: SalesCustomer) => {
    if (!window.confirm(`Delete ${c.company_name || c.full_name}?`)) return;
    try {
      await apiFetch(`/sales/customers/${c.id}`, { method: "DELETE" });
      await loadAll();
    } catch (e: any) {
      flash(e?.message || "Delete failed", true);
    }
  };

  return (
    <div className="salesPortal salesPortal--embedded">
      <div className="sp-app">
        {toast ? <div className={`sp-toast ${toast.err ? "err" : ""}`}>{toast.msg}</div> : null}

        <div className="sp-table-wrap">
          <div className="sp-table-head">
            <h3>
              <Users size={18} /> Visited customers
            </h3>
            <span>{customers.length} customers</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Company</th>
                <th>City</th>
                <th>Mobile</th>
                <th>Stage</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {customers.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ color: "#7a6b58" }}>
                    No customers yet. Add one from “Add new customer”.
                  </td>
                </tr>
              ) : (
                customers.map((c) => {
                  const stage = c.stage || c.status || "lead";
                  return (
                    <tr key={c.id}>
                      <td>
                        <span className="sp-badge">{(c.full_name || "?").split(" ")[0]}</span> {c.full_name}
                      </td>
                      <td>{c.company_name || "—"}</td>
                      <td>{c.city || "—"}</td>
                      <td>{c.mobile || "—"}</td>
                      <td>
                        <span className={`sp-stage stage-${stage}`}>{STAGE_LABELS[stage] || stage}</span>
                        {c.interested ? (
                          <span className="sp-flag" title="Offer sent — interested">
                            <Flag size={11} /> Interested
                          </span>
                        ) : null}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <span className="sp-rowact">
                          <Link to="/sales/customers/$id" params={{ id: c.id }} search={{ edit: false }} title="Track">
                            <Activity size={15} color="#1a2332" />
                          </Link>
                          <Link to="/sales/customers/$id" params={{ id: c.id }} search={{ edit: true }} title="Edit">
                            <UserPlus size={15} color="#1a2332" />
                          </Link>
                          <button title="Delete" onClick={() => deleteCustomer(c)}>
                            <Trash2 size={15} color="#b16a5e" />
                          </button>
                        </span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
