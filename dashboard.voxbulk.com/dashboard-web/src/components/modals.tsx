import * as React from "react";
import { Link } from "@tanstack/react-router";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/status-badge";
import { WaBookingPhonePreview } from "@/components/wa-booking-phone-preview";
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

export function WhatsAppPreviewModal({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>WhatsApp preview</DialogTitle>
          <DialogDescription>How patients will see your survey.</DialogDescription>
        </DialogHeader>
        <div className="mx-auto w-full max-w-[280px] overflow-hidden rounded-[2rem] border-[10px] border-foreground/90 bg-[#e5ddd5] shadow-xl">
          <div className="bg-[#075e54] px-3 py-2 text-xs text-white">
            <p className="font-semibold">Northwell Dental</p>
            <p className="opacity-80">online</p>
          </div>
          <div className="flex flex-col gap-2 px-3 py-4 text-[12px]">
            <Bubble>Hi Sarah 👋 We'd love your feedback on your recent hygienist visit. 2 quick questions?</Bubble>
            <Bubble>On a scale of 0-10, how likely are you to recommend us?</Bubble>
            <Bubble self>9</Bubble>
            <Bubble>Thanks! Anything we could have done better?</Bubble>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Restart preview</Button>
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
  agentName: string;
  script: string;
  candidateCount: number;
  referenceId: string;
  cvEmailEnabled: boolean;
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
  quote: { candidate_count?: number; total_gbp?: string; unit_price_gbp?: string; wallet_gbp?: string; requires_payment?: boolean } | null;
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
  const unitPrice = quote?.unit_price_gbp || "£0.50";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Run ATS before you approve?</DialogTitle>
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
            {busy ? "Starting ATS…" : count > 0 ? `Run ATS — ${quote?.total_gbp || ""}` : "Run ATS"}
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
  onLaunch?: () => void | Promise<void>;
  quoteLoading?: boolean;
  quoteError?: string | null;
  payBusy?: boolean;
  gcAvailable?: boolean;
  hasPackageSubscription?: boolean;
  packagePlanName?: string;
}) {
  const [previewApproved, setPreviewApproved] = React.useState(false);
  const [scriptApproved, setScriptApproved] = React.useState(Boolean(data.scriptApproved));
  const scriptLines = (data.script || "").split(/\n+/).filter(Boolean).slice(0, 8);
  const expectedTimeLabel = data.expectedDurationMinutes
    ? `~${data.expectedDurationMinutes} min per call`
    : "—";
  const quoteTotal = data.quoteTotalDisplay || data.quoteTotalGbp;
  const packageLabel = packagePlanName ? `Included in ${packagePlanName}` : "Included in your package";
  const canLaunchPackage = hasPackageSubscription && scriptApproved && previewApproved && !quoteLoading && !payBusy;
  const canPay = !hasPackageSubscription && scriptApproved && previewApproved && Boolean(quoteTotal) && !quoteLoading;
  const launchBlockedReason = quoteLoading
    ? "Loading quote…"
    : payBusy
      ? "Please wait…"
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
    `Hi Alex 👋\n\nYou've been shortlisted for the *${data.role || "interview"}* role at *Your Company* ✨\n\nTap *Book My Interview* below to choose a time that works for you 🗓️\n\n— VOXBULK`;

  React.useEffect(() => {
    if (open) {
      setPreviewApproved(false);
      setScriptApproved(Boolean(data.scriptApproved));
      onRefreshQuote?.();
    }
  }, [open, data.scriptApproved, data.script]);

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
              <PreviewMetric icon={<Users className="size-4" />} label="Candidates" value={`${data.candidateCount} ready`} />
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

            <Panel title="Approved script preview" icon={<PlayCircle className="size-4" />}>
              {scriptLines.length ? scriptLines.map((line, i) => <NumberedLine key={i} index={i + 1} text={line} />) : (
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
              <ChecklistItem done={data.candidateCount > 0} text="Candidate list uploaded" />
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
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={payBusy}>Back to edit</Button>
          <div className="flex w-full flex-col gap-2 sm:w-auto">
            {!canPay && !canLaunchPackage && launchBlockedReason ? (
              <p className="text-center text-xs text-muted-foreground sm:text-right">{launchBlockedReason}</p>
            ) : null}
            <div className="flex flex-col-reverse gap-2 sm:flex-row">
            <Button
              variant="outline"
              className="gap-1.5"
              disabled={!data.script.trim() || scriptApproved || payBusy}
              onClick={() => void onApproveScript().then(() => setScriptApproved(true))}
            >
              {scriptApproved ? <Lock className="size-4" /> : <LockOpen className="size-4" />}
              {scriptApproved ? "Script approved" : "Approve script"}
            </Button>
            <Button
              variant={previewApproved ? "outline" : "default"}
              className="gap-1.5"
              disabled={!scriptApproved || previewApproved || payBusy}
              onClick={() => setPreviewApproved(true)}
            >
              <CheckCircle2 className="size-4" /> {previewApproved ? "Preview confirmed" : "Confirm preview"}
            </Button>
            {hasPackageSubscription ? (
              <Button
                className="gap-1.5"
                disabled={!canLaunchPackage}
                onClick={() => void onLaunch?.()}
              >
                <PlayCircle className="size-4" />
                {payBusy ? "Launching…" : "Launch"}
              </Button>
            ) : (
              <Button
                className="gap-1.5"
                disabled={!canPay || !gcAvailable || payBusy}
                onClick={() => void onPayLaunch?.()}
              >
                <CreditCard className="size-4" />
                {payBusy ? "Redirecting…" : `Pay ${quoteTotal || ""} & launch`}
              </Button>
            )}
            </div>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
