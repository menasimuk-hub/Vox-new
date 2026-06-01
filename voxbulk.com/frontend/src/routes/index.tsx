import { createFileRoute } from "@tanstack/react-router";
import VOXBULKHome from "@/components/VOXBULKHome";
import { brandAssets } from "@/lib/brand";

const faqJsonLd = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: [
    { q: "What exactly does VoxBulk do?", a: "VoxBulk is an AI assistant platform that automates conversations, workflows and data collection. Our first live service is end-to-end recruitment automation — CV screening, scheduling, AI voice interviews, scoring and final-round booking. We also offer AI-run WhatsApp surveys." },
    { q: "How long does setup take?", a: "Most teams are live within a few days. We connect to your ATS, calendar (Cronofy or Calendly) and messaging tools, configure your roles, and run test conversations before going live." },
    { q: "How do AI voice interviews actually work?", a: "Candidates receive a scheduled link, dial in at their slot, and complete a natural conversation with our AI. The AI asks tailored questions, listens, follows up, and produces a scored, summarised report — all without human involvement." },
    { q: "Can I use VoxBulk just for surveys?", a: "Yes. WhatsApp surveys are available as a standalone service. The AI builds the questions, sends them, collects responses, and delivers a named or anonymous feedback report — whichever you need." },
    { q: "Is VoxBulk GDPR compliant?", a: "Yes. All data stays within UK/EU data centres, calls and messages are encrypted in transit and at rest, and we sign a Data Processing Agreement with every customer." },
    { q: "What integrations are supported?", a: "Cronofy and Calendly for scheduling, WhatsApp for messaging surveys, plus API access to push results into your ATS or HRIS. Custom integrations are available on the Enterprise plan." },
    { q: "Can candidates opt out of speaking to AI?", a: "Yes. The AI announces itself at the start of every interaction, and candidates can request a human follow-up at any time." },
    { q: "Is there a contract or commitment?", a: "No long-term contract. Monthly subscription, cancel anytime with 30 days' notice. Enterprise customers can opt for annual terms with custom pricing." },
  ].map(({ q, a }) => ({
    "@type": "Question",
    name: q,
    acceptedAnswer: { "@type": "Answer", text: a },
  })),
};

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "VoxBulk — AI Assistant Platform for Voice, Messaging & Workflows" },
      {
        name: "description",
        content:
          "VoxBulk automates conversations, workflows and data collection for businesses. Live now: AI-powered recruitment automation and WhatsApp surveys.",
      },
      { property: "og:title", content: "VoxBulk — AI Assistant Platform for Voice, Messaging & Workflows" },
      {
        property: "og:description",
        content:
          "Intelligent voice and messaging tools that save teams time and deliver real insights. Live now: end-to-end recruitment automation.",
      },
      { property: "og:type", content: "website" },
      { property: "og:url", content: "https://voxbulk.com/" },
    ],
    links: [
      { rel: "icon", href: brandAssets.favicon },
      { rel: "canonical", href: "https://voxbulk.com/" },
    ],
    scripts: [
      {
        type: "application/ld+json",
        children: JSON.stringify(faqJsonLd),
      },
    ],
  }),
  component: VOXBULKHome,
});
