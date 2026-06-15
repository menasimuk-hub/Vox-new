import { createFileRoute } from "@tanstack/react-router";

import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { requireOrgSettingsAccess } from "@/lib/guards/settings-route";
import { useAuditLog } from "@/lib/queries";

export const Route = createFileRoute("/_app/settings/audit")({
  head: () => ({ meta: [{ title: "Audit log — VoxBulk" }] }),
  beforeLoad: () => requireOrgSettingsAccess(),
  component: AuditPage,
});

function formatAction(action: string) {
  return action.replace(/\./g, " · ").replace(/_/g, " ");
}

function AuditPage() {
  const logQ = useAuditLog();

  const rows = (logQ.data || []).map((e) => {
    const eventType = String(e.event_type || e.action || "");
    const isDeletion = eventType.includes("account.deletion") || eventType.includes("deletion");
    return {
      id: e.id,
      who: e.actor_email || "System",
      action: formatAction(e.action),
      detail: e.detail || "—",
      when: e.created_at ? new Date(e.created_at).toLocaleString() : "—",
      sortWhen: e.created_at || "",
      isDeletion,
    };
  });
  const table = useTableSort(rows, "sortWhen", "desc");

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Settings"
        title="Audit log"
        description="Compliance-grade activity log of who did what, and when."
      />
      <Card>
        <CardContent className="px-0">
          {logQ.isLoading ? (
            <div className="p-6"><Skeleton className="h-10 w-full" /></div>
          ) : table.sorted.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">No activity yet. Team invites, opt-outs, logo updates, and settings changes appear here.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <SortHeader label="When" sortKey="when" active={table.sortKey} dir={table.sortDir} onToggle={table.toggleSort} className="pl-6" />
                  <SortHeader label="Who" sortKey="who" active={table.sortKey} dir={table.sortDir} onToggle={table.toggleSort} />
                  <SortHeader label="Action" sortKey="action" active={table.sortKey} dir={table.sortDir} onToggle={table.toggleSort} />
                  <TableHead className="pr-6">Details</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {table.sorted.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="pl-6 text-xs text-muted-foreground whitespace-nowrap">{row.when}</TableCell>
                    <TableCell className="text-sm">{row.who}</TableCell>
                    <TableCell className="text-sm capitalize">
                      {row.isDeletion ? (
                        <span className="inline-flex items-center gap-1.5">
                          <span className="rounded bg-destructive/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-destructive">
                            Deletion
                          </span>
                          {row.action}
                        </span>
                      ) : (
                        row.action
                      )}
                    </TableCell>
                    <TableCell className="pr-6 max-w-md truncate text-xs text-muted-foreground" title={row.detail}>{row.detail}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
