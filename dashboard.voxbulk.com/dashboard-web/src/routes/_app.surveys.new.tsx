import { createFileRoute } from "@tanstack/react-router";
import * as React from "react";
import { Upload, Download, Wand2, Lock, RotateCcw, Eye, ChevronUp, ChevronDown, Plus, X } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { WhatsAppPreviewModal, PreviewQuoteModal } from "@/components/modals";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { apiUploadFiles, downloadAuthenticatedFile } from "@/lib/api";
import { useCreateServiceOrder, usePatchServiceOrder, useSurveyPackages, useWaSurveyIndustries, useWaSurveyTypes, useWaSurveyStepBank, useGenerateWaSurvey } from "@/lib/queries";

export const Route = createFileRoute("/_app/surveys/new")({
  head: () => ({ meta: [{ title: "Create survey — VoxBulk" }] }),
  component: CreateSurvey,
});

const STEP_ROLE_LABELS: Record<string, string> = {
  start: "Start",
  completion: "Completion",
  rating: "Rating",
  yes_no: "Yes / No",
  helpfulness: "Helpfulness",
  abc_choice: "A / B / C choice",
  reason: "Reason",
  feeling_word: "Feeling word",
  follow_up: "Follow-up",
  improvement: "Improvement",
};

const PAGE_COUNT_TO_LENGTH: Record<4 | 5 | 6, "short" | "standard" | "detailed"> = {
  4: "short",
  5: "standard",
  6: "detailed",
};

function CreateSurvey() {
  const packagesQ = useSurveyPackages();
  const createM = useCreateServiceOrder();
  const patchM = usePatchServiceOrder();

  const [method, setMethod] = React.useState<"phone" | "whatsapp">("phone");
  const [waPreview, setWaPreview] = React.useState<Record<string, unknown> | null>(null);
  const [industryId, setIndustryId] = React.useState("");
  const [surveyTypeId, setSurveyTypeId] = React.useState("");
  const [privacyMode, setPrivacyMode] = React.useState<"off" | "on">("off");
  const surveyVariant = privacyMode === "on" ? "anonymous" : "standard";
  const [pageCount, setPageCount] = React.useState<4 | 5 | 6>(5);
  const [autoSelectSteps, setAutoSelectSteps] = React.useState(true);
  const [manualMiddleRoles, setManualMiddleRoles] = React.useState<string[]>([]);
  const [generating, setGenerating] = React.useState(false);
  const [waOpen, setWaOpen] = React.useState(false);
  const waIndustriesQ = useWaSurveyIndustries();
  const waTypesQ = useWaSurveyTypes(industryId || null);
  const stepBankQ = useWaSurveyStepBank(method === "whatsapp" ? surveyTypeId : null, privacyMode);
  const generateWaM = useGenerateWaSurvey();
  const [quote, setQuote] = React.useState(false);
  const [approved, setApproved] = React.useState(false);
  const [anonymous, setAnonymous] = React.useState(false);
  const [goal, setGoal] = React.useState("Measure satisfaction with our new hygienist team and identify the top 1 improvement.");
  const [script, setScript] = React.useState("1. On a scale of 0-10, how likely are you to recommend us?\n2. What stood out about your visit?\n3. Anything we could improve?");
  const [startAt, setStartAt] = React.useState("");
  const [endAt, setEndAt] = React.useState("");
  const [packageId, setPackageId] = React.useState("");
  const [orderId, setOrderId] = React.useState<string | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = React.useState(false);

  const packages = React.useMemo(() => {
    const data = packagesQ.data || {};
    const channel = method === "whatsapp" ? "whatsapp" : "ai_call";
    const list = (data.packages as Record<string, unknown[]>)?.[channel] || [];
    return list as Array<Record<string, unknown>>;
  }, [packagesQ.data, method]);

  React.useEffect(() => {
    if (packages[0] && !packageId) setPackageId(String(packages[0].id || packages[0].rule_id || ""));
  }, [packages, packageId]);

  const ensureOrder = async () => {
    if (orderId) return orderId;
    const created = await createM.mutateAsync({
      service_code: "survey",
      title: goal.slice(0, 80) || "New survey",
      config: {
        goal,
        delivery: method === "whatsapp" ? "whatsapp" : "ai_call",
        anonymous_responses: anonymous,
        script,
        package_id: packageId || undefined,
      },
    });
    setOrderId(created.id);
    return created.id;
  };

  React.useEffect(() => {
    const industries = (waIndustriesQ.data?.industries || []) as Array<Record<string, unknown>>;
    if (industries[0] && !industryId) setIndustryId(String(industries[0].id));
  }, [waIndustriesQ.data, industryId]);

  React.useEffect(() => {
    setSurveyTypeId("");
  }, [industryId]);

  React.useEffect(() => {
    const types = (waTypesQ.data?.types || []) as Array<Record<string, unknown>>;
    if (types[0] && !surveyTypeId) setSurveyTypeId(String(types[0].id));
  }, [waTypesQ.data, surveyTypeId]);

  React.useEffect(() => {
    if (privacyMode === "on") setAnonymous(true);
    else setAnonymous(false);
  }, [privacyMode]);

  const stepBankByRole = React.useMemo(
    () => (stepBankQ.data?.by_role || {}) as Record<string, { title?: string; body?: string; display_name?: string }>,
    [stepBankQ.data],
  );
  const suggestedRoles = React.useMemo(
    () => (stepBankQ.data?.suggested_page_roles || {}) as Record<string, string[]>,
    [stepBankQ.data],
  );
  const availableMiddleRoles = React.useMemo(
    () => ((stepBankQ.data?.middle_roles || []) as string[]).filter((r) => r !== "start" && r !== "completion"),
    [stepBankQ.data],
  );

  React.useEffect(() => {
    const suggested = suggestedRoles[String(pageCount)] || [];
    const middle = suggested.filter((r) => r !== "start" && r !== "completion");
    setManualMiddleRoles(middle.slice(0, Math.max(0, pageCount - 2)));
  }, [pageCount, surveyTypeId, surveyVariant, suggestedRoles]);

  const resolvedPageRoles = React.useMemo(() => {
    const auto = suggestedRoles[String(pageCount)];
    if (autoSelectSteps && auto?.length === pageCount) return auto;
    const middle = manualMiddleRoles.slice(0, Math.max(0, pageCount - 2));
    return ["start", ...middle, "completion"];
  }, [autoSelectSteps, suggestedRoles, pageCount, manualMiddleRoles]);

  const pageOrderValid =
    resolvedPageRoles.length === pageCount &&
    resolvedPageRoles[0] === "start" &&
    resolvedPageRoles[resolvedPageRoles.length - 1] === "completion" &&
    new Set(resolvedPageRoles.slice(1, -1)).size === resolvedPageRoles.slice(1, -1).length;

  const moveMiddleRole = (index: number, direction: -1 | 1) => {
    setManualMiddleRoles((prev) => {
      const next = [...prev];
      const target = index + direction;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
    setAutoSelectSteps(false);
  };

  const removeMiddleRole = (index: number) => {
    setManualMiddleRoles((prev) => prev.filter((_, i) => i !== index));
    setAutoSelectSteps(false);
  };

  const addMiddleRole = (role: string) => {
    setManualMiddleRoles((prev) => {
      if (prev.includes(role) || prev.length >= pageCount - 2) return prev;
      return [...prev, role];
    });
    setAutoSelectSteps(false);
  };

  const onGenerateWaSurvey = async () => {
    if (!pageOrderValid) {
      toast.error(`Choose ${pageCount - 2} unique middle steps between start and completion`);
      return;
    }
    setGenerating(true);
    try {
      const generated = await generateWaM.mutateAsync({
        survey_type_id: surveyTypeId,
        variant: surveyVariant,
        privacy_mode: privacyMode,
        length: PAGE_COUNT_TO_LENGTH[pageCount],
        page_count: pageCount,
        auto_select_steps: autoSelectSteps,
        selected_step_roles: autoSelectSteps ? undefined : resolvedPageRoles,
        goal,
      });
      setWaPreview(generated);
      setScript(String(generated.approved_script || script));
      setAnonymous(Boolean(generated.anonymous_responses));
      const id = await ensureOrder();
      await patchM.mutateAsync({
        orderId: id,
        body: {
          config: {
            goal,
            delivery: "whatsapp",
            anonymous_responses: Boolean(generated.anonymous_responses),
            allow_follow_up: generated.allow_follow_up !== false,
            script: String(generated.approved_script || script),
            survey_type_id: surveyTypeId,
            survey_length: PAGE_COUNT_TO_LENGTH[pageCount],
            page_count: pageCount,
            page_roles: generated.page_roles,
            survey_variant: surveyVariant,
            privacy_mode: privacyMode,
            wa_template_id: generated.wa_template_id,
            whatsapp_flow: generated.whatsapp_flow,
          },
        },
      });
      setApproved(true);
      toast.success("Survey generated from approved WhatsApp template library");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not generate survey");
    } finally {
      setGenerating(false);
    }
  };

  const onSaveDraft = async () => {
    try {
      const id = await ensureOrder();
      await patchM.mutateAsync({
        orderId: id,
        body: {
          title: goal.slice(0, 80) || "Survey draft",
          scheduled_start_at: startAt || null,
          scheduled_end_at: endAt || null,
          config: {
            goal,
            delivery: method === "whatsapp" ? "whatsapp" : "ai_call",
            anonymous_responses: anonymous,
            script,
            package_id: packageId || undefined,
          },
        },
      });
      toast.success("Draft saved");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save draft");
    }
  };

  const onUpload = async (files: FileList | null) => {
    if (!files?.length) return;
    setUploading(true);
    try {
      const id = await ensureOrder();
      await apiUploadFiles(`/service-orders/${encodeURIComponent(id)}/recipients/upload`, Array.from(files), "file");
      toast.success("Contacts uploaded");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const onDownloadTemplate = async () => {
    try {
      await downloadAuthenticatedFile("/service-orders/template.csv", "voxbulk-contacts-template.csv");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Download failed");
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader eyebrow="Surveys" title="Create new survey" description="AI phone call or WhatsApp — your choice." />

      <Card>
        <CardHeader><CardTitle>Channel</CardTitle><CardDescription>How patients will be contacted.</CardDescription></CardHeader>
        <CardContent className="space-y-4">
          <Tabs value={method} onValueChange={(v) => setMethod(v as "phone" | "whatsapp")}>
            <TabsList className="w-full sm:w-auto">
              <TabsTrigger value="phone">AI phone call</TabsTrigger>
              <TabsTrigger value="whatsapp">WhatsApp</TabsTrigger>
            </TabsList>
          </Tabs>
          {method === "whatsapp" && (
            <div className="animate-fade-in flex items-start justify-between gap-3 rounded-lg border border-border bg-background/40 p-3">
              <div>
                <p className="text-sm font-medium">Anonymous responses</p>
                <p className="text-xs text-muted-foreground">
                  When on, replies are recorded without name or phone number. Useful for honest feedback.
                </p>
              </div>
              <Switch checked={anonymous} onCheckedChange={setAnonymous} />
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>What do you want to learn?</CardTitle></CardHeader>
        <CardContent className="grid gap-5 md:grid-cols-2">
          <div className="md:col-span-2 space-y-1.5">
            <Label className="text-xs">Survey goal</Label>
            <Textarea rows={3} value={goal} onChange={(e) => setGoal(e.target.value)} />
          </div>
          {method === "whatsapp" && (
            <>
              <Field label="Industry">
                <Select value={industryId} onValueChange={setIndustryId}>
                  <SelectTrigger><SelectValue placeholder="Select industry" /></SelectTrigger>
                  <SelectContent>
                    {((waIndustriesQ.data?.industries || []) as Array<Record<string, unknown>>).map((ind) => (
                      <SelectItem key={String(ind.id)} value={String(ind.id)}>{String(ind.name)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Survey type">
                <Select value={surveyTypeId} onValueChange={setSurveyTypeId} disabled={!industryId}>
                  <SelectTrigger><SelectValue placeholder={industryId ? "Select survey type" : "Select industry first"} /></SelectTrigger>
                  <SelectContent>
                    {((waTypesQ.data?.types || []) as Array<Record<string, unknown>>).map((t) => (
                      <SelectItem key={String(t.id)} value={String(t.id)}>{String(t.name)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Privacy Mode">
                <Select value={privacyMode} onValueChange={(v) => setPrivacyMode(v as "off" | "on")}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="off">Off — identified / normal templates</SelectItem>
                    <SelectItem value="on">On — anonymous templates only</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Survey length (pages)">
                <Select value={String(pageCount)} onValueChange={(v) => setPageCount(Number(v) as 4 | 5 | 6)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="4">4 pages — start + 2 steps + completion</SelectItem>
                    <SelectItem value="5">5 pages — start + 3 steps + completion</SelectItem>
                    <SelectItem value="6">6 pages — start + 4 steps + completion</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <div className="md:col-span-2 space-y-4 rounded-lg border border-border bg-background/40 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium">Survey pages</p>
                    <p className="text-xs text-muted-foreground">
                      Pick 4–6 pages from the 10-template step bank. Start and completion are always included.
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Label htmlFor="auto-steps" className="text-xs text-muted-foreground">Auto-select best steps</Label>
                    <Switch id="auto-steps" checked={autoSelectSteps} onCheckedChange={setAutoSelectSteps} />
                  </div>
                </div>
                {stepBankQ.isLoading ? (
                  <Skeleton className="h-24 w-full" />
                ) : (
                  <>
                    {!autoSelectSteps && (
                      <div className="space-y-3">
                        <p className="text-xs font-medium text-muted-foreground">Middle steps (reorder or swap)</p>
                        <ol className="space-y-2">
                          <li className="flex items-center gap-2 rounded-md border border-border bg-muted/30 px-3 py-2 text-sm">
                            <span className="text-muted-foreground">1.</span>
                            <span className="font-medium">{STEP_ROLE_LABELS.start}</span>
                            <span className="ml-auto text-xs text-muted-foreground">Required</span>
                          </li>
                          {manualMiddleRoles.map((role, idx) => (
                            <li key={`${role}-${idx}`} className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm">
                              <span className="text-muted-foreground">{idx + 2}.</span>
                              <span className="font-medium">{STEP_ROLE_LABELS[role] || role}</span>
                              <div className="ml-auto flex items-center gap-1">
                                <Button type="button" size="icon" variant="ghost" className="size-7" onClick={() => moveMiddleRole(idx, -1)} disabled={idx === 0}>
                                  <ChevronUp className="size-4" />
                                </Button>
                                <Button type="button" size="icon" variant="ghost" className="size-7" onClick={() => moveMiddleRole(idx, 1)} disabled={idx === manualMiddleRoles.length - 1}>
                                  <ChevronDown className="size-4" />
                                </Button>
                                <Button type="button" size="icon" variant="ghost" className="size-7" onClick={() => removeMiddleRole(idx)}>
                                  <X className="size-4" />
                                </Button>
                              </div>
                            </li>
                          ))}
                          <li className="flex items-center gap-2 rounded-md border border-border bg-muted/30 px-3 py-2 text-sm">
                            <span className="text-muted-foreground">{pageCount}.</span>
                            <span className="font-medium">{STEP_ROLE_LABELS.completion}</span>
                            <span className="ml-auto text-xs text-muted-foreground">Required</span>
                          </li>
                        </ol>
                        {manualMiddleRoles.length < pageCount - 2 && (
                          <div className="flex flex-wrap gap-2">
                            {availableMiddleRoles
                              .filter((r) => !manualMiddleRoles.includes(r))
                              .map((role) => (
                                <Button key={role} type="button" size="sm" variant="outline" className="gap-1" onClick={() => addMiddleRole(role)}>
                                  <Plus className="size-3.5" /> {STEP_ROLE_LABELS[role] || role}
                                </Button>
                              ))}
                          </div>
                        )}
                      </div>
                    )}
                    <div className="space-y-2">
                      <p className="text-xs font-medium text-muted-foreground">Final page order preview</p>
                      <ol className="space-y-1.5">
                        {resolvedPageRoles.map((role, idx) => (
                          <li key={`preview-${role}-${idx}`} className="rounded-md border border-dashed border-border px-3 py-2 text-sm">
                            <span className="text-muted-foreground">{idx + 1}. </span>
                            <span className="font-medium">{STEP_ROLE_LABELS[role] || role}</span>
                            {stepBankByRole[role]?.title ? (
                              <span className="ml-2 text-xs text-muted-foreground">— {String(stepBankByRole[role].title)}</span>
                            ) : null}
                          </li>
                        ))}
                      </ol>
                      {!pageOrderValid && (
                        <p className="text-xs text-destructive">
                          Need exactly {pageCount} pages with unique middle steps between start and completion.
                        </p>
                      )}
                    </div>
                  </>
                )}
              </div>
              <div className="md:col-span-2">
                <Button className="gap-1.5" onClick={() => void onGenerateWaSurvey()} disabled={generating || !surveyTypeId || !pageOrderValid}>
                  <Wand2 className="size-4" /> {generating ? "Generating…" : "Generate"}
                </Button>
              </div>
            </>
          )}
          {method === "phone" && (
            <>
              <Field label="Max call length">
                <Select defaultValue="2">
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["1", "2", "3", "5"].map((m) => <SelectItem key={m} value={m}>{m} minutes</SelectItem>)}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="AI voice agent">
                <Select defaultValue="amelia">
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="amelia">Amelia (UK · warm)</SelectItem>
                    <SelectItem value="ravi">Ravi (UK · professional)</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Contacts</CardTitle><CardDescription>Upload patient list.</CardDescription></CardHeader>
        <CardContent>
          <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={(e) => void onUpload(e.target.files)} />
          <div className="flex flex-col items-center gap-2 rounded-xl border-2 border-dashed border-border bg-background/50 px-4 py-8 text-center sm:px-6 sm:py-10">
            <Upload className="size-6 text-muted-foreground" />
            <p className="text-sm font-medium">Upload CSV or Excel</p>
            <div className="mt-2 flex flex-col gap-2 sm:flex-row">
              <Button size="sm" onClick={() => fileRef.current?.click()} disabled={uploading}>
                {uploading ? "Uploading…" : "Choose file"}
              </Button>
              <Button size="sm" variant="outline" className="gap-1.5" onClick={() => void onDownloadTemplate()}>
                <Download className="size-3.5" /> Sample template
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>AI script</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <Textarea rows={6} value={script} onChange={(e) => setScript(e.target.value)} />
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" className="gap-1.5"><Wand2 className="size-4" /> AI write survey script</Button>
            <Button variant="outline" className="gap-1.5" onClick={() => setApproved(true)}><Lock className="size-4" /> Approve script</Button>
            <Button variant="ghost" className="gap-1.5"><RotateCcw className="size-4" /> Regenerate</Button>
            {method === "whatsapp" && (
              <Button variant="outline" className="gap-1.5" onClick={() => setWaOpen(true)}><Eye className="size-4" /> Preview WhatsApp</Button>
            )}
            <div className="ml-auto"><StatusBadge tone={approved ? "approved-script" : "draft-script"} /></div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Schedule & package</CardTitle></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
          <Field label="Start"><Input type="datetime-local" value={startAt} onChange={(e) => setStartAt(e.target.value)} /></Field>
          <Field label="End"><Input type="datetime-local" value={endAt} onChange={(e) => setEndAt(e.target.value)} /></Field>
          <Field label="Package">
            {packagesQ.isLoading ? (
              <Skeleton className="h-10 w-full" />
            ) : (
              <Select value={packageId} onValueChange={setPackageId}>
                <SelectTrigger><SelectValue placeholder="Select package" /></SelectTrigger>
                <SelectContent>
                  {packages.map((p) => (
                    <SelectItem key={String(p.id || p.rule_id)} value={String(p.id || p.rule_id)}>
                      {String(p.label || p.name || p.bundle_size || "Package")}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </Field>
        </CardContent>
      </Card>

      <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
        <Button variant="outline" onClick={() => void onSaveDraft()} disabled={createM.isPending || patchM.isPending}>
          {createM.isPending || patchM.isPending ? "Saving…" : "Save draft"}
        </Button>
        <Button className="gap-1.5" onClick={() => setQuote(true)}><Eye className="size-4" /> Preview & approve</Button>
      </div>

      <WhatsAppPreviewModal open={waOpen} onOpenChange={setWaOpen} preview={waPreview} />
      <PreviewQuoteModal open={quote} onOpenChange={setQuote} kind="survey" />
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label className="text-xs">{label}</Label>{children}</div>;
}
