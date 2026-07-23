import { createFileRoute, Link } from "@tanstack/react-router";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { frontpageApiFetch } from "@/lib/api";
import { ArrowRight, BookOpen, HelpCircle, Plug } from "lucide-react";

type FaqItem = {
  slug: string;
  title: string;
  question?: string;
  meta_description?: string;
  answer?: string;
  category_name?: string;
  category_slug?: string;
};

type HelpGroup = {
  key: string;
  title: string;
  blurb: string;
  items: FaqItem[];
};

const FALLBACK_ITEMS: FaqItem[] = [
  {
    slug: "what-exactly-does-voxbulk-do",
    title: "What exactly does VoxBulk do?",
    question: "What exactly does VoxBulk do?",
    category_name: "Product",
    category_slug: "product",
    meta_description:
      "VoxBulk is a UK-built AI platform for WhatsApp surveys, QR customer feedback, AI phone interviews, and voice agents.",
  },
  {
    slug: "zoho-recruit-what-is-voxbulk-ai-voice-screening",
    title: "What is VoxBulk AI Voice Screening for Zoho Recruit?",
    question: "What is VoxBulk AI Voice Screening for Zoho Recruit?",
    category_name: "Zoho Recruit",
    category_slug: "zoho-recruit",
    meta_description:
      "AI phone interviews in English and Arabic for Zoho Recruit — score, status, and report back to recruiters.",
  },
];

function groupItems(items: FaqItem[]): HelpGroup[] {
  const map = new Map<string, HelpGroup>();
  for (const it of items) {
    const key = it.category_slug || "product";
    const title = it.category_name || "Product";
    if (!map.has(key)) {
      map.set(key, {
        key,
        title,
        blurb:
          key === "zoho-recruit"
            ? "Install, connect, and use AI voice screening with Zoho Recruit."
            : "Product, billing, security, and how VoxBulk works.",
        items: [],
      });
    }
    map.get(key)!.items.push(it);
  }
  const order = ["product", "zoho-recruit"];
  return [...map.values()].sort((a, b) => {
    const ai = order.indexOf(a.key);
    const bi = order.indexOf(b.key);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });
}

export const Route = createFileRoute("/help/")({
  loader: async () => {
    try {
      const data = await frontpageApiFetch<{ items: FaqItem[] }>("/frontpage/faq");
      const items = data.items?.length ? data.items : FALLBACK_ITEMS;
      return { items, groups: groupItems(items) };
    } catch {
      return { items: FALLBACK_ITEMS, groups: groupItems(FALLBACK_ITEMS) };
    }
  },
  head: () => ({
    meta: [
      { title: "Help centre — VoxBulk" },
      {
        name: "description",
        content:
          "Public VoxBulk help centre: product FAQs, Zoho Recruit AI voice screening setup, pricing, privacy, and support.",
      },
      { name: "robots", content: "index,follow" },
      { property: "og:title", content: "Help centre — VoxBulk" },
      { property: "og:url", content: "https://voxbulk.com/help" },
      {
        property: "og:description",
        content: "Browse VoxBulk FAQs and Zoho Recruit integration help. No login required.",
      },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/help" }],
  }),
  component: HelpIndex,
});

function HelpIndex() {
  const { groups } = Route.useLoaderData() as { groups: HelpGroup[] };

  return (
    <div className="bg-beige text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[110px] md:pt-[130px] pb-24">
        <section className="border-b border-navy/10">
          <div className="max-w-[860px] mx-auto px-5 md:px-10 pb-10 md:pb-14">
            <div className="flex items-center gap-2 text-[12px] uppercase tracking-[0.22em] text-navy/60">
              <HelpCircle size={14} className="text-gold" />
              <span>Resources · Help</span>
            </div>
            <h1 className="mt-5 font-serif text-[42px] md:text-[56px] leading-[1.05] tracking-[-0.02em] text-navy">
              Help centre
            </h1>
            <p className="mt-5 max-w-[560px] text-[16px] text-navy/70 leading-[1.65]">
              Public guides and FAQs — no login required. Includes product answers and Zoho Recruit AI voice screening.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                to="/help/zoho-recruit"
                className="inline-flex items-center gap-2 rounded-full bg-navy text-white px-5 py-2.5 text-[13px] font-semibold hover:bg-navy/90 transition-colors"
              >
                <Plug size={14} /> Zoho Recruit setup guide
              </Link>
              <a
                href="mailto:support@voxbulk.com"
                className="inline-flex items-center gap-2 rounded-full border border-navy/15 bg-white px-5 py-2.5 text-[13px] font-semibold text-navy hover:border-gold transition-colors"
              >
                Email support
              </a>
            </div>
          </div>
        </section>

        <section className="max-w-[860px] mx-auto px-5 md:px-10 mt-12 space-y-12">
          <Link
            to="/help/zoho-recruit"
            className="group block rounded-2xl border border-navy/10 bg-white p-6 md:p-8 hover:border-gold transition-colors"
          >
            <div className="flex items-start gap-4">
              <div className="w-11 h-11 rounded-xl bg-beige flex items-center justify-center text-gold shrink-0">
                <BookOpen size={20} />
              </div>
              <div>
                <div className="text-[12px] uppercase tracking-[0.18em] text-navy/50">Featured guide</div>
                <h2 className="mt-2 font-serif text-[26px] text-navy group-hover:text-gold transition-colors">
                  Connect VoxBulk to Zoho Recruit
                </h2>
                <p className="mt-2 text-[14.5px] text-navy/65 leading-[1.65]">
                  Install from Marketplace, connect your account, send a test candidate, and read scores back in
                  Recruit. Built for UK and Middle East hiring (English + Arabic).
                </p>
                <span className="mt-4 inline-flex items-center gap-1.5 text-[13px] font-semibold text-gold">
                  Open guide <ArrowRight size={13} />
                </span>
              </div>
            </div>
          </Link>

          {groups.map((g) => (
            <div key={g.key} id={g.key}>
              <div className="mb-4">
                <h2 className="font-serif text-[28px] text-navy">{g.title}</h2>
                <p className="mt-1 text-[14px] text-navy/60">{g.blurb}</p>
              </div>
              <div className="space-y-3">
                {g.items.map((it) => (
                  <Link
                    key={it.slug}
                    to="/faq/$slug"
                    params={{ slug: it.slug }}
                    className="group block rounded-xl border border-navy/10 bg-white p-5 md:p-6 hover:border-gold transition-colors"
                  >
                    <h3 className="font-serif text-[20px] text-navy group-hover:text-gold transition-colors">
                      {it.question || it.title}
                    </h3>
                    {(it.meta_description || it.answer) && (
                      <p className="mt-2 text-[14.5px] text-navy/65 line-clamp-2">
                        {it.meta_description || it.answer}
                      </p>
                    )}
                    <span className="mt-3 inline-flex items-center gap-1.5 text-[13px] font-semibold text-gold">
                      Read answer <ArrowRight size={13} />
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
