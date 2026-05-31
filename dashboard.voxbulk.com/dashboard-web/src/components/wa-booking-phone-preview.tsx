import * as React from "react";

export type WaPreviewButton = {
  label: string;
  type?: string;
};

export type WaBookingPhonePreviewProps = {
  body: string;
  role?: string;
  templateName?: string;
  buttons?: WaPreviewButton[];
  confirmationBody?: string;
  confirmationButtons?: WaPreviewButton[];
  confirmationTemplateName?: string;
  syncLabel?: string;
};

const DEFAULT_MANAGE_BUTTONS: WaPreviewButton[] = [
  { label: "🔄 Reschedule", type: "quick_reply" },
  { label: "❌ Cancel", type: "quick_reply" },
];

function buttonStyle(type?: string, index?: number) {
  const t = String(type || "").toLowerCase();
  if (t === "url" || index === 0) {
    return "border-[#00a884]/40 bg-[#004d40] text-[#53bdeb]";
  }
  return "border-white/10 bg-[#1f2c34] text-[#e9edef]";
}

function WaBubble({
  body,
  role,
  buttons,
}: {
  body: string;
  role?: string;
  buttons: WaPreviewButton[];
}) {
  return (
    <div className="ml-auto max-w-[92%] rounded-lg rounded-tr-sm bg-[#005c4b] px-2.5 py-2 text-[10px] leading-relaxed text-[#e9edef] shadow-sm">
      <p className="whitespace-pre-wrap">{body}</p>
      {role ? <p className="mt-1.5 text-[9px] text-[#8696a0]">{role}</p> : null}
      {buttons.length > 0 && (
        <div className="mt-2 space-y-1">
          {buttons.map((btn, i) => (
            <div
              key={`${btn.label}-${i}`}
              className={`overflow-hidden rounded-md border px-2 py-1.5 text-center text-[10px] font-medium ${buttonStyle(btn.type, i)}`}
            >
              {btn.label}
            </div>
          ))}
        </div>
      )}
      <p className="mt-1 text-right text-[8px] text-[#8696a0]">9:41 ✓✓</p>
    </div>
  );
}

/** iPhone frame with WhatsApp-style booking message preview (invite + confirmation). */
export function WaBookingPhonePreview({
  body,
  role,
  templateName,
  buttons,
  confirmationBody,
  confirmationButtons,
  confirmationTemplateName,
  syncLabel,
}: WaBookingPhonePreviewProps) {
  const inviteButtons = Array.isArray(buttons) ? buttons : [];
  const manageButtons = confirmationButtons?.length ? confirmationButtons : DEFAULT_MANAGE_BUTTONS;
  const showConfirmation = Boolean(confirmationBody) || manageButtons.length > 0;

  return (
    <div className="mx-auto w-full max-w-[220px]">
      <p className="mb-2 text-center text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        WhatsApp preview
      </p>
      {syncLabel ? (
        <p className="mb-2 text-center text-[10px] text-muted-foreground">{syncLabel}</p>
      ) : null}
      <div
        className="relative mx-auto rounded-[2.4rem] border-[3px] border-zinc-800 bg-zinc-900 p-[7px] shadow-xl dark:border-zinc-600"
        style={{ aspectRatio: "9 / 19.5" }}
      >
        <div className="absolute -left-[4px] top-[18%] h-8 w-[3px] rounded-l bg-zinc-700" />
        <div className="absolute -left-[4px] top-[28%] h-12 w-[3px] rounded-l bg-zinc-700" />
        <div className="absolute -right-[4px] top-[24%] h-16 w-[3px] rounded-r bg-zinc-700" />

        <div className="relative flex h-full flex-col overflow-hidden rounded-[2rem] bg-[#0b141a]">
          <div className="relative shrink-0 bg-[#1f2c34] px-3 pb-2 pt-2">
            <div className="mx-auto mb-2 h-[22px] w-[78px] rounded-full bg-black" />
            <div className="flex items-center justify-between text-[9px] text-white/80">
              <span>9:41</span>
              <span className="truncate px-2 font-medium">VoxBulk</span>
              <span>5G</span>
            </div>
          </div>

          <div
            className="flex-1 space-y-2 overflow-y-auto px-2 py-3"
            style={{
              backgroundColor: "#0b141a",
              backgroundImage:
                "radial-gradient(circle at 20% 20%, rgba(37,211,102,0.06) 0%, transparent 40%), radial-gradient(circle at 80% 80%, rgba(37,211,102,0.04) 0%, transparent 35%)",
            }}
          >
            <WaBubble body={body} role={role} buttons={inviteButtons} />
            {showConfirmation ? (
              <WaBubble
                body={
                  confirmationBody ||
                  "Hi Alex, your interview is confirmed ✅\n\n📅 Sat 14 Jun 2026\n🕐 10:00 AM"
                }
                buttons={manageButtons}
              />
            ) : null}
          </div>

          <div className="shrink-0 border-t border-white/5 bg-[#1f2c34] px-2 py-1.5">
            <div className="h-6 rounded-full bg-[#2a3942]" />
          </div>
        </div>
      </div>
      {templateName || confirmationTemplateName ? (
        <p className="mt-2 truncate text-center text-[10px] text-muted-foreground" title={[templateName, confirmationTemplateName].filter(Boolean).join(" · ")}>
          {[templateName, confirmationTemplateName].filter(Boolean).join(" · ")}
        </p>
      ) : null}
    </div>
  );
}
