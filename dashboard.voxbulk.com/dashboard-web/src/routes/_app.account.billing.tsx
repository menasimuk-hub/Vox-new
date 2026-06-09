import { createFileRoute, Link } from "@tanstack/react-router";
import { AlertTriangle, Download, FileText, Wallet } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { downloadAuthenticatedFile } from "@/lib/api";
import { badgeToneFromStatus } from "@/lib/mappers/orders";
import { StatusBadge } from "@/components/status-badge";
import { useBillingAccess, useBillingInvoices, useBillingSubscription, useBillingUsage, useWalletTransactions } from "@/lib/queries";
import { useSession } from "@/lib/session";

export const Route = createFileRoute("/_app/account/billing")({
  head: () => ({ meta: [{ title: "Billing — VoxBulk" }] }),
  component: BillingPage,
});

type UsageMeter = {
  key: string;
  label: string;
  used?: number;
  included?: number;
  remaining?: number | null;
  percent?: number;
  unit?: string;
  unlimited?: boolean;
  display_gbp?: string;
};

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

function meterDisplay(m: UsageMeter) {
  if (m.key === "wallet") return m.display_gbp || moneyFromPence(m.remaining ?? m.used);
  if (m.unit === "credits") return String(m.remaining ?? m.included ?? 0);
  if (m.unlimited || (m.included ?? 0) <= 0) return `${m.used ?? 0} used`;
  return `${m.used ?? 0} / ${m.included ?? 0}`;
}

function meterSub(m: UsageMeter) {
  if (m.key === "wallet") return "Pay-as-you-go balance";
  if (m.key === "whatsapp") return "Interview WhatsApp: included · extra survey recipients invoiced at plan rate";
  if (m.unit === "credits") return "Promo credits remaining";
  if (m.unlimited || (m.included ?? 0) <= 0) return "No plan allowance";
  const left = m.remaining ?? Math.max(0, (m.included ?? 0) - (m.used ?? 0));
  return `${left} remaining this period`;
}

function invoiceKind(description?: string | null, provider?: string | null) {
  const text = `${description || ""} ${provider || ""}`.toLowerCase();
  if (text.includes("overage") || text.includes("usage")) return "Extra usage";
  if (text.includes("subscription") || text.includes("plan") || provider === "gocardless") return "Subscription";
  return "Invoice";
}

function billingErrorMessage(err: unknown) {
  if (err && typeof err === "object" && "message" in err) return String((err as { message: unknown }).message);
  return "Could not load billing data. Try refreshing the page.";
}

function BillingPage() {
  const { session } = useSession();
  const subQ = useBillingSubscription();
  const usageQ = useBillingUsage();
  const invoicesQ = useBillingInvoices();
  const accessQ = useBillingAccess();
  const walletTxQ = useWalletTransactions(30);

  const plan = subQ.data?.plan || usageQ.data?.current_plan || session?.subscription?.plan;
  const subscription = subQ.data?.subscription || usageQ.data?.subscription;
  const meters = (usageQ.data?.meters || []) as UsageMeter[];
  const period = fmtPeriod(usageQ.data?.period_start, usageQ.data?.period_end);
  const overagePending = Number(usageQ.data?.overage_pending_pence || 0);
  const estimatedOverage = usageQ.data?.estimated_overage_gbp;
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
    status: String(inv.status || "issued").replace(/^\w/, (c) => c.toUpperCase()),
  }));

  const inv = useTableSort(invoiceRows, "date", "desc");
  const usageMeters = meters.filter((m) => !["wallet", "interview_credits", "survey_credits"].includes(m.key));
  const balanceMeters = meters.filter((m) => ["wallet", "interview_credits", "survey_credits"].includes(m.key));

  return (
    <div className="flex w-full flex-col gap-6 pb-12">
      <PageHeader
        eyebrow="Account"
        title="Billing"
        description="Plan usage, balances, and invoices for your organisation."
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

      {!billingLoadError && !subQ.isLoading && !usageQ.isLoading && !plan ? (
        <div className="rounded-lg border border-border bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
          No active plan is linked to this organisation yet. Choose a package on{" "}
          <Link to="/account/packages" className="text-primary underline-offset-4 hover:underline">
            Packages & pricing
          </Link>
          . ATS and interview usage still appear here once a plan or wallet balance is active.
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="md:col-span-2">
          <CardHeader className="pb-2">
            <CardDescription>Current plan</CardDescription>
            <CardTitle className="text-2xl">
              {subQ.isLoading && usageQ.isLoading
                ? "Loading…"
                : `${plan?.name || "—"} · ${moneyFromPence(plan?.price_gbp_pence ?? (plan as { price_pence?: number })?.price_pence)}/mo`}
            </CardTitle>
            {period ? <p className="text-xs text-muted-foreground">Billing period: {period}</p> : null}
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-3 text-sm">
            <StatusBadge
              tone={subscription?.status === "active" ? "approved-script" : "draft-script"}
              label={String(subscription?.status || "—")}
            />
            <span className="text-muted-foreground">
              Change or downgrade your plan on{" "}
              <Link to="/account/packages" className="text-primary underline-offset-4 hover:underline">
                Packages & pricing
              </Link>
              .
            </span>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Extra usage</CardDescription>
            <CardTitle className="text-2xl">{overagePending > 0 ? moneyFromPence(overagePending) : estimatedOverage ? `~£${estimatedOverage}` : "£0.00"}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">
              {overagePending > 0
                ? "An invoice is being prepared for usage above your plan allowance."
                : "Extra recipients: billed at your plan rate after WA survey allowance is used. AI phone survey: connection + minutes."}
            </p>
          </CardContent>
        </Card>
      </div>

      {overagePending >= 100 ? (
        <div className="flex items-start gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" />
          <div>
            <p className="font-medium text-foreground">Extra usage invoice pending</p>
            <p className="text-muted-foreground">
              You have {moneyFromPence(overagePending)} of uninvoiced overage. A new invoice will appear below once issued.
            </p>
          </div>
        </div>
      ) : null}

      <section>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Plan usage this period</h2>
        {usageQ.isLoading ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-28" />
            ))}
          </div>
        ) : usageMeters.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No usage meters yet for this billing period. If you recently subscribed, refresh in a moment or contact support.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {usageMeters.map((m) => (
              <Card key={m.key}>
                <CardContent className="space-y-3 p-4">
                  <div>
                    <p className="text-xs text-muted-foreground">{m.label}</p>
                    <p className="text-xl font-semibold tabular-nums">{meterDisplay(m)}</p>
                    <p className="text-[11px] text-muted-foreground">{meterSub(m)}</p>
                  </div>
                  {!m.unlimited && (m.included ?? 0) > 0 ? (
                    <Progress value={Math.min(100, m.percent ?? 0)} className="h-2" />
                  ) : null}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Balances & promo credits</h2>
        {usageQ.isLoading ? (
          <div className="grid gap-3 sm:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-3">
            {balanceMeters.map((m) => (
              <Card key={m.key}>
                <CardContent className="flex items-center gap-3 p-4">
                  {m.key === "wallet" ? <Wallet className="size-5 text-primary" /> : <FileText className="size-5 text-primary" />}
                  <div>
                    <p className="text-xs text-muted-foreground">{m.label}</p>
                    <p className="text-lg font-semibold tabular-nums">{meterDisplay(m)}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
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
                  <TableHead className="pr-6 text-right" />
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
                      <StatusBadge tone={badgeToneFromStatus(i.status)} label={i.status} />
                    </TableCell>
                    <TableCell className="pr-6 text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="gap-1"
                        onClick={() => void downloadAuthenticatedFile(`/billing/invoices/${encodeURIComponent(i.invoiceId)}/pdf`, `invoice-${i.id}.pdf`)}
                      >
                        <Download className="size-3.5" /> PDF
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
