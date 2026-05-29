import { createFileRoute } from "@tanstack/react-router";
import * as React from "react";
import { Phone, Calendar } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { useRecoveryJobs } from "@/lib/queries";
import type { BadgeTone } from "@/components/status-badge";

export const Route = createFileRoute("/_app/recovery/")({
  head: () => ({ meta: [{ title: "Recovery queue — VoxBulk" }] }),
  component: RecoveryQueue,
});

function formatTime(value: unknown) {
  if (!value) return "—";
  try {
    const d = new Date(String(value));
    return d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch {
    return String(value);
  }
}

function stateTone(state: string): BadgeTone {
  const s = state.toLowerCase();
  if (s.includes("rebook") || s.includes("complete") || s.includes("success")) return "completed";
  if (s.includes("call") || s.includes("running") || s.includes("queued")) return "live";
  if (s.includes("no_answer") || s.includes("no-answer")) return "paused";
  if (s.includes("fail") || s.includes("error")) return "payment-failed";
  if (s.includes("wa") || s.includes("whatsapp")) return "scheduled";
  return "quoted";
}

function RecoveryQueue() {
  const jobsQ = useRecoveryJobs();
  const rows = React.useMemo(
    () =>
      (jobsQ.data || []).map((j) => ({
        id: String(j.job_id || j.id || Math.random()),
        time: formatTime(j.created_at || j.appointment_scheduled_start),
        patient: String(j.patient_name || "Patient"),
        phone: String(j.provider_ref || "—"),
        tone: stateTone(String(j.state || "queued")),
        status: String(j.state || "queued").replace(/_/g, " "),
      })),
    [jobsQ.data],
  );
  const { sorted, sortKey, sortDir, toggleSort } = useTableSort(rows, "time", "asc");

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Recovery"
        title="Recovery queue"
        description="Patients flagged for missed-appointment outreach."
        actions={<Button className="gap-1.5"><Phone className="size-4" /> Run AI calling now</Button>}
      />

      <Card><CardContent className="flex flex-wrap items-center gap-3 p-4">
        <div className="flex items-center gap-2 text-xs text-muted-foreground"><span>Status</span>
          <Select defaultValue="all">
            <SelectTrigger className="h-8 w-44"><SelectValue /></SelectTrigger>
            <SelectContent>
              {["all", "calling", "rebooked", "no-answer", "wa-sent", "completed"].map((s) => (
                <SelectItem key={s} value={s}>{s}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground"><Calendar className="size-3.5" />
          <Select defaultValue="today">
            <SelectTrigger className="h-8 w-44"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="today">Today</SelectItem>
              <SelectItem value="week">This week</SelectItem>
              <SelectItem value="month">This month</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <p className="ml-auto text-xs text-muted-foreground">{rows.length} patients pending</p>
      </CardContent></Card>

      <Card><CardContent className="px-0">
        {jobsQ.isLoading ? (
          <div className="space-y-2 p-6"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-full" /></div>
        ) : rows.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted-foreground">No recovery jobs in the queue.</p>
        ) : (
          <Table>
            <TableHeader><TableRow>
              <SortHeader label="Time" sortKey="time" active={sortKey} dir={sortDir} onToggle={toggleSort} className="pl-6" />
              <SortHeader label="Patient" sortKey="patient" active={sortKey} dir={sortDir} onToggle={toggleSort} />
              <SortHeader label="Reference" sortKey="phone" active={sortKey} dir={sortDir} onToggle={toggleSort} />
              <TableHead className="pr-6 text-right">Status</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {sorted.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="pl-6 font-mono text-xs">{r.time}</TableCell>
                  <TableCell className="font-medium">{r.patient}</TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">{r.phone}</TableCell>
                  <TableCell className="pr-6 text-right"><StatusBadge tone={r.tone} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent></Card>
    </div>
  );
}
