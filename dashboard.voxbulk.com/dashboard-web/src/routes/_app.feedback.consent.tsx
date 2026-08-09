import { createFileRoute } from "@tanstack/react-router";
import { Download, ShieldCheck, UserX } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch, downloadAuthenticatedFile } from "@/lib/api";
import { queryKeys, useFeedbackConsentEvents, type FeedbackConsentEventRow } from "@/lib/queries";

export const Route = createFileRoute("/_app/feedback/consent")({
  head: () => ({ meta: [{ title: "Consent — Customer feedback" }] }),
  component: FeedbackConsentPage,
});

function FeedbackConsentPage() {
  const [purpose, setPurpose] = React.useState<"callback_call" | "marketing">("callback_call");
  const consentsQ = useFeedbackConsentEvents({ purpose, consent_given: "true" });
  const qc = useQueryClient();
  const [optingOut, setOptingOut] = React.useState<string | null>(null);
  const items = consentsQ.data || [];

  const onExport = async () => {
    try {
      const qs = new URLSearchParams({ purpose, consent_given: "true" });
      await downloadAuthenticatedFile(
        `/customer-feedback/consent-events/export.csv?${qs.toString()}`,
        `feedback-consent-${purpose}.csv`,
      );
      toast.success("Consent list exported");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    }
  };

  const onOptOut = async (row: FeedbackConsentEventRow) => {
    setOptingOut(row.id);
    try {
      await apiFetch("/customer-feedback/consent-events/opt-out", {
        method: "POST",
        body: JSON.stringify({
          phone_number: row.phone_number,
          session_id: row.session_id,
          location_id: row.location_id,
          purpose: row.purpose,
        }),
      });
      toast.success(`Opted out ${row.phone_number}`);
      await qc.invalidateQueries({ queryKey: queryKeys.feedbackConsentEvents({ purpose, consent_given: "true" }) });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not opt out");
    } finally {
      setOptingOut(null);
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Customer feedback"
        title="Consent"
        description="People who said Yes to a callback or marketing opt-in. STOP on WhatsApp and admin opt-out are recorded here."
        actions={
          <Button type="button" variant="outline" className="gap-1.5" onClick={() => void onExport()}>
            <Download className="size-4" /> Export CSV
          </Button>
        }
      />

      <div className="flex items-center gap-2 rounded-lg border border-primary/20 bg-primary/5 p-3 text-sm">
        <ShieldCheck className="size-4 text-primary" />
        <span>
          Callback consent is for AI follow-up calls only. Marketing consent is separate. Both are append-only audit
          events.
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant={purpose === "callback_call" ? "default" : "outline"}
          onClick={() => setPurpose("callback_call")}
        >
          Callback Yes
        </Button>
        <Button
          size="sm"
          variant={purpose === "marketing" ? "default" : "outline"}
          onClick={() => setPurpose("marketing")}
        >
          Marketing Yes
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {purpose === "callback_call" ? "Callback consent" : "Marketing consent"}
          </CardTitle>
          <CardDescription>
            Showing latest Yes answers. Opt out removes them from active use and records a revoke event.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {consentsQ.isLoading ? (
            <div className="space-y-2 p-4">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : consentsQ.isError ? (
            <p className="p-6 text-sm text-destructive">Could not load consent events.</p>
          ) : items.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">No Yes consents yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="border-b bg-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">Mobile</th>
                    <th className="px-4 py-3 font-medium">Location</th>
                    <th className="px-4 py-3 font-medium">Method</th>
                    <th className="px-4 py-3 font-medium">When</th>
                    <th className="px-4 py-3 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {items.map((row) => (
                    <tr key={row.id}>
                      <td className="px-4 py-3 font-medium tabular-nums">{row.phone_number}</td>
                      <td className="px-4 py-3 text-muted-foreground">{row.location_name || "—"}</td>
                      <td className="px-4 py-3">
                        <Badge variant="secondary">{row.method}</Badge>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {row.timestamp ? new Date(row.timestamp).toLocaleString() : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <Button
                          size="sm"
                          variant="ghost"
                          className="gap-1.5 text-destructive hover:text-destructive"
                          disabled={optingOut === row.id}
                          onClick={() => void onOptOut(row)}
                        >
                          <UserX className="size-3.5" />
                          {optingOut === row.id ? "Opting out…" : "Opt out"}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
