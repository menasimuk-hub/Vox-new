import { Check } from "lucide-react";

export const DEMO_SERVICE_CARDS = [
  {
    code: "recruitment",
    label: "AI Interview Screening",
    description: "AI interviews every candidate automatically — scoring skills, communication and fit.",
    tag: "Live",
  },
  {
    code: "feedback",
    label: "Customer Feedback",
    description: "One QR on the table or counter. Customers scan, chat on WhatsApp, you get a weekly report.",
    tag: "Live",
  },
  {
    code: "surveys",
    label: "WhatsApp Surveys",
    description: "Smart surveys straight to WhatsApp. 98% open rates, answers in under a minute.",
    tag: "Live",
  },
  {
    code: "expo",
    label: "VoxBulk Expo",
    description: "Visitors scan your booth QR and leave their details. Scored leads, exportable, pay once per show.",
    tag: "Live",
  },
  {
    code: "smart_card",
    label: "Smart Card QR",
    description: "One personal QR per sales rep. Every scan becomes a scored, attributed lead.",
    tag: "Live",
  },
] as const;

export function ServicePicker({
  selected,
  onToggle,
}: {
  selected: string[];
  onToggle: (code: string) => void;
}) {
  const selectedCodes = Array.isArray(selected) ? selected : [];
  return (
    <div className="rounded-3xl border border-[#d9e3f2] bg-gradient-to-b from-[#f7f9fc] to-white p-4 shadow-[0_12px_40px_rgba(15,40,80,0.08)] sm:p-5">
      <p className="mb-3 text-[11px] font-bold uppercase tracking-[0.14em] text-[var(--primary,#1e6fd9)]">
        Choose services to explore
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {DEMO_SERVICE_CARDS.map((card) => {
          const on = selectedCodes.includes(card.code);
          return (
            <button
              key={card.code}
              type="button"
              onClick={() => onToggle(card.code)}
              className={`text-left rounded-2xl border p-4 transition ${
                on
                  ? "border-[var(--primary,#1e6fd9)] bg-[color-mix(in_srgb,var(--primary,#1e6fd9)_10%,white)] shadow-sm ring-2 ring-[color-mix(in_srgb,var(--primary,#1e6fd9)_28%,transparent)]"
                  : "border-[#e3eaf5] bg-white hover:border-[var(--primary,#1e6fd9)]/50"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-[#10233f] text-[15px]">{card.label}</span>
                    <span className="rounded-full bg-[color-mix(in_srgb,var(--primary,#1e6fd9)_12%,white)] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-[var(--primary,#1e6fd9)]">
                      {card.tag}
                    </span>
                  </div>
                  <p className="mt-1.5 text-[13px] leading-snug text-[#5a6b82]">{card.description}</p>
                </div>
                <span
                  className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border ${
                    on
                      ? "border-[var(--primary,#1e6fd9)] bg-[var(--primary,#1e6fd9)] text-white"
                      : "border-[#cfd9e8] text-transparent"
                  }`}
                >
                  <Check size={14} />
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
