import * as React from "react";
import { CircleDollarSign, Gift, Percent } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";

type Payout = {
  payout_method?: string | null;
  bank_holder_name?: string | null;
  bank_name?: string | null;
  bank_sort_code?: string | null;
  bank_account_number?: string | null;
  bank_address?: string | null;
  paypal_email?: string | null;
};

type WalletStats = {
  commission_minor?: number;
  commission_paid_minor?: number;
  commission_pending_minor?: number;
  commission_available_minor?: number;
  commission_requested_minor?: number;
};

type InvoiceRow = {
  id: string;
  invoice_number: string;
  amount_minor: number;
  amount_display?: string;
  status: string;
  submitted_at?: string | null;
  notes?: string | null;
};

type PackageRow = {
  service_id?: string;
  name?: string;
  list_price_display?: string | null;
  monthly_display?: string | null;
};

type RepInfo = {
  payout?: Payout;
  promo_code?: string;
  currency?: string;
  commission_summary?: string;
  commission_tiers?: { month: number; enabled: boolean; kind: string; value: number }[];
  promo_benefit_summaries?: string[];
  partner_terms?: { discount_percent?: number; billing?: string };
};

const SYMBOLS: Record<string, string> = { GBP: "£", EUR: "€", USD: "$", CAD: "CA$", AUD: "A$" };

function money(minor?: number, currency = "GBP") {
  const n = Number(minor || 0) / 100;
  const sym = SYMBOLS[currency] || currency + " ";
  return `${sym}${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function SalesPayoutWallet({ titleHint }: { titleHint?: string }) {
  const [wallet, setWallet] = React.useState<WalletStats | null>(null);
  const [payout, setPayout] = React.useState<Payout>({ payout_method: "bank" });
  const [invoices, setInvoices] = React.useState<InvoiceRow[]>([]);
  const [rep, setRep] = React.useState<RepInfo | null>(null);
  const [packages, setPackages] = React.useState<PackageRow[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [msg, setMsg] = React.useState("");
  const [err, setErr] = React.useState("");
  const [amountGbp, setAmountGbp] = React.useState("");
  const [notes, setNotes] = React.useState("");

  const currency = rep?.currency || "GBP";

  const load = React.useCallback(async () => {
    setLoading(true);
    setErr("");
    try {
      const res = await apiFetch<{
          wallet: WalletStats;
          rep?: RepInfo;
          payout_invoices?: InvoiceRow[];
          packages?: PackageRow[];
          commission_summary?: string;
          promo_benefit_summaries?: string[];
          currency?: string;
        }>("/sales/wallet");
      setWallet(res.wallet || null);
      const merged: RepInfo = {
        ...(res.rep || {}),
        commission_summary: res.rep?.commission_summary || res.commission_summary,
        promo_benefit_summaries: res.rep?.promo_benefit_summaries || res.promo_benefit_summaries,
        currency: res.rep?.currency || res.currency || "GBP",
      };
      setRep(merged);
      setPayout(res.rep?.payout || { payout_method: "bank" });
      setInvoices(res.payout_invoices || []);
      setPackages(res.packages || []);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Failed to load wallet");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const savePayout = async () => {
    setBusy(true);
    setMsg("");
    setErr("");
    try {
      await apiFetch("/sales/me/payout", {
        method: "PATCH",
        body: JSON.stringify({ payout }),
      });
      setMsg("Payout details saved");
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const createInvoice = async () => {
    setBusy(true);
    setMsg("");
    setErr("");
    try {
      await apiFetch("/sales/payout-invoices", {
        method: "POST",
        body: JSON.stringify({
          amount_gbp: amountGbp,
          notes,
        }),
      });
      setAmountGbp("");
      setNotes("");
      setMsg("Invoice submitted — awaiting admin approval");
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not create invoice");
    } finally {
      setBusy(false);
    }
  };

  const available = Number(wallet?.commission_available_minor || 0);

  return (
    <div className="flex w-full flex-col gap-6">
      {titleHint ? <p className="text-sm text-muted-foreground">{titleHint}</p> : null}
      {err ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {err}
        </div>
      ) : null}
      {msg ? (
        <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-800">
          {msg}
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1.5">
              <CircleDollarSign className="size-3.5" />
              Available
            </CardDescription>
            <CardTitle className="text-3xl tabular-nums">{loading ? "…" : money(available, currency)}</CardTitle>
          </CardHeader>
          <CardContent className="pt-0 text-xs text-muted-foreground">Ready to invoice</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Awaiting approval</CardDescription>
            <CardTitle className="text-3xl tabular-nums">
              {loading ? "…" : money(wallet?.commission_requested_minor, currency)}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Paid out</CardDescription>
            <CardTitle className="text-3xl tabular-nums">
              {loading ? "…" : money(wallet?.commission_paid_minor, currency)}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Percent className="size-4" /> Commission limits
            </CardTitle>
            <CardDescription>As set by admin — your earning rules.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p className="font-medium">{rep?.commission_summary || (loading ? "…" : "—")}</p>
            {(rep?.commission_tiers || [])
              .filter((t) => t.enabled)
              .map((t) => (
                <div key={t.month} className="flex justify-between text-muted-foreground">
                  <span>Month {t.month}</span>
                  <span>
                    {t.kind === "fixed" ? money(t.value, currency) : `${Number(t.value)}%`}
                  </span>
                </div>
              ))}
            {rep?.partner_terms?.discount_percent ? (
              <p className="text-muted-foreground">
                Partner discount {Number(rep.partner_terms.discount_percent)}% ·{" "}
                {rep.partner_terms.billing === "invoice_partner" ? "Invoice partner" : "Customer pays"}
              </p>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Gift className="size-4" /> Your promo
            </CardTitle>
            <CardDescription>Code and what it can do for customers.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="font-mono text-sm">
                {rep?.promo_code || "—"}
              </Badge>
              <span className="text-muted-foreground">{currency}</span>
            </div>
            {(rep?.promo_benefit_summaries || []).length === 0 ? (
              <p className="text-muted-foreground">{loading ? "…" : "No benefits configured yet."}</p>
            ) : (
              <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                {rep?.promo_benefit_summaries?.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            )}
            {packages.length > 0 ? (
              <div className="mt-3 border-t pt-3">
                <p className="mb-1 font-medium">Packages in your market</p>
                <ul className="space-y-1 text-muted-foreground">
                  {packages.map((p) => (
                    <li key={p.service_id || p.name} className="flex justify-between gap-2">
                      <span>{p.name}</span>
                      <span>{p.list_price_display || p.monthly_display || "—"}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Payout details</CardTitle>
            <CardDescription>UK bank account or PayPal — required before creating an invoice.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex gap-4">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  checked={(payout.payout_method || "bank") === "bank"}
                  onChange={() => setPayout({ ...payout, payout_method: "bank" })}
                />
                Bank
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  checked={payout.payout_method === "paypal"}
                  onChange={() => setPayout({ ...payout, payout_method: "paypal" })}
                />
                PayPal
              </label>
            </div>
            {(payout.payout_method || "bank") === "bank" ? (
              <div className="grid gap-2">
                <div>
                  <Label>Account holder / company name</Label>
                  <Input
                    value={payout.bank_holder_name || ""}
                    onChange={(e) => setPayout({ ...payout, bank_holder_name: e.target.value })}
                  />
                </div>
                <div>
                  <Label>Bank name</Label>
                  <Input value={payout.bank_name || ""} onChange={(e) => setPayout({ ...payout, bank_name: e.target.value })} />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <Label>Sort code</Label>
                    <Input
                      value={payout.bank_sort_code || ""}
                      onChange={(e) => setPayout({ ...payout, bank_sort_code: e.target.value })}
                    />
                  </div>
                  <div>
                    <Label>Account number</Label>
                    <Input
                      value={payout.bank_account_number || ""}
                      onChange={(e) => setPayout({ ...payout, bank_account_number: e.target.value })}
                    />
                  </div>
                </div>
                <div>
                  <Label>Bank address</Label>
                  <Input
                    value={payout.bank_address || ""}
                    onChange={(e) => setPayout({ ...payout, bank_address: e.target.value })}
                  />
                </div>
              </div>
            ) : (
              <div>
                <Label>PayPal email</Label>
                <Input
                  value={payout.paypal_email || ""}
                  onChange={(e) => setPayout({ ...payout, paypal_email: e.target.value })}
                />
              </div>
            )}
            <Button type="button" disabled={busy} onClick={() => void savePayout()}>
              Save payout details
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Request payout</CardTitle>
            <CardDescription>Create a withdrawal invoice against available commission.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label>Amount ({currency})</Label>
              <Input value={amountGbp} onChange={(e) => setAmountGbp(e.target.value)} placeholder="0.00" />
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} />
            </div>
            <Button type="button" disabled={busy || available <= 0} onClick={() => void createInvoice()}>
              Submit invoice
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Withdrawal invoices</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Number</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Submitted</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {invoices.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="text-muted-foreground">
                    No invoices yet.
                  </TableCell>
                </TableRow>
              ) : (
                invoices.map((inv) => (
                  <TableRow key={inv.id}>
                    <TableCell className="font-mono text-xs">{inv.invoice_number}</TableCell>
                    <TableCell>{inv.amount_display || money(inv.amount_minor, currency)}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{inv.status}</Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {(inv.submitted_at || "").slice(0, 10) || "—"}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
