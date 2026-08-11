import { Check } from "lucide-react";

export const DEMO_SERVICE_CARDS = [
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
    code: "recruitment",
    label: "AI Interview Screening",
    description: "AI interviews every candidate automatically — scoring skills, communication and fit.",
    tag: "Live",
  },
  {
    code: "expo",
    label: "VoxBulk Expo",
    description: "Visitors scan your booth QR and leave their details. Scored leads, exportable, pay once per show.",
    tag: "New",
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
    <div className="grid sm:grid-cols-2 gap-3">
      {DEMO_SERVICE_CARDS.map((card) => {
        const on = selectedCodes.includes(card.code);
        return (
          <button
            key={card.code}
            type="button"
            onClick={() => onToggle(card.code)}
            className={`text-left rounded-2xl border p-4 transition ${
              on ? "border-primary bg-primary/5 shadow-sm" : "border-border bg-white hover:border-primary/40"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-heading text-[15px]">{card.label}</span>
                  <span className="text-[10px] uppercase tracking-wider font-bold text-primary">{card.tag}</span>
                </div>
                <p className="mt-1.5 text-[13px] text-body leading-snug">{card.description}</p>
              </div>
              <span
                className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border ${
                  on ? "border-primary bg-primary text-white" : "border-border text-transparent"
                }`}
              >
                <Check size={14} />
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
