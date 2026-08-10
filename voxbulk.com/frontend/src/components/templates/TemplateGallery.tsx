import { useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { PhoneFrame } from "./PhoneFrame";
import { TemplateArt } from "./TemplateArt";
import { SurveyTemplateView } from "./SurveyTemplateView";
import { SmartCardView, SMARTCARD_THEMES, VOXBULK_CARD } from "./SmartCardView";
import { SURVEY_TEMPLATES } from "@/lib/survey-templates";

function QrPanel({ url, label }: { url: string; label: string }) {
  return (
    <div className="flex items-center gap-4 rounded-2xl border border-border bg-white p-4 shadow-elegant">
      <div className="shrink-0 rounded-xl border border-border p-2">
        <QRCodeSVG value={url} size={84} bgColor="#ffffff" fgColor="#0A1628" level="M" />
      </div>
      <div className="min-w-0">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">Scan to test live</p>
        <p className="mt-1 text-[13px] font-semibold text-heading">{label}</p>
        <p className="mt-1 text-[12px] text-muted-text">Point your phone camera at the code — the real customer flow opens instantly.</p>
      </div>
    </div>
  );
}

function Chips({ items, active, onPick }: { items: { id: string; name: string }[]; active: string; onPick: (id: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((t) => (
        <button
          key={t.id}
          onClick={() => onPick(t.id)}
          className={`inline-flex h-8 items-center rounded-full px-3.5 text-[12.5px] font-semibold transition-all ${
            active === t.id ? "bg-navy text-white shadow-elegant" : "border border-border bg-white text-heading hover:border-primary/40"
          }`}
        >
          {t.name}
        </button>
      ))}
    </div>
  );
}

/** Live mobile feedback-survey template gallery with QR test codes. */
export function SurveyTemplateGallery({ baseUrl = "https://voxbulk.com/t" }: { baseUrl?: string }) {
  const [id, setId] = useState(SURVEY_TEMPLATES[0].id);
  const t = SURVEY_TEMPLATES.find((x) => x.id === id)!;
  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
      <div className="min-w-0">
        <span className="eyebrow">Mobile templates</span>
        <h2 className="mt-4 text-[32px] font-bold leading-[1.06] tracking-[-0.03em] text-heading md:text-[44px]">
          Live templates, <span className="serif-italic text-primary">ready to brand</span>.
        </h2>
        <p className="mt-4 max-w-[520px] text-[15.5px] text-body">
          Every industry and seasonal theme below is a real, working mobile survey — tap through it in the phone. We load your company name, logo and questions before launch, and there are many more templates and industries available on request.
        </p>
        <div className="mt-7 space-y-4">
          <div>
            <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.16em] text-muted-text">By industry</p>
            <Chips items={SURVEY_TEMPLATES.filter((x) => x.category === "industry")} active={id} onPick={setId} />
          </div>
          <div>
            <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.16em] text-muted-text">Seasonal</p>
            <Chips items={SURVEY_TEMPLATES.filter((x) => x.category === "seasonal")} active={id} onPick={setId} />
          </div>
        </div>
        <p className="mt-6 max-w-[480px] text-[14.5px] text-body">{t.blurb}</p>
        <div className="mt-6 max-w-[430px]">
          <QrPanel url={`${baseUrl}/${t.id}`} label={`${t.name} survey demo`} />
        </div>
      </div>
      <div className="mx-auto lg:mx-0">
        <PhoneFrame>
          <SurveyTemplateView
            key={t.id}
            theme={t.theme}
            questions={t.questions}
            copy={{
              companyName: "VoxBulk",
              serviceLabel: t.name,
              thankYouTitle: t.thankYouTitle,
              thankYouSubtitle: t.thankYouSubtitle,
            }}
            Art={() => <TemplateArt accent={t.theme.accent} accent2={t.theme.accent2} motifs={t.motifs} />}
          />
        </PhoneFrame>
      </div>
    </div>
  );
}

/** Live smart-card QR template gallery (5 themes). */
export function SmartCardGallery({ baseUrl = "https://voxbulk.com/c" }: { baseUrl?: string }) {
  const [id, setId] = useState(SMARTCARD_THEMES[0].id);
  const t = SMARTCARD_THEMES.find((x) => x.id === id)!;
  return (
    <div className="grid gap-10 lg:grid-cols-[auto_minmax(0,1fr)] lg:items-start">
      <div className="mx-auto lg:mx-0">
        <PhoneFrame>
          <SmartCardView key={t.id} card={VOXBULK_CARD} theme={t} />
        </PhoneFrame>
      </div>
      <div className="min-w-0">
        <span className="eyebrow">Smart card themes</span>
        <h2 className="mt-4 text-[32px] font-bold leading-[1.06] tracking-[-0.03em] text-heading md:text-[44px]">
          Branded themes. <span className="serif-italic text-primary">One scan.</span>
        </h2>
        <p className="mt-4 max-w-[520px] text-[15.5px] text-body">
          Your QR code opens a branded mobile card — contact details, save-to-phone, WhatsApp and a 60-second feedback survey in one screen. Pick a theme, we brand it with your logo and colours.
        </p>
        <div className="mt-7">
          <Chips items={SMARTCARD_THEMES} active={id} onPick={setId} />
        </div>
        <p className="mt-6 max-w-[480px] text-[14.5px] text-body">{t.blurb}</p>
        <div className="mt-6 max-w-[430px]">
          <QrPanel url={`${baseUrl}/${t.id}`} label={`${t.name} smart card demo`} />
        </div>
      </div>
    </div>
  );
}
