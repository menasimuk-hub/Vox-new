import * as React from "react";
import { Signal, Wifi, BatteryFull, Phone, Video, ChevronLeft, Plus, Mic, Camera, Smile } from "lucide-react";

export type PreviewButton = { label: string; type?: "QUICK_REPLY" | "URL" | "PHONE_NUMBER" | "COPY_CODE" };

type Props = {
  banner?: string | null;
  body?: string;
  buttons?: (string | PreviewButton)[];
  footer?: string;
  businessName?: string;
  size?: "sm" | "md" | "lg";
};

/** iPhone 17 Pro — Titanium frame, Dynamic Island, full-size WhatsApp chat preview. */
export function IPhonePreview({
  banner,
  body = "",
  buttons = [],
  footer,
  businessName = "Your Business",
  size = "lg",
}: Props) {
  const w = size === "lg" ? 320 : size === "md" ? 280 : 240;
  const h = Math.round(w * 2.165);
  const normButtons: PreviewButton[] = buttons.map((b) => (typeof b === "string" ? { label: b } : b));
  const iconFor = (t?: PreviewButton["type"]) =>
    t === "URL" ? "🔗" : t === "PHONE_NUMBER" ? "📞" : t === "COPY_CODE" ? "📋" : "↩";

  const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  return (
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

          <div className="relative h-full w-full overflow-hidden rounded-[47px] bg-[#0b141a]">
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

            <div
              className="flex items-center gap-2 px-3 py-2 text-white"
              style={{ background: "linear-gradient(180deg,#1f2c33 0%, #182229 100%)" }}
            >
              <ChevronLeft className="size-4 opacity-80" />
              <div className="grid size-7 place-items-center rounded-full bg-[#25D366] text-[10px] font-bold text-white">
                {businessName.slice(0, 1).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[12px] font-semibold leading-tight">{businessName}</p>
                <p className="text-[9px] text-white/60">online</p>
              </div>
              <Video className="size-4 opacity-80" />
              <Phone className="size-4 opacity-80" />
            </div>

            <div
              className="relative flex-1 overflow-y-auto px-2.5 py-3"
              style={{
                height: `calc(100% - 44px - 44px - 56px)`,
                backgroundColor: "#0b141a",
                backgroundImage:
                  "radial-gradient(circle at 20% 10%, rgba(37,211,102,.06), transparent 40%), radial-gradient(circle at 80% 80%, rgba(37,211,102,.05), transparent 40%)",
              }}
            >
              <div className="mx-auto mb-3 w-fit rounded-md bg-[#1f2c33] px-2 py-0.5 text-[9px] text-white/70">Today</div>
              <div className="mr-auto max-w-[88%] overflow-hidden rounded-lg rounded-tl-sm bg-[#1f2c33] shadow">
                {banner && <img src={banner} alt="" className="aspect-[1.91/1] w-full object-cover" />}
                <div className="px-2 py-1.5">
                  <p className="whitespace-pre-wrap text-[11px] leading-snug text-white">
                    {body || "Your message body will appear here…"}
                  </p>
                  <p className="mt-1 text-right text-[8px] text-white/50">{now}</p>
                </div>
                {footer && <p className="px-2 pb-1.5 text-[9px] italic text-white/50">{footer}</p>}
                {normButtons.length > 0 && (
                  <div className="border-t border-white/10">
                    {normButtons.map((b, i) => (
                      <div
                        key={`${b.label}-${i}`}
                        className="border-t border-white/5 px-2 py-1.5 text-center text-[11px] font-medium text-[#53bdeb] first:border-t-0"
                      >
                        <span className="mr-1 opacity-70">{iconFor(b.type)}</span>
                        {b.label}
                      </div>
                    ))}
                  </div>
                )}
              </div>
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

            <div className="absolute bottom-1.5 left-1/2 z-30 h-[4px] w-[110px] -translate-x-1/2 rounded-full bg-white/70" />
          </div>
        </div>
      </div>
    </div>
  );
}
