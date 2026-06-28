import * as React from "react";
import { UserPlus, Save, Send, Phone, QrCode, Gift, MessageCircle, Mail, PhoneCall, X } from "lucide-react";

import { apiFetch } from "@/lib/api";

export type Rep = { id: string; name: string; promo_code: string; caller_id?: string | null };

export type SalesCustomer = {
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
  stage?: string;
  interested?: boolean;
  interested_at?: string | null;
  demo_wa_sent_at?: string | null;
  demo_call_sent_at?: string | null;
  offer_sent_at?: string | null;
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

type Props = {
  /** When set, the editor loads this customer and starts in edit mode. */
  customerId?: string | null;
  /** Called after a successful save / action so parents can refresh. */
  onChanged?: (customer: SalesCustomer) => void;
};

export function CustomerEditor({ customerId, onChanged }: Props) {
  const [rep, setRep] = React.useState<Rep | null>(null);
  const [form, setForm] = React.useState({ ...EMPTY_FORM });
  const [offerDetails, setOfferDetails] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [toast, setToast] = React.useState<{ msg: string; err?: boolean } | null>(null);
  const [showQr, setShowQr] = React.useState(false);

  const flash = (msg: string, err = false) => {
    setToast({ msg, err });
    window.setTimeout(() => setToast(null), 4000);
  };

  React.useEffect(() => {
    void (async () => {
      try {
        const meRes = await apiFetch<{ rep: Rep }>("/sales/me");
        setRep(meRes.rep);
      } catch (e: any) {
        flash(e?.message || "Failed to load sales profile", true);
      }
    })();
  }, []);

  React.useEffect(() => {
    if (!customerId) {
      setForm({ ...EMPTY_FORM });
      return;
    }
    void (async () => {
      try {
        const res = await apiFetch<{ customer: SalesCustomer }>(`/sales/customers/${customerId}`);
        const c = res.customer;
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
        setOfferDetails("");
      } catch (e: any) {
        flash(e?.message || "Failed to load customer", true);
      }
    })();
  }, [customerId]);

  const setField = (k: string, v: string | number) => setForm((f) => ({ ...f, [k]: v }));

  const saveCustomer = async () => {
    if (!form.full_name.trim()) return flash("Enter the customer's full name.", true);
    setBusy(true);
    try {
      const res = await apiFetch<{ customer: SalesCustomer }>("/sales/customers", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setForm((f) => ({ ...f, id: res.customer.id }));
      flash(`Saved ${res.customer.company_name || res.customer.full_name}.`);
      onChanged?.(res.customer);
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
      const res = await apiFetch<{ ok: boolean; message?: string; customer?: SalesCustomer }>(
        `/sales/customers/${form.id}/${path}`,
        { method: "POST", body: body ? JSON.stringify(body) : undefined },
      );
      flash(res.message || (res.ok ? "Done." : "Failed."), !res.ok);
      if (res.ok) {
        try {
          const fresh = await apiFetch<{ customer: SalesCustomer }>(`/sales/customers/${form.id}`);
          onChanged?.(fresh.customer);
        } catch {
          /* non-fatal: action succeeded, refresh failed */
        }
      }
    } catch (e: any) {
      flash(e?.message || "Action failed", true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
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
    </>
  );
}
