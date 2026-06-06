import * as React from "react";

export type WaSurveyFlowStep = {
  step: number;
  title?: string;
  body?: string;
  kind?: string;
  description?: string;
};

export type WaSurveyPhonePreviewProps = {
  businessName?: string;
  renderedBody?: string;
  footer?: string;
  buttons?: Array<{ label: string; type?: string }>;
  flowSteps?: WaSurveyFlowStep[];
  disclaimer?: string;
  templateName?: string;
  approvalStatus?: string;
};

function substituteVars(text: string, values: string[] = []) {
  let out = String(text || "");
  values.forEach((value, index) => {
    out = out.replace(new RegExp(`\\{\\{${index + 1}\\}\\}`, "g"), String(value));
  });
  return out;
}

export function WaSurveyPhonePreview({
  businessName = "Your business",
  renderedBody = "",
  footer = "",
  buttons = [],
  flowSteps = [],
  disclaimer = "",
  templateName = "",
  approvalStatus = "",
}: WaSurveyPhonePreviewProps) {
  const [activeStep, setActiveStep] = React.useState(1);
  const steps =
    Array.isArray(flowSteps) && flowSteps.length
      ? flowSteps
      : [{ step: 1, title: "Template message", body: renderedBody }];
  const current = steps.find((s) => s.step === activeStep) || steps[0];
  const showTemplateBubble = current?.kind === "template_outbound" || activeStep === 1;
  const bubbleBody = showTemplateBubble ? renderedBody : current?.body || renderedBody;
  const bubbleButtons = showTemplateBubble ? buttons : [];

  return (
    <div className="mx-auto w-full max-w-[240px]">
      <p className="mb-2 text-center text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        WhatsApp preview
      </p>
      {(templateName || approvalStatus) && (
        <p className="mb-2 truncate text-center text-[10px] text-muted-foreground">
          {[templateName, approvalStatus].filter(Boolean).join(" · ")}
        </p>
      )}
      <div
        className="relative mx-auto rounded-[2.4rem] border-[3px] border-zinc-300 bg-zinc-100 p-[7px] shadow-lg"
        style={{ aspectRatio: "9 / 19.5" }}
      >
        <div className="absolute -left-[4px] top-[18%] h-8 w-[3px] rounded-l bg-zinc-400" />
        <div className="absolute -left-[4px] top-[28%] h-12 w-[3px] rounded-l bg-zinc-400" />
        <div className="absolute -right-[4px] top-[24%] h-16 w-[3px] rounded-r bg-zinc-400" />
        <div className="relative flex h-full flex-col overflow-hidden rounded-[2rem] bg-[#ece5dd]">
          <div className="relative shrink-0 border-b border-[#d1d7db] bg-[#f0f2f5] px-3 pb-2 pt-2">
            <div className="mx-auto mb-2 h-[22px] w-[78px] rounded-full bg-zinc-900" />
            <div className="flex items-center justify-between text-[9px] text-[#111b21]">
              <span>9:41</span>
              <span className="truncate px-2 font-semibold text-[#111b21]">{businessName}</span>
              <span className="text-[#667781]">5G</span>
            </div>
          </div>
          <div
            className="flex-1 space-y-2 overflow-y-auto px-2 py-3"
            style={{
              backgroundColor: "#ece5dd",
              backgroundImage:
                "radial-gradient(circle at 25% 25%, rgba(0,0,0,0.02) 0%, transparent 45%), radial-gradient(circle at 75% 75%, rgba(0,0,0,0.02) 0%, transparent 40%)",
            }}
          >
            <div className="mr-auto max-w-[92%] rounded-lg rounded-tl-sm bg-white px-2.5 py-2 text-[10px] leading-relaxed text-[#111b21] shadow-sm">
              <p className="whitespace-pre-wrap">{substituteVars(bubbleBody)}</p>
              {footer ? <p className="mt-1.5 text-[9px] text-[#667781]">{footer}</p> : null}
              {bubbleButtons.length > 0 && (
                <div className="mt-2 space-y-1">
                  {bubbleButtons.map((btn, i) => (
                    <div
                      key={`${btn.label}-${i}`}
                      className="overflow-hidden rounded-md border border-[#e9edef] bg-[#f0f2f5] px-2 py-1.5 text-center text-[10px] font-medium text-[#008069]"
                    >
                      {btn.label}
                    </div>
                  ))}
                </div>
              )}
              <p className="mt-1 text-right text-[8px] text-[#667781]">9:41</p>
            </div>
            {!showTemplateBubble && current?.kind === "user_action" ? (
              <div className="ml-auto max-w-[80%] rounded-lg rounded-tr-sm bg-[#d9fdd3] px-2.5 py-2 text-[10px] text-[#111b21]">
                {current.description || "Recipient tapped a button"}
              </div>
            ) : null}
            {!showTemplateBubble && current?.kind === "survey_question" ? (
              <div className="mr-auto max-w-[92%] rounded-lg rounded-tl-sm bg-white px-2.5 py-2 text-[10px] text-[#111b21] shadow-sm">
                <p className="whitespace-pre-wrap">{current.body}</p>
                <p className="mt-1 text-right text-[8px] text-[#667781]">9:42</p>
              </div>
            ) : null}
          </div>
          <div className="shrink-0 border-t border-[#d1d7db] bg-[#f0f2f5] px-2 py-1.5">
            <div className="h-6 rounded-full border border-[#d1d7db] bg-white" />
          </div>
        </div>
      </div>
      {steps.length > 1 ? (
        <div className="mt-4 space-y-1.5">
          <p className="text-[11px] font-medium text-muted-foreground">Simulated survey flow</p>
          {steps.map((step) => (
            <button
              key={step.step}
              type="button"
              onClick={() => setActiveStep(step.step)}
              className={
                "flex w-full items-start gap-2 rounded-md border px-2 py-1.5 text-left text-[11px] transition-colors " +
                (step.step === activeStep
                  ? "border-primary/40 bg-primary/5"
                  : "border-border hover:bg-muted/50")
              }
            >
              <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-semibold">
                {step.step}
              </span>
              <span>
                <strong className="block">{step.title}</strong>
                {step.body ? <span className="text-muted-foreground">{step.body}</span> : null}
              </span>
            </button>
          ))}
        </div>
      ) : null}
      {disclaimer ? <p className="mt-2 text-center text-[10px] text-muted-foreground">{disclaimer}</p> : null}
    </div>
  );
}
