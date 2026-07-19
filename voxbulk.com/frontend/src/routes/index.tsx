import { createFileRoute } from "@tanstack/react-router";
import VOXBULKHome from "@/components/VOXBULKHome";
import { brandAssets, SITE_ORIGIN } from "@/lib/brand";
import { PAGE_SEO, pageMeta } from "@/lib/seo-defaults";

const softwareJsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "VoxBulk",
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web",
  url: `${SITE_ORIGIN}/`,
  description: PAGE_SEO.home.description,
  offers: {
    "@type": "Offer",
    priceCurrency: "GBP",
    url: `${SITE_ORIGIN}/pricing`,
  },
  provider: {
    "@type": "Organization",
    name: "VoxBulk LTD",
    url: SITE_ORIGIN,
  },
};

const faqJsonLd = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: [
    {
      q: "What exactly does VoxBulk do?",
      a: "VoxBulk is a UK-built AI platform for WhatsApp surveys, QR customer feedback, AI phone interviews, and voice agents. Automate conversations, collect multilingual responses, and act from live dashboards.",
    },
    {
      q: "How long does setup take?",
      a: "Most teams are live within a few days. We connect messaging, scheduling, and your workflows, configure your surveys or interview scripts, and run test conversations before going live.",
    },
    {
      q: "How do AI voice interviews actually work?",
      a: "Candidates receive a scheduled invite, join at their slot, and complete a natural phone conversation with our AI interviewer. The AI asks tailored questions, listens, follows up, and produces a scored, summarised report.",
    },
    {
      q: "Can I use VoxBulk just for surveys or feedback?",
      a: "Yes. WhatsApp surveys and QR customer feedback are available as standalone products. Collect replies (including voice notes), translate them, and deliver actionable reports — named or anonymous.",
    },
    {
      q: "Is VoxBulk GDPR compliant?",
      a: "Yes. All data stays within UK/EU data centres, calls and messages are encrypted in transit and at rest, and we sign a Data Processing Agreement with every customer.",
    },
    {
      q: "What integrations are supported?",
      a: "Cronofy and Calendly for scheduling, WhatsApp for surveys and feedback, plus API access to push results into your ATS or HRIS. Custom integrations are available on Enterprise.",
    },
    {
      q: "Can candidates opt out of speaking to AI?",
      a: "Yes. The AI announces itself at the start of every interaction, and candidates can request a human follow-up at any time.",
    },
    {
      q: "Is there a contract or commitment?",
      a: "No long-term contract. Monthly subscription, cancel anytime with 30 days' notice. Enterprise customers can opt for annual terms with custom pricing.",
    },
  ].map(({ q, a }) => ({
    "@type": "Question",
    name: q,
    acceptedAnswer: { "@type": "Answer", text: a },
  })),
};

export const Route = createFileRoute("/")({
  head: () => ({
    meta: pageMeta("home", { url: `${SITE_ORIGIN}/` }),
    links: [
      { rel: "icon", href: brandAssets.favicon },
      { rel: "canonical", href: `${SITE_ORIGIN}/` },
    ],
    scripts: [
      {
        type: "application/ld+json",
        children: JSON.stringify(softwareJsonLd),
      },
      {
        type: "application/ld+json",
        children: JSON.stringify(faqJsonLd),
      },
    ],
  }),
  component: VOXBULKHome,
});
