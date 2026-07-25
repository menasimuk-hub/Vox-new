import * as React from "react";
import { BatteryFull, ChevronLeft, Mic, Phone, Plus, Signal, Smile, Video, Wifi, Camera } from "lucide-react";
import { cn } from "@/lib/utils";

export type ExpoChatBubble = {
  from: "bot" | "user";
  text: string;
};

type FrameProps = {
  children: React.ReactNode;
  size?: "sm" | "md";
  label?: string;
};

/** iPhone 17 Pro Max–style titanium frame for Expo WA / web previews. */
export function ExpoIPhoneFrame({ children, size = "md", label }: FrameProps) {
  const w = size === "sm" ? 260 : 300;
  const h = Math.round(w * 2.165);
  const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  return (
    <div className="flex flex-col items-center gap-2">
      {label ? <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</p> : null}
      <div className="relative mx-auto" style={{ width: w, height: h }}>
        <div
          className="absolute inset-0 rounded-[52px] p-[3px]"
          style={{
            background:
              "linear-gradient(145deg, #6b6b6e 0%, #2c2c2e 25%, #4a4a4d 55%, #1c1c1e 80%, #5a5a5d 100%)",
            boxShadow:
              "0 30px 60px -20px rgba(0,0,0,.55), 0 0 0 1px rgba(255,255,255,.04), inset 0 1px 0 rgba(255,255,255,.18)",
          }}
        >
          <div className="relative h-full w-full overflow-hidden rounded-[49px] bg-black p-[2px]">
            <span className="absolute -left-[5px] top-[110px] h-[28px] w-[3px] rounded-l bg-[#3a3a3c]" />
            <span className="absolute -left-[5px] top-[160px] h-[44px] w-[3px] rounded-l bg-[#3a3a3c]" />
            <span className="absolute -left-[5px] top-[214px] h-[44px] w-[3px] rounded-l bg-[#3a3a3c]" />
            <span className="absolute -right-[5px] top-[170px] h-[64px] w-[3px] rounded-r bg-[#3a3a3c]" />
            <div className="relative flex h-full w-full flex-col overflow-hidden rounded-[47px] bg-[#0b141a]">
              <div className="relative z-20 flex h-[44px] items-center justify-between px-7 pt-2 text-[11px] font-semibold text-white">
                <span className="tabular-nums">{now}</span>
                <span className="flex items-center gap-1">
                  <Signal className="size-3" />
                  <Wifi className="size-3" />
                  <BatteryFull className="size-3.5" />
                </span>
              </div>
              <div className="absolute left-1/2 top-[10px] z-30 flex h-[34px] w-[112px] -translate-x-1/2 items-center justify-center rounded-full bg-black">
                <span className="ml-12 size-1.5 rounded-full bg-[#1f1f22] ring-1 ring-[#2a2a2d]" />
              </div>
              <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
              <div className="absolute bottom-1.5 left-1/2 z-30 h-[4px] w-[110px] -translate-x-1/2 rounded-full bg-white/70" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

type WaProps = {
  businessName: string;
  messages: ExpoChatBubble[];
  size?: "sm" | "md";
  label?: string;
};

export function ExpoWaPhonePreview({ businessName, messages, size = "md", label = "WhatsApp" }: WaProps) {
  const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return (
    <ExpoIPhoneFrame size={size} label={label}>
      <div
        className="flex items-center gap-2 px-3 py-2 text-white"
        style={{ background: "linear-gradient(180deg,#1f2c33 0%, #182229 100%)" }}
      >
        <ChevronLeft className="size-4 opacity-80" />
        <div className="grid size-7 place-items-center rounded-full bg-[#25D366] text-[10px] font-bold text-white">
          {(businessName || "V").slice(0, 1).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[12px] font-semibold leading-tight">{businessName || "Your stand"}</p>
          <p className="text-[9px] text-white/60">online</p>
        </div>
        <Video className="size-4 opacity-80" />
        <Phone className="size-4 opacity-80" />
      </div>
      <div
        className="overflow-y-auto px-2.5 py-3"
        style={{
          height: "calc(100% - 100px)",
          backgroundImage:
            "radial-gradient(circle at 20% 10%, rgba(37,211,102,.06), transparent 40%), radial-gradient(circle at 80% 80%, rgba(37,211,102,.05), transparent 40%)",
        }}
      >
        <div className="mx-auto mb-3 w-fit rounded-md bg-[#1f2c33] px-2 py-0.5 text-[9px] text-white/70">Today</div>
        {messages.map((m, i) => (
          <div
            key={`${m.from}-${i}`}
            className={cn(
              "mb-2 max-w-[88%] overflow-hidden rounded-lg px-2 py-1.5 shadow",
              m.from === "bot"
                ? "mr-auto rounded-tl-sm bg-[#1f2c33] text-white"
                : "ml-auto rounded-tr-sm bg-[#005c4b] text-white",
            )}
          >
            <p className="whitespace-pre-wrap text-[11px] leading-snug">{m.text}</p>
            <p className="mt-1 text-right text-[8px] text-white/50">{now}</p>
          </div>
        ))}
      </div>
      <div className="absolute bottom-0 left-0 right-0 flex items-center gap-1.5 bg-[#1f2c33] px-2 py-2 pb-7">
        <div className="flex flex-1 items-center gap-1.5 rounded-full bg-[#2a3942] px-2.5 py-1.5">
          <Smile className="size-3.5 text-white/60" />
          <span className="flex-1 text-[10px] text-white/40">Message</span>
          <Plus className="size-3.5 text-white/60" />
          <Camera className="size-3.5 text-white/60" />
        </div>
        <div className="grid size-7 place-items-center rounded-full bg-[#25D366]">
          <Mic className="size-3.5 text-white" />
        </div>
      </div>
    </ExpoIPhoneFrame>
  );
}

type WebProps = {
  companyName: string;
  eventName: string;
  contactHint: string;
  questions: string[];
  size?: "sm" | "md";
  label?: string;
  templateName?: string;
};

export function ExpoWebPhonePreview({
  companyName,
  eventName,
  contactHint,
  questions,
  size = "md",
  label = "Web",
  templateName = "Default",
}: WebProps) {
  return (
    <ExpoIPhoneFrame size={size} label={label}>
      <div className="flex h-full flex-col bg-white text-[#0f172a]">
        <div className="border-b border-slate-200 bg-gradient-to-br from-slate-50 to-white px-4 pb-3 pt-10">
          <p className="text-[10px] font-medium uppercase tracking-wide text-slate-400">{templateName} template</p>
          <p className="mt-1 text-[15px] font-semibold leading-tight">{companyName || "Your company"}</p>
          <p className="text-[11px] text-slate-500">{eventName || "Exhibition"}</p>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3 pb-10">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
            <p className="text-[11px] font-medium text-slate-700">Contact</p>
            <p className="mt-1 text-[10px] leading-snug text-slate-500">{contactHint}</p>
            <div className="mt-2 grid gap-1.5">
              <div className="h-7 rounded-md border border-dashed border-slate-300 bg-white text-center text-[10px] leading-7 text-slate-400">
                Upload business card photo
              </div>
              <div className="h-7 rounded-md border border-slate-200 bg-white px-2 text-[10px] leading-7 text-slate-400">
                Name
              </div>
              <div className="h-7 rounded-md border border-slate-200 bg-white px-2 text-[10px] leading-7 text-slate-400">
                Company
              </div>
              <div className="h-7 rounded-md border border-slate-200 bg-white px-2 text-[10px] leading-7 text-slate-400">
                Mobile
              </div>
            </div>
          </div>
          {questions.slice(0, 3).map((q, i) => (
            <div key={i} className="rounded-xl border border-slate-200 p-3">
              <p className="text-[11px] font-medium text-slate-700">{q}</p>
              <div className="mt-2 h-8 rounded-md border border-slate-200 bg-slate-50" />
            </div>
          ))}
          <div className="rounded-full bg-slate-900 py-2 text-center text-[11px] font-semibold text-white">Continue</div>
        </div>
      </div>
    </ExpoIPhoneFrame>
  );
}
