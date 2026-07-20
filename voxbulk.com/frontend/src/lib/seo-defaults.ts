/** Canonical marketing SEO copy for VoxBulk public pages. */

import { SITE_ORIGIN } from "@/lib/brand";

export const HOME_KEYWORDS =
  "whatsapp survey software, ai interview platform, customer feedback whatsapp, voice ai agents, recruitment automation uk, qr code feedback, multilingual surveys";

export const PAGE_SEO = {
  home: {
    title: "VoxBulk | WhatsApp Surveys, AI Interviews & Voice Agents for Business",
    description:
      "Run WhatsApp surveys, QR customer feedback, and AI phone interviews from one UK-built platform. Multilingual replies, scored interviews, and live dashboards — cancel anytime.",
    keywords: HOME_KEYWORDS,
    ogDescription:
      "WhatsApp surveys, QR customer feedback, and AI phone interviews — one platform for modern teams.",
  },
  surveys: {
    title: "WhatsApp Survey Software with AI Calling | VoxBulk",
    description:
      "Send surveys on WhatsApp or short AI calls. Get 50+ language replies, voice-note transcripts, and real-time charts — far higher response rates than email.",
    keywords:
      "whatsapp surveys, whatsapp survey software, ai calling surveys, multilingual survey software, pulse survey whatsapp, employee survey whatsapp",
    ogDescription:
      "WhatsApp and AI calling surveys with multilingual dashboards and actionable charts.",
  },
  feedback: {
    title: "WhatsApp Customer Feedback via QR Code | VoxBulk",
    description:
      "One QR per location. Guests reply on WhatsApp in their language — including voice notes — while you see English insights across every site.",
    keywords:
      "whatsapp customer feedback, qr code feedback, restaurant feedback software, multi location feedback, hospitality feedback whatsapp",
    ogDescription: "One QR. Customers reply on WhatsApp in their language — you get English insights.",
  },
  recruitment: {
    title: "AI Interview & Recruitment Automation | VoxBulk",
    description:
      "Automate CV screening, WhatsApp scheduling, and 10–12 minute AI phone interviews. Ranked shortlists for agencies and TA teams hiring at scale.",
    keywords:
      "ai interview software, automated candidate screening, recruitment automation, ai phone interviews, voice interview platform, ats screening",
    ogDescription:
      "AI screening, WhatsApp booking, and scored voice interviews — fully automated for high-volume hiring.",
  },
  pricing: {
    title: "Pricing — WhatsApp Surveys, Feedback & AI Interviews | VoxBulk",
    description:
      "Transparent pricing for WhatsApp surveys, customer feedback, and AI interview screening. Combine products, pay for usage, cancel anytime.",
    keywords: "voxbulk pricing, whatsapp survey pricing, ai interview cost, customer feedback pricing",
    ogDescription: "Simple pricing across WhatsApp surveys, feedback, and AI interviews. Cancel anytime.",
  },
  contact: {
    title: "Book a Demo | Contact VoxBulk",
    description:
      "Talk to VoxBulk about WhatsApp surveys, AI interviews, voice agents, pricing, integrations, and GDPR-ready onboarding for your team.",
    keywords: "voxbulk demo, whatsapp survey demo, ai interview demo, contact voxbulk",
    ogDescription: "Book a demo or ask about pricing, integrations, and GDPR onboarding.",
  },
} as const;

export type PageSeoOverride = {
  title?: string;
  description?: string;
  keywords?: string;
  og_description?: string;
  ogDescription?: string;
};

export function resolvePageSeo(
  page: keyof typeof PAGE_SEO,
  override?: PageSeoOverride | null,
): {
  title: string;
  description: string;
  keywords: string;
  ogDescription: string;
} {
  const base = PAGE_SEO[page];
  const og =
    (override?.og_description || override?.ogDescription || "").trim() || base.ogDescription;
  return {
    title: (override?.title || "").trim() || base.title,
    description: (override?.description || "").trim() || base.description,
    keywords: (override?.keywords || "").trim() || base.keywords,
    ogDescription: og,
  };
}

export function pageMeta(
  page: keyof typeof PAGE_SEO,
  opts?: { url?: string; ogType?: string; override?: PageSeoOverride | null; ogImage?: string | null },
): Array<Record<string, string>> {
  const seo = resolvePageSeo(page, opts?.override);
  const url = opts?.url || `${SITE_ORIGIN}/${page === "home" ? "" : page}`;
  const meta: Array<Record<string, string>> = [
    { title: seo.title },
    { name: "description", content: seo.description },
    { name: "keywords", content: seo.keywords },
    { property: "og:title", content: seo.title },
    { property: "og:description", content: seo.ogDescription },
    { property: "og:type", content: opts?.ogType || "website" },
    { property: "og:url", content: url },
    { name: "twitter:card", content: "summary_large_image" },
    { name: "twitter:title", content: seo.title },
    { name: "twitter:description", content: seo.ogDescription },
  ];
  const image = (opts?.ogImage || "").trim();
  if (image) {
    const abs = image.startsWith("http") ? image : `${SITE_ORIGIN}${image.startsWith("/") ? image : `/${image}`}`;
    meta.push({ property: "og:image", content: abs });
    meta.push({ name: "twitter:image", content: abs });
  }
  return meta;
}
