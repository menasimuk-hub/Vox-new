import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Plus,
  Search,
  Eye,
  CheckCircle2,
  PhoneCall,
  XCircle,
  CalendarDays,
  AlertTriangle,
  MapPin,
  Filter,
  ChevronRight,
  Mic,
  Mail,
  Bell,
  RefreshCw,
} from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { AppointmentReportsPanel } from "@/components/appointments/appointment-reports-panel";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";

/* ============================================================================
   TYPES
============================================================================ */

type Status = "Scheduled" | "Confirmed" | "Rescheduled" | "Cancelled" | "No Show";
type CrmSource = "HubSpot" | "Pipedrive" | "Zoho" | "Manual";

type ApiAppointment = {
  id: string;
  contact_name: string;
  contact_phone: string;
  contact_email?: string | null;
  appointment_datetime: string;
  timezone: string;
  branch?: string | null;
  service_type?: string | null;
  status: string;
  crm_source: string;
  crm_record_id?: string | null;
  wa_confirmation_sent_at?: string | null;
  wa_confirmation_status?: string | null;
  call_triggered_at?: string | null;
  call_outcome?: string | null;
  rescheduled_to_datetime?: string | null;
  notes?: string | null;
  updated_at?: string;
};

type ApiAppointmentLog = {
  id: string;
  appointment_id: string;
  event_type: string;
  detail_json?: string | null;
  created_at: string;
};

type ApiAppointmentDetail = ApiAppointment & {
  logs: ApiAppointmentLog[];
};

type Appointment = {
  id: string;
  name: string;
  phone: string;
  datetime: string;
  service: string;
  branch: string;
  crm: CrmSource;
  status: Status;
  waSent: boolean;
  lastAction: string;
  timezone: string;
  notes?: string;
  rescheduledTo?: string;
  crmRecordId?: string | null;
  timeline: { t: string; label: string; tone?: "ok" | "warn" | "info" }[];
};

type ReportSummary = {
  total: number;
  scheduled: number;
  confirmed: number;
  rescheduled: number;
  cancelled: number;
  no_show: number;
  wa_sent: number;
  calls_triggered: number;
};

type AppointmentSettings = {
  setup_complete: boolean;
  wa_template_name: string;
  wa_send_hours_before: number;
  call_hours_before: number;
  wa_enabled: boolean;
  call_enabled: boolean;
  outreach_window_start?: string;
  outreach_window_end?: string;
  appointment_agent_id?: string | null;
};

/* ============================================================================
   MAPPERS
============================================================================ */

function titleCaseStatus(status: string): Status {
  const s = String(status || "scheduled").toLowerCase();
  if (s === "no_show") return "No Show";
  if (s === "cancelled") return "Cancelled";
  if (s === "confirmed") return "Confirmed";
  if (s === "rescheduled") return "Rescheduled";
  return "Scheduled";
}

function formatCrmSource(source: string): CrmSource {
  const key = String(source || "manual").toLowerCase();
  const map: Record<string, CrmSource> = {
    hubspot: "HubSpot",
    pipedrive: "Pipedrive",
    zoho: "Zoho",
    manual: "Manual",
  };
  return map[key] ?? (source.charAt(0).toUpperCase() + source.slice(1) as CrmSource);
}

function formatAppointmentDatetime(iso: string, timezone?: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const parts = new Intl.DateTimeFormat("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezone || undefined,
  }).formatToParts(d);
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((p) => p.type === type)?.value ?? "";
  return `${get("weekday")} ${get("day")} ${get("month")} · ${get("hour")}:${get("minute")}`;
}

function formatLogTime(iso: string, timezone?: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezone || undefined,
  }).format(d);
}

function formatRelative(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const diffMs = Date.now() - d.getTime();
  const mins = Math.round(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function parseLogDetail(raw?: string | null): Record<string, unknown> | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function logEventLabel(eventType: string, detail: Record<string, unknown> | null): string {
  const type = String(eventType || "").toLowerCase();
  const labels: Record<string, string> = {
    created: "Appointment created",
    updated: "Appointment updated",
    status_changed: detail?.status ? `Status changed to ${detail.status}` : "Status changed",
    wa_confirmation_sent: "WhatsApp confirmation sent",
    wa_confirmed: "Customer confirmed via WhatsApp",
    wa_cancelled: "Customer cancelled via WhatsApp",
    wa_reschedule_requested: "Customer requested reschedule",
    crm_sync_created: "Appointment booked in CRM",
    crm_sync_updated: "Updated from CRM sync",
    call_confirmation_started: "AI confirmation call started",
    call_reschedule_started: "AI reschedule call started",
    call_completed: detail?.outcome
      ? `Call completed · ${String(detail.outcome).replace(/_/g, " ")}`
      : "Call completed",
    call_analyzed: "Call analyzed",
  };
  if (labels[type]) return labels[type];
  return type.replace(/_/g, " ");
}

function logEventTone(eventType: string): "ok" | "warn" | "info" {
  const type = String(eventType || "").toLowerCase();
  if (type.includes("confirm") && !type.includes("sent")) return "ok";
  if (type === "call_completed") return "ok";
  if (type.includes("cancel") || type.includes("reschedule") || type.includes("no_show")) return "warn";
  return "info";
}

function buildTimeline(logs: ApiAppointmentLog[], timezone?: string): Appointment["timeline"] {
  return logs.map((log) => ({
    t: formatLogTime(log.created_at, timezone),
    label: logEventLabel(log.event_type, parseLogDetail(log.detail_json)),
    tone: logEventTone(log.event_type),
  }));
}

function buildLastAction(row: ApiAppointment): string {
  if (row.wa_confirmation_status === "replied") {
    if (row.status === "confirmed") return `WA reply YES · ${formatRelative(row.updated_at)}`.trim();
    if (row.status === "cancelled") return `Customer cancelled via WA · ${formatRelative(row.updated_at)}`.trim();
    if (row.status === "rescheduled") return `Reschedule via WA · ${formatRelative(row.updated_at)}`.trim();
  }
  if (row.call_outcome) {
    return `Call ${row.call_outcome.replace(/_/g, " ")} · ${formatRelative(row.call_triggered_at || row.updated_at)}`.trim();
  }
  if (row.wa_confirmation_sent_at) {
    return `WA delivered · ${formatRelative(row.wa_confirmation_sent_at)}`.trim();
  }
  if (row.status === "no_show") return `Marked no-show · ${formatRelative(row.updated_at)}`.trim();
  if (formatCrmSource(row.crm_source) === "Manual") return `Created manually · ${formatRelative(row.updated_at)}`.trim();
  return formatRelative(row.updated_at) || "—";
}

function mapAppointment(row: ApiAppointment, logs?: ApiAppointmentLog[]): Appointment {
  return {
    id: row.id,
    name: row.contact_name,
    phone: row.contact_phone,
    datetime: formatAppointmentDatetime(row.appointment_datetime, row.timezone),
    service: row.service_type || "—",
    branch: row.branch || "—",
    crm: formatCrmSource(row.crm_source),
    status: titleCaseStatus(row.status),
    waSent: Boolean(row.wa_confirmation_sent_at),
    lastAction: buildLastAction(row),
    timezone: row.timezone || "Europe/London",
    notes: row.notes || undefined,
    rescheduledTo: row.rescheduled_to_datetime
      ? formatAppointmentDatetime(row.rescheduled_to_datetime, row.timezone)
      : undefined,
    crmRecordId: row.crm_record_id,
    timeline: logs ? buildTimeline(logs, row.timezone) : [],
  };
}

/* ============================================================================
   PAGE
============================================================================ */

export function AppointmentManagerPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [openAdd, setOpenAdd] = React.useState(false);
  const [search, setSearch] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState<Status | "all">("all");
  const [crmFilter, setCrmFilter] = React.useState<CrmSource | "all">("all");
  const [branchFilter, setBranchFilter] = React.useState<string>("all");

  const listQ = useQuery({
    queryKey: ["appointments", "list"],
    queryFn: () => apiFetch<ApiAppointment[]>("/appointments"),
  });

  const summaryQ = useQuery({
    queryKey: ["appointments", "reports", "summary"],
    queryFn: () => apiFetch<ReportSummary>("/appointments/reports/summary"),
  });

  const settingsQ = useQuery({
    queryKey: ["appointments", "settings"],
    queryFn: () => apiFetch<AppointmentSettings>("/appointments/settings"),
  });

  const detailQ = useQuery({
    queryKey: ["appointments", "detail", selectedId],
    queryFn: () => apiFetch<ApiAppointmentDetail>(`/appointments/${selectedId}`),
    enabled: Boolean(selectedId),
  });

  const syncMut = useMutation({
    mutationFn: () => apiFetch<{ synced?: number }>("/appointments/sync-crm", { method: "POST" }),
    onSuccess: (data) => {
      toast.success(`CRM sync complete (${data.synced ?? 0} records)`);
      void queryClient.invalidateQueries({ queryKey: ["appointments"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const invalidateAppointments = () => {
    void queryClient.invalidateQueries({ queryKey: ["appointments"] });
  };

  const statusMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      apiFetch<ApiAppointment>(`/appointments/${id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }),
    onSuccess: () => {
      toast.success("Status updated");
      invalidateAppointments();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const callMut = useMutation({
    mutationFn: (id: string) =>
      apiFetch<{ ok?: boolean }>(`/appointments/${id}/call`, { method: "POST" }),
    onSuccess: () => {
      toast.success("Call triggered");
      invalidateAppointments();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const createMut = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch<ApiAppointment>("/appointments", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      toast.success("Appointment created");
      setOpenAdd(false);
      invalidateAppointments();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const appointments = React.useMemo(
    () => (listQ.data ?? []).map((row) => mapAppointment(row)),
    [listQ.data],
  );

  const branches = React.useMemo(() => {
    const set = new Set<string>();
    appointments.forEach((a) => {
      if (a.branch && a.branch !== "—") set.add(a.branch);
    });
    return Array.from(set).sort();
  }, [appointments]);

  const rows = appointments.filter((a) => {
    if (statusFilter !== "all" && a.status !== statusFilter) return false;
    if (crmFilter !== "all" && a.crm !== crmFilter) return false;
    if (branchFilter !== "all" && a.branch !== branchFilter) return false;
    if (search && !`${a.name} ${a.phone}`.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const selected = React.useMemo(() => {
    if (!selectedId) return null;
    if (detailQ.data) return mapAppointment(detailQ.data, detailQ.data.logs);
    const fromList = appointments.find((a) => a.id === selectedId);
    return fromList ?? null;
  }, [selectedId, detailQ.data, appointments]);

  const handleConfirm = (id: string) => statusMut.mutate({ id, status: "confirmed" });
  const handleCancel = (id: string) => statusMut.mutate({ id, status: "cancelled" });
  const handleCall = (id: string) => callMut.mutate(id);

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Appointment Manager"
        title="Appointments"
        description="WhatsApp + AI-call confirmation for every booking — across HubSpot, Pipedrive, Zoho and manual."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              className="gap-1.5"
              disabled={syncMut.isPending}
              onClick={() => syncMut.mutate()}
            >
              <RefreshCw className={cn("size-4", syncMut.isPending && "animate-spin")} />
              Sync CRM
            </Button>
            <Button className="gap-1.5" onClick={() => setOpenAdd(true)}>
              <Plus className="size-4" /> Add appointment
            </Button>
          </div>
        }
      />

      {settingsQ.data && !settingsQ.data.setup_complete && (
        <Card className="border-amber-500/40 bg-amber-500/5">
          <CardContent className="flex flex-wrap items-center gap-3 p-4">
            <AlertTriangle className="size-5 shrink-0 text-amber-600" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">Finish appointment setup</p>
              <p className="text-xs text-muted-foreground">
                Connect your CRM, choose templates, and configure confirmation timing before going live.
              </p>
            </div>
            <Button asChild size="sm" variant="outline">
              <a href="/appointments/setup">Complete setup</a>
            </Button>
          </CardContent>
        </Card>
      )}

      <KpiBar summary={summaryQ.data} loading={summaryQ.isLoading} />

      <Tabs defaultValue="table">
        <TabsList>
          <TabsTrigger value="table" className="gap-1.5">
            <CalendarDays className="size-3.5" /> Appointments
          </TabsTrigger>
          <TabsTrigger value="reports" className="gap-1.5">
            <Filter className="size-3.5" /> Reports
          </TabsTrigger>
          <TabsTrigger value="settings" className="gap-1.5">
            <Bell className="size-3.5" /> Settings
          </TabsTrigger>
        </TabsList>

        <TabsContent value="table" className="space-y-4">
          {listQ.isLoading && (
            <p className="text-sm text-muted-foreground">Loading appointments…</p>
          )}
          {listQ.isError && (
            <p className="text-sm text-destructive">{(listQ.error as Error).message}</p>
          )}

          <Card>
            <CardContent className="flex flex-wrap items-center gap-2 p-3">
              <div className="relative min-w-[220px] flex-1">
                <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search name or phone"
                  className="pl-8"
                />
              </div>
              <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as Status | "all")}>
                <SelectTrigger className="w-[160px]">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  <SelectItem value="Scheduled">Scheduled</SelectItem>
                  <SelectItem value="Confirmed">Confirmed</SelectItem>
                  <SelectItem value="Rescheduled">Rescheduled</SelectItem>
                  <SelectItem value="Cancelled">Cancelled</SelectItem>
                  <SelectItem value="No Show">No show</SelectItem>
                </SelectContent>
              </Select>
              <Select value={crmFilter} onValueChange={(v) => setCrmFilter(v as CrmSource | "all")}>
                <SelectTrigger className="w-[150px]">
                  <SelectValue placeholder="CRM" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All CRMs</SelectItem>
                  <SelectItem value="HubSpot">HubSpot</SelectItem>
                  <SelectItem value="Pipedrive">Pipedrive</SelectItem>
                  <SelectItem value="Zoho">Zoho</SelectItem>
                  <SelectItem value="Manual">Manual</SelectItem>
                </SelectContent>
              </Select>
              <Select value={branchFilter} onValueChange={setBranchFilter}>
                <SelectTrigger className="w-[220px]">
                  <SelectValue placeholder="Branch" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All branches</SelectItem>
                  {branches.map((b) => (
                    <SelectItem key={b} value={b}>
                      {b}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button variant="outline" size="sm">
                Date range
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="px-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="pl-6">Contact</TableHead>
                    <TableHead>Phone</TableHead>
                    <TableHead>Date &amp; time</TableHead>
                    <TableHead>Service / Branch</TableHead>
                    <TableHead>CRM</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>WA</TableHead>
                    <TableHead>Last action</TableHead>
                    <TableHead className="pr-6 text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((a) => (
                    <TableRow
                      key={a.id}
                      className="cursor-pointer"
                      onClick={() => setSelectedId(a.id)}
                    >
                      <TableCell className="pl-6 font-medium">{a.name}</TableCell>
                      <TableCell className="text-muted-foreground">{a.phone}</TableCell>
                      <TableCell className="whitespace-nowrap">{a.datetime}</TableCell>
                      <TableCell>
                        <div className="text-sm">{a.service}</div>
                        <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                          <MapPin className="size-3" /> {a.branch}
                        </div>
                      </TableCell>
                      <TableCell>
                        <CrmBadge crm={a.crm} />
                      </TableCell>
                      <TableCell>
                        <StatusPill status={a.status} />
                      </TableCell>
                      <TableCell>
                        {a.waSent ? (
                          <CheckCircle2 className="size-4 text-emerald-500" />
                        ) : (
                          <span className="text-[11px] text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-[11px] text-muted-foreground">{a.lastAction}</TableCell>
                      <TableCell className="pr-6 text-right">
                        <div className="inline-flex gap-0.5" onClick={(e) => e.stopPropagation()}>
                          <Button
                            size="sm"
                            variant="ghost"
                            title="View"
                            onClick={() => setSelectedId(a.id)}
                          >
                            <Eye className="size-4" />
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            title="Confirm"
                            disabled={statusMut.isPending}
                            onClick={() => handleConfirm(a.id)}
                          >
                            <CheckCircle2 className="size-4" />
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            title="Reschedule call"
                            disabled={callMut.isPending}
                            onClick={() => handleCall(a.id)}
                          >
                            <PhoneCall className="size-4" />
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            title="Cancel"
                            className="text-destructive hover:text-destructive"
                            disabled={statusMut.isPending}
                            onClick={() => handleCancel(a.id)}
                          >
                            <XCircle className="size-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {rows.length === 0 && !listQ.isLoading && (
                <div className="flex flex-col items-center gap-2 px-6 py-16 text-center">
                  <CalendarDays className="size-8 text-muted-foreground" />
                  <p className="text-sm font-medium">No appointments match these filters.</p>
                  <p className="text-xs text-muted-foreground">
                    Try clearing filters or add a new appointment.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="reports" className="space-y-4">
          <AppointmentReportsPanel />
        </TabsContent>

        <TabsContent value="settings" className="space-y-4">
          <SettingsTab settings={settingsQ.data} loading={settingsQ.isLoading} />
        </TabsContent>
      </Tabs>

      <DetailSheet
        appt={selected}
        loading={Boolean(selectedId && detailQ.isLoading)}
        onClose={() => setSelectedId(null)}
        onConfirm={handleConfirm}
        onCall={handleCall}
        onCancel={handleCancel}
        actionsPending={statusMut.isPending || callMut.isPending}
      />

      <AddAppointmentDialog
        open={openAdd}
        onOpenChange={setOpenAdd}
        branches={branches}
        pending={createMut.isPending}
        onCreate={(body) => createMut.mutate(body)}
      />
    </div>
  );
}

/* ============================================================================
   KPI BAR
============================================================================ */

function KpiBar({ summary, loading }: { summary?: ReportSummary; loading?: boolean }) {
  const total = summary?.total ?? 0;
  const confirmed = summary?.confirmed ?? 0;
  const rescheduled = summary?.rescheduled ?? 0;
  const scheduled = summary?.scheduled ?? 0;
  const rate = total > 0 ? Math.round((100 * confirmed) / total) : 0;
  const rescheduledPct = total > 0 ? ((100 * rescheduled) / total).toFixed(1) : "0";

  const items = [
    { label: "Total (month)", value: String(total), hint: "All bookings" },
    { label: "Confirm rate", value: `${rate}%`, tone: rate >= 80 ? "ok" as const : "default" as const },
    { label: "Rescheduled", value: String(rescheduled), hint: `${rescheduledPct}%` },
    { label: "Unconfirmed", value: String(scheduled), tone: scheduled > 0 ? "warn" as const : "default" as const, urgent: scheduled > 0 },
  ];

  if (loading && !summary) {
    return (
      <div className="flex flex-nowrap gap-2 overflow-x-auto">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-9 min-w-[140px] flex-1 animate-pulse rounded-md border bg-muted/40" />
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-nowrap gap-2 overflow-x-auto pb-0.5">
      {items.map((item) => (
        <KpiCard key={item.label} {...item} />
      ))}
    </div>
  );
}

function KpiCard({
  label,
  value,
  hint,
  tone,
  urgent,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "ok" | "warn" | "info";
  urgent?: boolean;
}) {
  const colour =
    tone === "ok"
      ? "text-emerald-600"
      : tone === "warn"
        ? "text-amber-600"
        : tone === "info"
          ? "text-blue-600"
          : "text-foreground";
  return (
    <div
      className={cn(
        "flex min-w-[140px] flex-1 items-center justify-between gap-2 rounded-md border border-border bg-card px-3 py-2",
        urgent && "border-amber-500/40 bg-amber-500/5",
      )}
    >
      <div className="min-w-0">
        <p className="truncate text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className={cn("text-lg font-semibold tabular-nums leading-tight", colour)}>{value}</p>
      </div>
      {hint ? <span className="shrink-0 text-[10px] text-muted-foreground">{hint}</span> : null}
      {urgent && !hint ? (
        <Badge variant="destructive" className="shrink-0 text-[9px]">
          Urgent
        </Badge>
      ) : null}
    </div>
  );
}

/* ============================================================================
   BADGES
============================================================================ */

function CrmBadge({ crm }: { crm: CrmSource }) {
  const map: Record<CrmSource, string> = {
    HubSpot: "bg-orange-500/10 text-orange-600 border-orange-500/30",
    Pipedrive: "bg-slate-500/10 text-slate-600 border-slate-500/30 dark:text-slate-300",
    Zoho: "bg-rose-500/10 text-rose-600 border-rose-500/30",
    Manual: "bg-blue-500/10 text-blue-600 border-blue-500/30",
  };
  return (
    <Badge variant="outline" className={cn("text-[10px]", map[crm])}>
      {crm}
    </Badge>
  );
}

function StatusPill({ status }: { status: Status }) {
  const map: Record<Status, string> = {
    Scheduled: "bg-blue-500/10 text-blue-600 border-blue-500/30",
    Confirmed: "bg-emerald-500/10 text-emerald-600 border-emerald-500/30",
    Rescheduled: "bg-amber-500/10 text-amber-600 border-amber-500/30",
    Cancelled: "bg-slate-500/10 text-slate-600 border-slate-500/30",
    "No Show": "bg-red-500/10 text-red-600 border-red-500/30",
  };
  return (
    <Badge variant="outline" className={cn("text-[10px]", map[status])}>
      {status}
    </Badge>
  );
}

/* ============================================================================
   DETAIL SLIDE-OVER
============================================================================ */

function DetailSheet({
  appt,
  loading,
  onClose,
  onConfirm,
  onCall,
  onCancel,
  actionsPending,
}: {
  appt: Appointment | null;
  loading?: boolean;
  onClose: () => void;
  onConfirm: (id: string) => void;
  onCall: (id: string) => void;
  onCancel: (id: string) => void;
  actionsPending?: boolean;
}) {
  return (
    <Sheet open={!!appt} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full sm:max-w-lg">
        {appt && (
          <>
            <SheetHeader>
              <SheetTitle>{appt.name}</SheetTitle>
              <SheetDescription>
                {appt.phone} · {appt.timezone}
              </SheetDescription>
            </SheetHeader>
            <div className="mt-6 space-y-5">
              <div className="rounded-lg border border-border bg-muted/30 p-3">
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Appointment</p>
                <p className="mt-1 text-base font-semibold">{appt.datetime}</p>
                <p className="text-xs text-muted-foreground">
                  {appt.service} · {appt.branch}
                </p>
                {appt.rescheduledTo && (
                  <p className="mt-2 text-xs text-amber-600">
                    Rescheduled to: <span className="font-medium">{appt.rescheduledTo}</span>
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2">
                <CrmBadge crm={appt.crm} />
                <StatusPill status={appt.status} />
                {appt.crm !== "Manual" && (
                  <span className="ml-auto inline-flex items-center gap-1 text-xs text-primary">
                    Open in {appt.crm} <ChevronRight className="size-3" />
                  </span>
                )}
              </div>
              <div>
                <p className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  Timeline
                </p>
                {loading && appt.timeline.length === 0 && (
                  <p className="text-xs text-muted-foreground">Loading timeline…</p>
                )}
                {appt.timeline.length === 0 && !loading && (
                  <p className="text-xs text-muted-foreground">No activity logged yet.</p>
                )}
                <ol className="relative space-y-3 border-l border-border pl-4">
                  {appt.timeline.map((t, i) => (
                    <li key={i} className="relative">
                      <span
                        className={cn(
                          "absolute -left-[20px] top-1 grid size-3 place-items-center rounded-full ring-2 ring-background",
                          t.tone === "ok"
                            ? "bg-emerald-500"
                            : t.tone === "warn"
                              ? "bg-amber-500"
                              : "bg-blue-500",
                        )}
                      />
                      <p className="text-sm">{t.label}</p>
                      <p className="text-[10px] text-muted-foreground">{t.t}</p>
                    </li>
                  ))}
                </ol>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1"
                  disabled={actionsPending}
                  onClick={() => onConfirm(appt.id)}
                >
                  <CheckCircle2 className="size-3.5" /> Confirm
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1"
                  disabled={actionsPending}
                  onClick={() => onCall(appt.id)}
                >
                  <PhoneCall className="size-3.5" /> Call now
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1 text-destructive"
                  disabled={actionsPending}
                  onClick={() => onCancel(appt.id)}
                >
                  <XCircle className="size-3.5" /> Cancel
                </Button>
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

/* ============================================================================
   SETTINGS TAB
============================================================================ */

function SettingsTab({
  settings,
  loading,
}: {
  settings?: AppointmentSettings;
  loading?: boolean;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = React.useState<Partial<AppointmentSettings>>({});

  React.useEffect(() => {
    if (settings) setDraft(settings);
  }, [settings]);

  const saveMut = useMutation({
    mutationFn: (body: Partial<AppointmentSettings>) =>
      apiFetch<AppointmentSettings>("/appointments/settings", {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      toast.success("Settings saved");
      void queryClient.invalidateQueries({ queryKey: ["appointments", "settings"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (loading && !settings) {
    return <p className="text-sm text-muted-foreground">Loading settings…</p>;
  }

  const s = { ...settings, ...draft } as AppointmentSettings;

  const update = (patch: Partial<AppointmentSettings>) => {
    setDraft((prev) => ({ ...prev, ...patch }));
  };

  const handleSave = () => {
    saveMut.mutate({
      wa_send_hours_before: s.wa_send_hours_before,
      call_hours_before: s.call_hours_before,
      wa_enabled: s.wa_enabled,
      call_enabled: s.call_enabled,
      wa_template_name: s.wa_template_name,
      outreach_window_start: s.outreach_window_start,
      outreach_window_end: s.outreach_window_end,
    });
  };

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>WhatsApp template</CardTitle>
          <CardDescription>Choose the confirmation template sent before each appointment.</CardDescription>
        </CardHeader>
        <CardContent>
          <WaTemplatePicker
            value={s.wa_template_name}
            onChange={(wa_template_name) => update({ wa_template_name })}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Confirmation timing</CardTitle>
          <CardDescription>When to ask, when to call.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="wa-h">WhatsApp reminder — hours before</Label>
            <Input
              id="wa-h"
              type="number"
              min={1}
              value={s.wa_send_hours_before ?? 48}
              onChange={(e) => update({ wa_send_hours_before: Number(e.target.value) })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="call-h">AI confirmation call — hours before (if no reply)</Label>
            <Input
              id="call-h"
              type="number"
              min={1}
              value={s.call_hours_before ?? 24}
              onChange={(e) => update({ call_hours_before: Number(e.target.value) })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="outreach-start">Outreach window start</Label>
            <Input
              id="outreach-start"
              type="time"
              value={s.outreach_window_start ?? "09:00"}
              onChange={(e) => update({ outreach_window_start: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="outreach-end">Outreach window end</Label>
            <Input
              id="outreach-end"
              type="time"
              value={s.outreach_window_end ?? "16:00"}
              onChange={(e) => update({ outreach_window_end: e.target.value })}
            />
          </div>
          <p className="sm:col-span-2 text-xs text-muted-foreground">
            WhatsApp and AI calls are only sent between these times (e.g. 09:00 – 16:00).
          </p>
          <ToggleRow
            id="t-wa"
            label="Enable WhatsApp confirmation"
            checked={Boolean(s.wa_enabled)}
            onCheckedChange={(wa_enabled) => update({ wa_enabled })}
          />
          <ToggleRow
            id="t-call"
            label="Enable AI confirmation calls"
            checked={Boolean(s.call_enabled)}
            onCheckedChange={(call_enabled) => update({ call_enabled })}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mic className="size-4" /> Voice agent
          </CardTitle>
          <CardDescription>AI confirmation call settings.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Voice</Label>
              <Select defaultValue="female">
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="female">Female</SelectItem>
                  <SelectItem value="male">Male</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Fallback if no answer</Label>
              <Select defaultValue="retry">
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="voicemail">Leave voicemail</SelectItem>
                  <SelectItem value="retry">Try again in 2h</SelectItem>
                  <SelectItem value="noanswer">Mark as no_answer</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="greet">Agent greeting</Label>
            <Textarea
              id="greet"
              rows={3}
              defaultValue="Hello, this is the VoxBulk assistant calling on behalf of {{company}}. We just want to confirm your appointment for {{service}} on {{date}}. Is that still convenient?"
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mail className="size-4" /> Notifications
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <ToggleRow id="n-unconf" label="Email alert for unconfirmed appointments" defaultChecked />
          <div className="space-y-1.5">
            <Label htmlFor="alert-email">Alert email</Label>
            <Input id="alert-email" type="email" defaultValue="manager@voxbulk.com" />
          </div>
          <ToggleRow id="n-daily" label="Daily summary email" />
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button disabled={saveMut.isPending} onClick={handleSave}>
          Save settings
        </Button>
      </div>
    </>
  );
}

function WaTemplatePicker({
  value,
  onChange,
}: {
  value?: string;
  onChange: (name: string) => void;
}) {
  const templatesQ = useQuery({
    queryKey: ["appointments", "templates"],
    queryFn: () =>
      apiFetch<Array<{ name: string; label: string; description?: string }>>("/appointments/templates"),
  });

  if (templatesQ.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading templates…</p>;
  }

  const rows = templatesQ.data ?? [];
  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No templates found. Complete setup at{" "}
        <a href="/appointments/setup" className="text-primary underline">
          Appointment setup
        </a>
        .
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      {rows.map((t) => {
        const selected = value === t.name;
        return (
          <button
            key={t.name}
            type="button"
            onClick={() => onChange(t.name)}
            className={cn(
              "flex items-center gap-2 rounded-md border px-3 py-2 text-left text-sm transition",
              selected ? "border-primary bg-primary/5" : "hover:border-primary/40",
            )}
          >
            <span className="min-w-0 flex-1 truncate font-medium">{t.label}</span>
            <span className="hidden truncate text-xs text-muted-foreground sm:inline">{t.description}</span>
            {selected ? <CheckCircle2 className="size-4 shrink-0 text-primary" /> : null}
          </button>
        );
      })}
    </div>
  );
}

function ToggleRow({
  id,
  label,
  checked,
  defaultChecked,
  onCheckedChange,
}: {
  id: string;
  label: string;
  checked?: boolean;
  defaultChecked?: boolean;
  onCheckedChange?: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border bg-muted/20 px-3 py-2.5">
      <Label htmlFor={id} className="text-sm font-normal">
        {label}
      </Label>
      <Switch
        id={id}
        checked={checked}
        defaultChecked={defaultChecked}
        onCheckedChange={onCheckedChange}
      />
    </div>
  );
}

/* ============================================================================
   ADD APPOINTMENT
============================================================================ */

function AddAppointmentDialog({
  open,
  onOpenChange,
  branches,
  pending,
  onCreate,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  branches: string[];
  pending?: boolean;
  onCreate: (body: Record<string, unknown>) => void;
}) {
  const fallbackBranches = branches.length
    ? branches
    : ["London — Marylebone", "Berlin — Mitte", "Milan — Brera"];

  const [contactName, setContactName] = React.useState("");
  const [countryCode, setCountryCode] = React.useState("+44");
  const [phone, setPhone] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [date, setDate] = React.useState("");
  const [time, setTime] = React.useState("");
  const [timezone, setTimezone] = React.useState("Europe/London");
  const [service, setService] = React.useState("");
  const [branch, setBranch] = React.useState(fallbackBranches[0]);
  const [notes, setNotes] = React.useState("");

  React.useEffect(() => {
    if (open) {
      setContactName("");
      setPhone("");
      setEmail("");
      setDate("");
      setTime("");
      setService("");
      setNotes("");
      setBranch(fallbackBranches[0]);
    }
  }, [open, fallbackBranches[0]]);

  const handleCreate = () => {
    if (!contactName.trim() || !phone.trim() || !date || !time) {
      toast.error("Name, phone, date and time are required");
      return;
    }
    const appointmentDatetime = new Date(`${date}T${time}:00`).toISOString();
    onCreate({
      contact_name: contactName.trim(),
      contact_phone: `${countryCode}${phone.replace(/\s+/g, "")}`,
      contact_email: email.trim() || null,
      appointment_datetime: appointmentDatetime,
      timezone,
      branch,
      service_type: service.trim() || null,
      notes: notes.trim() || null,
      crm_source: "manual",
      status: "scheduled",
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add appointment</DialogTitle>
          <DialogDescription>
            Manually create an appointment when it&apos;s not flowing in from a CRM.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="space-y-1.5">
            <Label>Contact name</Label>
            <Input
              placeholder="Sara Patel"
              value={contactName}
              onChange={(e) => setContactName(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-[110px_1fr] gap-2">
            <div className="space-y-1.5">
              <Label>Country</Label>
              <Select value={countryCode} onValueChange={setCountryCode}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="+44">+44 UK</SelectItem>
                  <SelectItem value="+49">+49 DE</SelectItem>
                  <SelectItem value="+39">+39 IT</SelectItem>
                  <SelectItem value="+45">+45 DK</SelectItem>
                  <SelectItem value="+1">+1 US</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Phone</Label>
              <Input
                placeholder="7700 900123"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Email (optional)</Label>
            <Input
              type="email"
              placeholder="sara@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label>Date</Label>
              <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Time</Label>
              <Input type="time" value={time} onChange={(e) => setTime(e.target.value)} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label>Timezone</Label>
              <Select value={timezone} onValueChange={setTimezone}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Europe/London">Europe/London</SelectItem>
                  <SelectItem value="Europe/Berlin">Europe/Berlin</SelectItem>
                  <SelectItem value="Europe/Rome">Europe/Rome</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Service</Label>
              <Input
                placeholder="Hygiene visit"
                value={service}
                onChange={(e) => setService(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Branch / location</Label>
            <Select value={branch} onValueChange={setBranch}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {fallbackBranches.map((b) => (
                  <SelectItem key={b} value={b}>
                    {b}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Notes</Label>
            <Textarea
              rows={2}
              placeholder="Optional notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={pending} onClick={handleCreate}>
            Create appointment
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export { titleCaseStatus, formatCrmSource, formatAppointmentDatetime, mapAppointment };
export type { Appointment, ApiAppointment, Status, CrmSource };
