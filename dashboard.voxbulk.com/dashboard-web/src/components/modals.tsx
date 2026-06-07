import * as React from "react";
import { Link } from "@tanstack/react-router";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/status-badge";
import { WaBookingPhonePreview } from "@/components/wa-booking-phone-preview";
import { WaSurveyPhonePreview } from "@/components/wa-survey-phone-preview";
import { parseScriptQuestions } from "@/lib/interview-script";
import { ATS_ANALYZING_LABEL } from "@/lib/interview-campaign";
import {
  AlertCircle,
  CheckCircle2,
  ClipboardCheck,
  Clock,
  Coins,
  CreditCard,
  FileText,
  Lock,
  LockOpen,
  MessageSquare,
  PhoneCall,
  PlayCircle,
  ReceiptText,
  Rocket,
  ShieldCheck,
  Users,
} from "lucide-react";

export function ConfirmDialog({
  open, onOpenChange, title, message, confirmLabel = "Confirm", destructive,
}: {
  open: boolean; onOpenChange: (v: boolean) => void; title: string; message: string;
  confirmLabel?: string; destructive?: boolean;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{message}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant={destructive ? "destructive" : "default"} onClick={() => onOpenChange(false)}>{confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function PaymentModal({
  open,
  onOpenChange,
  amount = "£412.00",
  busy,
  gcAvailable = true,
  onPayGoCardless,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  amount?: string;
  busy?: boolean;
  gcAvailable?: boolean;
  onPayGoCardless?: () => void | Promise<void>;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Pay {amount}</DialogTitle>
          <DialogDescription>Pay securely with GoCardless direct debit to launch your campaign.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <PayBtn
            icon={<CreditCard className="size-4" />}
            title="Pay with GoCardless"
            sub="Direct debit · secure checkout"
            disabled={!gcAvailable || busy}
            onClick={() => void onPayGoCardless?.()}
          />
          {!gcAvailable && (
            <p className="text-xs text-muted-foreground">GoCardless is not configured. Contact support or check admin integrations.</p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function PreviewQuoteModal({
  open, onOpenChange, kind,
}: { open: boolean; onOpenChange: (v: boolean) => void; kind: "interview" | "survey" }) {
  const [showPay, setShowPay] = React.useState(false);
  const [approved, setApproved] = React.useState(false);
  const isInterview = kind === "interview";
  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[92vh] max-w-6xl overflow-y-auto p-0">
          <div className="border-b border-border bg-card px-6 py-5">
            <DialogHeader>
              <div className="flex flex-wrap items-start justify-between gap-3 pr-8">
                <div>
                  <DialogTitle>{isInterview ? "Interview preview & approval" : "Survey preview & approval"}</DialogTitle>
                  <DialogDescription>
                    Review the real participant experience, script, checks, schedule, and quote before payment is unlocked.
                  </DialogDescription>
                </div>
                <StatusBadge tone={approved ? "approved-script" : "draft-script"} label={approved ? "Preview approved" : "Needs approval"} />
              </div>
            </DialogHeader>
          </div>

          <div className="grid gap-0 lg:grid-cols-[1.35fr_0.85fr]">
            <div className="space-y-5 p-6">
              <div className="grid gap-3 sm:grid-cols-3">
                <PreviewMetric icon={<Users className="size-4" />} label={isInterview ? "Candidates" : "Patients"} value={isInterview ? "12 ready" : "640 ready"} />
                <PreviewMetric icon={<PhoneCall className="size-4" />} label="Channel" value={isInterview ? "AI phone" : "Phone + WhatsApp"} />
                <PreviewMetric icon={<ReceiptText className="size-4" />} label="Est. cost" value={isInterview ? "£412.00" : "£328.00"} />
              </div>

              {isInterview ? <InterviewPreview /> : <SurveyPreview />}
            </div>

            <aside className="border-t border-border bg-muted/25 p-6 lg:border-l lg:border-t-0">
              <div className="space-y-5">
                <Panel title="Approval checklist" icon={<ClipboardCheck className="size-4" />}>
                  <ChecklistItem done text={isInterview ? "Job role and candidate list confirmed" : "Patient list and audience confirmed"} />
                  <ChecklistItem done text="Script wording reviewed" />
                  <ChecklistItem done text="Calling window and quiet hours set" />
                  <ChecklistItem done text="Opt-out and recording notice included" />
                  <ChecklistItem done={approved} text="Owner approved final preview" />
                </Panel>

                <Panel title="Quote breakdown" icon={<Coins className="size-4" />}>
                  <QuoteRow label={isInterview ? "AI interview calls" : "AI survey calls"} value={isInterview ? "12 × £24.50" : "420 × £0.38"} />
                  <QuoteRow label={isInterview ? "Transcript + scoring" : "WhatsApp responses"} value={isInterview ? "£78.00" : "220 × £0.18"} />
                  <QuoteRow label="Platform checks" value={isInterview ? "£40.00" : "£88.80"} />
                  <div className="my-2 border-t border-border" />
                  <QuoteRow label="Total due after approval" value={isInterview ? "£412.00" : "£328.00"} bold />
                </Panel>

                <div className="rounded-xl border border-warning/40 bg-warning/10 p-3 text-xs text-warning-foreground">
                  <div className="flex gap-2">
                    <AlertCircle className="mt-0.5 size-4 shrink-0" />
                    <p>Payment is disabled until this preview is approved. Going back to edit resets the approval.</p>
                  </div>
                </div>
              </div>
            </aside>
          </div>

          <DialogFooter className="sticky bottom-0 border-t border-border bg-background/95 px-6 py-4 backdrop-blur sm:justify-between sm:space-x-0">
            <div className="flex flex-col-reverse gap-2 sm:flex-row">
              <Button variant="ghost" onClick={() => { setApproved(false); onOpenChange(false); }}>Back to edit</Button>
              <Button variant="outline">Save draft</Button>
            </div>
            <div className="flex flex-col-reverse gap-2 sm:flex-row">
              <Button variant={approved ? "outline" : "default"} className="gap-1.5" onClick={() => setApproved(true)}>
                <CheckCircle2 className="size-4" /> Approve preview
              </Button>
              <Button disabled={!approved} onClick={() => { onOpenChange(false); setShowPay(true); }} className="gap-1.5">
                <Coins className="size-4" /> {isInterview ? "Pay & launch interviews" : "Pay & schedule survey"}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <PaymentModal open={showPay} onOpenChange={setShowPay} amount={isInterview ? "£412.00" : "£328.00"} />
    </>
  );
}

function InterviewPreview() {
  return (
    <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
      <Panel title="Candidate call preview" icon={<PlayCircle className="size-4" />}>
        <div className="rounded-2xl border border-border bg-background p-4">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold">Amelia · UK warm voice</p>
              <p className="text-xs text-muted-foreground">Senior dental hygienist screening</p>
            </div>
            <span className="rounded-full bg-success/15 px-2 py-0.5 text-[11px] font-medium text-success">Sample 4m 30s</span>
          </div>
          <div className="space-y-3 text-sm">
            <Speech who="AI">Hi Alex, this is Amelia calling on behalf of Northwell Dental about your hygienist application. Is now still a good time?</Speech>
            <Speech who="Candidate">Yes, I have around ten minutes.</Speech>
            <Speech who="AI">Great. I’ll ask five short questions about GDC registration, clinical experience, anxious patients, diary availability, and notice period.</Speech>
          </div>
        </div>
      </Panel>

      <Panel title="Scoring rubric" icon={<FileText className="size-4" />}>
        <ScoreLine label="GDC registration confirmed" value={25} />
        <ScoreLine label="3+ years relevant experience" value={20} />
        <ScoreLine label="Communication clarity" value={20} />
        <ScoreLine label="Patient empathy examples" value={20} />
        <ScoreLine label="Availability and salary fit" value={15} />
        <div className="mt-3 rounded-lg border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
          HR output includes ATS score, call audio, transcript, red flags, recommendation, and next-step note.
        </div>
      </Panel>

      <Panel title="Questions candidates will hear" icon={<PhoneCall className="size-4" />}>
        {[
          "Can you confirm your GDC registration and current indemnity status?",
          "Tell me about your experience with nervous or anxious patients.",
          "Which dental systems and charting workflows are you comfortable with?",
          "What working days and notice period should the practice plan around?",
        ].map((item, index) => <NumberedLine key={item} index={index + 1} text={item} />)}
      </Panel>

      <Panel title="Launch schedule" icon={<ShieldCheck className="size-4" />}>
        <TimelineLine label="CV collection closes" value="Thu 4 Jun · 17:00" />
        <TimelineLine label="Calls begin" value="Fri 5 Jun · 09:00" />
        <TimelineLine label="Quiet hours" value="After 18:00 + Sunday evening" />
        <TimelineLine label="Auto-send report" value="When each call completes" />
      </Panel>
    </div>
  );
}

function SurveyPreview() {
  return (
    <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
      <Panel title="Patient WhatsApp preview" icon={<MessageSquare className="size-4" />}>
        <div className="mx-auto max-w-[320px] rounded-2xl border border-border bg-muted p-3">
          <div className="rounded-xl bg-background p-3 text-xs">
            <p className="font-semibold">Northwell Dental</p>
            <p className="text-muted-foreground">Patient experience survey</p>
          </div>
          <div className="mt-3 space-y-2 text-xs">
            <ChatBubble>Hi Sarah, thanks for visiting Northwell Dental. Can we ask 3 quick questions about your hygienist appointment?</ChatBubble>
            <ChatBubble>On a scale of 0–10, how likely are you to recommend us?</ChatBubble>
            <ChatBubble self>9</ChatBubble>
            <ChatBubble>Thanks. What stood out about your visit?</ChatBubble>
          </div>
        </div>
      </Panel>

      <Panel title="Question preview" icon={<FileText className="size-4" />}>
        <QuestionPreview type="NPS" title="How likely are you to recommend us?" detail="0–10 scale · calculates promoters, passives, detractors" />
        <QuestionPreview type="CSAT" title="Overall satisfaction with the visit" detail="1–5 rating · shown by clinic and channel" />
        <QuestionPreview type="Open text" title="What could we improve?" detail="AI theme clustering, sentiment, and action suggestions" />
      </Panel>

      <Panel title="Data privacy and opt-out" icon={<ShieldCheck className="size-4" />}>
        <ChecklistItem done text="Anonymous aggregate reporting enabled" />
        <ChecklistItem done text="Opt-out wording included in first message" />
        <ChecklistItem done text="No clinical advice or diagnosis questions" />
        <ChecklistItem done text="Low-confidence answers flagged for review" />
      </Panel>

      <Panel title="Schedule" icon={<PhoneCall className="size-4" />}>
        <TimelineLine label="Start" value="Mon 1 Jun · 09:00" />
        <TimelineLine label="First reminder" value="+24h to non-responders" />
        <TimelineLine label="Final reminder" value="+72h only once" />
        <TimelineLine label="Close" value="Mon 8 Jun · 18:00" />
      </Panel>
    </div>
  );
}

function PreviewMetric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-background p-3">
      <div className="flex items-center gap-2 text-muted-foreground">
        {icon}<span className="text-[11px] uppercase tracking-wider">{label}</span>
      </div>
      <p className="mt-2 text-xl font-semibold tracking-tight">{value}</p>
    </div>
  );
}

function Panel({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <span className="grid size-7 place-items-center rounded-md bg-primary/10 text-primary">{icon}</span>
        {title}
      </div>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function ChecklistItem({ done, text }: { done: boolean; text: string }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className={done ? "text-success" : "text-muted-foreground"}><CheckCircle2 className="size-4" /></span>
      <span className={done ? "text-foreground" : "text-muted-foreground"}>{text}</span>
    </div>
  );
}

function QuoteRow({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <div className={"flex items-center justify-between gap-3 text-sm " + (bold ? "font-semibold text-foreground" : "text-muted-foreground")}>
      <span>{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  );
}

function Speech({ who, children }: { who: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-muted/30 p-3">
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-primary">{who}</p>
      <p className="text-sm leading-relaxed">{children}</p>
    </div>
  );
}

function ScoreLine({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-3 text-xs">
      <span className="w-36 text-muted-foreground">{label}</span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-border">
        <div className="h-full rounded-full bg-success" style={{ width: `${value * 4}%` }} />
      </div>
      <span className="w-8 text-right tabular-nums">{value}</span>
    </div>
  );
}

function NumberedLine({ index, text }: { index: number; text: string }) {
  return (
    <div className="flex gap-3 rounded-lg border border-border bg-background p-3 text-sm">
      <span className="grid size-6 shrink-0 place-items-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">{index}</span>
      <span>{text}</span>
    </div>
  );
}

function TimelineLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-foreground">{value}</span>
    </div>
  );
}

function ChatBubble({ children, self }: { children: React.ReactNode; self?: boolean }) {
  return (
    <div className={(self ? "ml-auto bg-success/20 text-foreground" : "bg-background text-foreground") + " max-w-[84%] rounded-xl border border-border px-3 py-2 shadow-sm"}>
      {children}
    </div>
  );
}

function QuestionPreview({ type, title, detail }: { type: string; title: string; detail: string }) {
  return (
    <div className="rounded-lg border border-border bg-background p-3">
      <div className="mb-1 flex items-center justify-between gap-2">
        <p className="text-sm font-medium">{title}</p>
        <span className="rounded-full bg-accent px-2 py-0.5 text-[11px] font-medium text-accent-foreground">{type}</span>
      </div>
      <p className="text-xs text-muted-foreground">{detail}</p>
    </div>
  );
}

export function WhatsAppPreviewModal({
  open,
  onOpenChange,
  preview,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  preview?: Record<string, unknown> | null;
}) {
  const templatePreview = (preview?.template_preview || {}) as Record<string, unknown>;
  const flowSteps = (preview?.flow_steps || []) as Array<Record<string, unknown>>;
  const pages = (preview?.pages || []) as Array<Record<string, unknown>>;
  const pageRoles = (preview?.page_roles || []) as string[];
  const hasGenerated = Boolean(preview?.ok);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>WhatsApp preview</DialogTitle>
          <DialogDescription>
            {hasGenerated
              ? "Approved template message plus simulated survey steps."
              : "Generate a survey first to see the approved template and flow."}
          </DialogDescription>
        </DialogHeader>
        {hasGenerated ? (
          <div className="space-y-4">
            {pageRoles.length > 0 && (
              <div className="rounded-lg border border-border bg-muted/20 p-3">
                <p className="mb-2 text-xs font-medium text-muted-foreground">Survey page order ({pageRoles.length} pages)</p>
                <ol className="space-y-1 text-xs">
                  {pageRoles.map((role, idx) => {
                    const page = pages.find((p) => Number(p.page) === idx + 1) || pages[idx];
                    return (
                      <li key={`${role}-${idx}`}>
                        {idx + 1}. {String(page?.title || role).replace(/_/g, " ")}
                      </li>
                    );
                  })}
                </ol>
              </div>
            )}
            <WaSurveyPhonePreview
            businessName={String(templatePreview.business_name || "Your business")}
            renderedBody={String(templatePreview.rendered_body || "")}
            footer={String(templatePreview.footer || "")}
            buttons={(templatePreview.buttons as Array<{ label: string; type?: string }>) || []}
            flowSteps={flowSteps.map((s) => ({
              step: Number(s.step),
              title: String(s.title || ""),
              body: s.body ? String(s.body) : undefined,
              kind: s.kind ? String(s.kind) : undefined,
              description: s.description ? String(s.description) : undefined,
            }))}
            disclaimer={String(preview?.anonymous_responses ? "Anonymous survey — names hidden in results." : "")}
            templateName={String(preview?.wa_template_name || "")}
            approvalStatus="APPROVED"
          />
          </div>
        ) : (
          <div className="mx-auto w-full max-w-[280px] overflow-hidden rounded-[2rem] border-[10px] border-foreground/90 bg-[#e5ddd5] shadow-xl">
            <div className="bg-[#075e54] px-3 py-2 text-xs text-white">
              <p className="font-semibold">Your business</p>
              <p className="opacity-80">online</p>
            </div>
            <div className="flex flex-col gap-2 px-3 py-4 text-[12px]">
              <Bubble>Select survey type, variant, and length, then click Generate.</Bubble>
            </div>
          </div>
        )}
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Bubble({ children, self }: { children: React.ReactNode; self?: boolean }) {
  return (
    <div className={"max-w-[80%] rounded-lg px-2 py-1.5 shadow-sm " + (self ? "self-end bg-[#dcf8c6] text-[#111]" : "self-start bg-white text-[#111]")}>
      {children}
    </div>
  );
}

function Row({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <div className={"flex justify-between " + (bold ? "font-semibold text-foreground" : "text-muted-foreground")}>
      <span>{label}</span><span>{value}</span>
    </div>
  );
}

function PayBtn({
  icon,
  title,
  sub,
  disabled,
  onClick,
}: {
  icon: React.ReactNode;
  title: string;
  sub: string;
  disabled?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="flex w-full items-center gap-3 rounded-lg border border-border bg-background p-3 text-left hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
    >
      <span className="grid size-9 place-items-center rounded-md bg-primary/10 text-primary">{icon}</span>
      <span>
        <p className="text-sm font-medium">{title}</p>
        <p className="text-[11px] text-muted-foreground">{sub}</p>
      </span>
    </button>
  );
}

export type InterviewPreviewData = {
  position: string;
  role: string;
  criteria: string;
  reportNotes?: string;
  agentName: string;
  script: string;
  candidateCount: number;
  screeningEligibleCount?: number;
  minAtsScore?: number;
  atsSkipped?: boolean;
  referenceId: string;
  cvEmailEnabled: boolean;
  cvCollectionComplete?: boolean;
  careersInbox?: string;
  collectionStart: string;
  collectionEnd: string;
  callingStart: string;
  callingEnd: string;
  expectedDurationMinutes?: number;
  scriptApproved?: boolean;
  quoteTotalDisplay?: string;
  /** @deprecated use quoteTotalDisplay */
  quoteTotalGbp?: string;
  waPreviewBody?: string;
  waPreviewTemplateName?: string;
  waPreviewButtons?: { label: string; type?: string }[];
  waPreviewConfirmationBody?: string;
  waPreviewConfirmationButtons?: { label: string; type?: string }[];
  waPreviewConfirmationTemplateName?: string;
  hasPackageSubscription?: boolean;
  packagePlanName?: string;
};

export function PackageUpgradeModal({
  open,
  onOpenChange,
  blockReason,
  currentPlanName,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  blockReason?: string;
  currentPlanName?: string;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Upgrade to unlock CV email collection</DialogTitle>
          <DialogDescription>
            CV email collection is included on monthly Starter, Pro, and Business packages. Candidates email CVs to
            careers@voxbulk.com and they appear automatically in your list — not on Pay as you go or top-up only.
          </DialogDescription>
        </DialogHeader>
        {currentPlanName ? (
          <p className="text-sm text-muted-foreground">
            Your current plan: <span className="font-medium text-foreground">{currentPlanName}</span>
          </p>
        ) : null}
        {blockReason ? (
          <div className="rounded-lg border border-border bg-muted/30 p-3 text-sm text-muted-foreground">{blockReason}</div>
        ) : (
          <div className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm text-muted-foreground">
            Upgrade your package to enable inbox collection, then set your collection window and job reference on this interview.
          </div>
        )}
        <DialogFooter className="gap-2 sm:justify-between">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Not now</Button>
          <Button asChild onClick={() => onOpenChange(false)}>
            <Link to="/account/packages">Upgrade package</Link>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function AtsPreviewGateModal({
  open,
  onOpenChange,
  quote,
  quoteLoading,
  quoteError,
  onRetryQuote,
  onRunAts,
  onContinueWithoutAts,
  busy,
  candidateCount,
  unscoredCount,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  quote: { candidate_count?: number; already_scored_count?: number; total_gbp?: string; unit_price_gbp?: string; wallet_gbp?: string; requires_payment?: boolean } | null;
  quoteLoading?: boolean;
  quoteError?: string | null;
  onRetryQuote?: () => void;
  onRunAts: () => void;
  onContinueWithoutAts: () => void;
  busy?: boolean;
  candidateCount: number;
  unscoredCount: number;
}) {
  const count = Number(quote?.candidate_count || 0);
  const alreadyScored = Number(quote?.already_scored_count || 0);
  const unitPrice = quote?.unit_price_gbp || "£0.50";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Run ATS before preview?</DialogTitle>
          <DialogDescription>
            ATS reads each CV against your role and screening criteria so you only phone-screen strong matches.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 text-sm text-muted-foreground">
          <p>
            <strong className="text-foreground">Why it matters:</strong> Without ATS, every uploaded candidate stays unscored — you pay to call people who may not meet basic requirements. ATS ranks candidates, flags gaps early, and lets you remove weak profiles before launch.
          </p>
          <ul className="list-disc space-y-1 pl-5">
            <li>Scores {candidateCount} candidate{candidateCount === 1 ? "" : "s"} against your approved script context</li>
            <li>Surfaces {unscoredCount > 0 ? `${unscoredCount} still unscored` : "who still needs scoring"}</li>
            <li>You can delete anyone you do not want before final approval</li>
          </ul>
        </div>
        {quoteLoading ? (
          <p className="rounded-lg border border-border bg-muted/30 px-3 py-4 text-center text-sm text-muted-foreground">
            Loading ATS pricing…
          </p>
        ) : quoteError ? (
          <div className="space-y-2 rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-3 text-sm">
            <p className="text-destructive">{quoteError}</p>
            {onRetryQuote ? (
              <Button type="button" variant="outline" size="sm" onClick={onRetryQuote}>
                Try again
              </Button>
            ) : null}
          </div>
        ) : quote ? (
          <div className="space-y-2 rounded-lg border border-border bg-muted/30 p-3 text-sm">
            {alreadyScored > 0 ? (
              <p className="text-xs text-muted-foreground">
                {alreadyScored} CV{alreadyScored === 1 ? "" : "s"} already scored — you are only charged for new ones below.
              </p>
            ) : null}
            <Row label="Candidates to score" value={String(count)} />
            <Row label="Unit price" value={unitPrice} />
            <Row label="Total" value={quote.total_gbp || "£0.00"} bold />
            <Row label="ATS wallet balance" value={quote.wallet_gbp || "£0.00"} />
            {count <= 0 ? (
              <p className="pt-1 text-xs text-muted-foreground">
                No CVs are ready to score yet (text may still be parsing). You can continue without ATS or try again after uploads finish.
              </p>
            ) : quote.requires_payment !== false ? (
              <p className="pt-1 text-xs text-muted-foreground">
                Your ATS wallet is empty or insufficient. Confirming records the charge and starts scoring immediately.
              </p>
            ) : null}
          </div>
        ) : null}
        <DialogFooter className="flex-col gap-2 sm:flex-col sm:items-stretch">
          <Button
            className="w-full"
            onClick={onRunAts}
            disabled={busy || quoteLoading || Boolean(quoteError) || count <= 0}
          >
            {busy ? ATS_ANALYZING_LABEL : count > 0 ? `Run ATS — ${quote?.total_gbp || ""}` : "Run ATS"}
          </Button>
          <Button
            variant="outline"
            className="w-full"
            onClick={onContinueWithoutAts}
            disabled={busy || quoteLoading}
          >
            Continue without ATS
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function InterviewPreviewQuoteModal({
  open,
  onOpenChange,
  data,
  onApproveScript,
  onRefreshQuote,
  onPayLaunch,
  onLaunch,
  launchBlockers = [],
  quoteLoading,
  quoteError,
  payBusy,
  gcAvailable = true,
  hasPackageSubscription = false,
  packagePlanName,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  data: InterviewPreviewData;
  onApproveScript: () => Promise<void>;
  onRefreshQuote?: () => void;
  onPayLaunch?: () => void | Promise<void>;
  /** Return true when launch finished successfully (modal will close). */
  onLaunch?: () => boolean | Promise<boolean>;
  /** Extra gates from the wizard (e.g. ATS) — must match page-level launch validation. */
  launchBlockers?: string[];
  quoteLoading?: boolean;
  quoteError?: string | null;
  payBusy?: boolean;
  gcAvailable?: boolean;
  hasPackageSubscription?: boolean;
  packagePlanName?: string;
}) {
  const [previewApproved, setPreviewApproved] = React.useState(false);
  const [scriptApproved, setScriptApproved] = React.useState(Boolean(data.scriptApproved));
  const [launching, setLaunching] = React.useState(false);
  const [launchActionError, setLaunchActionError] = React.useState<string | null>(null);
  const scriptQuestions = parseScriptQuestions(data.script || "");
  const expectedTimeLabel = data.expectedDurationMinutes
    ? `~${data.expectedDurationMinutes} min per call`
    : "—";
  const quoteTotal = data.quoteTotalDisplay || data.quoteTotalGbp;
  const packageLabel = packagePlanName ? `Included in ${packagePlanName}` : "Included in your package";
  const readyCount = data.screeningEligibleCount ?? data.candidateCount;
  const candidateMetricValue =
    readyCount !== data.candidateCount
      ? `${readyCount} ready`
      : data.cvEmailEnabled
        ? `${data.candidateCount} via email`
        : `${data.candidateCount} ready`;
  const candidateMetricHint =
    readyCount !== data.candidateCount && data.minAtsScore != null
      ? `${data.candidateCount} uploaded · ${readyCount} meet ${data.minAtsScore}% ATS cutoff`
      : undefined;
  const launchReadinessErrors: string[] = [...launchBlockers];
  if (data.cvEmailEnabled) {
    if (!data.cvCollectionComplete) {
      launchReadinessErrors.push("CV collection must finish first (or close early in Step 2).");
    }
    if (data.candidateCount <= 0) {
      launchReadinessErrors.push(
        `No CVs received — share reference ${data.referenceId || "—"} and ${data.careersInbox || "careers@voxbulk.com"} with applicants.`,
      );
    } else if ((data.screeningEligibleCount ?? data.candidateCount) <= 0 && !data.atsSkipped) {
      launchReadinessErrors.push(
        `No candidates meet the ${data.minAtsScore ?? 40}% ATS cutoff — lower the cutoff or remove weak profiles.`,
      );
    }
  } else if (data.candidateCount <= 0) {
    launchReadinessErrors.push("Upload at least one candidate in Step 2.");
  } else if ((data.screeningEligibleCount ?? data.candidateCount) <= 0 && !data.atsSkipped) {
    launchReadinessErrors.push(
      `No candidates meet the ${data.minAtsScore ?? 40}% ATS cutoff — lower the cutoff or remove weak profiles.`,
    );
  }
  const actionBusy = Boolean(payBusy || launching);
  const canLaunchPackage =
    hasPackageSubscription &&
    scriptApproved &&
    previewApproved &&
    !quoteLoading &&
    !actionBusy &&
    launchReadinessErrors.length === 0;
  const canPay =
    !hasPackageSubscription &&
    scriptApproved &&
    previewApproved &&
    Boolean(quoteTotal) &&
    !quoteLoading &&
    !actionBusy &&
    launchReadinessErrors.length === 0;
  const launchBlockedReason = quoteLoading
    ? "Loading quote…"
    : actionBusy
      ? "Please wait…"
    : launchReadinessErrors.length > 0
      ? launchReadinessErrors[0]
    : quoteError && !hasPackageSubscription
      ? quoteError
      : !scriptApproved
        ? "Approve the script in this dialog first."
        : !previewApproved
          ? 'Click "Confirm preview" to unlock launch.'
          : hasPackageSubscription
            ? null
          : !quoteTotal
            ? "Quote not ready — save draft with a calling window, then retry."
            : !gcAvailable
              ? "GoCardless is not configured."
              : null;
  const waBody =
    data.waPreviewBody ||
    `Dear Alex 👋\nWe have sent you an email from 📧 careers@voxbulk.com regarding your interview for the position of *${data.role || "Interview"}* at *Your Company*\nPlease check your Spam / Junk folder in case it landed there 📁\nOnce you receive it, kindly book your interview slot as mentioned in the email 📅\nWe look forward to hearing from you! 🤝\nYour Company 🏢`;

  React.useEffect(() => {
    if (open) {
      const approved = Boolean(data.scriptApproved);
      setScriptApproved(approved);
      // Step 2 approval already done — unlock preview + launch without repeating gates.
      setPreviewApproved(approved);
      setLaunchActionError(null);
      setLaunching(false);
      onRefreshQuote?.();
    }
  }, [open, data.scriptApproved, onRefreshQuote]);

  const handleLaunchClick = async () => {
    if (!onLaunch || !canLaunchPackage) return;
    setLaunchActionError(null);
    setLaunching(true);
    try {
      await onLaunch();
      onOpenChange(false);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Could not launch campaign";
      setLaunchActionError(message);
    } finally {
      setLaunching(false);
    }
  };

  const handlePayLaunchClick = async () => {
    if (!onPayLaunch || !canPay) return;
    setLaunchActionError(null);
    setLaunching(true);
    try {
      await onPayLaunch();
    } catch (e) {
      const message = e instanceof Error ? e.message : "Could not start payment";
      setLaunchActionError(message);
      setLaunching(false);
    }
    // Redirect to GoCardless leaves the page — do not clear launching on success.
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-6xl overflow-y-auto p-0">
        <div className="border-b border-border bg-card px-6 py-5">
          <DialogHeader>
            <div className="flex flex-wrap items-start justify-between gap-3 pr-8">
              <div>
                <DialogTitle>Interview preview & approval</DialogTitle>
                <DialogDescription>Review role, candidates, script, schedule, and quote before launch.</DialogDescription>
              </div>
              <StatusBadge tone={scriptApproved ? "approved-script" : "draft-script"} />
            </div>
          </DialogHeader>
        </div>

        <div className="grid gap-0 lg:grid-cols-[1.35fr_0.85fr]">
          <div className="space-y-5 p-6">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="space-y-1">
                <PreviewMetric icon={<Users className="size-4" />} label="Candidates" value={candidateMetricValue} />
                {candidateMetricHint ? (
                  <p className="text-[11px] text-muted-foreground">{candidateMetricHint}</p>
                ) : null}
              </div>
              <PreviewMetric icon={<PhoneCall className="size-4" />} label="Agent" value={data.agentName || "—"} />
              <PreviewMetric icon={<Clock className="size-4" />} label="Expected call time" value={expectedTimeLabel} />
              <PreviewMetric icon={<ReceiptText className="size-4" />} label="Est. cost" value={quoteLoading ? "…" : hasPackageSubscription ? packageLabel : quoteTotal || "—"} />
            </div>

            <Panel title="Job details" icon={<FileText className="size-4" />}>
              <TimelineLine label="Position" value={data.position || "—"} />
              <TimelineLine label="Role" value={data.role || "—"} />
              <TimelineLine label="Reference" value={data.referenceId || "—"} />
              <TimelineLine label="CV email collection" value={data.cvEmailEnabled ? "Enabled" : "Off"} />
            </Panel>

            <Panel title="Screening criteria" icon={<ClipboardCheck className="size-4" />}>
              <p className="whitespace-pre-wrap text-sm text-muted-foreground">{data.criteria || "—"}</p>
            </Panel>

            {data.reportNotes?.trim() ? (
              <Panel title="Additional report notes" icon={<FileText className="size-4" />}>
                <p className="whitespace-pre-wrap text-sm text-muted-foreground">{data.reportNotes.trim()}</p>
              </Panel>
            ) : null}

            <Panel title="Approved script preview" icon={<PlayCircle className="size-4" />}>
              {scriptQuestions.length ? (
                <>
                  <p className="mb-3 text-[11px] text-muted-foreground">
                    You approved the job script. Questions 1–2 are templates — each candidate gets different CV questions on the call. Questions 3+ are the same for everyone.
                  </p>
                  {scriptQuestions.map((q) => (
                    <div key={q.index} className="mb-2 last:mb-0">
                      <NumberedLine index={q.index} text={q.text} />
                    </div>
                  ))}
                </>
              ) : (
                <p className="text-sm text-destructive">Generate the AI script before approving.</p>
              )}
            </Panel>

            <Panel title="Schedule" icon={<ShieldCheck className="size-4" />}>
              <TimelineLine label="Expected call time" value={expectedTimeLabel} />
              <TimelineLine label="CV collection" value={data.cvEmailEnabled ? `${data.collectionStart || "—"} → ${data.collectionEnd || "—"}` : "Not used"} />
              <TimelineLine label="Calling window" value={`${data.callingStart || "—"} → ${data.callingEnd || "—"}`} />
            </Panel>
          </div>

          <aside className="border-t border-border bg-muted/25 p-6 lg:border-l lg:border-t-0">
            <Panel title="Approval checklist" icon={<ClipboardCheck className="size-4" />}>
              <ChecklistItem done={Boolean(data.position && data.role)} text="Position and role confirmed" />
              <ChecklistItem
                done={data.cvEmailEnabled ? data.cvCollectionComplete && data.candidateCount > 0 : data.candidateCount > 0}
                text={data.cvEmailEnabled ? "Candidates collected via email" : "Candidate list uploaded"}
              />
              <ChecklistItem done={Boolean(data.criteria.trim())} text="Screening criteria set" />
              <ChecklistItem done={Boolean(data.script.trim())} text="AI script generated" />
              <ChecklistItem done={Boolean(data.expectedDurationMinutes)} text={`Expected time reviewed (${expectedTimeLabel})`} />
              <ChecklistItem done={scriptApproved} text="Script approved for calls" />
              <ChecklistItem done={previewApproved} text="Preview signed off" />
            </Panel>

            <div className="mt-6 flex justify-center">
              <WaBookingPhonePreview
                body={waBody}
                role={data.role}
                templateName={data.waPreviewTemplateName}
                buttons={data.waPreviewButtons}
                confirmationBody={data.waPreviewConfirmationBody}
                confirmationButtons={data.waPreviewConfirmationButtons}
                confirmationTemplateName={data.waPreviewConfirmationTemplateName}
                syncLabel={data.waPreviewSyncLabel}
              />
            </div>

            {(quoteTotal || hasPackageSubscription) && (
              <Panel title="Quote" icon={<Coins className="size-4" />}>
                <QuoteRow label="Total due" value={hasPackageSubscription ? packageLabel : quoteTotal || "—"} bold />
                <p className="mt-2 text-[11px] text-muted-foreground">
                  {hasPackageSubscription
                    ? "Your monthly package covers this campaign — confirm preview and tap Launch."
                    : gcAvailable
                      ? "Pay with GoCardless after confirming the preview. WhatsApp booking invites send after payment."
                      : "GoCardless checkout is not available — contact support."}
                </p>
              </Panel>
            )}
            {launchReadinessErrors.length > 0 ? (
              <div className="mt-4 space-y-1 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-900 dark:text-amber-100">
                <p className="font-medium">Before you can launch:</p>
                <ul className="list-disc space-y-1 pl-5 text-xs">
                  {launchReadinessErrors.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {launchActionError ? (
              <div className="mt-4 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
                {launchActionError}
              </div>
            ) : null}
            {quoteError && !hasPackageSubscription && onRefreshQuote ? (
              <div className="mt-4 space-y-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm">
                <p className="text-destructive">{quoteError}</p>
                <Button type="button" variant="outline" size="sm" onClick={onRefreshQuote}>
                  Retry quote
                </Button>
              </div>
            ) : null}
          </aside>
        </div>

        <DialogFooter className="sticky bottom-0 flex-col gap-3 border-t border-border bg-background/95 px-6 py-4 backdrop-blur sm:flex-row sm:justify-between">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Back to edit</Button>
          <div className="flex w-full flex-col gap-2 sm:w-auto">
            {!canPay && !canLaunchPackage && launchBlockedReason ? (
              <p className="text-center text-xs text-muted-foreground sm:text-right">{launchBlockedReason}</p>
            ) : null}
            <div className="flex flex-col-reverse gap-2 sm:flex-row">
            <Button
              type="button"
              variant="outline"
              className="gap-1.5"
              disabled={!data.script.trim() || scriptApproved || actionBusy}
              onClick={() => void onApproveScript().then(() => setScriptApproved(true))}
            >
              {scriptApproved ? <Lock className="size-4" /> : <LockOpen className="size-4" />}
              {scriptApproved ? "Script approved" : "Approve script"}
            </Button>
            <Button
              type="button"
              variant={previewApproved ? "outline" : "default"}
              className="gap-1.5"
              disabled={!scriptApproved || previewApproved || actionBusy}
              onClick={() => setPreviewApproved(true)}
            >
              <CheckCircle2 className="size-4" /> {previewApproved ? "Preview confirmed" : "Confirm preview"}
            </Button>
            {hasPackageSubscription ? (
              <Button
                type="button"
                className="gap-1.5"
                disabled={!canLaunchPackage}
                onClick={() => void handleLaunchClick()}
              >
                <PlayCircle className="size-4" />
                {actionBusy ? "Launching…" : "Launch"}
              </Button>
            ) : (
              <Button
                type="button"
                className="gap-1.5"
                disabled={!canPay || !gcAvailable}
                onClick={() => void handlePayLaunchClick()}
              >
                <CreditCard className="size-4" />
                {actionBusy ? "Redirecting…" : `Pay ${quoteTotal || ""} & launch`}
              </Button>
            )}
            </div>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export type SurveyLaunchModalData = {
  campaignName: string;
  firstStepName?: string;
  recipientCount: number;
  channelLabel: string;
  launchModeLabel: string;
  packageName?: string | null;
};

export type SurveyLaunchEligibilityView = {
  can_launch?: boolean;
  payment_required?: boolean;
  mode?: string;
  launch_action?: "launch" | "pay_and_launch" | "blocked";
  summary?: string;
  block_reason?: string | null;
  covered_by_allowance?: number;
  covered_by_promo_credits?: number;
  shortfall_units?: number;
  amount_due_display?: string | null;
  estimated_send_cost_display?: string | null;
  minimum_charge_display?: string | null;
  setup_fee_display?: string | null;
  estimated_whatsapp_usage?: number;
  remaining_whatsapp_after_launch?: number;
  remaining_promo_credits_after_launch?: number;
  billing?: {
    has_active_subscription?: boolean;
    plan_name?: string | null;
    whatsapp_remaining?: number;
    survey_credits?: number;
  };
};

export function SurveyLaunchQuoteModal({
  open,
  onOpenChange,
  data,
  eligibility,
  eligibilityLoading,
  eligibilityError,
  billingCheckPhase = "idle",
  launchBlockers = [],
  onRefreshEligibility,
  onLaunch,
  onPayLaunch,
  payBusy,
  gcAvailable = true,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  data: SurveyLaunchModalData;
  eligibility?: SurveyLaunchEligibilityView | null;
  eligibilityLoading?: boolean;
  eligibilityError?: string | null;
  billingCheckPhase?: "idle" | "loading" | "ready" | "error" | "timeout";
  launchBlockers?: string[];
  onRefreshEligibility?: () => void;
  onLaunch?: () => void | Promise<void>;
  onPayLaunch?: () => void | Promise<void>;
  payBusy?: boolean;
  gcAvailable?: boolean;
}) {
  const [launching, setLaunching] = React.useState(false);
  const [launchActionError, setLaunchActionError] = React.useState<string | null>(null);

  const mode = eligibility?.mode || "blocked";
  const launchAction = eligibility?.launch_action || "blocked";
  const paymentRequired = Boolean(eligibility?.payment_required);
  const canLaunchNow = Boolean(eligibility?.can_launch) && launchAction === "launch";
  const canPayLaunch = paymentRequired && launchAction === "pay_and_launch";
  const amountDue = eligibility?.amount_due_display || null;
  const actionBusy = Boolean(payBusy || launching || billingCheckPhase === "loading");
  const readinessErrors = [...launchBlockers];
  if (data.recipientCount <= 0) readinessErrors.push("Upload at least one contact before launch.");
  if (eligibility?.block_reason && launchAction === "blocked") readinessErrors.push(eligibility.block_reason);

  const showBillingLoading = billingCheckPhase === "loading";
  const showBillingError =
    billingCheckPhase === "error" || billingCheckPhase === "timeout" || Boolean(eligibilityError);

  const costLabel = showBillingLoading
    ? "…"
    : canLaunchNow
      ? mode === "promo_credits"
        ? "Included · promo credits"
        : mode === "subscription_whatsapp"
          ? `Included · ${data.packageName || eligibility?.billing?.plan_name || "your package"}`
          : "£0.00 · included"
      : canPayLaunch
        ? amountDue || "—"
        : eligibility?.estimated_send_cost_display || "—";

  const canLaunch = canLaunchNow && readinessErrors.length === 0 && !actionBusy && billingCheckPhase === "ready";
  const canPay =
    canPayLaunch && readinessErrors.length === 0 && !actionBusy && billingCheckPhase === "ready" && Boolean(amountDue) && gcAvailable;

  React.useEffect(() => {
    if (open) {
      setLaunchActionError(null);
      setLaunching(false);
      onRefreshEligibility?.();
    }
    // Only refetch eligibility when modal opens — not when callback identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleLaunch = async () => {
    if (!onLaunch || !canLaunch) return;
    setLaunchActionError(null);
    setLaunching(true);
    try {
      await onLaunch();
      onOpenChange(false);
    } catch (e) {
      setLaunchActionError(e instanceof Error ? e.message : "Could not launch campaign");
    } finally {
      setLaunching(false);
    }
  };

  const handlePayLaunch = async () => {
    if (!onPayLaunch || !canPay) return;
    setLaunchActionError(null);
    setLaunching(true);
    try {
      await onPayLaunch();
    } catch (e) {
      setLaunchActionError(e instanceof Error ? e.message : "Could not start payment");
      setLaunching(false);
    }
  };

  const blockedReason =
    readinessErrors[0] ||
    (billingCheckPhase === "timeout"
      ? "Billing check timed out."
      : billingCheckPhase === "error"
        ? eligibilityError || "Could not verify billing."
        : null) ||
    eligibilityError ||
    (launchAction === "blocked" ? eligibility?.summary || "Launch is not available for this account." : null);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-3xl overflow-y-auto p-0">
        <div className="border-b border-border bg-card px-6 py-5">
          <DialogHeader>
            <DialogTitle>Launch survey</DialogTitle>
            <DialogDescription>
              Review recipients, allowance, and billing before you send.
            </DialogDescription>
          </DialogHeader>
        </div>

        <div className="space-y-5 p-6">
          <div className="grid gap-3 sm:grid-cols-3">
            <PreviewMetric icon={<Users className="size-4" />} label="Recipients" value={`${data.recipientCount}`} />
            <PreviewMetric icon={<MessageSquare className="size-4" />} label="Channel" value={data.channelLabel} />
            <PreviewMetric icon={<ReceiptText className="size-4" />} label="Amount due" value={costLabel} />
          </div>

          {canPayLaunch && eligibility?.estimated_send_cost_display ? (
            <div className="rounded-lg border border-border bg-muted/20 p-3 text-sm">
              <p>
                Estimated send cost: <span className="font-medium">{eligibility.estimated_send_cost_display}</span>
                {data.recipientCount > 0 ? ` · ${data.recipientCount} contact${data.recipientCount === 1 ? "" : "s"}` : ""}
              </p>
              {eligibility.minimum_charge_display &&
              eligibility.minimum_charge_display !== eligibility.estimated_send_cost_display ? (
                <p className="mt-1 text-muted-foreground">
                  Minimum launch charge: <span className="font-medium text-foreground">{eligibility.minimum_charge_display}</span>
                </p>
              ) : null}
              {eligibility.setup_fee_display ? (
                <p className="mt-1 text-muted-foreground">
                  Setup fee: <span className="font-medium text-foreground">{eligibility.setup_fee_display}</span>
                </p>
              ) : null}
              {amountDue ? (
                <p className="mt-1 font-medium">
                  Amount due at checkout: {amountDue}
                </p>
              ) : null}
            </div>
          ) : null}

          <Panel title="Campaign" icon={<FileText className="size-4" />}>
            <TimelineLine label="Survey name" value={data.campaignName || "—"} />
            <TimelineLine label="Step 1" value={data.firstStepName || "—"} />
            <TimelineLine label="Launch timing" value={data.launchModeLabel} />
            <TimelineLine label="Recipients" value={`${data.recipientCount} contacts`} />
          </Panel>

          <Panel title="Allowance & billing" icon={<Coins className="size-4" />}>
            {showBillingLoading ? (
              <p className="text-sm text-muted-foreground">Checking your package and allowance…</p>
            ) : showBillingError ? (
              <p className="text-sm text-destructive">
                {billingCheckPhase === "timeout"
                  ? "Billing check timed out. Try Refresh or close and open launch again."
                  : eligibilityError || "Could not load billing state."}
              </p>
            ) : (
              <>
                {eligibility?.billing?.has_active_subscription ? (
                  <QuoteRow
                    label="Package"
                    value={`Active${eligibility.billing.plan_name ? ` · ${eligibility.billing.plan_name}` : ""}`}
                  />
                ) : (
                  <QuoteRow label="Package" value="No active subscription package" />
                )}
                {typeof eligibility?.billing?.whatsapp_remaining === "number" ? (
                  <QuoteRow label="Remaining WhatsApp allowance" value={`${eligibility.billing.whatsapp_remaining}`} />
                ) : null}
                {typeof eligibility?.estimated_whatsapp_usage === "number" && eligibility.estimated_whatsapp_usage > 0 ? (
                  <QuoteRow label="Estimated usage for this launch" value={`${eligibility.estimated_whatsapp_usage}`} />
                ) : null}
                {typeof eligibility?.covered_by_allowance === "number" && eligibility.covered_by_allowance > 0 ? (
                  <QuoteRow label="Covered by package" value={`${eligibility.covered_by_allowance}`} />
                ) : null}
                {typeof eligibility?.covered_by_promo_credits === "number" && eligibility.covered_by_promo_credits > 0 ? (
                  <QuoteRow label="Covered by promo credits" value={`${eligibility.covered_by_promo_credits}`} />
                ) : null}
                {typeof eligibility?.shortfall_units === "number" && eligibility.shortfall_units > 0 ? (
                  <QuoteRow label="Additional WhatsApp usage required" value={`${eligibility.shortfall_units}`} />
                ) : null}
                {typeof eligibility?.remaining_whatsapp_after_launch === "number" ? (
                  <QuoteRow label="Remaining after launch" value={`${eligibility.remaining_whatsapp_after_launch}`} />
                ) : null}
                {typeof eligibility?.billing?.survey_credits === "number" ? (
                  <QuoteRow label="Survey promo credits" value={`${eligibility.billing.survey_credits}`} />
                ) : null}
                {canPayLaunch && amountDue ? <QuoteRow label="Amount due at checkout" value={amountDue} bold /> : null}
                {canLaunchNow && !canPayLaunch ? (
                  <QuoteRow label="Estimated send cost" value={eligibility?.estimated_send_cost_display || "£0.00 · included"} />
                ) : null}
                {eligibility?.summary ? (
                  <p className="mt-2 text-xs text-muted-foreground">{eligibility.summary}</p>
                ) : null}
              </>
            )}
          </Panel>

          {readinessErrors.length > 0 ? (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-900 dark:text-amber-100">
              <p className="font-medium">Before you can launch:</p>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-xs">
                {readinessErrors.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {launchActionError ? (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
              {launchActionError}
            </div>
          ) : null}
        </div>

        <DialogFooter className="sticky bottom-0 flex-col gap-3 border-t border-border bg-background/95 px-6 py-4 backdrop-blur sm:flex-row sm:justify-between">
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={actionBusy}>
            Back
          </Button>
          <div className="flex w-full flex-col gap-2 sm:w-auto">
            {!canLaunch && !canPay && blockedReason ? (
              <p className="text-center text-xs text-muted-foreground sm:text-right">{blockedReason}</p>
            ) : null}
            <div className="flex flex-col-reverse gap-2 sm:flex-row">
              {onRefreshEligibility ? (
                <Button type="button" variant="outline" disabled={actionBusy} onClick={() => void onRefreshEligibility()}>
                  Refresh
                </Button>
              ) : null}
              {canLaunchNow ? (
                <Button type="button" className="gap-1.5" disabled={!canLaunch} onClick={() => void handleLaunch()}>
                  <Rocket className="size-4" />
                  {actionBusy ? "Launching…" : "Launch now"}
                </Button>
              ) : canPayLaunch ? (
                <Button type="button" className="gap-1.5" disabled={!canPay} onClick={() => void handlePayLaunch()}>
                  <CreditCard className="size-4" />
                  {actionBusy ? "Redirecting…" : `Pay ${amountDue || ""} & launch`}
                </Button>
              ) : launchAction === "blocked" ? (
                <Button type="button" variant="outline" asChild>
                  <Link to="/account/packages">View packages</Link>
                </Button>
              ) : null}
            </div>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
