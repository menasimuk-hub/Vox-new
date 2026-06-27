import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import {
  UserPlus,
  Save,
  Send,
  Phone,
  QrCode,
  Gift,
  MessageCircle,
  Mail,
  PhoneCall,
  Users,
  Trash2,
  X,
} from "lucide-react";

import { apiFetch } from "@/lib/api";
import { requireSalesRep } from "@/lib/guards/settings-route";
import "@/styles/sales-portal.css";

export const Route = createFileRoute("/_app/sales/")({
  head: () => ({ meta: [{ title: "My customers — Sales" }] }),
  beforeLoad: () => requireSalesRep(),
  component: SalesCustomers,
});

type Rep = { id: string; name: string; promo_code: string; caller_id?: string | null };
type Customer = {
  id: string;
  full_name: string;
  company_name?: string | null;
  address?: string | null;
  city?: string | null;
  country?: string | null;
  mobile?: string | null;
  email?: string | null;
  business_type?: string | null;
  branches?: number;
  contact_person?: string | null;
  status?: string;
  org_id?: string | null;
};

const BUSINESS_TYPES = ["Retail", "Wholesale", "Manufacturing", "Services", "Technology", "Healthcare", "Other"];

const EMPTY_FORM = {
  id: "",
  full_name: "",
  company_name: "",
  address: "",
  city: "",
  country: "",
  mobile: "",
  email: "",
  business_type: "Retail",
  branches: 1,
  contact_person: "",
};

function SalesCustomers() {
  const [rep, setRep] = React.useState<Rep | null>(null);
  const [customers, setCustomers] = React.useState<Customer[]>([]);
  const [form, setForm] = React.useState({ ...EMPTY_FORM });
  const [offerDetails, setOfferDetails] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [toast, setToast] = React.useState<{ msg: string; err?: boolean } | null>(null);
  const [showQr, setShowQr] = React.useState(false);

  const flash = (msg: string, err = false) => {
    setToast({ msg, err });
    window.setTimeout(() => setToast(null), 4000);
  };

  const loadAll = React.useCallback(async () => {
    try {
      const [meRes, custRes] = await Promise.all([
        apiFetch<{ rep: Rep }>("/sales/me"),
        apiFetch<{ items: Customer[] }>("/sales/customers"),
      ]);
      setRep(meRes.rep);
      setCustomers(custRes.items || []);
    } catch (e: any) {
      flash(e?.message || "Failed to load sales data", true);
    }
  }, []);

  React.useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const setField = (k: string, v: string | number) => setForm((f) => ({ ...f, [k]: v }));

  const saveCustomer = async () => {
    if (!form.full_name.trim()) return flash("Enter the customer's full name.", true);
    setBusy(true);
    try {
      const res = await apiFetch<{ customer: Customer }>("/sales/customers", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setForm((f) => ({ ...f, id: res.customer.id }));
      flash(`Saved ${res.customer.company_name || res.customer.full_name}.`);
      await loadAll();
    } catch (e: any) {
      flash(e?.message || "Save failed", true);
    } finally {
      setBusy(false);
    }
  };

  const requireSaved = () => {
    if (!form.id) {
      flash("Save the customer first, then send.", true);
      return false;
    }
    return true;
  };

  const doAction = async (path: string, body?: object) => {
    if (!requireSaved()) return;
    setBusy(true);
    try {
      const res = await apiFetch<{ ok: boolean; message?: string }>(`/sales/customers/${form.id}/${path}`, {
        method: "POST",
        body: body ? JSON.stringify(body) : undefined,
      });
      flash(res.message || (res.ok ? "Done." : "Failed."), !res.ok);
      await loadAll();
    } catch (e: any) {
      flash(e?.message || "Action failed", true);
    } finally {
      setBusy(false);
    }
  };

  const editCustomer = (c: Customer) => {
    setForm({
      id: c.id,
      full_name: c.full_name || "",
      company_name: c.company_name || "",
      address: c.address || "",
      city: c.city || "",
      country: c.country || "",
      mobile: c.mobile || "",
      email: c.email || "",
      business_type: c.business_type || "Retail",
      branches: c.branches || 1,
      contact_person: c.contact_person || "",
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const deleteCustomer = async (c: Customer) => {
    if (!window.confirm(`Delete ${c.company_name || c.full_name}?`)) return;
    try {
      await apiFetch(`/sales/customers/${c.id}`, { method: "DELETE" });
      if (form.id === c.id) setForm({ ...EMPTY_FORM });
      await loadAll();
    } catch (e: any) {
      flash(e?.message || "Delete failed", true);
    }
  };

  const newCustomer = () => setForm({ ...EMPTY_FORM });

  return (
    <div className="salesPortal salesPortal--embedded">
      <div className="sp-app">
        {toast ? <div className={`sp-toast ${toast.err ? "err" : ""}`}>{toast.msg}</div> : null}

        <div className="sp-form">
          <h2>
            <UserPlus size={20} /> {form.id ? "Edit customer" : "Add new customer"}
          </h2>
          <div className="sp-row">
            <div className="sp-group">
              <label>Full name</label>
              <input value={form.full_name} onChange={(e) => setField("full_name", e.target.value)} placeholder="e.g. John Doe" />
            </div>
            <div className="sp-group">
              <label>Company name</label>
              <input value={form.company_name} onChange={(e) => setField("company_name", e.target.value)} placeholder="Company" />
            </div>
          </div>
          <div className="sp-row">
            <div className="sp-group">
              <label>Address</label>
              <input value={form.address} onChange={(e) => setField("address", e.target.value)} placeholder="Street" />
            </div>
            <div className="sp-group">
              <label>City</label>
              <input value={form.city} onChange={(e) => setField("city", e.target.value)} placeholder="City" />
            </div>
          </div>
          <div className="sp-row-3">
            <div className="sp-group">
              <label>Country</label>
              <input value={form.country} onChange={(e) => setField("country", e.target.value)} placeholder="Country" />
            </div>
            <div className="sp-group">
              <label>Mobile number</label>
              <input value={form.mobile} onChange={(e) => setField("mobile", e.target.value)} placeholder="+44 7788 1234" />
            </div>
            <div className="sp-group">
              <label>Business type</label>
              <select value={form.business_type} onChange={(e) => setField("business_type", e.target.value)}>
                {BUSINESS_TYPES.map((b) => (
                  <option key={b}>{b}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="sp-row">
            <div className="sp-group">
              <label>How many branches?</label>
              <input type="number" value={form.branches} onChange={(e) => setField("branches", Number(e.target.value) || 0)} />
            </div>
            <div className="sp-group">
              <label>Contact person</label>
              <input value={form.contact_person} onChange={(e) => setField("contact_person", e.target.value)} placeholder="Contact name" />
            </div>
          </div>
          <div className="sp-group">
            <label>Email (for offers)</label>
            <input value={form.email} onChange={(e) => setField("email", e.target.value)} placeholder="name@company.com" />
          </div>

          <div className="sp-actions">
            <button className="sp-btn primary" onClick={saveCustomer} disabled={busy}>
              <Save size={16} /> {form.id ? "Update customer" : "Save customer"}
            </button>
            {form.id ? (
              <button className="sp-btn" onClick={newCustomer} disabled={busy}>
                New customer
              </button>
            ) : null}
          </div>

          <div className="sp-survey-actions">
            <div className="sp-survey-card">
              <span className="sp-icon">
                <MessageCircle size={28} />
              </span>
              <h4>Send WA Survey</h4>
              <div className="sp-field-group">
                <input value={form.mobile} onChange={(e) => setField("mobile", e.target.value)} placeholder="Mobile number" />
                <button className="sp-btn-send" onClick={() => doAction("demo-wa")} disabled={busy}>
                  <Send size={14} /> Send Survey
                </button>
              </div>
            </div>
            <div className="sp-survey-card">
              <span className="sp-icon">
                <Phone size={28} />
              </span>
              <h4>AI Calling Survey</h4>
              <div className="sp-field-group">
                <input value={form.mobile} onChange={(e) => setField("mobile", e.target.value)} placeholder="Mobile number" />
                <button className="sp-btn-send" onClick={() => doAction("demo-call")} disabled={busy}>
                  <PhoneCall size={14} /> Call &amp; Survey
                </button>
              </div>
            </div>
            <div className="sp-survey-card">
              <span className="sp-icon">
                <QrCode size={28} />
              </span>
              <h4>Show QR Code</h4>
              <div className="sp-field-group">
                <button className="sp-btn-send" onClick={() => setShowQr(true)}>
                  <QrCode size={14} /> Show QR Code
                </button>
              </div>
            </div>
          </div>

          <div className="sp-offer">
            <h4>
              <Gift size={16} /> Send offer to customer
            </h4>
            <div className="sp-offer-row">
              <div className="sp-group">
                <label>Promo code</label>
                <input value={rep?.promo_code || ""} readOnly style={{ background: "#e5ddd0" }} />
              </div>
              <div className="sp-group">
                <label>Offer details</label>
                <input value={offerDetails} onChange={(e) => setOfferDetails(e.target.value)} placeholder="e.g. 20% off first order" />
              </div>
              <div className="sp-offer-buttons">
                <button className="sp-btn-offer" onClick={() => doAction("offer", { channel: "wa", offer_details: offerDetails })} disabled={busy}>
                  <MessageCircle size={14} /> Send WA
                </button>
                <button className="sp-btn-offer" onClick={() => doAction("offer", { channel: "email", offer_details: offerDetails })} disabled={busy}>
                  <Mail size={14} /> Send Email
                </button>
              </div>
            </div>
          </div>

          {rep?.caller_id ? (
            <div className="sp-callerid">
              <Phone size={14} /> Caller ID: {rep.caller_id}
            </div>
          ) : null}
        </div>

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
                <th>Country</th>
                <th>Mobile</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {customers.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ color: "#7a6b58" }}>
                    No customers yet. Add one with the form above.
                  </td>
                </tr>
              ) : (
                customers.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <span className="sp-badge">{(c.full_name || "?").split(" ")[0]}</span> {c.full_name}
                    </td>
                    <td>{c.company_name || "—"}</td>
                    <td>{c.city || "—"}</td>
                    <td>{c.country || "—"}</td>
                    <td>{c.mobile || "—"}</td>
                    <td style={{ textAlign: "right" }}>
                      <span className="sp-rowact">
                        <button title="Edit" onClick={() => editCustomer(c)}>
                          <UserPlus size={15} color="#1a2332" />
                        </button>
                        <button title="Delete" onClick={() => deleteCustomer(c)}>
                          <Trash2 size={15} color="#b16a5e" />
                        </button>
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showQr ? (
        <div className="sp-qr-overlay" onClick={() => setShowQr(false)}>
          <div className="sp-qr" onClick={(e) => e.stopPropagation()}>
            <div className="sp-qr-box">
              <QrCode size={120} />
            </div>
            <h3>Promo code</h3>
            <p>
              Share this code with the customer
              <br />
              <strong style={{ fontSize: 16, color: "#1a2332" }}>{rep?.promo_code || "—"}</strong>
            </p>
            <button className="sp-btn primary" onClick={() => setShowQr(false)}>
              <X size={14} /> Close
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
