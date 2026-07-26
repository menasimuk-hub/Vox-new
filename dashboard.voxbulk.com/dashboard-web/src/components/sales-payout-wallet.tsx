import * as React from "react";
import { CircleDollarSign, Wallet } from "lucide-react";

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

function money(minor?: number) {
  const n = Number(minor || 0) / 100;
  return `£${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function SalesPayoutWallet({ titleHint }: { titleHint?: string }) {
  const [wallet, setWallet] = React.useState<WalletStats | null>(null);
  const [payout, setPayout] = React.useState<Payout>({ payout_method: "bank" });
  const [invoices, setInvoices] = React.useState<InvoiceRow[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [msg, setMsg] = React.useState("");
  const [err, setErr] = React.useState("");
  const [amountGbp, setAmountGbp] = React.useState("");
  const [notes, setNotes] = React.useState("");

  const load = React.useCallback(async () => {
    setLoading(true);
    setErr("");
    try {
      const res = await apiFetch<{
        wallet: WalletStats;
        rep?: { payout?: Payout };
        payout_invoices?: InvoiceRow[];
      }>("/sales/wallet");
      setWallet(res.wallet || null);
      setPayout(res.rep?.payout || { payout_method: "bank" });
      setInvoices(res.payout_invoices || []);
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
      {err ? <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">{err}</div> : null}
      {msg ? <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-800">{msg}</div> : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1.5">
              <CircleDollarSign className="size-3.5" />
              Available
            </CardDescription>
            <CardTitle className="text-3xl tabular-nums">{loading ? "…" : money(available)}</CardTitle>
          </CardHeader>
          <CardContent className="pt-0 text-xs text-muted-foreground">Ready to invoice</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Awaiting approval</CardDescription>
            <CardTitle className="text-3xl tabular-nums">
              {loading ? "…" : money(wallet?.commission_requested_minor)}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Paid out</CardDescription>
            <CardTitle className="text-3xl tabular-nums">
              {loading ? "…" : money(wallet?.commission_paid_minor)}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1.5">
              <Wallet className="size-3.5" />
              Lifetime
            </CardDescription>
            <CardTitle className="text-3xl tabular-nums">
              {loading ? "…" : money(wallet?.commission_minor)}
            </CardTitle>
          </CardHeader>
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
                  <Label>Address</Label>
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
                  type="email"
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
            <CardTitle>Create invoice</CardTitle>
            <CardDescription>
              Amount cannot exceed available commission ({money(available)}).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label>Amount (GBP)</Label>
              <Input
                type="number"
                min="0.01"
                step="0.01"
                value={amountGbp}
                onChange={(e) => setAmountGbp(e.target.value)}
                placeholder="e.g. 150.00"
              />
            </div>
            <div>
              <Label>Notes (optional)</Label>
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
          <CardTitle>Your payout invoices</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Invoice</TableHead>
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
                    <TableCell className="font-medium">{inv.invoice_number}</TableCell>
                    <TableCell>{inv.amount_display || money(inv.amount_minor)}</TableCell>
                    <TableCell>
                      <Badge variant={inv.status === "paid" ? "default" : "secondary"}>{inv.status}</Badge>
                    </TableCell>
                    <TableCell>{(inv.submitted_at || "").slice(0, 10)}</TableCell>
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
