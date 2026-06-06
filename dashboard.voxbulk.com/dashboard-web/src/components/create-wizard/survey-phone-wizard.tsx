import * as React from "react";
import { Download, Lock, Phone, Rocket, RotateCcw, Sparkles, Target, Upload, Users, Wand2 } from "lucide-react";
import { toast } from "sonner";

import { StatusBadge } from "@/components/status-badge";
import { PreviewQuoteModal } from "@/components/modals";
import { Stepper, Summary, WizardNav, type WizardStepDef } from "@/components/create-wizard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

const PHONE_STEPS: WizardStepDef[] = [
  { id: 1, title: "Goal & script", subtitle: "Questions & voice", icon: Target },
  { id: 2, title: "Contacts", subtitle: "Upload & schedule", icon: Users },
  { id: 3, title: "Launch", subtitle: "Preview & go", icon: Rocket },
];

const VOICE_LABELS: Record<string, string> = {
  amelia: "Amelia (UK · warm)",
  ravi: "Ravi (UK · professional)",
  nora: "Nora (US · neutral)",
};

export type SurveyPhoneWizardProps = {
  onBack: () => void;
  anonymous: boolean;
  goal: string;
  setGoal: (v: string) => void;
  script: string;
  setScript: (v: string) => void;
  approved: boolean;
  setApproved: (v: boolean) => void;
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      {children}
    </div>
  );
}

export function SurveyPhoneWizard(props: SurveyPhoneWizardProps) {
  const [step, setStep] = React.useState(1);
  const [quote, setQuote] = React.useState(false);
  const [voice, setVoice] = React.useState("amelia");

  const canNext = React.useMemo(() => {
    if (step === 1) {
      return props.goal.trim().length > 0 && props.script.trim().length > 0 && props.approved;
    }
    if (step === 2) return true;
    return true;
  }, [step, props.goal, props.script, props.approved]);

  const goNext = () => {
    if (!canNext) {
      if (step === 1 && !props.approved) {
        toast.error("Approve your script before continuing");
      } else if (step === 1) {
        toast.error("Add a survey goal and script before continuing");
      }
      return;
    }
    setStep((s) => Math.min(PHONE_STEPS.length, s + 1));
  };

  const voiceLabel = VOICE_LABELS[voice]?.split(" (")[0] || "Amelia";
  const selectedPackage = props.packages.find((p) => String(p.id || p.rule_id) === props.packageId);

  return (
    <>
      <Stepper steps={PHONE_STEPS} current={step} onStepClick={(n) => n < step && setStep(n)} />

      <div key={step} className="animate-fade-in">
        {step === 1 && (
          <Card className="animate-scale-in">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Target className="size-4 text-primary" /> Step 1 · Survey goal & script
              </CardTitle>
              <CardDescription>Tell the AI what you need to learn — it drafts a natural phone conversation.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="flex items-start gap-3 rounded-xl border border-primary/15 bg-primary/5 p-4">
                <div className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/20">
                  <Sparkles className="size-3.5" />
                </div>
                <div>
                  <p className="text-sm font-medium text-primary">Keep calls short and friendly</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    3–5 clear questions work best. The AI voice agent reads your approved script on each call.
                  </p>
                </div>
              </div>

              <Field label="Survey goal">
                <Textarea rows={3} value={props.goal} onChange={(e) => props.setGoal(e.target.value)} />
              </Field>

              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="AI voice agent">
                  <Select value={voice} onValueChange={setVoice}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="amelia">Amelia (UK · warm)</SelectItem>
                      <SelectItem value="ravi">Ravi (UK · professional)</SelectItem>
                      <SelectItem value="nora">Nora (US · neutral)</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                <Field label="Max call length">
                  <Select defaultValue="2">
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {["1", "2", "3", "5"].map((m) => (
                        <SelectItem key={m} value={m}>
                          {m} minutes
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
              </div>

              <Field label="Script">
                <Textarea rows={6} value={props.script} onChange={(e) => props.setScript(e.target.value)} />
              </Field>

              <div className="flex flex-wrap items-center gap-2">
                <Button variant="outline" className="gap-1.5" disabled>
                  <Wand2 className="size-4" /> AI write survey script
                </Button>
                <Button variant="outline" className="gap-1.5" onClick={() => props.setApproved(true)}>
                  <Lock className="size-4" /> Approve script
                </Button>
                <Button
                  variant="ghost"
                  className="gap-1.5"
                  onClick={() => {
                    props.setApproved(false);
                    toast.message("Edit the script, then approve again when ready.");
                  }}
                >
                  <RotateCcw className="size-4" /> Regenerate
                </Button>
                <div className="ml-auto">
                  <StatusBadge tone={props.approved ? "approved-script" : "draft-script"} />
                </div>
              </div>

              {props.anonymous ? (
                <p className="text-[11px] text-muted-foreground">
                  Anonymous mode on — answers are transcribed without saving caller identity.
                </p>
              ) : null}
            </CardContent>
          </Card>
        )}

        {step === 2 && (
          <Card className="animate-scale-in">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="size-4 text-primary" /> Step 2 · Contacts & calling window
              </CardTitle>
              <CardDescription>Upload patients and choose when the AI may call.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <input
                ref={props.fileRef}
                type="file"
                accept=".csv,.xlsx,.xls"
                className="hidden"
                onChange={(e) => void props.onUpload(e.target.files)}
              />
              <div className="group relative overflow-hidden rounded-xl border-2 border-dashed border-border bg-gradient-to-br from-background/60 via-background/40 to-accent/20 px-4 py-10 text-center transition-colors hover:border-primary/40 sm:px-6">
                <div className="relative flex flex-col items-center gap-2">
                  <div className="rounded-full bg-primary/10 p-3 ring-1 ring-primary/20 transition-transform group-hover:scale-110">
                    <Upload className="size-6 text-primary" />
                  </div>
                  <p className="text-sm font-medium">Upload CSV or Excel</p>
                  <p className="text-xs text-muted-foreground">Columns: name, phone (required)</p>
                  <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                    <Button size="sm" onClick={() => props.fileRef.current?.click()} disabled={props.uploading}>
                      {props.uploading ? "Uploading…" : "Choose file"}
                    </Button>
                    <Button size="sm" variant="outline" className="gap-1.5" onClick={() => void props.onDownloadTemplate()}>
                      <Download className="size-3.5" /> Sample template
                    </Button>
                    <Button size="sm" type="button" variant="ghost" className="gap-1.5 text-muted-foreground" onClick={goNext}>
                      Skip for now
                    </Button>
                  </div>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <Field label="Calling start">
                  <Input type="datetime-local" value={props.startAt} onChange={(e) => props.setStartAt(e.target.value)} />
                </Field>
                <Field label="Calling end">
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
            </CardContent>
          </Card>
        )}

        {step === 3 && (
          <Card className="animate-scale-in">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Rocket className="size-4 text-primary" /> Step 3 · Preview & launch
              </CardTitle>
              <CardDescription>Hear a sample call flow and confirm everything before launch.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-2xl border border-border bg-gradient-to-br from-background to-accent/10 p-5">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <div className="grid size-9 place-items-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/20">
                      <Phone className="size-4" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold">{voiceLabel} · sample call</p>
                      <p className="text-xs text-muted-foreground">AI phone survey preview</p>
                    </div>
                  </div>
                  <span className="shrink-0 rounded-full bg-success/15 px-2 py-0.5 text-[11px] font-medium text-success">
                    ~2 min call
                  </span>
                </div>
                <div className="space-y-2">
                  {props.script
                    .split("\n")
                    .filter(Boolean)
                    .slice(0, 4)
                    .map((q, i) => (
                      <div key={i} className="flex gap-3 rounded-lg border border-border bg-background p-3 text-sm">
                        <span className="grid size-6 shrink-0 place-items-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">
                          {i + 1}
                        </span>
                        <span>{q.replace(/^\d+\.\s*/, "")}</span>
                      </div>
                    ))}
                </div>
              </div>

              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                <Summary label="Channel" value="AI phone call" />
                <Summary label="Voice" value={voiceLabel} />
                <Summary label="Anonymous" value={props.anonymous ? "On" : "Off"} />
                <Summary label="Script" value={props.approved ? "Approved" : "Draft"} />
              </div>

              {(props.startAt || props.endAt || selectedPackage) && (
                <div className="grid gap-2 sm:grid-cols-3">
                  <Summary label="Calling start" value={props.startAt || "Not set"} />
                  <Summary label="Calling end" value={props.endAt || "Not set"} />
                  <Summary
                    label="Package"
                    value={String(selectedPackage?.label || selectedPackage?.name || selectedPackage?.bundle_size || "—")}
                  />
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      <WizardNav
        step={step}
        total={PHONE_STEPS.length}
        onBack={props.onBack}
        onPrev={() => setStep((s) => Math.max(1, s - 1))}
        onNext={goNext}
        nextDisabled={!canNext}
        skippable={step === 2}
        onSkip={goNext}
        skipLabel="Skip for now"
        finalLabel="Preview & launch"
        onFinish={() => setQuote(true)}
        finishDisabled={!props.approved}
        leftActions={
          <Button variant="outline" className="gap-1.5" onClick={() => void props.onSaveDraft()} disabled={props.savePending}>
            {props.savePending ? "Saving…" : "Save draft"}
          </Button>
        }
      />

      <PreviewQuoteModal open={quote} onOpenChange={setQuote} kind="survey" />
    </>
  );
}
