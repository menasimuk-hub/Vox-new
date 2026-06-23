import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { Check, ChevronLeft, ChevronRight, Eye, Plug, CreditCard } from "lucide-react";
import { toast } from "sonner";

import { IPhonePreview } from "@/components/iphone-preview";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useIntegrationsCatalogue, useHubSpotStatus, usePatchHubSpotSettings, useSchedulingStatus, useServiceOrders } from "@/lib/queries";
import { HubSpotAppointmentListPickers } from "@/components/integrations/hubspot-list-import-panel";
import { showCrmSyncToast, type CrmSyncResult } from "@/components/appointments/appointment-crm-sync-panel";

type Settings = {
  setup_complete?: boolean;
  workspace_name?: string;
  crm_provider?: string;
  crm_object?: string;
  crm_date_property?: string;
  sync_interval_minutes?: number;
  appointment_agent_id?: string | null;
  wa_template_name?: string;
  wa_send_hours_before?: number;
  call_hours_before?: number;
  wa_enabled?: boolean;
  call_enabled?: boolean;
  calendar_enabled?: boolean;
  calendar_id?: string;
  slot_duration_minutes?: number;
  post_survey_enabled?: boolean;
  post_survey_order_id?: string | null;
  post_survey_delay_hours?: number;
};

type WaTemplate = {
  name: string;
  label: string;
  description?: string;
  body?: string;
  footer?: string;
  buttons?: Array<{ label: string; type?: string }>;
  approval_status?: string;
};

type BillingEligibility = {
  allowed: boolean;
  reason?: string | null;
  plan_name?: string | null;
  package_remaining?: number;
};

type Agent = { id: string; name: string; voice_label?: string; is_platform_default?: boolean };

type SurveyOrder = { id: string; title: string; status?: string };

const TOTAL_STEPS = 5;

const CRM_PROVIDERS = [
  { id: "hubspot", label: "HubSpot" },
  { id: "pipedrive", label: "Pipedrive" },
  { id: "zoho_crm", label: "Zoho CRM" },
];

const SYNC_OPTIONS = [
  { value: 15, label: "Every 15 minutes" },
  { value: 60, label: "Every hour" },
  { value: 360, label: "Every 6 hours" },
  { value: 1440, label: "Daily" },
];

export function AppointmentSetupWizard() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [step, setStep] = React.useState(1);

  const settingsQ = useQuery({
    queryKey: ["appointments", "settings"],
    queryFn: () => apiFetch<Settings>("/appointments/settings"),
  });
  const templatesQ = useQuery({
    queryKey: ["appointments", "templates"],
    queryFn: () => apiFetch<WaTemplate[]>("/appointments/templates"),
    enabled: step >= 3,
  });
  const billingQ = useQuery({
    queryKey: ["appointments", "billing", "eligibility"],
    queryFn: () => apiFetch<BillingEligibility>("/appointments/billing/eligibility"),
  });
  const agentsQ = useQuery({
    queryKey: ["appointments", "agents"],
    queryFn: () => apiFetch<Agent[]>("/appointments/agents"),
    enabled: step >= 4,
  });
  const integrationsQ = useIntegrationsCatalogue();
  const hubspotQ = useHubSpotStatus();
  const schedulingQ = useSchedulingStatus();
  const surveysQ = useServiceOrders("survey");
  const patchHubspotM = usePatchHubSpotSettings();

  const [form, setForm] = React.useState<Settings>({});
  const [appointmentListId, setAppointmentListId] = React.useState("");
  const [confirmedListId, setConfirmedListId] = React.useState("");
  const [cancelledListId, setCancelledListId] = React.useState("");

  React.useEffect(() => {
    if (settingsQ.data) setForm(settingsQ.data);
  }, [settingsQ.data]);

  React.useEffect(() => {
    if (!hubspotQ.data) return;
    setAppointmentListId(String(hubspotQ.data.appointment_list_id || ""));
    setConfirmedListId(String(hubspotQ.data.appointment_confirmed_list_id || ""));
    setCancelledListId(String(hubspotQ.data.appointment_cancelled_list_id || ""));
  }, [hubspotQ.data]);

  const patch = (partial: Partial<Settings>) => setForm((prev) => ({ ...prev, ...partial }));

  const crmViews = integrationsQ.data?.crm ?? [];
  const connectedCrm = crmViews.find((p) => p.connected);
  const crmReady = Boolean(connectedCrm);

  const selectedTemplate = (templatesQ.data ?? []).find((t) => t.name === form.wa_template_name);

  const saveMut = useMutation({
    mutationFn: (body: Partial<Settings>) =>
      apiFetch<Settings>("/appointments/settings", { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["appointments"] }),
  });

  const launchMut = useMutation({
    mutationFn: async () => {
      await apiFetch<Settings>("/appointments/settings", {
        method: "PATCH",
        body: JSON.stringify({ ...form, setup_complete: true }),
      });
      if (connectedCrm?.key === "hubspot") {
        const hubspotPatch: Record<string, string> = {};
        if (appointmentListId) hubspotPatch.appointment_list_id = appointmentListId;
        if (confirmedListId) hubspotPatch.appointment_confirmed_list_id = confirmedListId;
        if (cancelledListId) hubspotPatch.appointment_cancelled_list_id = cancelledListId;
        if (Object.keys(hubspotPatch).length > 0) {
          await patchHubspotM.mutateAsync(hubspotPatch);
        }
      }
      const syncResult = await apiFetch<CrmSyncResult>("/appointments/sync-crm", { method: "POST" });
      return syncResult;
    },
    onSuccess: (data) => {
      showCrmSyncToast(data);
      toast.success("Appointment Manager is live");
      void queryClient.invalidateQueries({ queryKey: ["appointments"] });
      void navigate({ to: "/appointments" });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const hubspotCrm = connectedCrm?.key === "hubspot";
  const schedulingReady = Boolean(schedulingQ.data?.connected);
  const calendarApiReady = Boolean(schedulingQ.data?.google_calendar_connected || schedulingQ.data?.microsoft_calendar_connected);
  const canNextStep1 =
    crmReady &&
    Boolean(form.workspace_name?.trim());
  const canNextStep2 = !form.calendar_enabled || schedulingReady;
  const canNextStep3 = !form.wa_enabled || Boolean(form.wa_template_name);
  const canNextStep4 = !form.call_enabled || Boolean(form.appointment_agent_id);
  const canNextStep5 = !form.post_survey_enabled || Boolean(form.post_survey_order_id);
  const billingOk = billingQ.data?.allowed !== false;

  const surveyOrders = (surveysQ.data ?? []) as SurveyOrder[];

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <PageHeader
        eyebrow="Appointment Manager"
        title="Setup wizard"
        description="Connect CRM, calendar, WhatsApp, AI calls, and optional post-visit survey."
        actions={
          <Button variant="outline" asChild>
            <Link to="/appointments">Back to manager</Link>
          </Button>
        }
      />

      {billingQ.data && !billingQ.data.allowed && (
        <Card className="border-amber-500/40 bg-amber-500/5">
          <CardContent className="flex flex-wrap items-center gap-3 p-4">
            <CreditCard className="size-5 shrink-0 text-amber-600" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">Platform subscription required</p>
              <p className="text-xs text-muted-foreground">
                {billingQ.data.reason ||
                  "Appointment Manager uses your core platform package (same as surveys & interviews). Wallet top-up alone is not enough."}
              </p>
            </div>
            <Button asChild size="sm" variant="outline">
              <Link to="/account/billing">View billing</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="flex items-center gap-2 text-sm">
        {[1, 2, 3, 4, 5].map((n) => (
          <div key={n} className="flex items-center gap-2">
            <span
              className={cn(
                "grid size-7 place-items-center rounded-full text-xs font-semibold",
                step === n ? "bg-primary text-primary-foreground" : step > n ? "bg-emerald-500/15 text-emerald-600" : "bg-muted text-muted-foreground",
              )}
            >
              {step > n ? <Check className="size-3.5" /> : n}
            </span>
            <span className={cn("hidden sm:inline", step === n ? "font-medium" : "text-muted-foreground")}>
              {n === 1 ? "Basics & CRM" : n === 2 ? "Calendar" : n === 3 ? "WhatsApp" : n === 4 ? "AI call" : "Launch"}
            </span>
            {n < TOTAL_STEPS && <ChevronRight className="size-4 text-muted-foreground" />}
          </div>
        ))}
      </div>

      {step === 1 && (
        <Card>
          <CardHeader>
            <CardTitle>Step 1 — Basics & CRM</CardTitle>
            <CardDescription>Name your flow, sync schedule, and CRM object mapping.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            {!crmReady && (
              <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4">
                <p className="text-sm font-medium">Connect your CRM first</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Appointments sync from HubSpot, Pipedrive, or Zoho. Enable one in Settings → Integrations.
                </p>
                <div className="mt-3 grid gap-2 sm:grid-cols-3">
                  {CRM_PROVIDERS.map((p) => {
                    const view = crmViews.find((v) => v.key === p.id);
                    const connected = Boolean(view?.connected);
                    return (
                      <div key={p.id} className="flex items-center justify-between rounded-md border bg-background px-3 py-2 text-sm">
                        <span>{p.label}</span>
                        <span className={connected ? "text-emerald-600" : "text-muted-foreground"}>
                          {connected ? "Connected" : "Not connected"}
                        </span>
                      </div>
                    );
                  })}
                </div>
                <Button className="mt-3 gap-1.5" asChild>
                  <Link to="/settings/integrations"><Plug className="size-4" /> Open integrations</Link>
                </Button>
              </div>
            )}

            {crmReady && connectedCrm && (
              <div className="rounded-lg border bg-muted/30 px-3 py-2 text-sm">
                Active CRM: <strong>{connectedCrm.label || connectedCrm.key}</strong>
              </div>
            )}

            <div className="grid gap-2">
              <Label htmlFor="ws-name">Workspace name</Label>
              <Input
                id="ws-name"
                value={form.workspace_name ?? ""}
                onChange={(e) => patch({ workspace_name: e.target.value })}
                placeholder="Northwell Dental confirmations"
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label>Sync frequency</Label>
                <Select
                  value={String(form.sync_interval_minutes ?? 60)}
                  onValueChange={(v) => patch({ sync_interval_minutes: Number(v) })}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {SYNC_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={String(o.value)}>{o.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label>CRM object / table</Label>
                {hubspotCrm ? (
                  <>
                    <Input value="Contacts" readOnly disabled />
                    <p className="text-xs text-muted-foreground">
                      HubSpot appointment sync reads <strong>contact</strong> static lists only. Deals and other objects are not used here yet.
                    </p>
                  </>
                ) : (
                  <Select value={form.crm_object ?? "contacts"} onValueChange={(v) => patch({ crm_object: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="contacts">Contacts</SelectItem>
                      <SelectItem value="deals">Deals</SelectItem>
                      <SelectItem value="appointments">Appointments</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              </div>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="date-prop">Appointment date field</Label>
              <Input
                id="date-prop"
                value={form.crm_date_property ?? "appointment_date"}
                onChange={(e) => patch({ crm_date_property: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">HubSpot internal property name on each contact.</p>
            </div>

            {hubspotCrm && crmReady && (
              <>
                <p className="text-xs text-muted-foreground">
                  HubSpot sync is automatic: contacts with <strong>phone</strong> and your appointment date field are imported on every sync. List membership is handled for you.
                </p>
                <HubSpotAppointmentListPickers
                  appointmentListId={appointmentListId}
                  confirmedListId={confirmedListId}
                  cancelledListId={cancelledListId}
                  onChange={(patch) => {
                    if (patch.appointment_list_id !== undefined) setAppointmentListId(patch.appointment_list_id);
                    if (patch.appointment_confirmed_list_id !== undefined) setConfirmedListId(patch.appointment_confirmed_list_id);
                    if (patch.appointment_cancelled_list_id !== undefined) setCancelledListId(patch.appointment_cancelled_list_id);
                  }}
                />
              </>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label>Outreach window start</Label>
                <Input
                  type="time"
                  value={form.outreach_window_start ?? "09:00"}
                  onChange={(e) => patch({ outreach_window_start: e.target.value })}
                />
              </div>
              <div className="grid gap-2">
                <Label>Outreach window end</Label>
                <Input
                  type="time"
                  value={form.outreach_window_end ?? "16:00"}
                  onChange={(e) => patch({ outreach_window_end: e.target.value })}
                />
              </div>
            </div>

            <div className="grid gap-3 rounded-lg border p-3">
              <div className="flex items-center justify-between">
                <div>
                  <Label>Enable WhatsApp confirmation</Label>
                  <p className="text-xs text-muted-foreground">Send template before appointment</p>
                </div>
                <Switch checked={Boolean(form.wa_enabled)} onCheckedChange={(v) => patch({ wa_enabled: v })} />
              </div>
              {form.wa_enabled && (
                <div className="grid gap-2 sm:max-w-xs">
                  <Label>Send WA (hours before)</Label>
                  <Input
                    type="number"
                    min={1}
                    value={form.wa_send_hours_before ?? 72}
                    onChange={(e) => patch({ wa_send_hours_before: Number(e.target.value) })}
                  />
                </div>
              )}
              <div className="flex items-center justify-between">
                <div>
                  <Label>Enable AI call if no WA reply</Label>
                  <p className="text-xs text-muted-foreground">Trigger voice agent when customer does not respond</p>
                </div>
                <Switch checked={Boolean(form.call_enabled)} onCheckedChange={(v) => patch({ call_enabled: v })} />
              </div>
              {form.call_enabled && (
                <div className="grid gap-2 sm:max-w-xs">
                  <Label>Trigger call (hours before)</Label>
                  <Input
                    type="number"
                    min={1}
                    value={form.call_hours_before ?? 24}
                    onChange={(e) => patch({ call_hours_before: Number(e.target.value) })}
                  />
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {step === 2 && (
        <Card>
          <CardHeader>
            <CardTitle>Step 2 — Calendar</CardTitle>
            <CardDescription>
              Use your connected booking calendar for free/busy slots and write-back when appointments change.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="flex items-center justify-between rounded-lg border p-3">
              <div>
                <Label>Sync with org calendar</Label>
                <p className="text-xs text-muted-foreground">
                  Reuses the provider from Settings → Integrations (Google or Microsoft for API sync).
                </p>
              </div>
              <Switch checked={Boolean(form.calendar_enabled)} onCheckedChange={(v) => patch({ calendar_enabled: v })} />
            </div>

            {form.calendar_enabled && !schedulingReady && (
              <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm">
                <p className="font-medium">Connect a calendar provider first</p>
                <p className="mt-1 text-muted-foreground">
                  Connect Google Calendar or Microsoft 365 in Settings → Integrations → Booking.
                </p>
                <Button className="mt-3 gap-1.5" asChild size="sm" variant="outline">
                  <Link to="/settings/integrations"><Plug className="size-4" /> Open integrations</Link>
                </Button>
              </div>
            )}

            {form.calendar_enabled && schedulingReady && (
              <>
                <div className="rounded-lg border bg-muted/30 px-3 py-2 text-sm">
                  Provider: <strong>{String(schedulingQ.data?.provider_label || schedulingQ.data?.provider || "Connected")}</strong>
                  {calendarApiReady ? " · API read/write enabled" : " · Link-only provider (internal hours used for slots)"}
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="grid gap-2">
                    <Label>Slot length (minutes)</Label>
                    <Input
                      type="number"
                      min={15}
                      max={240}
                      value={form.slot_duration_minutes ?? 30}
                      onChange={(e) => patch({ slot_duration_minutes: Number(e.target.value) })}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label>Calendar ID</Label>
                    <Input
                      value={form.calendar_id ?? "primary"}
                      onChange={(e) => patch({ calendar_id: e.target.value })}
                      placeholder="primary"
                    />
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {step === 3 && form.wa_enabled && (
        <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
          <Card>
            <CardHeader>
              <CardTitle>Step 3 — WhatsApp template</CardTitle>
              <CardDescription>Preview and select an approved template (like survey templates).</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-1.5">
              {(templatesQ.data ?? []).length === 0 && !templatesQ.isLoading && (
                <p className="text-sm text-muted-foreground">No templates available yet — contact support.</p>
              )}
              {(templatesQ.data ?? []).map((t) => {
                const selected = form.wa_template_name === t.name;
                return (
                  <button
                    key={t.name}
                    type="button"
                    onClick={() => patch({ wa_template_name: t.name })}
                    className={cn(
                      "flex items-center gap-2 rounded-md border px-3 py-2 text-left transition",
                      selected ? "border-primary bg-primary/5 ring-1 ring-primary/30" : "hover:border-primary/40",
                    )}
                  >
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{t.label}</span>
                    <span className="hidden max-w-[40%] truncate text-xs text-muted-foreground sm:inline">
                      {t.description}
                    </span>
                    {t.approval_status && t.approval_status !== "APPROVED" && (
                      <span className="shrink-0 text-[10px] text-amber-600">{t.approval_status}</span>
                    )}
                    <span className="shrink-0 text-xs text-primary">
                      {selected ? <Check className="inline size-3" /> : <Eye className="inline size-3" />}
                    </span>
                  </button>
                );
              })}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-sm">iPhone preview</CardTitle></CardHeader>
            <CardContent>
              <IPhonePreview
                businessName={form.workspace_name || "Your Business"}
                body={selectedTemplate?.body?.replace(/\{\{\d+\}\}/g, "Alex") ?? "Select a template"}
                footer={selectedTemplate?.footer}
                buttons={(selectedTemplate?.buttons ?? []).map((b) => b.label)}
              />
            </CardContent>
          </Card>
        </div>
      )}

      {step === 3 && !form.wa_enabled && (
        <Card><CardContent className="p-6 text-sm text-muted-foreground">WhatsApp is disabled — continue to AI call settings.</CardContent></Card>
      )}

      {step === 4 && form.call_enabled && (
        <Card>
          <CardHeader>
            <CardTitle>Step 4 — AI call agent</CardTitle>
            <CardDescription>Choose the voice agent and when to call if WhatsApp gets no reply.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            {(agentsQ.data ?? []).length === 0 && (
              <p className="text-sm text-muted-foreground">
                No appointment agents yet. Ask your admin to enable agents with &quot;supports appointment&quot; in Admin → Agents.
              </p>
            )}
            <div className="grid gap-2 sm:grid-cols-2">
              {(agentsQ.data ?? []).map((a) => {
                const selected = form.appointment_agent_id === a.id;
                return (
                  <button
                    key={a.id}
                    type="button"
                    onClick={() => patch({ appointment_agent_id: a.id })}
                    className={cn(
                      "rounded-lg border p-3 text-left",
                      selected ? "border-primary ring-2 ring-primary/30" : "hover:border-primary/40",
                    )}
                  >
                    <p className="font-medium">{a.voice_label || a.name}</p>
                    {a.is_platform_default && <p className="text-xs text-muted-foreground">Platform default</p>}
                  </button>
                );
              })}
            </div>
            <div className="grid gap-2 sm:max-w-xs">
              <Label>Call timing (hours before appointment)</Label>
              <Input
                type="number"
                min={1}
                value={form.call_hours_before ?? 24}
                onChange={(e) => patch({ call_hours_before: Number(e.target.value) })}
              />
            </div>
          </CardContent>
        </Card>
      )}

      {step === 4 && !form.call_enabled && (
        <Card><CardContent className="p-6 text-sm text-muted-foreground">AI calls are disabled — continue to launch.</CardContent></Card>
      )}

      {step === 5 && (
        <Card>
          <CardHeader>
            <CardTitle>Step 5 — Post-visit survey & launch</CardTitle>
            <CardDescription>Optionally send a WhatsApp survey after the visit, then go live.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="flex items-center justify-between rounded-lg border p-3">
              <div>
                <Label>Send post-visit survey</Label>
                <p className="text-xs text-muted-foreground">Uses the same contact phone — no separate HubSpot list.</p>
              </div>
              <Switch checked={Boolean(form.post_survey_enabled)} onCheckedChange={(v) => patch({ post_survey_enabled: v })} />
            </div>

            {form.post_survey_enabled && (
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="grid gap-2">
                  <Label>Saved WhatsApp survey</Label>
                  <Select
                    value={form.post_survey_order_id ?? ""}
                    onValueChange={(v) => patch({ post_survey_order_id: v })}
                  >
                    <SelectTrigger><SelectValue placeholder="Choose survey campaign" /></SelectTrigger>
                    <SelectContent>
                      {surveyOrders.map((s) => (
                        <SelectItem key={s.id} value={s.id}>
                          {s.title || s.id} {s.status ? `(${s.status})` : ""}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {surveyOrders.length === 0 && (
                    <p className="text-xs text-muted-foreground">Create a survey first under Surveys, then return here.</p>
                  )}
                </div>
                <div className="grid gap-2">
                  <Label>Delay after appointment (hours)</Label>
                  <Input
                    type="number"
                    min={0}
                    max={168}
                    value={form.post_survey_delay_hours ?? 2}
                    onChange={(e) => patch({ post_survey_delay_hours: Number(e.target.value) })}
                  />
                </div>
              </div>
            )}

            <div className="grid gap-2 border-t pt-4 text-sm">
              <p><strong>Workspace:</strong> {form.workspace_name || "—"}</p>
              <p><strong>CRM:</strong> {connectedCrm?.label || "Not connected"} · sync every {form.sync_interval_minutes ?? 60}m</p>
              <p><strong>Calendar:</strong> {form.calendar_enabled ? `On · ${form.slot_duration_minutes ?? 30} min slots` : "Off"}</p>
              <p><strong>WhatsApp:</strong> {form.wa_enabled ? `On · ${form.wa_template_name} · ${form.wa_send_hours_before}h before` : "Off"}</p>
              <p><strong>AI call:</strong> {form.call_enabled ? `On · agent ${form.appointment_agent_id ?? "default"} · ${form.call_hours_before}h before` : "Off"}</p>
              <p><strong>Post-visit survey:</strong> {form.post_survey_enabled ? `On · ${form.post_survey_delay_hours ?? 2}h after` : "Off"}</p>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="flex justify-between">
        <Button variant="outline" disabled={step <= 1} onClick={() => setStep((s) => s - 1)} className="gap-1">
          <ChevronLeft className="size-4" /> Back
        </Button>
        {step < TOTAL_STEPS ? (
          <Button
            disabled={
              (step === 1 && !canNextStep1) ||
              (step === 2 && !canNextStep2) ||
              (step === 3 && !canNextStep3) ||
              (step === 4 && !canNextStep4) ||
              saveMut.isPending
            }
            onClick={async () => {
              try {
                await saveMut.mutateAsync(form);
                setStep((s) => s + 1);
              } catch (e) {
                toast.error(e instanceof Error ? e.message : "Could not save");
              }
            }}
            className="gap-1"
          >
            Next <ChevronRight className="size-4" />
          </Button>
        ) : (
          <Button
            disabled={launchMut.isPending || !crmReady || !billingOk || !canNextStep5}
            onClick={() => launchMut.mutate()}
          >
            Launch appointment manager
          </Button>
        )}
      </div>
    </div>
  );
}
