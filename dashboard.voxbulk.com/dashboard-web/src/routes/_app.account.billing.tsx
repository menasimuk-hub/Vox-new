import { createFileRoute } from "@tanstack/react-router";
import { CreditCard, Download } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { downloadAuthenticatedFile } from "@/lib/api";
import { badgeToneFromStatus } from "@/lib/mappers/orders";
import { StatusBadge } from "@/components/status-badge";
import { useBillingInvoices, useBillingPlans, useBillingSubscription, useBillingUsage } from "@/lib/queries";
import { useSession } from "@/lib/session";

export const Route = createFileRoute("/_app/account/billing")({
  head: () => ({ meta: [{ title: "Billing — VoxBulk" }] }),
  component: BillingPage,
});

function moneyFromPence(pence?: number) {
  return `£${((Number(pence || 0)) / 100).toFixed(2)}`;
}

function BillingPage() {
  const { session } = useSession();
  const subQ = useBillingSubscription();
  const usageQ = useBillingUsage();
  const plansQ = useBillingPlans();
  const invoicesQ = useBillingInvoices();

  const plan = subQ.data?.plan || session?.subscription?.plan;
  const usage = usageQ.data?.usage as Record<string, { used?: number; limit?: number }> | undefined;
  const minutes = usage?.ai_minutes || usage?.minutes;
  const whatsapp = usage?.whatsapp_messages || usage?.whatsapp;

  const invoiceRows = (invoicesQ.data || []).map((inv) => ({
    invoiceId: inv.id,
    id: inv.invoice_number || inv.id,
    date: inv.issued_at ? new Date(inv.issued_at).toLocaleDateString() : "—",
    amount: inv.total_gbp || moneyFromPence(inv.total_pence),
    status: String(inv.status || "paid").replace(/^\w/, (c) => c.toUpperCase()),
  }));

  const inv = useTableSort(invoiceRows, "date", "desc");
  const currentPlanId = plan?.id;

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader eyebrow="Account" title="Billing" description="Your current plan, usage, and invoices." />

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="md:col-span-2">
          <CardHeader>
            <CardDescription>Current plan</CardDescription>
            <CardTitle className="text-2xl">
              {subQ.isLoading ? "Loading…" : `${plan?.name || "—"} · ${moneyFromPence(plan?.price_pence)}/mo`}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {usageQ.isLoading ? (
              <Skeleton className="h-16 w-full" />
            ) : (
              <>
                {minutes && (
                  <div>
                    <div className="mb-1 flex justify-between text-xs"><span>AI minutes used</span><span className="tabular-nums text-muted-foreground">{minutes.used ?? 0} / {minutes.limit ?? "—"}</span></div>
                    <Progress value={minutes.limit ? ((minutes.used || 0) / minutes.limit) * 100 : 0} className="h-2" />
                  </div>
                )}
                {whatsapp && (
                  <div>
                    <div className="mb-1 flex justify-between text-xs"><span>WhatsApp messages</span><span className="tabular-nums text-muted-foreground">{whatsapp.used ?? 0} / {whatsapp.limit ?? "—"}</span></div>
                    <Progress value={whatsapp.limit ? ((whatsapp.used || 0) / whatsapp.limit) * 100 : 0} className="h-2" />
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Subscription</CardDescription>
            <CardTitle className="text-2xl">{subQ.data?.subscription?.status || "—"}</CardTitle>
          </CardHeader>
          <CardContent><p className="text-xs text-muted-foreground">Manage plans below or contact support to change billing.</p></CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Change plan</CardTitle></CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-3">
          {plansQ.isLoading && <Skeleton className="h-24 w-full md:col-span-3" />}
          {(plansQ.data || []).map((p) => (
            <div key={p.id} className={"rounded-lg border p-3 " + (p.id === currentPlanId ? "border-primary bg-primary/5" : "border-border")}>
              <p className="text-sm font-medium">{p.name}</p>
              <p className="text-xs text-muted-foreground">{moneyFromPence(p.price_pence)}{p.id === currentPlanId ? " · Current plan" : ""}</p>
              <Button size="sm" variant={p.id === currentPlanId ? "outline" : "default"} className="mt-3 w-full" disabled={p.id === currentPlanId}>
                {p.id === currentPlanId ? "Active" : "Contact support"}
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card><CardContent className="px-0">
        {invoicesQ.isLoading ? (
          <div className="p-6"><Skeleton className="h-10 w-full" /></div>
        ) : (
          <Table>
            <TableHeader><TableRow>
              <SortHeader label="Invoice" sortKey="id" active={inv.sortKey} dir={inv.sortDir} onToggle={inv.toggleSort} className="pl-6" />
              <SortHeader label="Date" sortKey="date" active={inv.sortKey} dir={inv.sortDir} onToggle={inv.toggleSort} />
              <SortHeader label="Amount" sortKey="amount" active={inv.sortKey} dir={inv.sortDir} onToggle={inv.toggleSort} />
              <SortHeader label="Status" sortKey="status" active={inv.sortKey} dir={inv.sortDir} onToggle={inv.toggleSort} />
              <TableHead className="pr-6 text-right"></TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {inv.sorted.map((i) => (
                <TableRow key={i.id}>
                  <TableCell className="pl-6 font-mono text-xs">{i.id}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{i.date}</TableCell>
                  <TableCell>{i.amount}</TableCell>
                  <TableCell><StatusBadge tone={badgeToneFromStatus(i.status)} label={i.status} /></TableCell>
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
        )}
      </CardContent></Card>
      void CreditCard;
    </div>
  );
}
