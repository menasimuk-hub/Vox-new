import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";

type Lead = {
  id: string;
  name?: string | null;
  company?: string | null;
  representative_name?: string | null;
  lead_score?: string | null;
  interest?: string | null;
  ai_summary?: string | null;
  suggested_follow_up?: string | null;
  follow_up_status?: string;
  created_at?: string | null;
};

export const Route = createFileRoute("/_app/smart-card/leads")({
  component: SmartCardLeadsPage,
});

function SmartCardLeadsPage() {
  const qc = useQueryClient();
  const leadsQ = useQuery({
    queryKey: ["smart-card", "leads"],
    queryFn: () => apiFetch<{ ok: boolean; items: Lead[] }>("/smart-card/results/leads"),
  });

  const markMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      apiFetch(`/smart-card/results/leads/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ follow_up_status: status }),
      }),
    onSuccess: async () => {
      toast.success("Lead updated");
      await qc.invalidateQueries({ queryKey: ["smart-card", "leads"] });
      await qc.invalidateQueries({ queryKey: ["smart-card", "summary"] });
    },
  });

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Smart Card QR" title="Leads" description="Owner/manager see all; representatives see only their own." />
      <div className="space-y-3">
        {(leadsQ.data?.items || []).map((lead) => (
          <Card key={lead.id}>
            <CardContent className="space-y-2 p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-medium">
                    {lead.name || "Unknown"} · {lead.company || "—"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {lead.representative_name} · {lead.lead_score || "unscored"} · {lead.follow_up_status}
                  </p>
                </div>
                {lead.follow_up_status === "open" ? (
                  <Button size="sm" variant="secondary" onClick={() => markMut.mutate({ id: lead.id, status: "done" })}>
                    Mark done
                  </Button>
                ) : null}
              </div>
              {lead.ai_summary ? <p className="text-sm text-muted-foreground">{lead.ai_summary}</p> : null}
              {lead.suggested_follow_up ? (
                <p className="rounded-md border bg-muted/40 p-2 text-sm">{lead.suggested_follow_up}</p>
              ) : null}
            </CardContent>
          </Card>
        ))}
        {!leadsQ.isLoading && !(leadsQ.data?.items || []).length ? (
          <p className="text-sm text-muted-foreground">No leads yet.</p>
        ) : null}
      </div>
    </div>
  );
}
