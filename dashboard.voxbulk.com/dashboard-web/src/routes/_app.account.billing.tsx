import { createFileRoute, Link } from "@tanstack/react-router";
import { AlertTriangle, CreditCard, Download, Eye, Loader2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { InvoicePayDialog } from "@/components/invoice-pay-dialog";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { downloadAuthenticatedFile, openAuthenticatedHtmlInTab } from "@/lib/api";
import { startGoCardlessMandateUpdate, readBillingReturnParams } from "@/lib/billing/gocardless";
import { invoiceStatusLabel } from "@/lib/billing/order-pay-labels";
import { badgeToneFromStatus } from "@/lib/mappers/orders";
import { StatusBadge } from "@/components/status-badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { useBillingAccess, useBillingInvoices, useBillingRequests, useBillingSubscription, useBillingSubscriptionCancellation, useBillingUsage, useSetBillingOverage, useWalletTransactions } from "@/lib/queries";
import { SubscriptionCancellationBar } from "@/components/billing/subscription-cancellation-card";
import { REFUND_TIMING_BANK, REFUND_TIMING_PROCESSING } from "@/lib/billing/refund-timing";
import type { BillingMonitorPayload, Invoice } from "@/lib/types/api";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/account/billing")({
  head: () => ({ meta: [{ title: "Billing — VoxBulk" }] }),
  validateSearch: (search: Record<string, unknown>) => ({
    pay: typeof search.pay === "string" ? search.pay : undefined,
  }),
  component: BillingPage,
});

const PAGE_SIZE = 10;

const CURRENCY_SYMBOLS: Record<string, string> = {
  GBP: "£",
  EUR: "€",
  USD: "$",
  CAD: "CA$",
  AUD: "A$",
};

function currencySymbol(code?: string | null) {
  return CURRENCY_SYMBOLS[String(code || "GBP").toUpperCase()] || "$";
}

function moneyFromPence(pence?: number, currency?: string | null, display?: string | null) {
  if (display) return display;
  const sym = currencySymbol(currency);
  return `${sym}${((Number(pence || 0)) / 100).toFixed(2)}`;
}

function invoiceKind(description?: string | null, provider?: string | null) {
  const text = `${description || ""} ${provider || ""}`.toLowerCase();
  if (text.includes("overage") || text.includes("usage")) return "Extra usage";
  if (text.includes("subscription") || text.includes("plan") || provider === "gocardless") return "Subscription";
  return "Invoice";
}

function walletRowKind(kind?: string | null, direction?: string | null) {
  const k = String(kind || "").toLowerCase();
  if (k === "subscription_cancellation_credit" || k === "refund_adjustment_credit") return "Wallet credit";
  if (k === "refund_adjustment_reversal") return "Credit reversal";
  if (k === "topup" || direction === "credit") return "Top-up";
  return "Receipt";
}

function ledgerKindPriority(type: string, payable = false) {
  if (payable) return -1;
  if (type === "Top-up") return 0;
  if (type === "Receipt") return 1;
  return 2;
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

function usageMeterTone(pct: number) {
  if (pct >= 90) {
    return {
      text: "text-destructive",
      bar: "[&>div]:bg-destructive bg-destructive/20",
    };
  }
  if (pct >= 75) {
    return {
      text: "text-amber-600 dark:text-amber-500",
      bar: "[&>div]:bg-amber-500 bg-amber-500/20",
    };
  }
  return {
    text: "text-emerald-600 dark:text-emerald-500",
    bar: "[&>div]:bg-emerald-600 bg-emerald-600/20",
  };
}

function UsageMeterBar({
  label,
  used,
  included,
}: {
  label: string;
  used: number;
  included: number;
}) {
  const pct = included > 0 ? Math.min(100, Math.round((used / included) * 100)) : 0;
  const tone = usageMeterTone(pct);
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className={cn("tabular-nums font-semibold", tone.text)}>{pct}%</span>
      </div>
      <Progress value={pct} className={cn("h-2", tone.bar)} />
    </div>
  );
}

function BillingPage() {
  const { pay: payInvoiceId } = Route.useSearch();
  const subQ = useBillingSubscription();
  const cancelQ = useBillingSubscriptionCancellation();
  const requestsQ = useBillingRequests();
  const usageQ = useBillingUsage();
  const invoicesQ = useBillingInvoices();
  const accessQ = useBillingAccess();
  const overageM = useSetBillingOverage();
  const walletTxQ = useWalletTransactions(100);
  const allowOverage = accessQ.data?.allow_overage !== false;
  const [payInvoice, setPayInvoice] = React.useState<Invoice | null>(null);
  const [ledgerPage, setLedgerPage] = React.useState(1);
  const [billingTab, setBillingTab] = React.useState<"transactions" | "requests">("transactions");
  const [mandateBusy, setMandateBusy] = React.useState(false);

  const billingRequests = (requestsQ.data?.items || []) as Array<Record<string, unknown>>;
  const pendingRequestsCount = billingRequests.filter((r) => String(r.status || "").toLowerCase() === "pending").length;

  const plan = subQ.data?.plan || usageQ.data?.current_plan;
  const monitor = (usageQ.data?.billing_monitor || {}) as BillingMonitorPayload;
  const billingCurrency = String(monitor.currency || usageQ.data?.billing_currency || "GBP");
  const commercial = monitor.commercial || {};
  const estimates = monitor.capacity_estimates || {};
  const status = monitor.status || {};
  const nextInvoice = status.next_invoice || {};
  const sharedPool = Boolean(monitor.shared_package_pool);
  const meters = usageQ.data?.meters || [];

  const callsMeter = meters.find((m) => m.key === "calls");
  const waMeter = meters.find((m) => m.key === "whatsapp");
  const packageMeter = meters.find((m) => m.key === "package");

  const overagePending = Number(status.overage_pending_pence ?? usageQ.data?.overage_pending_pence ?? 0);
  const openInvoices = Number(status.open_invoices_count ?? usageQ.data?.open_invoices_count ?? 0);
  const nextActionLabel = status.next_action_label || usageQ.data?.next_action_label;
  const exhausted = Number(commercial.package_remaining_pence || 0) <= 0 && Number(commercial.wallet_balance_pence || 0) <= 0;

  const billingLoadError = subQ.isError || usageQ.isError || invoicesQ.isError;
  const billingErrorDetail =
    (usageQ.error && billingErrorMessage(usageQ.error)) ||
    (subQ.error && billingErrorMessage(subQ.error)) ||
    (invoicesQ.error && billingErrorMessage(invoicesQ.error)) ||
    "";

  const invoiceRows = (invoicesQ.data || []).map((inv) => {
    const dateRaw = inv.issued_at || inv.created_at;
    const dateObj = dateRaw ? new Date(String(dateRaw)) : null;
    return {
      ledgerId: `inv-${inv.id}`,
      invoiceId: inv.id,
      id: inv.invoice_number || inv.id,
      kind: invoiceKind(inv.description, inv.provider),
      kindPriority: ledgerKindPriority(
        invoiceKind(inv.description, inv.provider),
        Boolean(inv.payable ?? inv.payment_context?.payable ?? canShowPayAction(String(inv.status || "issued").toLowerCase())),
      ),
      description: inv.description || "—",
      date: dateObj ? dateObj.toLocaleDateString() : "—",
      dateSort: dateObj ? dateObj.getTime() : 0,
      amount: inv.total_gbp || moneyFromPence(inv.total_pence, inv.currency || billingCurrency),
      status: invoiceStatusLabel(inv.status),
      rawStatus: String(inv.status || "issued").toLowerCase(),
      payable: Boolean(inv.payable ?? inv.payment_context?.payable ?? canShowPayAction(String(inv.status || "issued").toLowerCase())),
      paymentContext: inv.payment_context,
      raw: inv,
      isInvoice: true as const,
    };
  });

  const walletRows = (walletTxQ.data?.transactions || []).map((tx) => {
    const dateRaw = tx.created_at;
    const dateObj = dateRaw ? new Date(String(dateRaw)) : null;
    const kind = walletRowKind(String(tx.kind || ""), String(tx.direction || ""));
    const signed =
      tx.direction === "credit"
        ? `+${String(tx.amount_display || "")}`
        : `−${String(tx.amount_display || "")}`;
    return {
      ledgerId: `tx-${String(tx.id)}`,
      invoiceId: "",
      id: String(tx.id).slice(0, 8),
      kind,
      kindPriority: ledgerKindPriority(kind),
      description: String(tx.description || tx.kind || "—"),
      date: dateObj ? dateObj.toLocaleString() : "—",
      dateSort: dateObj ? dateObj.getTime() : 0,
      amount: signed,
      status: String(tx.status || "—"),
      rawStatus: "",
      payable: false,
      paymentContext: undefined,
      raw: undefined,
      isInvoice: false as const,
    };
  });

  const defaultLedger = React.useMemo(() => {
    return [...walletRows, ...invoiceRows].sort((a, b) => {
      if (a.kindPriority !== b.kindPriority) return a.kindPriority - b.kindPriority;
      return b.dateSort - a.dateSort;
    });
  }, [walletRows, invoiceRows]);

  const ledger = useTableSort(defaultLedger, "dateSort", "desc");
  const sortedLedger =
    ledger.sortKey === "dateSort" && ledger.sortDir === "desc"
      ? defaultLedger
      : ledger.sorted;
  const totalLedgerPages = Math.max(1, Math.ceil(sortedLedger.length / PAGE_SIZE));
  const ledgerPageRows = sortedLedger.slice((ledgerPage - 1) * PAGE_SIZE, ledgerPage * PAGE_SIZE);

  React.useEffect(() => {
    setLedgerPage(1);
  }, [ledger.sortKey, ledger.sortDir, defaultLedger.length]);

  React.useEffect(() => {
    if (!payInvoiceId || invoicesQ.isLoading || !invoicesQ.data?.length) return;
    const match = invoicesQ.data.find((row) => row.id === payInvoiceId);
    if (match && canShowPayAction(String(match.status || "issued").toLowerCase())) {
      setPayInvoice(match);
    }
  }, [payInvoiceId, invoicesQ.isLoading, invoicesQ.data]);

  const onUpdateMandate = async () => {
    setMandateBusy(true);
    try {
      await startGoCardlessMandateUpdate();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not start Direct Debit update");
      setMandateBusy(false);
    }
  };

  React.useEffect(() => {
    const resetMandateBusy = () => {
      const params = readBillingReturnParams();
      if (params.billing === "mandate_success" || params.billing === "mandate_cancelled") {
        setMandateBusy(false);
        return;
      }
      setMandateBusy(false);
    };
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) resetMandateBusy();
    };
    resetMandateBusy();
    window.addEventListener("pageshow", onPageShow);
    return () => window.removeEventListener("pageshow", onPageShow);
  }, []);

  const outstandingInvoices = invoiceRows.filter((row) => row.payable);
  const planPrice = plan
    ? moneyFromPence(
        plan?.price_gbp_pence ?? (plan as { price_pence?: number; monthly_price_minor?: number })?.price_pence
          ?? (plan as { monthly_price_minor?: number })?.monthly_price_minor,
        billingCurrency,
        (plan as { price_display?: string })?.price_display,
      )
    : "—";
  const cancelStatus = String(cancelQ.data?.status || "none").toLowerCase();
  const cancellationScheduled = cancelStatus === "scheduled" || cancelStatus === "requested";
  const subscriptionCancelled = cancelStatus === "cancelled" || cancelQ.data?.effective_subscription_status === "cancelled";

  return (
    <div className="flex w-full flex-col gap-6 pb-12">
      <PageHeader
        eyebrow="Account"
        title="Billing"
        description="Commercial balance, usage, and invoices for your organisation."
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
          <div className="grid gap-3 lg:grid-cols-2">
            <Skeleton className="h-44" />
            <Skeleton className="h-44" />
          </div>
        ) : (
          <div className="grid gap-3 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader className="pb-2">
                <CardDescription>Current plan</CardDescription>
                <CardTitle className="text-2xl">
                  {plan?.name || "—"}
                  {plan ? ` · ${planPrice}/mo` : ""}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {sharedPool && packageMeter ? (
                  <UsageMeterBar
                    label="Package usage"
                    used={Number(packageMeter.used || 0)}
                    included={Number(packageMeter.included || 0)}
                  />
                ) : (
                  <>
                    <UsageMeterBar
                      label="AI minutes used"
                      used={Number(callsMeter?.used ?? 0)}
                      included={Number(callsMeter?.included ?? 0)}
                    />
                    <UsageMeterBar
                      label="WhatsApp messages"
                      used={Number(waMeter?.used ?? 0)}
                      included={Number(waMeter?.included ?? 0)}
                    />
                  </>
                )}
                {!cancellationScheduled && !subscriptionCancelled ? (
                  <Button asChild size="sm">
                    <Link to="/account/packages">Change plan</Link>
                  </Button>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    Plan changes are unavailable while cancellation is scheduled or active.
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Next invoice</CardDescription>
                <CardTitle className="text-2xl tabular-nums">
                  {String(nextInvoice.amount_display || "—")}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  Charged on {String(nextInvoice.charge_date_display || "—")}
                </p>
                <div className="space-y-1 text-sm">
                  <p className="text-muted-foreground">
                    Payment method:{" "}
                    {nextInvoice.payment_method_label && nextInvoice.payment_method_label !== "—"
                      ? nextInvoice.payment_method_label
                      : "Not set up"}
                  </p>
                  {nextInvoice.can_update_mandate ? (
                    <Button
                      type="button"
                      variant="link"
                      className="h-auto p-0 text-primary"
                      disabled={mandateBusy}
                      onClick={() => void onUpdateMandate()}
                    >
                      {mandateBusy ? (
                        <>
                          <Loader2 className="mr-1 inline size-3.5 animate-spin" /> Redirecting…
                        </>
                      ) : (
                        "Update Direct Debit"
                      )}
                    </Button>
                  ) : (
                    <Link to="/account/packages" className="text-primary underline-offset-4 hover:underline">
                      Set up payment method
                    </Link>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {!usageQ.isLoading ? (
          <div className="mt-3 flex items-center justify-between gap-4 rounded-lg border border-border bg-muted/20 px-4 py-3">
            <div>
              <p className="text-sm font-medium">Allow extra usage billing</p>
              <p className="text-xs text-muted-foreground">
                When disabled, usage stops at plan limits instead of generating overage charges.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                id="allow-overage"
                checked={allowOverage}
                disabled={overageM.isPending || accessQ.isLoading}
                onCheckedChange={(checked) => {
                  overageM.mutate(checked, {
                    onSuccess: () => toast.success(checked ? "Extra usage billing enabled" : "Extra usage billing disabled"),
                    onError: (e) => toast.error(e instanceof Error ? e.message : "Could not update overage setting"),
                  });
                }}
              />
              <Label htmlFor="allow-overage" className="text-xs text-muted-foreground">
                {allowOverage ? "On" : "Off"}
              </Label>
            </div>
          </div>
        ) : null}

        {!usageQ.isLoading ? (
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <KpiCard
              label="Extra usage"
              value={
                overagePending > 0
                  ? moneyFromPence(overagePending, billingCurrency)
                  : status.overage_risk
                    ? "At risk"
                    : "Normal"
              }
              sub={overagePending > 0 ? "Pending invoice" : "No extra usage pending"}
            />
            <KpiCard label="Open invoices" value={String(openInvoices)} sub="Outstanding invoices" />
            <KpiCard
              label="Wallet balance"
              value={commercial.wallet_balance_display || usageQ.data?.wallet_balance_gbp || moneyFromPence(commercial.wallet_balance_pence, billingCurrency)}
              sub="Actual money available"
            />
          </div>
        ) : null}
      </section>

      <section>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Approximate capacity left</h2>
        <p className="mb-3 text-xs text-muted-foreground">
          {estimates.disclaimer || "Approximate capacity only — not used for billing or invoicing."}
        </p>
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
              sub={estimates.label || "Estimated from plan or wallet"}
            />
            <KpiCard
              label="Estimated AI minutes left"
              value={String(estimates.estimated_ai_minutes ?? 0)}
              sub={estimates.label || "Estimated from plan or wallet"}
            />
          </div>
        )}
      </section>

      {plan ? <SubscriptionCancellationBar planName={plan?.name} /> : null}

      {outstandingInvoices.length > 0 ? (
        <Card className="border-amber-500/40 bg-amber-500/5">
          <CardHeader className="pb-2">
            <CardTitle>Outstanding invoices</CardTitle>
            <CardDescription>Invoices waiting for payment — pay now to avoid service interruption.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {outstandingInvoices.map((row) => (
              <div key={row.ledgerId} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-background px-4 py-3">
                <div>
                  <p className="font-mono text-sm font-medium">{row.id}</p>
                  <p className="text-xs text-muted-foreground">{row.description}</p>
                  <p className="text-xs text-muted-foreground">{row.date} · {row.status}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-lg font-semibold tabular-nums">{row.amount}</span>
                  {row.raw ? (
                    <Button size="sm" onClick={() => setPayInvoice(row.raw!)}>
                      <CreditCard className="mr-1 size-3.5" /> Pay now
                    </Button>
                  ) : null}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader className="space-y-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardTitle>Invoices & payments</CardTitle>
              <CardDescription>Top-ups, receipts, subscription charges, cancellation requests, and extra usage.</CardDescription>
            </div>
            <div className="flex gap-1 rounded-lg border border-border p-1">
              <Button
                size="sm"
                variant={billingTab === "transactions" ? "secondary" : "ghost"}
                onClick={() => setBillingTab("transactions")}
              >
                Transactions
              </Button>
              <Button
                size="sm"
                variant={billingTab === "requests" ? "secondary" : "ghost"}
                onClick={() => setBillingTab("requests")}
                className="gap-1.5"
              >
                Requests
                {pendingRequestsCount > 0 ? (
                  <span className="rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground">
                    {pendingRequestsCount}
                  </span>
                ) : null}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="px-0">
          {billingTab === "requests" ? (
            requestsQ.isLoading ? (
              <div className="p-6">
                <Skeleton className="h-10 w-full" />
              </div>
            ) : billingRequests.length === 0 ? (
              <p className="p-8 text-center text-sm text-muted-foreground">
                No cancellation or refund requests yet.
              </p>
            ) : (
              <div className="table-scroll">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="pl-6">Date</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Refund preference</TableHead>
                      <TableHead className="pr-6">Details</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {billingRequests.map((req) => (
                      <TableRow key={`${req.type}-${req.id}`}>
                        <TableCell className="pl-6 text-xs text-muted-foreground">
                          {req.requested_at ? new Date(String(req.requested_at)).toLocaleDateString() : "—"}
                        </TableCell>
                        <TableCell className="text-xs capitalize">{String(req.type || "").replace("_", " ")}</TableCell>
                        <TableCell>
                          <StatusBadge
                            tone={req.status === "approved" ? "approved-script" : req.status === "pending" ? "scheduled" : "draft-script"}
                            label={String(req.status || "pending")}
                          />
                        </TableCell>
                        <TableCell className="text-xs">{String(req.requested_refund_type || "—").replace(/_/g, " ")}</TableCell>
                        <TableCell className="max-w-[280px] pr-6 text-xs text-muted-foreground">
                          {req.admin_notes ? String(req.admin_notes) : null}
                          {String(req.status || "").toLowerCase() === "pending" &&
                          String(req.requested_refund_type || "") !== "none" ? (
                            <p className="mt-1">{REFUND_TIMING_PROCESSING} {REFUND_TIMING_BANK}</p>
                          ) : null}
                          {req.support_ticket_id ? (
                            <Link
                              to="/account/support/tickets"
                              className="mt-1 inline-block text-primary underline-offset-4 hover:underline"
                            >
                              View support ticket
                            </Link>
                          ) : null}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )
          ) : invoicesQ.isLoading || walletTxQ.isLoading ? (
            <div className="p-6">
              <Skeleton className="h-10 w-full" />
            </div>
          ) : sortedLedger.length === 0 ? (
            <p className="p-8 text-center text-sm text-muted-foreground">
              No billing activity yet. Plan renewals, top-ups, and extra usage will appear here.
            </p>
          ) : (
            <>
              <div className="table-scroll">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <SortHeader label="Reference" sortKey="id" active={ledger.sortKey} dir={ledger.sortDir} onToggle={ledger.toggleSort} className="pl-6" />
                      <SortHeader label="Type" sortKey="kind" active={ledger.sortKey} dir={ledger.sortDir} onToggle={ledger.toggleSort} />
                      <TableHead>Description</TableHead>
                      <SortHeader label="Date" sortKey="dateSort" active={ledger.sortKey} dir={ledger.sortDir} onToggle={ledger.toggleSort} />
                      <SortHeader label="Amount" sortKey="amount" active={ledger.sortKey} dir={ledger.sortDir} onToggle={ledger.toggleSort} />
                      <SortHeader label="Status" sortKey="status" active={ledger.sortKey} dir={ledger.sortDir} onToggle={ledger.toggleSort} />
                      <TableHead className="pr-6 text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {ledgerPageRows.map((row) => (
                      <TableRow key={row.ledgerId}>
                        <TableCell className="pl-6 font-mono text-xs">{row.id}</TableCell>
                        <TableCell className="text-xs">{row.kind}</TableCell>
                        <TableCell className="max-w-[220px] truncate text-xs text-muted-foreground">{row.description}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{row.date}</TableCell>
                        <TableCell className="tabular-nums">{row.amount}</TableCell>
                        <TableCell>
                          {row.isInvoice ? (
                            <StatusBadge tone={badgeToneFromStatus(row.rawStatus)} label={row.status} />
                          ) : (
                            <span className="text-xs capitalize text-muted-foreground">{row.status}</span>
                          )}
                        </TableCell>
                        <TableCell className="pr-6 text-right">
                          {row.isInvoice && row.raw ? (
                            <div className="flex flex-wrap items-center justify-end gap-1">
                              <Button
                                size="sm"
                                variant="outline"
                                className="gap-1"
                                onClick={() =>
                                  void openAuthenticatedHtmlInTab(`/billing/invoices/${encodeURIComponent(row.invoiceId)}/html`)
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
                                    `/billing/invoices/${encodeURIComponent(row.invoiceId)}/pdf`,
                                    `invoice-${row.id}.pdf`,
                                  )
                                }
                              >
                                <Download className="size-3.5" /> Download
                              </Button>
                              {row.payable ? (
                                <Button size="sm" variant="default" className="gap-1" onClick={() => setPayInvoice(row.raw!)}>
                                  <CreditCard className="size-3.5" /> Pay
                                </Button>
                              ) : null}
                            </div>
                          ) : null}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              {sortedLedger.length > PAGE_SIZE ? (
                <div className="flex items-center justify-between border-t border-border px-6 py-3 text-sm">
                  <span className="text-muted-foreground">
                    Page {ledgerPage} of {totalLedgerPages} · {sortedLedger.length} records
                  </span>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" disabled={ledgerPage <= 1} onClick={() => setLedgerPage((p) => p - 1)}>
                      Previous
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={ledgerPage >= totalLedgerPages}
                      onClick={() => setLedgerPage((p) => p + 1)}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              ) : null}
            </>
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
