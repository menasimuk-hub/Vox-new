import { createFileRoute, useSearch } from "@tanstack/react-router";
import * as React from "react";
import { ListChecks, Phone, Plug, Wand2, Play, Check, CalendarCheck } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import { useSaveServiceApiSettings, useSchedulingStatus, useServiceApiSettings, useTestServiceApiSettings } from "@/lib/queries";

export const Route = createFileRoute("/_app/settings/system")({
  head: () => ({ meta: [{ title: "System settings — VoxBulk" }] }),
  component: SystemSettings,
  validateSearch: (s: Record<string, unknown>) => ({
    scheduling: typeof s.scheduling === "string" ? s.scheduling : undefined,
    provider: typeof s.provider === "string" ? s.provider : undefined,
  }),
});

function SystemSettings() {
  const search = useSearch({ from: "/_app/settings/system" });
  const settingsQ = useServiceApiSettings();
  const schedulingQ = useSchedulingStatus();
  const saveM = useSaveServiceApiSettings();
  const testM = useTestServiceApiSettings();

  React.useEffect(() => {
    if (search.scheduling === "connected") {
      toast.success(`Connected ${search.provider || "scheduling"} successfully`);
      void schedulingQ.refetch();
    }
  }, [search.scheduling, search.provider, schedulingQ]);

  const service = (settingsQ.data?.service || null) as Record<string, unknown> | null;
  const requiredFields = (settingsQ.data?.required_fields || []) as Array<{ key: string; label: string; secret?: boolean; placeholder?: string }>;
  const connection = (settingsQ.data?.connection || {}) as Record<string, unknown>;
  const config = (connection.config || {}) as Record<string, string>;
  const scheduling = (schedulingQ.data || {}) as Record<string, unknown>;

  const [formConfig, setFormConfig] = React.useState<Record<string, string>>({});
  const [enabled, setEnabled] = React.useState(true);

  React.useEffect(() => {
    setFormConfig({ ...config });
    setEnabled(connection.is_enabled !== false);
  }, [config, connection.is_enabled]);

  const serviceName = String(service?.display_name || "External service");
  const interviewReady = scheduling.interview_booking_ready !== false;

  const startOAuth = async (provider: "calendly" | "cronofy") => {
    try {
      const data = await apiFetch<{ authorize_url?: string }>(`/service-orders/scheduling/oauth/${provider}/start`);
      if (data?.authorize_url) {
        window.location.href = data.authorize_url;
        return;
      }
      toast.error("No authorization URL returned");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "OAuth start failed");
    }
  };

  const onSaveConnection = async () => {
    try {
      await saveM.mutateAsync({ is_enabled: enabled, config: formConfig });
      toast.success("Connection settings saved");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Save failed");
    }
  };

  const onValidate = async () => {
    try {
      const res = await testM.mutateAsync();
      if (res.ok) toast.success(res.message || "Connection looks good");
      else toast.error(res.message || "Validation failed");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Validation failed");
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Settings"
        title="System"
        description="Practice management API, interview booking, and optional calendar integrations."
        actions={<Button variant="outline" className="gap-1.5"><ListChecks className="size-4" /> Show setup checklist</Button>}
      />

      <Tabs defaultValue="api">
        <TabsList>
          <TabsTrigger value="api">API connections</TabsTrigger>
          <TabsTrigger value="wa">WhatsApp</TabsTrigger>
          <TabsTrigger value="ai">AI calling</TabsTrigger>
        </TabsList>

        <TabsContent value="api" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><CalendarCheck className="size-5 text-success" /> Interview booking</CardTitle>
              <CardDescription>
                Interviews use VoxBulk native booking links — candidates pick a slot from your campaign window. No Calendly or Cronofy setup required.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {schedulingQ.isLoading ? (
                <Skeleton className="h-10 w-full" />
              ) : (
                <div className="flex items-center gap-2 text-sm">
                  <span className={"size-2 rounded-full " + (interviewReady ? "bg-success" : "bg-warning")} />
                  {interviewReady ? "Ready — send booking invites from any live interview campaign" : "Not configured"}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>External service connection</CardTitle>
              <CardDescription>{service ? String(service.short_description || serviceName) : "Select booking software during onboarding."}</CardDescription>
            </CardHeader>
            <CardContent>
              {settingsQ.isLoading ? (
                <Skeleton className="h-24 w-full" />
              ) : service ? (
                <div className="rounded-lg border border-primary bg-primary/5 p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{serviceName}</span>
                    <span className="inline-flex items-center gap-1 text-[11px] text-success">
                      <Check className="size-3" /> {connection.configured ? "Configured" : "Needs setup"}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] text-muted-foreground">{String(service.slug || "")}</p>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No booking software selected for this organisation yet.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Credentials for {serviceName}</CardTitle>
              <CardDescription>Save API keys for your connected practice management system.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2">
              {settingsQ.isLoading ? (
                <Skeleton className="md:col-span-2 h-24 w-full" />
              ) : requiredFields.length === 0 ? (
                <p className="md:col-span-2 text-sm text-muted-foreground">No credential fields for the selected service.</p>
              ) : (
                requiredFields.map((f) => (
                  <Field key={f.key} label={f.label}>
                    <Input
                      type={f.secret ? "password" : "text"}
                      placeholder={f.placeholder}
                      value={formConfig[f.key] || ""}
                      onChange={(e) => setFormConfig((prev) => ({ ...prev, [f.key]: e.target.value }))}
                    />
                  </Field>
                ))
              )}
              <div className="md:col-span-2 flex flex-wrap gap-2">
                <Button variant="outline" onClick={() => void onValidate()} disabled={testM.isPending || !service}>
                  {testM.isPending ? "Validating…" : "Validate"}
                </Button>
                <Button onClick={() => void onSaveConnection()} disabled={saveM.isPending || !service}>
                  {saveM.isPending ? "Saving…" : "Save & connect"}
                </Button>
                <Button variant="outline" className="gap-1.5 ml-auto"><Phone className="size-4" /> Call me now (test AI)</Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Optional external calendars</CardTitle>
              <CardDescription>Only needed if you want Calendly or Cronofy links instead of VoxBulk booking. Interviews work without these.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" className="gap-1.5" onClick={() => void startOAuth("calendly")}><Plug className="size-4" /> Connect Calendly</Button>
                <Button variant="outline" className="gap-1.5" onClick={() => void startOAuth("cronofy")}><Plug className="size-4" /> Connect Cronofy</Button>
              </div>
              <div className="space-y-2 text-sm">
                <Health name="Calendly (optional)" ok={Boolean(scheduling.calendly_connected)} />
                <Health name="Cronofy (optional)" ok={Boolean(scheduling.cronofy_connected)} />
                <Health name={`${serviceName} · sync`} ok={Boolean(connection.configured)} />
                <Health name="WhatsApp Business" ok />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="wa" className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
            <Card>
              <CardHeader><CardTitle>Reminder template</CardTitle><CardDescription>Variables: {"{first_name}, {time}, {clinic_name}"}</CardDescription></CardHeader>
              <CardContent className="space-y-4">
                <Textarea rows={4} defaultValue="Hi {first_name}, this is a reminder of your appointment at {clinic_name} on {time}. Tap below to confirm or reschedule." />
                <div className="grid gap-3 md:grid-cols-2">
                  <Field label="Confirm button label"><Input defaultValue="Confirm" /></Field>
                  <Field label="Reschedule button label"><Input defaultValue="Reschedule" /></Field>
                </div>
                <div className="flex justify-end"><Button>Save all templates</Button></div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="text-base">Live preview</CardTitle></CardHeader>
              <CardContent>
                <div className="mx-auto w-full max-w-[260px] overflow-hidden rounded-[1.5rem] border-[8px] border-foreground/90 bg-muted">
                  <div className="bg-primary px-3 py-2 text-[11px] text-primary-foreground">Your clinic</div>
                  <div className="flex flex-col gap-2 p-3 text-[11px]">
                    <div className="self-start rounded-lg bg-card p-2 shadow-sm text-foreground">
                      Hi Sarah, this is a reminder of your appointment on Thu 10:30.
                      <div className="mt-2 flex gap-1">
                        <span className="rounded-md bg-accent px-2 py-1 text-[10px] text-accent-foreground">Confirm</span>
                        <span className="rounded-md bg-accent px-2 py-1 text-[10px] text-accent-foreground">Reschedule</span>
                      </div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="ai" className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Voice</CardTitle></CardHeader>
            <CardContent className="flex flex-wrap items-end gap-3">
              <Field label="Voice">
                <Select defaultValue="amelia">
                  <SelectTrigger className="w-56"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="amelia">Amelia (UK · warm)</SelectItem>
                    <SelectItem value="ravi">Ravi (UK · professional)</SelectItem>
                    <SelectItem value="nora">Nora (US · neutral)</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Button variant="outline" className="gap-1.5"><Play className="size-4" /> Preview</Button>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Calling behaviour</CardTitle></CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-3">
              <Field label="Max attempts"><Input type="number" defaultValue={3} /></Field>
              <Field label="Call hours">
                <Select defaultValue="business">
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="business">9:00 – 18:00</SelectItem>
                    <SelectItem value="extended">8:00 – 20:00</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Field label="No-answer behaviour">
                <Select defaultValue="whatsapp">
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="whatsapp">Send WhatsApp</SelectItem>
                    <SelectItem value="retry">Retry tomorrow</SelectItem>
                    <SelectItem value="stop">Stop</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Script builder</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <Field label="Purpose"><Input defaultValue="Rebook missed hygiene appointments" /></Field>
              <Field label="Tone">
                <Select defaultValue="warm">
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="warm">Warm & friendly</SelectItem>
                    <SelectItem value="formal">Formal</SelectItem>
                    <SelectItem value="concise">Brief & concise</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Textarea rows={5} defaultValue="Hi {first_name}, this is Amelia from your clinic..." />
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" className="gap-1.5"><Wand2 className="size-4" /> Generate AI script</Button>
                <Button variant="outline">Edit script manually</Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label className="text-xs">{label}</Label>{children}</div>;
}
function Health({ name, ok }: { name: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between rounded-md border border-border p-2.5">
      <div className="flex items-center gap-2">
        <span className={"size-2 rounded-full " + (ok ? "bg-success" : "bg-muted-foreground/40")} />
        {name}
      </div>
      <Switch checked={ok} disabled />
    </div>
  );
}
