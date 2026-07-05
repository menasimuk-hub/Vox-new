import * as React from "react";
import { ChevronLeft, ChevronRight, Eye, Loader2, Send } from "lucide-react";
import { toast } from "sonner";

import { WizardAlert } from "@/components/create-wizard/wizard-alert";
import { Summary } from "@/components/create-wizard/summary";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { cn } from "@/lib/utils";
import { wizardTemplateDisplayName } from "@/lib/survey-step-labels";

type PreviewMessage = { you?: boolean; text: string; button?: boolean };

export type WaPreviewSlide = {
  id: string;
  title: string;
  kind: "welcome" | "survey" | "thanks";
  messages: PreviewMessage[];
};

function personalize(text: string, firstName: string, businessName?: string): string {
  let out = text
    .replace(/\{\{name\}\}/gi, firstName)
    .replace(/\{\{first_name\}\}/gi, firstName)
    .replace(/\{\{1\}\}/g, firstName);
  if (businessName) {
    out = out
      .replace(/\{\{clinic_name\}\}/gi, businessName)
      .replace(/\{\{organisation_name\}\}/gi, businessName)
      .replace(/\{\{company_name\}\}/gi, businessName)
      .replace(/\{\{2\}\}/g, businessName);
  }
  return out;
}

function bodyFromComponents(raw: unknown): string {
  if (!Array.isArray(raw)) return "";
  for (const comp of raw) {
    if (!comp || typeof comp !== "object") continue;
    const type = String((comp as Record<string, unknown>).type || "").toUpperCase();
    if (type === "BODY") {
      return String((comp as Record<string, unknown>).text || "").trim();
    }
  }
  return "";
}

function templateBody(row: Record<string, unknown>): string {
  const direct = String(row.body_preview || row.body || row.body_text || "").trim();
  const name = String(row.name || "").trim();
  // Never treat Meta template name as the message body.
  if (direct && direct !== name && !direct.startsWith("voxbulk_survey_") && !direct.startsWith("voxbulk_sales_")) {
    return direct;
  }
  return (
    bodyFromComponents(row.draft_components) ||
    bodyFromComponents(row.remote_components) ||
    bodyFromComponents(row.components) ||
    (direct && direct !== name ? direct : "")
  );
}

function templateTitle(
  row: Record<string, unknown>,
  fallback: string,
  questionNumber?: number,
): string {
  return wizardTemplateDisplayName(row, fallback, questionNumber);
}

function buttonsFromRow(row: Record<string, unknown>): string[] {
  if (String(row.send_mode || "").toLowerCase() === "session_text") return [];
  const raw = row.buttons;
  if (!Array.isArray(raw)) return [];
  return raw
    .map((btn) => {
      if (!btn || typeof btn !== "object") return "";
      return String((btn as Record<string, unknown>).text || (btn as Record<string, unknown>).label || "").trim();
    })
    .filter(Boolean);
}

function messagesFromTemplateRow(
  row: Record<string, unknown>,
  firstName: string,
  businessName?: string,
): PreviewMessage[] {
  let body = templateBody(row);
  if (!body) return [];

  const examples = Array.isArray(row.example_values) ? row.example_values : [];
  examples.forEach((value, index) => {
    body = body.replace(new RegExp(`\\{\\{${index + 1}\\}\\}`, "g"), String(value ?? ""));
  });
  body = personalize(body, firstName, businessName);

  const messages: PreviewMessage[] = [{ text: body }];
  const footer = String(row.footer || "").trim();
  if (footer) {
    messages[0] = { text: `${messages[0].text}\n\n${footer}` };
  }
  for (const label of buttonsFromRow(row)) {
    messages.push({ text: label, button: true });
  }
  return messages;
}

/** Build carousel slides from Step 3 template selections only — no generated/dummy copy. */
export function buildWaPreviewSlides(input: {
  welcomeTemplate?: Record<string, unknown> | null;
  thankYouTemplate?: Record<string, unknown> | null;
  orderedTypeIds: string[];
  serviceTypes: Array<Record<string, unknown>>;
  selectedServiceTemplateIds: Record<string, string>;
  libraryTemplatesByTypeId: Record<string, Array<Record<string, unknown>>>;
  firstName: string;
  businessName?: string;
  rejectTitles?: string[];
}): WaPreviewSlide[] {
  const slides: WaPreviewSlide[] = [];
  const { firstName, businessName } = input;
  const rejectTitles = input.rejectTitles || [];

  if (input.welcomeTemplate) {
    const messages = messagesFromTemplateRow(input.welcomeTemplate, firstName, businessName);
    if (messages.length) {
      slides.push({
        id: "welcome",
        title: templateTitle(input.welcomeTemplate, "Welcome"),
        kind: "welcome",
        messages,
      });
    }
  }

  for (const [qIndex, typeId] of input.orderedTypeIds.entries()) {
    const typeRow = input.serviceTypes.find((t) => String(t.id) === typeId);
    const typeName = String(typeRow?.name || "Survey question");
    const templateId = input.selectedServiceTemplateIds[typeId];
    const libraryRows = input.libraryTemplatesByTypeId[typeId] || [];
    const tplRow = libraryRows.find((r) => String(r.id) === templateId);
    if (!tplRow) continue;
    const messages = messagesFromTemplateRow(tplRow, firstName, businessName);
    if (!messages.length) continue;
    slides.push({
      id: typeId,
      title: templateTitle(tplRow, typeName, qIndex + 1),
      kind: "survey",
      messages,
    });
  }

  if (input.thankYouTemplate) {
    const messages = messagesFromTemplateRow(input.thankYouTemplate, firstName, businessName);
    if (messages.length) {
      slides.push({
        id: "thanks",
        title: templateTitle(input.thankYouTemplate, "Thank you"),
        kind: "thanks",
        messages,
      });
    }
  }

  return slides;
}

function PhonePreview({ messages, compact }: { messages: PreviewMessage[]; compact?: boolean }) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-[2.5rem] border-[12px] border-foreground/90 bg-[#e5ddd5] shadow-2xl",
        compact ? "w-[260px]" : "w-[280px]",
      )}
    >
      <div className="bg-[#075e54] px-3 py-2.5 text-xs text-white">
        <p className="font-semibold">VoxBulk Survey</p>
        <p className="opacity-80">online</p>
      </div>
      <div className={cn("flex flex-col gap-2 overflow-y-auto px-3 py-3 text-[12px]", compact ? "h-[420px]" : "h-[500px]")}>
        {messages.map((m, idx) =>
          m.button ? (
            <div
              key={idx}
              className="max-w-[85%] rounded-md border border-[#e9edef] bg-[#f0f2f5] px-2.5 py-1.5 text-center text-[11px] font-medium text-[#008069] shadow-sm"
            >
              {m.text}
            </div>
          ) : (
            <div
              key={idx}
              className={cn(
                "max-w-[85%] whitespace-pre-wrap rounded-xl px-2.5 py-1.5 shadow-sm",
                m.you ? "ml-auto bg-[#dcf8c6] text-[#111]" : "bg-white text-[#111]",
              )}
            >
              {m.text}
            </div>
          ),
        )}
      </div>
    </div>
  );
}

export type SurveyWaPreviewCarouselProps = {
  slides: WaPreviewSlide[];
  industryLabel: string;
  surveyTypeLabel: string;
  templateSummary: string;
  contactsCount: number;
  anonymous: boolean;
  sendMode: "all" | "test";
  setSendMode: (v: "all" | "test") => void;
  testPhone: string;
  setTestPhone: (v: string) => void;
  typeCount: number;
  defaultTestPhone?: string;
  welcomeTemplateId: string;
  previewFirstName?: string;
  onSendTest: (input: { testPhone: string; welcomeTemplateId: string; firstName: string }) => Promise<void>;
  sendTestPending?: boolean;
  testCostHint?: string;
};

export function SurveyWaPreviewCarousel({
  slides,
  industryLabel,
  surveyTypeLabel,
  templateSummary,
  contactsCount,
  anonymous,
  sendMode,
  setSendMode,
  testPhone,
  setTestPhone,
  typeCount,
  defaultTestPhone,
  welcomeTemplateId,
  previewFirstName = "there",
  onSendTest,
  sendTestPending,
  testCostHint = "This test WhatsApp may be charged to your package allowance or wallet.",
}: SurveyWaPreviewCarouselProps) {
  const [slide, setSlide] = React.useState(0);
  const [testConfirmOpen, setTestConfirmOpen] = React.useState(false);
  const total = slides.length;
  const current = slides[slide];

  React.useEffect(() => {
    setSlide(0);
  }, [slides.length]);

  React.useEffect(() => {
    if (testPhone.trim() || !defaultTestPhone) return;
    setTestPhone(defaultTestPhone);
  }, [defaultTestPhone, setTestPhone, testPhone]);

  if (!current || total === 0) {
    return (
      <Card className="animate-scale-in">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Eye className="size-4 text-primary" /> Step 5 · Preview the full conversation
          </CardTitle>
          <CardDescription>Select templates in Step 3 to preview the real WhatsApp messages here.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const prev = () => setSlide((s) => Math.max(0, s - 1));
  const next = () => setSlide((s) => Math.min(total - 1, s + 1));
  const surveySlideIndex =
    current.kind === "survey"
      ? slides.filter((s, i) => i <= slide && s.kind === "survey").length
      : 0;
  const slideLabel =
    current.kind === "welcome"
      ? "Welcome"
      : current.kind === "thanks"
        ? "Thank-you"
        : current.title || `Question ${surveySlideIndex || 1}`;

  const handleSendTest = async () => {
    const phone = testPhone.trim() || defaultTestPhone || "";
    if (!phone) {
      toast.error("Add your mobile number in Profile settings or enter a test number.");
      return;
    }
    if (!welcomeTemplateId) {
      toast.error("Select a welcome template in Step 3 before sending a test.");
      return;
    }
    try {
      await onSendTest({
        testPhone: phone,
        welcomeTemplateId,
        firstName: previewFirstName,
      });
      toast.success(`Test WhatsApp sent to ${phone}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Test send failed");
    }
  };

  return (
    <Card className="animate-scale-in">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Eye className="size-4 text-primary" /> Step 5 · Preview the full conversation
        </CardTitle>
        <CardDescription>Showing the exact welcome, survey, and thank-you templates you selected.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {contactsCount === 0 ? (
          <WizardAlert title="No contacts uploaded yet">
            Upload contacts in Step 4 before launch, or skip for now and add them later from the survey order.
          </WizardAlert>
        ) : null}

        <div className="grid gap-5 lg:grid-cols-[auto_1fr]">
          <div className="flex flex-col items-center gap-3">
            <div className="relative flex items-center justify-center">
              {slide > 0 && (
                <button
                  type="button"
                  onClick={prev}
                  className="absolute -left-12 top-1/2 z-10 grid size-10 -translate-y-1/2 place-items-center rounded-full border border-border bg-background/95 shadow-lg backdrop-blur-sm transition-all hover:scale-110 hover:border-primary/30 hover:bg-accent hover:text-accent-foreground active:scale-95 max-md:-left-4 max-md:size-8"
                  aria-label="Previous template"
                >
                  <ChevronLeft className="size-5 max-md:size-4" />
                </button>
              )}
              {slide < total - 1 && (
                <button
                  type="button"
                  onClick={next}
                  className="absolute -right-12 top-1/2 z-10 grid size-10 -translate-y-1/2 place-items-center rounded-full border border-border bg-background/95 shadow-lg backdrop-blur-sm transition-all hover:scale-110 hover:border-primary/30 hover:bg-accent hover:text-accent-foreground active:scale-95 max-md:-right-4 max-md:size-8"
                  aria-label="Next template"
                >
                  <ChevronRight className="size-5 max-md:size-4" />
                </button>
              )}
              <PhonePreview messages={current.messages} />
            </div>
            <div className="flex items-center gap-2">
              {slides.map((s, i) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setSlide(i)}
                  className={cn(
                    "size-2 rounded-full transition-all",
                    i === slide ? "w-4 bg-primary" : "bg-border hover:bg-primary/40",
                  )}
                  aria-label={`Go to slide ${i + 1}`}
                />
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {slide + 1} / {total} · {slideLabel}
            </p>
          </div>

          <div className="space-y-3">
            <div className="grid gap-2 sm:grid-cols-2">
              <Summary label="Industry" value={industryLabel || "—"} />
              <Summary label="Survey types" value={surveyTypeLabel || "—"} />
              <Summary label="Templates" value={templateSummary || "—"} />
              <Summary
                label="Contacts"
                value={`${contactsCount}`}
                className={contactsCount === 0 ? "border-[#B45309]/40 bg-[#B45309]/10" : undefined}
                valueClassName={contactsCount === 0 ? "text-[#B45309]" : undefined}
              />
              <Summary label="Channel" value="WhatsApp" />
              <Summary
                label="Estimated cost"
                value={`£${(contactsCount * 0.18 * Math.max(1, typeCount)).toFixed(2)}`}
              />
              {anonymous ? <Summary label="Anonymous" value="On" /> : null}
            </div>
            <div className="rounded-xl border border-border bg-muted/30 p-4">
              <p className="mb-3 text-sm font-semibold">Send mode</p>
              <RadioGroup value={sendMode} onValueChange={(v) => setSendMode(v as "all" | "test")} className="space-y-2">
                <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-border bg-background p-3 hover:border-primary/40">
                  <RadioGroupItem value="all" id="send-all" className="mt-0.5" />
                  <div>
                    <p className="text-sm font-medium">Send to all {contactsCount} contacts</p>
                    <p className="text-xs text-muted-foreground">Launch immediately after approval.</p>
                  </div>
                </label>
                <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-border bg-background p-3 hover:border-primary/40">
                  <RadioGroupItem value="test" id="send-test" className="mt-0.5" />
                  <div className="w-full">
                    <p className="text-sm font-medium">Send a test to my number first</p>
                    <p className="mb-2 text-xs text-muted-foreground">
                      Sends your selected welcome template to your mobile via WhatsApp for verification.
                    </p>
                    {sendMode === "test" && (
                      <div className="space-y-2">
                        <div className="space-y-1">
                          <Label className="text-xs text-muted-foreground">Test mobile number</Label>
                          <Input
                            placeholder={defaultTestPhone || "+44 7700 900000"}
                            value={testPhone}
                            onChange={(e) => setTestPhone(e.target.value)}
                          />
                          {defaultTestPhone ? (
                            <p className="text-[11px] text-muted-foreground">
                              Pre-filled from your account — edit if you want a different test number.
                            </p>
                          ) : (
                            <p className="text-[11px] text-[#B45309]">
                              Add your mobile in Profile settings, or enter a number below.
                            </p>
                          )}
                        </div>
                        <Button
                          size="sm"
                          className="gap-1.5"
                          disabled={sendTestPending || !(testPhone.trim() || defaultTestPhone)}
                          onClick={() => setTestConfirmOpen(true)}
                        >
                          {sendTestPending ? (
                            <Loader2 className="size-3.5 animate-spin" />
                          ) : (
                            <Send className="size-3.5" />
                          )}
                          Send test to my number
                        </Button>
                      </div>
                    )}
                  </div>
                </label>
              </RadioGroup>
            </div>
          </div>
        </div>
      </CardContent>

      <AlertDialog open={testConfirmOpen} onOpenChange={setTestConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Send test WhatsApp?</AlertDialogTitle>
            <AlertDialogDescription>
              {testCostHint} Confirm to send the test conversation to your number.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={sendTestPending}
              onClick={(e) => {
                e.preventDefault();
                setTestConfirmOpen(false);
                void handleSendTest();
              }}
            >
              {sendTestPending ? "Sending…" : "Send test"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
