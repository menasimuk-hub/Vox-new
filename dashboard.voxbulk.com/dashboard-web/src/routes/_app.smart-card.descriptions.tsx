import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { canManageTeam, normalizeOrgRole } from "@/lib/org-roles";
import { useSession } from "@/lib/session";

type Company = {
  description?: string | null;
  products_summary?: string | null;
  pricing_notes?: string | null;
};

export const Route = createFileRoute("/_app/smart-card/descriptions")({
  component: SmartCardDescriptionsPage,
});

function SmartCardDescriptionsPage() {
  const { session } = useSession();
  const canEdit = canManageTeam(normalizeOrgRole(session?.profile?.role));
  const qc = useQueryClient();
  const companyQ = useQuery({
    queryKey: ["smart-card", "company"],
    queryFn: () => apiFetch<{ ok: boolean; company: Company }>("/smart-card/company"),
  });
  const [form, setForm] = React.useState<Company | null>(null);

  React.useEffect(() => {
    if (companyQ.data?.company) {
      setForm({
        description: companyQ.data.company.description,
        products_summary: companyQ.data.company.products_summary,
        pricing_notes: companyQ.data.company.pricing_notes,
      });
    }
  }, [companyQ.data]);

  const saveMut = useMutation({
    mutationFn: (body: Company) =>
      apiFetch("/smart-card/company", { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: async () => {
      toast.success("Descriptions saved");
      await qc.invalidateQueries({ queryKey: ["smart-card", "company"] });
    },
    onError: (e: Error) => toast.error(e.message || "Save failed"),
  });

  if (!form) return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Descriptions"
        description="Company story, products overview, and pricing notes shown during visitor sessions."
        actions={
          canEdit ? (
            <Button disabled={saveMut.isPending} onClick={() => saveMut.mutate(form)}>
              Save
            </Button>
          ) : null
        }
      />
      <Card>
        <CardContent className="grid gap-4 p-4">
          <div className="space-y-1.5">
            <Label>Company description</Label>
            <Textarea
              disabled={!canEdit}
              rows={3}
              maxLength={150}
              value={form.description || ""}
              onChange={(e) => setForm({ ...form, description: e.target.value.slice(0, 150) })}
            />
            <p className="text-[11px] text-muted-foreground">{(form.description || "").length}/150 · max 3 lines</p>
          </div>
          <div className="space-y-1.5">
            <Label>Products summary</Label>
            <Textarea
              disabled={!canEdit}
              rows={4}
              value={form.products_summary || ""}
              onChange={(e) => setForm({ ...form, products_summary: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Pricing notes</Label>
            <Textarea
              disabled={!canEdit}
              rows={3}
              value={form.pricing_notes || ""}
              onChange={(e) => setForm({ ...form, pricing_notes: e.target.value })}
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
