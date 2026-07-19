import { createFileRoute } from "@tanstack/react-router";
import VOXBULKHome, { type HomeFaqItem } from "@/components/VOXBULKHome";
import { brandAssets, SITE_ORIGIN } from "@/lib/brand";
import { frontpageApiFetch } from "@/lib/api";
import { fetchSeoSettings } from "@/lib/seo";
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

function buildFaqJsonLd(items: Array<{ question: string; answer: string }>) {
  const entity = items.length
    ? items
    : [
        {
          question: "What exactly does VoxBulk do?",
          answer: PAGE_SEO.home.description,
        },
      ];
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: entity.map(({ question, answer }) => ({
      "@type": "Question",
      name: question,
      acceptedAnswer: { "@type": "Answer", text: answer },
    })),
  };
}

export const Route = createFileRoute("/")({
  loader: async () => {
    const [settings, faqPayload] = await Promise.all([
      fetchSeoSettings(),
      frontpageApiFetch<{
        items: Array<{ question?: string; answer?: string; title?: string; slug?: string }>;
      }>("/frontpage/faq").catch(() => ({ items: [] })),
    ]);
    const faqRows = (faqPayload.items || [])
      .map((row) => ({
        question: String(row.question || row.title || "").trim(),
        answer: String(row.answer || "").trim(),
        slug: row.slug,
      }))
      .filter((row) => row.question && row.answer);
    return { settings, faqRows };
  },
  head: ({ loaderData }) => {
    const s = loaderData?.settings || {};
    const keywords = [s.home_focus_keyword, s.home_tags].filter(Boolean).join(", ");
    const faqJsonLd = buildFaqJsonLd(loaderData?.faqRows || []);
    return {
      meta: pageMeta("home", {
        url: `${SITE_ORIGIN}/`,
        override: {
          title: s.home_title,
          description: s.home_description,
          keywords: keywords || undefined,
          ogDescription: s.home_description || PAGE_SEO.home.ogDescription,
        },
      }),
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
    };
  },
  component: HomePage,
});

function HomePage() {
  const { faqRows } = Route.useLoaderData();
  const items: HomeFaqItem[] = (faqRows || []).map((row) => ({
    q: row.question,
    a: row.answer,
    slug: row.slug,
  }));
  return <VOXBULKHome faqItems={items} />;
}
