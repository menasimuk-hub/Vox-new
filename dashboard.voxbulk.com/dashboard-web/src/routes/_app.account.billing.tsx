import { createFileRoute, Link } from "@tanstack/react-router";
import { AlertTriangle, CreditCard, Download, Eye, Wallet } from "lucide-react";
import * as React from "react";

import { InvoicePayDialog } from "@/components/invoice-pay-dialog";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { downloadAuthenticatedFile, openAuthenticatedHtmlInTab } from "@/lib/api";
import { invoiceStatusLabel } from "@/lib/billing/order-pay-labels";
import { badgeToneFromStatus } from "@/lib/mappers/orders";
import { StatusBadge } from "@/components/status-badge";
import { useBillingAccess, useBillingInvoices, useBillingSubscription, useBillingUsage, useWalletTransactions } from "@/lib/queries";
import type { BillingMonitorPayload, Invoice } from "@/lib/types/api";
import { useSession } from "@/lib/session";

export const Route = createFileRoute("/_app/account/billing")({
  head: () => ({ meta: [{ title: "Billing — VoxBulk" }] }),
  validateSearch: (search: Record<string, unknown>) => ({
    pay: typeof search.pay === "string" ? search.pay : undefined,
  }),
  component: BillingPage,
});

function moneyFromPence(pence?: number) {
  return `£${((Number(pence || 0)) / 100).toFixed(2)}`;
}

function fmtPeriod(start?: string | null, end?: string | null) {
  if (!start || !end) return null;
  try {
    const a = new Date(start).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
    const b = new Date(end).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
    return `${a} – ${b}`;
  } catch {
    return null;
  }
}

function invoiceKind(description?: string | null, provider?: string | null) {
  const text = `${description || ""} ${provider || ""}`.toLowerCase();
  if (text.includes("overage") || text.includes("usage")) return "Extra usage";
  if (text.includes("subscription") || text.includes("plan") || provider === "gocardless") return "Subscription";
  return "Invoice";
}

function canShowPayAction(rawStatus: string) {
  const st = String(rawStatus || "").toLowerCase();
  return !["paid", "collecting", "void", "cancelled", "refunded", "credited"].includes(st);
}

function billingErrorMessage(err: unknown) {
  if (err && typeof err === "object" && "message" in err) return String((err as { message: unknown }).message);
  return "Could not load billing data. Try refreshing the page.";
}

function KpiCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card>
      <CardContent className="space-y-1 p-4">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-xl font-semibold tabular-nums">{value}</p>
        {sub ? <p className="text-[11px] text-muted-foreground">{sub}</p> : null}
      </CardContent>
    </Card>
  );
}

function BillingPage() {
  const { session } = useSession();
  const { pay: payInvoiceId } = Route.useSearch();
  const subQ = useBillingSubscription();
  const usageQ = useBillingUsage();
  const invoicesQ = useBillingInvoices();
  const accessQ = useBillingAccess();
  const walletTxQ = useWalletTransactions(30);
  const [payInvoice, setPayInvoice] = React.useState<Invoice | null>(null);

  const plan = subQ.data?.plan || usageQ.data?.current_plan || session?.subscription?.plan;
  const subscription = subQ.data?.subscription || usageQ.data?.subscription;
  const monitor = (usageQ.data?.billing_monitor || {}) as BillingMonitorPayload;
  const commercial = monitor.commercial || {};
  const estimates = monitor.capacity_estimates || {};
  const actual = monitor.actual_usage || {};
  const status = monitor.status || {};

  const period = fmtPeriod(
    status.billing_period_start || usageQ.data?.period_start,
    status.billing_period_end || usageQ.data?.period_end,
  );
  const overagePending = Number(status.overage_pending_pence ?? usageQ.data?.overage_pending_pence ?? 0);
  const estimatedOverage = usageQ.data?.estimated_overage_gbp;
  const openInvoices = Number(status.open_invoices_count ?? usageQ.data?.open_invoices_count ?? 0);
  const nextActionLabel = status.next_action_label || usageQ.data?.next_action_label;
  const paymentStatus = status.payment_status || usageQ.data?.payment_status || subscription?.status || "—";

  const billingLoadError = subQ.isError || usageQ.isError || invoicesQ.isError;
  const billingErrorDetail =
    (usageQ.error && billingErrorMessage(usageQ.error)) ||
    (subQ.error && billingErrorMessage(subQ.error)) ||
    (invoicesQ.error && billingErrorMessage(invoicesQ.error)) ||
    "";

  const invoiceRows = (invoicesQ.data || []).map((inv) => ({
    invoiceId: inv.id,
    id: inv.invoice_number || inv.id,
    kind: invoiceKind(inv.description, inv.provider),
    description: inv.description || "—",
    date: inv.issued_at
      ? new Date(inv.issued_at).toLocaleDateString()
      : inv.created_at
        ? new Date(String(inv.created_at)).toLocaleDateString()
        : "—",
    amount: inv.total_gbp || moneyFromPence(inv.total_pence),
    status: invoiceStatusLabel(inv.status),
    rawStatus: String(inv.status || "issued").toLowerCase(),
    payable: Boolean(inv.payable ?? inv.payment_context?.payable),
    paymentContext: inv.payment_context,
    raw: inv,
  }));

  const inv = useTableSort(invoiceRows, "date", "desc");
  const exhausted = Number(commercial.package_remaining_pence || 0) <= 0 && Number(commercial.wallet_balance_pence || 0) <= 0;

  React.useEffect(() => {
    if (!payInvoiceId || invoicesQ.isLoading || !invoicesQ.data?.length) return;
    const match = invoicesQ.data.find((row) => row.id === payInvoiceId);
    if (match && canShowPayAction(String(match.status || "issued").toLowerCase())) {
      setPayInvoice(match);
    }
  }, [payInvoiceId, invoicesQ.isLoading, invoicesQ.data]);

  return (
    <div className="flex w-full flex-col gap-6 pb-12">
      <PageHeader
        eyebrow="Account"
        title="Billing"
        description="Commercial balance, actual usage, and approximate capacity for your organisation."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link to="/account/packages">Packages & pricing</Link>
          </Button>
        }
      />

      {billingLoadError ? (
        <div className="flex items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
          <div>
            <p className="font-medium text-foreground">Billing data could not be loaded</p>
            <p className="text-muted-foreground">{billingErrorDetail}</p>
          </div>
        </div>
      ) : null}

      {!billingLoadError && accessQ.data && accessQ.data.can_launch === false && accessQ.data.launch_block_reason ? (
        <div className="flex items-start gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" />
          <div>
            <p className="font-medium text-foreground">Campaign launches are blocked</p>
            <p className="text-muted-foreground">{accessQ.data.launch_block_reason}</p>
          </div>
        </div>
      ) : null}

      {!billingLoadError && nextActionLabel && (exhausted || status.next_action === "top_up_wallet") ? (
        <div className="flex items-start gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" />
          <div>
            <p className="font-medium text-foreground">{exhausted ? "No remaining package balance" : "Billing notice"}</p>
            <p className="text-muted-foreground">{nextActionLabel}</p>
            {status.next_action === "top_up_wallet" ? (
              <Link to="/account/packages" className="mt-2 inline-block text-primary underline-offset-4 hover:underline">
                Top up wallet to continue
              </Link>
            ) : null}
          </div>
        </div>
      ) : null}

      {!billingLoadError && !subQ.isLoading && !usageQ.isLoading && !plan ? (
        <div className="rounded-lg border border-border bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
          No active plan is linked to this organisation yet. Choose a package on{" "}
          <Link to="/account/packages" className="text-primary underline-offset-4 hover:underline">
            Packages & pricing
          </Link>
          .
        </div>
      ) : null}

      <section>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Billing overview</h2>
        {usageQ.isLoading ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 7 }).map((_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <KpiCard
              label="Wallet balance"
              value={commercial.wallet_balance_display || usageQ.data?.wallet_balance_gbp || moneyFromPence(commercial.wallet_balance_pence)}
              sub="Actual money available"
            />
            <KpiCard
              label="Current plan"
              value={plan?.name || "—"}
              sub={plan ? `${moneyFromPence(plan?.price_gbp_pence ?? (plan as { price_pence?: number })?.price_pence)}/mo` : undefined}
            />
            <KpiCard
              label="Package remaining"
              value={commercial.package_remaining_display || moneyFromPence(commercial.package_remaining_pence)}
              sub={
                commercial.package_used_display
                  ? `${commercial.package_used_display} used of ${commercial.package_included_display || "—"}`
                  : "Commercial entitlement balance"
              }
            />
            <KpiCard label="Payment status" value={String(paymentStatus)} sub={period ? `Period: ${period}` : undefined} />
            <KpiCard
              label="Extra usage risk"
              value={status.overage_risk ? "At risk" : "Normal"}
              sub={overagePending > 0 ? `${moneyFromPence(overagePending)} pending invoice` : estimatedOverage ? `~£${estimatedOverage} estimated` : "No extra usage pending"}
            />
            <KpiCard label="Open invoices" value={String(openInvoices)} sub="Outstanding invoices" />
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Actual usage this period</h2>
        {usageQ.isLoading ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <KpiCard label="WhatsApp usage" value={String(actual.whatsapp_used ?? 0)} sub="Recipients sent this period" />
            <KpiCard label="AI usage" value={String(actual.calls_used ?? 0)} sub="Call minutes this period" />
            <KpiCard label="SMS usage" value={String(actual.sms_used ?? 0)} sub="Messages this period" />
            <KpiCard label="Survey credits" value={String(actual.survey_credits ?? 0)} sub="Promo credits" />
            <KpiCard label="Interview credits" value={String(actual.interview_credits ?? 0)} sub="Promo credits" />
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Approximate capacity left</h2>
        <p className="mb-3 text-xs text-muted-foreground">{estimates.disclaimer || "Approximate capacity only — not used for billing or invoicing."}</p>
        {usageQ.isLoading ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            <KpiCard
              label="Estimated WA surveys left"
              value={String(estimates.estimated_wa_surveys ?? 0)}
              sub={estimates.label || (estimates.source === "wallet" ? "Estimated from wallet" : estimates.source === "package" ? "Estimated from plan" : "No remaining balance")}
            />
            <KpiCard
              label="Estimated AI minutes left"
              value={String(estimates.estimated_ai_minutes ?? 0)}
              sub={estimates.label || (estimates.source === "wallet" ? "Estimated from wallet" : estimates.source === "package" ? "Estimated from plan" : "No remaining balance")}
            />
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Balances</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <Card>
            <CardContent className="flex items-center gap-3 p-4">
              <Wallet className="size-5 text-primary" />
              <div>
                <p className="text-xs text-muted-foreground">Wallet balance</p>
                <p className="text-lg font-semibold tabular-nums">
                  {commercial.wallet_balance_display || usageQ.data?.wallet_balance_gbp || moneyFromPence(commercial.wallet_balance_pence)}
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Wallet activity</CardTitle>
          <CardDescription>Top-ups and launch charges from your pay-as-you-go wallet.</CardDescription>
        </CardHeader>
        <CardContent className="px-0">
          {walletTxQ.isLoading ? (
            <div className="p-6">
              <Skeleton className="h-10 w-full" />
            </div>
          ) : (walletTxQ.data?.transactions || []).length === 0 ? (
            <p className="p-8 text-center text-sm text-muted-foreground">
              No wallet transactions yet. Top up on{" "}
              <Link to="/account/packages" className="text-primary underline-offset-4 hover:underline">
                Packages & pricing
              </Link>
              .
            </p>
          ) : (
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="pl-6">Date</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead>Kind</TableHead>
                    <TableHead className="hidden xl:table-cell">Related</TableHead>
                    <TableHead className="pr-6 text-right">Amount</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(walletTxQ.data?.transactions || []).map((tx) => (
                    <TableRow key={String(tx.id)}>
                      <TableCell className="pl-6 text-xs text-muted-foreground">
                        {tx.created_at ? new Date(String(tx.created_at)).toLocaleString() : "—"}
                      </TableCell>
                      <TableCell className="max-w-[240px] truncate text-xs">{String(tx.description || tx.kind || "—")}</TableCell>
                      <TableCell className="text-xs capitalize">{String(tx.kind || "—").replace(/_/g, " ")}</TableCell>
                      <TableCell className={`pr-6 text-right tabular-nums ${tx.direction === "credit" ? "text-green-700 dark:text-green-400" : ""}`}>
                        {tx.direction === "credit" ? "+" : "−"}
                        {String(tx.amount_display || "")}
                      </TableCell>
                      <TableCell className="hidden pr-6 text-xs text-muted-foreground xl:table-cell">
                        {tx.invoice_id ? `Invoice ${String(tx.invoice_id).slice(0, 8)}` : tx.order_id ? `Order ${String(tx.order_id).slice(0, 8)}` : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Invoices</CardTitle>
          <CardDescription>Subscription charges and extra usage beyond your plan allowance.</CardDescription>
        </CardHeader>
        <CardContent className="px-0">
          {invoicesQ.isLoading ? (
            <div className="p-6">
              <Skeleton className="h-10 w-full" />
            </div>
          ) : inv.sorted.length === 0 ? (
            <p className="p-8 text-center text-sm text-muted-foreground">No invoices yet. Plan renewals and extra usage will appear here.</p>
          ) : (
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <SortHeader label="Invoice" sortKey="id" active={inv.sortKey} dir={inv.sortDir} onToggle={inv.toggleSort} className="pl-6" />
                    <SortHeader label="Type" sortKey="kind" active={inv.sortKey} dir={inv.sortDir} onToggle={inv.toggleSort} />
                    <TableHead>Description</TableHead>
                    <SortHeader label="Date" sortKey="date" active={inv.sortKey} dir={inv.sortDir} onToggle={inv.toggleSort} />
                    <SortHeader label="Amount" sortKey="amount" active={inv.sortKey} dir={inv.sortDir} onToggle={inv.toggleSort} />
                    <SortHeader label="Status" sortKey="status" active={inv.sortKey} dir={inv.sortDir} onToggle={inv.toggleSort} />
                    <TableHead className="pr-6 text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {inv.sorted.map((i) => (
                    <TableRow key={i.invoiceId}>
                      <TableCell className="pl-6 font-mono text-xs">{i.id}</TableCell>
                      <TableCell className="text-xs">{i.kind}</TableCell>
                      <TableCell className="max-w-[220px] truncate text-xs text-muted-foreground">{i.description}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{i.date}</TableCell>
                      <TableCell className="tabular-nums">{i.amount}</TableCell>
                      <TableCell>
                        <StatusBadge tone={badgeToneFromStatus(i.rawStatus)} label={i.status} />
                      </TableCell>
                      <TableCell className="pr-6 text-right">
                        <div className="flex flex-wrap items-center justify-end gap-1">
                          <Button
                            size="sm"
                            variant="outline"
                            className="gap-1"
                            onClick={() =>
                              void openAuthenticatedHtmlInTab(`/billing/invoices/${encodeURIComponent(i.invoiceId)}/html`)
                            }
                          >
                            <Eye className="size-3.5" /> View
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="gap-1"
                            onClick={() =>
                              void downloadAuthenticatedFile(
                                `/billing/invoices/${encodeURIComponent(i.invoiceId)}/pdf`,
                                `invoice-${i.id}.pdf`,
                              )
                            }
                          >
                            <Download className="size-3.5" /> Download
                          </Button>
                          {canShowPayAction(i.rawStatus) ? (
                            <Button size="sm" variant="default" className="gap-1" onClick={() => setPayInvoice(i.raw)}>
                              <CreditCard className="size-3.5" /> Pay
                            </Button>
                          ) : null}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <InvoicePayDialog
        invoice={payInvoice}
        open={Boolean(payInvoice)}
        onOpenChange={(open) => !open && setPayInvoice(null)}
        onPaid={() => {
          void invoicesQ.refetch();
          void usageQ.refetch();
          void walletTxQ.refetch();
        }}
      />
    </div>
  );
}
