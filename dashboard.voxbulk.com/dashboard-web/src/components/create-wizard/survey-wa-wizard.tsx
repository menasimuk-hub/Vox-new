import * as React from "react";
import {
  Briefcase,
  Check,
  Download,
  Eye,
  FileText,
  Lock,
  Rocket,
  Sparkles,
  Target,
  Upload,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import { StatusBadge } from "@/components/status-badge";
import { WhatsAppPreviewModal, PreviewQuoteModal } from "@/components/modals";
import { Stepper, Summary, WizardNav, type WizardStepDef } from "@/components/create-wizard";
import {
  buildSurveyTypeTemplateOptions,
  mapSystemTemplates,
  WaDraggableTypeGroup,
  WaTemplatePickerSection,
} from "@/components/create-wizard/survey-wa-template-step";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { waIndustryIcon } from "@/lib/wa-industry-icon";

const WA_STEPS: WizardStepDef[] = [
  { id: 1, title: "Industry", subtitle: "Your sector", icon: Briefcase },
  { id: 2, title: "Survey type", subtitle: "1–4 topics", icon: Target },
  { id: 3, title: "Template", subtitle: "Welcome & flow", icon: FileText },
  { id: 4, title: "Contacts", subtitle: "Upload list", icon: Users },
  { id: 5, title: "Preview", subtitle: "Review flow", icon: Eye },
  { id: 6, title: "Launch", subtitle: "Schedule & go", icon: Rocket },
];

export type SurveyWaWizardProps = {
  onBack: () => void;
  anonymous: boolean;
  industryId: string;
  setIndustryId: (v: string) => void;
  industries: Array<Record<string, unknown>>;
  industriesLoading: boolean;
  selectedServiceTagIds: string[];
  orderedServiceTagIds: string[];
  setOrderedServiceTagIds: React.Dispatch<React.SetStateAction<string[]>>;
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
  selectedServiceTemplateIds: Record<string, string>;
  onSelectServiceTemplate: (typeId: string, templateId: string) => void;
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
  onGenerateWaSurvey: () => Promise<boolean>;
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
  const [draggedServiceIndex, setDraggedServiceIndex] = React.useState<number | null>(null);
  const [dragOverServiceIndex, setDragOverServiceIndex] = React.useState<number | null>(null);
  const [contactsSkipped, setContactsSkipped] = React.useState(false);

  const selectedIndustry = props.industries.find((i) => String(i.id) === props.industryId);
  const welcomeTemplateRows = React.useMemo(
    () => mapSystemTemplates(props.welcomeTemplates),
    [props.welcomeTemplates],
  );
  const thankYouTemplateRows = React.useMemo(
    () => mapSystemTemplates(props.thankYouTemplates),
    [props.thankYouTemplates],
  );

  const templatePickCount =
    (props.welcomeTemplateId ? 1 : 0) +
    (props.thankYouTemplateId ? 1 : 0) +
    props.orderedServiceTagIds.filter((id) => Boolean(props.selectedServiceTemplateIds[id])).length;
  const templatePickTotal = props.orderedServiceTagIds.length + 2;

  const reorderServices = (from: number, to: number) => {
    if (from === to) return;
    props.setOrderedServiceTagIds((prev) => {
      const next = [...prev];
      const [removed] = next.splice(from, 1);
      next.splice(to, 0, removed);
      return next;
    });
  };

  const moveService = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= props.orderedServiceTagIds.length) return;
    reorderServices(index, target);
  };

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
        !!props.welcomeTemplateId &&
        !!props.thankYouTemplateId &&
        props.orderedServiceTagIds.length >= 1 &&
        props.orderedServiceTagIds.every((id) => Boolean(props.selectedServiceTemplateIds[id]))
      );
    }
    if (step === 4) return true;
    if (step === 5) return props.approved;
    return true;
  }, [step, props]);

  const goNext = async () => {
    if (!canNext) {
      if (step === 2 && props.serviceTagErrors[0]) toast.error(props.serviceTagErrors[0]);
      else if (step === 3) toast.error("Pick welcome, thank-you, and one template for each survey type");
      return;
    }
    if (step === 3 && !props.approved) {
      const ok = await props.onGenerateWaSurvey();
      if (!ok) return;
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
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
                  {props.industries.map((ind) => {
                    const id = String(ind.id);
                    const active = props.industryId === id;
                    const industryName = String(ind.name || ind.label || "");
                    const IndustryIcon = waIndustryIcon(industryName, String(ind.slug || ind.industry_slug || ""));
                    return (
                      <button
                        key={id}
                        type="button"
                        onClick={() => props.setIndustryId(id)}
                        className={cn(
                          "group flex flex-col items-start gap-2 rounded-xl border p-3 text-left transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md",
                          active ? "border-primary bg-primary/5 shadow-md ring-1 ring-primary/30" : "border-border bg-background/40",
                        )}
                      >
                        <div
                          className={cn(
                            "grid size-10 place-items-center rounded-lg ring-1 transition-transform group-hover:scale-105",
                            active ? "bg-primary text-primary-foreground ring-primary/40" : "bg-primary/10 text-primary ring-primary/20",
                          )}
                        >
                          <IndustryIcon className="size-5" />
                        </div>
                        <p className="text-sm font-semibold leading-tight">{industryName || "Industry"}</p>
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
                  <p className="text-sm font-medium text-primary">Quick tip — keep it short</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Most surveys perform best with just 3 questions. Short surveys get up to 3x more responses than long ones.
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
                {props.selectedServiceTagIds.length >= 1 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs text-muted-foreground"
                    type="button"
                    onClick={() => {
                      for (const id of [...props.selectedServiceTagIds]) props.toggleServiceTag(id);
                      props.setOrderedServiceTagIds([]);
                    }}
                  >
                    Clear all
                  </Button>
                )}
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
                <FileText className="size-4 text-primary" /> Step 3 · Select & arrange templates
              </CardTitle>
              <CardDescription>Pick welcome & thanks templates, then one survey template per type. Drag to reorder the flow.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">
                  Selected:{" "}
                  <span
                    className={cn(
                      "font-semibold",
                      templatePickCount >= templatePickTotal ? "text-success" : "text-primary",
                    )}
                  >
                    {templatePickCount}
                  </span>{" "}
                  / {templatePickTotal}
                </p>
              </div>

              <WaTemplatePickerSection
                label="Welcome message"
                badge="Opening"
                templates={welcomeTemplateRows}
                selectedId={props.welcomeTemplateId}
                onSelect={props.setWelcomeTemplateId}
              />

              <div className="space-y-3">
                <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Survey questions — drag to reorder
                </p>
                {props.orderedServiceTagIds.length === 0 ? (
                  <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
                    Select at least one survey type in step 2 to configure templates here.
                  </p>
                ) : (
                  props.orderedServiceTagIds.map((typeId, idx) => {
                    const row = props.serviceTypes.find((t) => String(t.id) === typeId);
                    if (!row) return null;
                    const serviceName = String(row.name);
                    const isPrimary = typeId === props.orderedServiceTagIds[0];
                    const bankEntry =
                      isPrimary && props.stepBankByRole.rating
                        ? props.stepBankByRole.rating
                        : props.stepBankByRole[props.resolvedPageRoles[1] || "rating"];
                    const libraryBody = String(bankEntry?.body || bankEntry?.display_name || "").trim();
                    return (
                      <div
                        key={typeId}
                        className={cn(
                          "overflow-hidden rounded-xl border border-transparent transition-all duration-200",
                          draggedServiceIndex === idx && "scale-[0.98] border-dashed border-primary/50 opacity-40 shadow-inner",
                          dragOverServiceIndex === idx &&
                            draggedServiceIndex !== idx &&
                            "translate-y-0.5 border-primary bg-primary/5 shadow-md",
                        )}
                        onDragOver={(e) => {
                          e.preventDefault();
                          setDragOverServiceIndex(idx);
                        }}
                        onDragLeave={() => setDragOverServiceIndex(null)}
                        onDrop={() => {
                          if (draggedServiceIndex !== null) reorderServices(draggedServiceIndex, idx);
                          setDraggedServiceIndex(null);
                          setDragOverServiceIndex(null);
                        }}
                      >
                        <WaDraggableTypeGroup
                          serviceName={serviceName}
                          index={idx}
                          total={props.orderedServiceTagIds.length}
                          templates={buildSurveyTypeTemplateOptions(serviceName, typeId, libraryBody)}
                          selectedId={props.selectedServiceTemplateIds[typeId] || ""}
                          onSelect={(id) => props.onSelectServiceTemplate(typeId, id)}
                          onMoveUp={idx > 0 ? () => moveService(idx, -1) : undefined}
                          onMoveDown={idx < props.orderedServiceTagIds.length - 1 ? () => moveService(idx, 1) : undefined}
                          onDragStart={() => setDraggedServiceIndex(idx)}
                          onDragEnd={() => {
                            setDraggedServiceIndex(null);
                            setDragOverServiceIndex(null);
                          }}
                          isDragging={draggedServiceIndex === idx}
                          isDragOver={dragOverServiceIndex === idx && draggedServiceIndex !== idx}
                        />
                      </div>
                    );
                  })
                )}
              </div>

              <WaTemplatePickerSection
                label="Thank-you message"
                badge="Closing"
                templates={thankYouTemplateRows}
                selectedId={props.thankYouTemplateId}
                onSelect={props.setThankYouTemplateId}
              />
            </CardContent>
          </Card>
        )}

        {step === 4 && (
          <Card className="animate-scale-in">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="size-4 text-primary" /> Step 4 · Upload contacts
              </CardTitle>
              <CardDescription>CSV or Excel with at least name and phone columns. You can upload later.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <input ref={props.fileRef} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={(e) => void props.onUpload(e.target.files)} />
              <label className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed border-border bg-background/50 px-4 py-10 text-center transition hover:border-primary/40 hover:bg-primary/5">
                <div className="rounded-full bg-primary/10 p-3 ring-1 ring-primary/20">
                  <Upload className="size-6 text-primary" />
                </div>
                <p className="text-sm font-medium">Click to upload CSV or Excel</p>
                <p className="text-xs text-muted-foreground">Columns: name, phone, language (optional)</p>
                <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                  <Button size="sm" type="button" onClick={() => props.fileRef.current?.click()} disabled={props.uploading}>
                    {props.uploading ? "Uploading…" : "Choose file"}
                  </Button>
                  <Button size="sm" type="button" variant="outline" className="gap-1.5" onClick={() => void props.onDownloadTemplate()}>
                    <Download className="size-3.5" /> Sample template
                  </Button>
                  <Button
                    size="sm"
                    type="button"
                    variant="ghost"
                    className="gap-1.5 text-muted-foreground"
                    onClick={() => {
                      setContactsSkipped(true);
                      goNext();
                    }}
                  >
                    Skip for now
                  </Button>
                </div>
              </label>
              {contactsSkipped ? (
                <p className="text-xs text-muted-foreground">Contacts skipped — you can upload a list later from the survey order.</p>
              ) : null}
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
        onNext={() => void goNext()}
        nextDisabled={!canNext || (step === 3 && props.generating)}
        skippable={step === 4}
        onSkip={() => {
          setContactsSkipped(true);
          goNext();
        }}
        skipLabel="Skip for now"
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
