import * as React from "react";
import {
  Briefcase,
  Check,
  ChevronDown,
  ChevronUp,
  Download,
  Eye,
  FileText,
  Lock,
  Plus,
  Rocket,
  Sparkles,
  Target,
  Upload,
  Users,
  Wand2,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { StatusBadge } from "@/components/status-badge";
import { WhatsAppPreviewModal, PreviewQuoteModal } from "@/components/modals";
import { Stepper, Summary, WizardNav, type WizardStepDef } from "@/components/create-wizard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const WA_STEPS: WizardStepDef[] = [
  { id: 1, title: "Industry", subtitle: "Your sector", icon: Briefcase },
  { id: 2, title: "Services", subtitle: "1–4 topics", icon: Target },
  { id: 3, title: "Configure", subtitle: "Templates & pages", icon: FileText },
  { id: 4, title: "Contacts", subtitle: "Upload list", icon: Users },
  { id: 5, title: "Preview", subtitle: "Script & WA", icon: Eye },
  { id: 6, title: "Launch", subtitle: "Schedule & go", icon: Rocket },
];

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

export type SurveyWaWizardProps = {
  onBack: () => void;
  anonymous: boolean;
  industryId: string;
  setIndustryId: (v: string) => void;
  industries: Array<Record<string, unknown>>;
  industriesLoading: boolean;
  selectedServiceTagIds: string[];
  toggleServiceTag: (id: string) => void;
  serviceTypes: Array<Record<string, unknown>>;
  serviceTypesLoading: boolean;
  serviceTagErrors: string[];
  welcomeTemplateId: string;
  setWelcomeTemplateId: (v: string) => void;
  thankYouTemplateId: string;
  setThankYouTemplateId: (v: string) => void;
  welcomeTemplates: Array<Record<string, unknown>>;
  thankYouTemplates: Array<Record<string, unknown>>;
  privacyMode: "off" | "on";
  setPrivacyMode: (v: "off" | "on") => void;
  pageCount: 4 | 5 | 6;
  setPageCount: (v: 4 | 5 | 6) => void;
  autoSelectSteps: boolean;
  setAutoSelectSteps: (v: boolean) => void;
  manualMiddleRoles: string[];
  moveMiddleRole: (index: number, direction: -1 | 1) => void;
  removeMiddleRole: (index: number) => void;
  addMiddleRole: (role: string) => void;
  availableMiddleRoles: string[];
  resolvedPageRoles: string[];
  pageOrderValid: boolean;
  stepBankByRole: Record<string, { title?: string; body?: string; display_name?: string }>;
  stepBankLoading: boolean;
  goal: string;
  setGoal: (v: string) => void;
  script: string;
  setScript: (v: string) => void;
  approved: boolean;
  setApproved: (v: boolean) => void;
  generating: boolean;
  onGenerateWaSurvey: () => Promise<void>;
  waPreview: Record<string, unknown> | null;
  startAt: string;
  setStartAt: (v: string) => void;
  endAt: string;
  setEndAt: (v: string) => void;
  packageId: string;
  setPackageId: (v: string) => void;
  packages: Array<Record<string, unknown>>;
  packagesLoading: boolean;
  fileRef: React.RefObject<HTMLInputElement | null>;
  uploading: boolean;
  onUpload: (files: FileList | null) => void;
  onDownloadTemplate: () => void;
  onSaveDraft: () => void;
  savePending: boolean;
};

export function SurveyWaWizard(props: SurveyWaWizardProps) {
  const [step, setStep] = React.useState(1);
  const [quote, setQuote] = React.useState(false);
  const [waOpen, setWaOpen] = React.useState(false);

  const selectedIndustry = props.industries.find((i) => String(i.id) === props.industryId);

  const canNext = React.useMemo(() => {
    if (step === 1) return !!props.industryId;
    if (step === 2) {
      if (props.selectedServiceTagIds.length < 1) return false;
      for (const id of props.selectedServiceTagIds) {
        const row = props.serviceTypes.find((t) => String(t.id) === id);
        if (row && !row.has_wa_template) return false;
      }
      return true;
    }
    if (step === 3) {
      return (
        props.goal.trim().length > 0 &&
        !!props.welcomeTemplateId &&
        !!props.thankYouTemplateId &&
        props.pageOrderValid &&
        props.approved
      );
    }
    if (step === 5) return props.approved;
    return true;
  }, [step, props]);

  const goNext = () => {
    if (!canNext) {
      if (step === 2 && props.serviceTagErrors[0]) toast.error(props.serviceTagErrors[0]);
      else if (step === 3 && !props.approved) toast.error("Generate and approve your survey before continuing");
      return;
    }
    setStep((s) => Math.min(WA_STEPS.length, s + 1));
  };

  return (
    <>
      <Stepper steps={WA_STEPS} current={step} onStepClick={(n) => n < step && setStep(n)} />

      <div key={step} className="animate-fade-in">
        {step === 1 && (
          <Card className="animate-scale-in">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Briefcase className="size-4 text-primary" /> Step 1 · Choose your industry
              </CardTitle>
              <CardDescription>This tailors survey types and WhatsApp templates to your business.</CardDescription>
            </CardHeader>
            <CardContent>
              {props.industriesLoading ? (
                <Skeleton className="h-32 w-full" />
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {props.industries.map((ind) => {
                    const id = String(ind.id);
                    const active = props.industryId === id;
                    return (
                      <button
                        key={id}
                        type="button"
                        onClick={() => props.setIndustryId(id)}
                        className={cn(
                          "group flex flex-col items-start gap-2 rounded-xl border p-4 text-left transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md",
                          active ? "border-primary bg-primary/5 shadow-md ring-1 ring-primary/30" : "border-border bg-background/40",
                        )}
                      >
                        <div
                          className={cn(
                            "grid size-10 place-items-center rounded-lg ring-1 transition-transform group-hover:scale-105",
                            active ? "bg-primary text-primary-foreground ring-primary/40" : "bg-primary/10 text-primary ring-primary/20",
                          )}
                        >
                          <Briefcase className="size-5" />
                        </div>
                        <p className="text-sm font-semibold leading-tight">{String(ind.name)}</p>
                        {active ? (
                          <span className="inline-flex items-center gap-1 text-[11px] font-medium text-primary">
                            <Check className="size-3" /> Selected
                          </span>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {step === 2 && (
          <Card className="animate-scale-in">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Target className="size-4 text-primary" /> Step 2 · What do you want to measure?
              </CardTitle>
              <CardDescription>
                Pick 1–4 services for this survey
                {selectedIndustry ? ` — ${String(selectedIndustry.name)}` : ""}.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-start gap-3 rounded-xl border border-primary/15 bg-primary/5 p-4">
                <div className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/20">
                  <Sparkles className="size-3.5" />
                </div>
                <div>
                  <p className="text-sm font-medium text-primary">Select 1–4 services</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Each service needs an approved WhatsApp template. Shorter surveys get more responses.
                  </p>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">
                  Selected:{" "}
                  <span
                    className={cn(
                      "font-semibold",
                      props.selectedServiceTagIds.length === 0
                        ? "text-muted-foreground"
                        : props.selectedServiceTagIds.length === 4
                          ? "text-warning"
                          : "text-primary",
                    )}
                  >
                    {props.selectedServiceTagIds.length}
                  </span>{" "}
                  / 4
                </p>
              </div>
              {props.serviceTypesLoading ? (
                <Skeleton className="h-10 w-full" />
              ) : (
                <div className="flex flex-wrap gap-2">
                  {props.serviceTypes.map((t) => {
                    const id = String(t.id);
                    const active = props.selectedServiceTagIds.includes(id);
                    const missingTemplate = !t.has_wa_template;
                    const disabled = !active && props.selectedServiceTagIds.length >= 4;
                    return (
                      <button
                        key={id}
                        type="button"
                        onClick={() => props.toggleServiceTag(id)}
                        disabled={disabled || !props.industryId}
                        className={cn(
                          "rounded-full border px-3.5 py-1.5 text-sm transition-all",
                          active && "border-primary bg-primary text-primary-foreground shadow",
                          !active && !disabled && !missingTemplate && "border-border bg-background hover:border-primary/40 hover:bg-primary/5",
                          missingTemplate && !active && "border-destructive/50 text-destructive/80",
                          disabled && "cursor-not-allowed border-border bg-muted/40 text-muted-foreground/50",
                        )}
                      >
                        {active ? <Check className="mr-1 inline size-3.5" /> : null}
                        {String(t.name)}
                      </button>
                    );
                  })}
                </div>
              )}
              {props.serviceTagErrors.length ? (
                <p className="text-xs text-destructive">{props.serviceTagErrors[0]}</p>
              ) : (
                <p className="text-xs text-muted-foreground">{props.selectedServiceTagIds.length} of 4 selected</p>
              )}
            </CardContent>
          </Card>
        )}

        {step === 3 && (
          <Card className="animate-scale-in">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="size-4 text-primary" /> Step 3 · Configure & generate
              </CardTitle>
              <CardDescription>Templates, privacy, survey pages, then generate from your approved library.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-5 md:grid-cols-2">
              <div className="md:col-span-2 space-y-1.5">
                <Label className="text-xs">Survey goal</Label>
                <Textarea rows={3} value={props.goal} onChange={(e) => props.setGoal(e.target.value)} />
              </div>
              <Field label="Welcome template">
                <Select value={props.welcomeTemplateId} onValueChange={props.setWelcomeTemplateId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select welcome template" />
                  </SelectTrigger>
                  <SelectContent>
                    {props.welcomeTemplates.map((t) => (
                      <SelectItem key={String(t.id)} value={String(t.id)}>
                        {String(t.display_name || t.name || t.id)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Thank-you template">
                <Select value={props.thankYouTemplateId} onValueChange={props.setThankYouTemplateId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select thank-you template" />
                  </SelectTrigger>
                  <SelectContent>
                    {props.thankYouTemplates.map((t) => (
                      <SelectItem key={String(t.id)} value={String(t.id)}>
                        {String(t.display_name || t.name || t.id)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Privacy mode">
                <Select value={props.privacyMode} onValueChange={(v) => props.setPrivacyMode(v as "off" | "on")}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="off">Off — identified / normal templates</SelectItem>
                    <SelectItem value="on">On — anonymous templates only</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Survey length (pages)">
                <Select value={String(props.pageCount)} onValueChange={(v) => props.setPageCount(Number(v) as 4 | 5 | 6)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
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
                    <p className="text-xs text-muted-foreground">Pick 4–6 pages from the step bank. Start and completion are always included.</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Label htmlFor="auto-steps" className="text-xs text-muted-foreground">
                      Auto-select best steps
                    </Label>
                    <Switch id="auto-steps" checked={props.autoSelectSteps} onCheckedChange={props.setAutoSelectSteps} />
                  </div>
                </div>
                {props.stepBankLoading ? (
                  <Skeleton className="h-24 w-full" />
                ) : (
                  <>
                    {!props.autoSelectSteps && (
                      <div className="space-y-3">
                        <p className="text-xs font-medium text-muted-foreground">Middle steps (reorder or swap)</p>
                        <ol className="space-y-2">
                          <li className="flex items-center gap-2 rounded-md border border-border bg-muted/30 px-3 py-2 text-sm">
                            <span className="text-muted-foreground">1.</span>
                            <span className="font-medium">{STEP_ROLE_LABELS.start}</span>
                            <span className="ml-auto text-xs text-muted-foreground">Required</span>
                          </li>
                          {props.manualMiddleRoles.map((role, idx) => (
                            <li key={`${role}-${idx}`} className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm">
                              <span className="text-muted-foreground">{idx + 2}.</span>
                              <span className="font-medium">{STEP_ROLE_LABELS[role] || role}</span>
                              <div className="ml-auto flex items-center gap-1">
                                <Button type="button" size="icon" variant="ghost" className="size-7" onClick={() => props.moveMiddleRole(idx, -1)} disabled={idx === 0}>
                                  <ChevronUp className="size-4" />
                                </Button>
                                <Button type="button" size="icon" variant="ghost" className="size-7" onClick={() => props.moveMiddleRole(idx, 1)} disabled={idx === props.manualMiddleRoles.length - 1}>
                                  <ChevronDown className="size-4" />
                                </Button>
                                <Button type="button" size="icon" variant="ghost" className="size-7" onClick={() => props.removeMiddleRole(idx)}>
                                  <X className="size-4" />
                                </Button>
                              </div>
                            </li>
                          ))}
                          <li className="flex items-center gap-2 rounded-md border border-border bg-muted/30 px-3 py-2 text-sm">
                            <span className="text-muted-foreground">{props.pageCount}.</span>
                            <span className="font-medium">{STEP_ROLE_LABELS.completion}</span>
                            <span className="ml-auto text-xs text-muted-foreground">Required</span>
                          </li>
                        </ol>
                        {props.manualMiddleRoles.length < props.pageCount - 2 && (
                          <div className="flex flex-wrap gap-2">
                            {props.availableMiddleRoles
                              .filter((r) => !props.manualMiddleRoles.includes(r))
                              .map((role) => (
                                <Button key={role} type="button" size="sm" variant="outline" className="gap-1" onClick={() => props.addMiddleRole(role)}>
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
                        {props.resolvedPageRoles.map((role, idx) => (
                          <li key={`preview-${role}-${idx}`} className="rounded-md border border-dashed border-border px-3 py-2 text-sm">
                            <span className="text-muted-foreground">{idx + 1}. </span>
                            <span className="font-medium">{STEP_ROLE_LABELS[role] || role}</span>
                            {props.stepBankByRole[role]?.title ? (
                              <span className="ml-2 text-xs text-muted-foreground">— {String(props.stepBankByRole[role].title)}</span>
                            ) : null}
                          </li>
                        ))}
                      </ol>
                      {!props.pageOrderValid && (
                        <p className="text-xs text-destructive">
                          Need exactly {props.pageCount} pages with unique middle steps between start and completion.
                        </p>
                      )}
                    </div>
                  </>
                )}
              </div>
              <div className="md:col-span-2 flex flex-wrap items-center gap-2">
                <Button
                  className="gap-1.5"
                  onClick={() => void props.onGenerateWaSurvey()}
                  disabled={
                    props.generating ||
                    props.selectedServiceTagIds.length === 0 ||
                    !props.pageOrderValid ||
                    props.serviceTagErrors.length > 0
                  }
                >
                  <Wand2 className="size-4" /> {props.generating ? "Generating…" : "Generate survey"}
                </Button>
                {props.approved ? (
                  <span className="inline-flex items-center gap-1 text-xs text-success">
                    <Check className="size-3.5" /> Generated & saved
                  </span>
                ) : null}
              </div>
              {props.anonymous ? (
                <p className="md:col-span-2 text-[11px] text-muted-foreground">
                  Anonymous responses on — WhatsApp replies are recorded without name or phone.
                </p>
              ) : null}
            </CardContent>
          </Card>
        )}

        {step === 4 && (
          <Card className="animate-scale-in">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="size-4 text-primary" /> Step 4 · Upload contacts
              </CardTitle>
              <CardDescription>CSV or Excel with at least name and phone columns.</CardDescription>
            </CardHeader>
            <CardContent>
              <input ref={props.fileRef} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={(e) => void props.onUpload(e.target.files)} />
              <div className="flex flex-col items-center gap-2 rounded-xl border-2 border-dashed border-border bg-background/50 px-4 py-10 text-center">
                <div className="rounded-full bg-primary/10 p-3 ring-1 ring-primary/20">
                  <Upload className="size-6 text-primary" />
                </div>
                <p className="text-sm font-medium">Upload CSV or Excel</p>
                <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                  <Button size="sm" onClick={() => props.fileRef.current?.click()} disabled={props.uploading}>
                    {props.uploading ? "Uploading…" : "Choose file"}
                  </Button>
                  <Button size="sm" variant="outline" className="gap-1.5" onClick={() => void props.onDownloadTemplate()}>
                    <Download className="size-3.5" /> Sample template
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {step === 5 && (
          <Card className="animate-scale-in">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Eye className="size-4 text-primary" /> Step 5 · Script & WhatsApp preview
              </CardTitle>
              <CardDescription>Review the generated script and preview the WhatsApp flow.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Textarea rows={6} value={props.script} onChange={(e) => props.setScript(e.target.value)} />
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" className="gap-1.5" onClick={() => setWaOpen(true)} disabled={!props.waPreview}>
                  <Eye className="size-4" /> Preview WhatsApp
                </Button>
                <Button variant="outline" className="gap-1.5" onClick={() => props.setApproved(true)} disabled={props.approved}>
                  <Lock className="size-4" /> Approve script
                </Button>
                <div className="ml-auto">
                  <StatusBadge tone={props.approved ? "approved-script" : "draft-script"} />
                </div>
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                <Summary label="Industry" value={selectedIndustry ? String(selectedIndustry.name) : "—"} />
                <Summary label="Services" value={String(props.selectedServiceTagIds.length)} />
                <Summary label="Pages" value={String(props.pageCount)} />
                <Summary label="Anonymous" value={props.anonymous ? "On" : "Off"} />
              </div>
            </CardContent>
          </Card>
        )}

        {step === 6 && (
          <Card className="animate-scale-in">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Rocket className="size-4 text-primary" /> Step 6 · Schedule & launch
              </CardTitle>
              <CardDescription>Set your calling window and package, then preview and approve.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-3">
                <Field label="Start">
                  <Input type="datetime-local" value={props.startAt} onChange={(e) => props.setStartAt(e.target.value)} />
                </Field>
                <Field label="End">
                  <Input type="datetime-local" value={props.endAt} onChange={(e) => props.setEndAt(e.target.value)} />
                </Field>
                <Field label="Package">
                  {props.packagesLoading ? (
                    <Skeleton className="h-10 w-full" />
                  ) : (
                    <Select value={props.packageId} onValueChange={props.setPackageId}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select package" />
                      </SelectTrigger>
                      <SelectContent>
                        {props.packages.map((p) => (
                          <SelectItem key={String(p.id || p.rule_id)} value={String(p.id || p.rule_id)}>
                            {String(p.label || p.name || p.bundle_size || "Package")}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                </Field>
              </div>
              <div className="grid gap-2 sm:grid-cols-3">
                <Summary label="Channel" value="WhatsApp" />
                <Summary label="Script" value={props.approved ? "Approved" : "Draft"} />
                <Summary label="Privacy" value={props.privacyMode === "on" ? "Anonymous" : "Standard"} />
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      <WizardNav
        step={step}
        total={WA_STEPS.length}
        onBack={props.onBack}
        onPrev={() => setStep((s) => Math.max(1, s - 1))}
        onNext={goNext}
        nextDisabled={!canNext}
        onFinish={() => setQuote(true)}
        finishDisabled={!props.approved}
        leftActions={
          <Button variant="outline" className="gap-1.5" onClick={() => void props.onSaveDraft()} disabled={props.savePending}>
            {props.savePending ? "Saving…" : "Save draft"}
          </Button>
        }
      />

      <WhatsAppPreviewModal open={waOpen} onOpenChange={setWaOpen} preview={props.waPreview} />
      <PreviewQuoteModal open={quote} onOpenChange={setQuote} kind="survey" />
    </>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      {children}
    </div>
  );
}
