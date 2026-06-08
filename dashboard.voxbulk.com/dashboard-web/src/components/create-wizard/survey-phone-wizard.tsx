import * as React from "react";
import { Download, Lock, Phone, Rocket, RotateCcw, Sparkles, Target, Upload, Users, Wand2 } from "lucide-react";
import { toast } from "sonner";

import { parseScriptQuestions } from "@/lib/interview-script";
import type { SurveyAgent } from "@/lib/queries";
import { StatusBadge } from "@/components/status-badge";
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

export type SurveyPhoneWizardProps = {
  onBack: () => void;
  anonymous: boolean;
  goal: string;
  setGoal: (v: string) => void;
  script: string;
  setScript: (v: string) => void;
  approved: boolean;
  setApproved: (v: boolean) => void;
  agentId: string;
  setAgentId: (v: string) => void;
  agents: SurveyAgent[];
  agentsLoading: boolean;
  onGenerateScript: () => void | Promise<void>;
  generatePending: boolean;
  expectedDurationMinutes?: number;
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
  contactsCount?: number;
  launchBlockers?: string[];
  onOpenLaunch: () => void | Promise<void>;
  launchPending?: boolean;
};

function Field({ label, children, error }: { label: string; children: React.ReactNode; error?: string }) {
  return (
    <div className="space-y-1.5">
      <Label className={`text-xs ${error ? "text-destructive" : ""}`}>{label}</Label>
      {children}
      {error ? <p className="text-[11px] text-destructive">{error}</p> : null}
    </div>
  );
}

export function SurveyPhoneWizard(props: SurveyPhoneWizardProps) {
  const [step, setStep] = React.useState(1);

  const selectedAgent = props.agents.find((a) => a.id === props.agentId);
  const agentLabel = selectedAgent?.voice_label || selectedAgent?.name || "Survey agent";
  const questionCount = React.useMemo(() => parseScriptQuestions(props.script).length, [props.script]);
  const missingCallingWindow = !props.startAt || !props.endAt;
  const launchBlockers = props.launchBlockers || [];

  const canNext = React.useMemo(() => {
    if (step === 1) {
      return (
        props.goal.trim().length > 0 &&
        props.script.trim().length > 0 &&
        props.approved &&
        Boolean(props.agentId)
      );
    }
    if (step === 2) return !missingCallingWindow;
    return true;
  }, [step, props.goal, props.script, props.approved, props.agentId, missingCallingWindow]);

  const goNext = () => {
    if (!canNext) {
      if (step === 1 && !props.approved) {
        toast.error("Approve your script before continuing");
      } else if (step === 1 && !props.agentId) {
        toast.error("Select a survey voice agent");
      } else if (step === 1) {
        toast.error("Add a survey goal and script before continuing");
      } else if (step === 2 && missingCallingWindow) {
        toast.error("Set calling start and end date/time");
      }
      return;
    }
    setStep((s) => Math.min(PHONE_STEPS.length, s + 1));
  };

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
              <CardDescription>
                Tell the AI what you need to learn — it drafts a natural phone survey (up to 4 questions).
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="flex items-start gap-3 rounded-xl border border-primary/15 bg-primary/5 p-4">
                <div className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/20">
                  <Sparkles className="size-3.5" />
                </div>
                <div>
                  <p className="text-sm font-medium text-primary">Keep calls short and friendly</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    AI generates up to 4 questions. You can edit or add your own before approving — billing is per call.
                  </p>
                </div>
              </div>

              <Field label="Survey goal">
                <Textarea rows={3} value={props.goal} onChange={(e) => props.setGoal(e.target.value)} />
              </Field>

              <Field label="AI voice agent">
                {props.agentsLoading ? (
                  <Skeleton className="h-10 w-full" />
                ) : props.agents.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    No survey agents configured yet. Ask your admin to enable survey voice agents.
                  </p>
                ) : (
                  <Select value={props.agentId} onValueChange={props.setAgentId}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select survey agent" />
                    </SelectTrigger>
                    <SelectContent>
                      {props.agents.map((a) => (
                        <SelectItem key={a.id} value={a.id}>
                          {a.voice_label || a.name}
                          {a.is_default_for_org ? " · default" : a.is_zone_match ? " · GB" : ""}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </Field>

              <Field label="Survey script">
                <Textarea rows={10} value={props.script} onChange={(e) => props.setScript(e.target.value)} className="font-mono text-sm" />
                {questionCount > 4 ? (
                  <p className="text-[11px] text-amber-700 dark:text-amber-400">
                    {questionCount} questions detected — AI generation is capped at 4; longer scripts are allowed if you wrote them manually.
                  </p>
                ) : null}
              </Field>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  className="gap-1.5"
                  disabled={props.generatePending || !props.goal.trim() || !props.agentId}
                  onClick={() => void props.onGenerateScript()}
                >
                  <Wand2 className="size-4" /> {props.generatePending ? "Generating…" : "AI write survey script"}
                </Button>
                <Button
                  variant="outline"
                  className="gap-1.5"
                  disabled={!props.script.trim()}
                  onClick={() => {
                    props.setApproved(true);
                    toast.success("Script approved — save draft or continue to contacts");
                  }}
                >
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
                  <RotateCcw className="size-4" /> Reset approval
                </Button>
                <div className="ml-auto flex items-center gap-2">
                  {props.expectedDurationMinutes ? (
                    <span className="text-[11px] text-muted-foreground">~{props.expectedDurationMinutes} min/call</span>
                  ) : null}
                  <StatusBadge tone={props.approved ? "approved-script" : "draft-script"} />
                </div>
              </div>

              {props.anonymous ? (
                <p className="text-[11px] text-muted-foreground">
                  Anonymous mode on — answers are aggregated without identifying individuals in reports.
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
              <CardDescription>Upload contacts and choose when the AI may place survey calls.</CardDescription>
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
                  {(props.contactsCount ?? 0) > 0 ? (
                    <p className="text-xs font-medium text-foreground">{props.contactsCount} contact(s) ready</p>
                  ) : null}
                  <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                    <Button size="sm" onClick={() => props.fileRef.current?.click()} disabled={props.uploading}>
                      {props.uploading ? "Uploading…" : "Choose file"}
                    </Button>
                    <Button size="sm" variant="outline" className="gap-1.5" onClick={() => void props.onDownloadTemplate()}>
                      <Download className="size-3.5" /> Sample template
                    </Button>
                  </div>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <Field label="Calling start (date & time)" error={!props.startAt ? "Required" : undefined}>
                  <Input type="datetime-local" value={props.startAt} onChange={(e) => props.setStartAt(e.target.value)} />
                </Field>
                <Field label="Calling end (date & time)" error={!props.endAt ? "Required" : undefined}>
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
              <CardDescription>Review your survey script and calling window, then launch — billed per call.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {launchBlockers.length > 0 ? (
                <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 px-4 py-3 text-sm">
                  <p className="font-medium text-foreground">Before launch:</p>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-muted-foreground">
                    {launchBlockers.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <div className="rounded-2xl border border-border bg-gradient-to-br from-background to-accent/10 p-5">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <div className="grid size-9 place-items-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/20">
                      <Phone className="size-4" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold">{agentLabel} · sample call</p>
                      <p className="text-xs text-muted-foreground">AI phone survey preview</p>
                    </div>
                  </div>
                  <span className="shrink-0 rounded-full bg-success/15 px-2 py-0.5 text-[11px] font-medium text-success">
                    ~{props.expectedDurationMinutes || 3} min call
                  </span>
                </div>
                <div className="space-y-2">
                  {parseScriptQuestions(props.script).slice(0, 4).map((q) => (
                    <div key={q.index} className="flex gap-3 rounded-lg border border-border bg-background p-3 text-sm">
                      <span className="grid size-6 shrink-0 place-items-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">
                        {q.index}
                      </span>
                      <span>{q.text}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                <Summary label="Channel" value="AI phone call" />
                <Summary label="Voice agent" value={agentLabel} />
                <Summary label="Anonymous" value={props.anonymous ? "On" : "Off"} />
                <Summary label="Script" value={props.approved ? "Approved" : "Draft"} />
              </div>

              <div className="grid gap-2 sm:grid-cols-3">
                <Summary label="Calling start" value={props.startAt || "Not set"} />
                <Summary label="Calling end" value={props.endAt || "Not set"} />
                <Summary label="Contacts" value={String(props.contactsCount ?? 0)} />
              </div>
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
        finalLabel="Preview & launch"
        onFinish={() => void props.onOpenLaunch()}
        finishDisabled={!props.approved || props.launchPending || launchBlockers.length > 0}
        leftActions={
          <Button variant="outline" className="gap-1.5" onClick={() => void props.onSaveDraft()} disabled={props.savePending}>
            {props.savePending ? "Saving…" : "Save draft"}
          </Button>
        }
      />
    </>
  );
}
