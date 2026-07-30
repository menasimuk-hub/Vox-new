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

type ChangeRequest = {
  id: string;
  status: string;
  message?: string | null;
  created_at?: string | null;
  admin_note?: string | null;
  target_type?: string | null;
};

export const Route = createFileRoute("/_app/smart-card/change-requests")({
  component: SmartCardChangeRequestsPage,
});

function SmartCardChangeRequestsPage() {
  const { session } = useSession();
  const canManage = canManageTeam(normalizeOrgRole(session?.profile?.role));
  const qc = useQueryClient();
  const [message, setMessage] = React.useState("");

  const listQ = useQuery({
    queryKey: ["smart-card", "change-requests"],
    queryFn: () => apiFetch<{ ok: boolean; items: ChangeRequest[] }>("/smart-card/change-requests"),
  });

  const createMut = useMutation({
    mutationFn: () =>
      apiFetch("/smart-card/change-requests", {
        method: "POST",
        body: JSON.stringify({ message, target_type: "general" }),
      }),
    onSuccess: async () => {
      toast.success("Request submitted");
      setMessage("");
      await qc.invalidateQueries({ queryKey: ["smart-card", "change-requests"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const resolveMut = useMutation({
    mutationFn: ({ id, status, note }: { id: string; status: string; note?: string }) =>
      apiFetch(`/smart-card/change-requests/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status, admin_note: note || "" }),
      }),
    onSuccess: async () => {
      toast.success("Updated");
      await qc.invalidateQueries({ queryKey: ["smart-card", "change-requests"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Change requests"
        description="Representatives request profile or catalogue updates; owners/managers approve or reject."
      />

      {!canManage ? (
        <Card>
          <CardContent className="grid gap-3 p-4">
            <div className="space-y-1.5">
              <Label>What needs changing?</Label>
              <Textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={4} />
            </div>
            <Button disabled={!message.trim() || createMut.isPending} onClick={() => createMut.mutate()}>
              Submit request
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <div className="space-y-3">
        {(listQ.data?.items || []).map((item) => (
          <Card key={item.id}>
            <CardContent className="space-y-2 p-4 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium capitalize">{item.target_type || "general"}</p>
                <span className="text-xs capitalize text-muted-foreground">{item.status}</span>
              </div>
              <p className="text-muted-foreground">{item.message}</p>
              <p className="text-xs text-muted-foreground">
                {item.created_at ? new Date(item.created_at).toLocaleString() : "—"}
              </p>
              {item.admin_note ? <p className="text-xs">Note: {item.admin_note}</p> : null}
              {canManage && item.status === "pending" ? (
                <div className="flex flex-wrap gap-2 pt-1">
                  <Button
                    size="sm"
                    disabled={resolveMut.isPending}
                    onClick={() => resolveMut.mutate({ id: item.id, status: "done" })}
                  >
                    Done
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={resolveMut.isPending}
                    onClick={() => resolveMut.mutate({ id: item.id, status: "rejected", note: "Declined" })}
                  >
                    Reject
                  </Button>
                </div>
              ) : null}
            </CardContent>
          </Card>
        ))}
      </div>
      {!listQ.isLoading && !(listQ.data?.items || []).length ? (
        <p className="text-sm text-muted-foreground">No change requests yet.</p>
      ) : null}
    </div>
  );
}
