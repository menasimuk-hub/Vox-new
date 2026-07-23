import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { frontpageApiFetch } from "@/lib/api";
import { BookOpen, HelpCircle } from "lucide-react";

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
  items: FaqItem[];
};

const GUIDE_ID = "guide:zoho-recruit";

const FALLBACK_ITEMS: FaqItem[] = [
  {
    slug: "what-exactly-does-voxbulk-do",
    title: "What exactly does VoxBulk do?",
    question: "What exactly does VoxBulk do?",
    category_name: "Product",
    category_slug: "product",
    answer:
      "VoxBulk is a UK-built AI platform for WhatsApp surveys, QR customer feedback, AI phone interviews, and voice agents.",
  },
  {
    slug: "zoho-recruit-what-is-voxbulk-ai-voice-screening",
    title: "What is VoxBulk AI Voice Screening for Zoho Recruit?",
    question: "What is VoxBulk AI Voice Screening for Zoho Recruit?",
    category_name: "Zoho Recruit",
    category_slug: "zoho-recruit",
    answer:
      "AI phone interviews in English and Arabic for Zoho Recruit — score, status, and report back to recruiters.",
  },
];

function groupItems(items: FaqItem[]): HelpGroup[] {
  const map = new Map<string, HelpGroup>();
  for (const it of items) {
    const key = it.category_slug || "product";
    const title = it.category_name || "Product";
    if (!map.has(key)) map.set(key, { key, title, items: [] });
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
  validateSearch: (search: Record<string, unknown>) => ({
    q: typeof search.q === "string" ? search.q : undefined,
  }),
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
          "VoxBulk help centre: product FAQs and Zoho Recruit AI voice screening setup. Public pages, no login required.",
      },
      { name: "robots", content: "index,follow" },
      { property: "og:title", content: "Help centre — VoxBulk" },
      { property: "og:url", content: "https://voxbulk.com/help" },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/help" }],
  }),
  component: HelpIndex,
});

function HelpIndex() {
  const { items, groups } = Route.useLoaderData() as { items: FaqItem[]; groups: HelpGroup[] };
  const { q } = Route.useSearch();
  const navigate = useNavigate({ from: "/help/" });

  const firstSlug = items[0]?.slug || GUIDE_ID;
  const [activeId, setActiveId] = useState<string>(q || firstSlug);

  useEffect(() => {
    if (q && q !== activeId) setActiveId(q);
  }, [q]);

  const activeFaq = useMemo(() => items.find((it) => it.slug === activeId) || null, [items, activeId]);
  const isGuide = activeId === GUIDE_ID;

  const select = (id: string) => {
    setActiveId(id);
    if (id === GUIDE_ID) {
      navigate({ search: {}, replace: true });
      return;
    }
    navigate({ search: { q: id }, replace: true });
  };

  return (
    <div className="bg-beige text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[88px] md:pt-[100px]">
        <div className="max-w-[1180px] mx-auto px-5 md:px-8 py-10 md:py-14">
          <div className="flex items-center gap-2 text-[12px] uppercase tracking-[0.22em] text-navy/55 mb-3">
            <HelpCircle size={14} className="text-gold" />
            <span>Resources · Help</span>
          </div>
          <h1 className="font-serif text-[36px] md:text-[48px] leading-[1.05] tracking-[-0.02em] text-navy">
            Help centre
          </h1>
          <p className="mt-3 max-w-[520px] text-[15px] text-navy/65 leading-[1.65]">
            Browse topics on the left. Answers open on the right — no login required.
          </p>

          <div className="mt-10 flex flex-col lg:flex-row gap-10 lg:gap-14">
            {/* Left menu — legal-style sticky nav */}
            <aside className="lg:w-[260px] shrink-0">
              <div className="lg:sticky lg:top-[112px] max-h-[calc(100vh-130px)] overflow-y-auto pr-1">
                <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-navy/45 px-2 mb-3">
                  Guides
                </div>
                <button
                  type="button"
                  onClick={() => select(GUIDE_ID)}
                  className={`w-full text-left block text-[13px] font-medium py-2 pl-3 border-l-2 mb-1 transition-colors ${
                    isGuide
                      ? "border-gold text-navy bg-white/70"
                      : "border-transparent text-navy/55 hover:text-navy hover:bg-white/40"
                  }`}
                >
                  Zoho Recruit setup
                </button>
                <Link
                  to="/help/zoho-recruit"
                  className="block text-[12.5px] text-gold font-semibold pl-3 mb-6 hover:underline underline-offset-2"
                >
                  Open full guide page →
                </Link>

                {groups.map((g) => (
                  <div key={g.key} className="mb-6">
                    <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-navy/45 px-2 mb-3">
                      {g.title}
                    </div>
                    {g.items.map((it) => {
                      const id = it.slug;
                      const active = activeId === id;
                      return (
                        <button
                          key={id}
                          type="button"
                          onClick={() => select(id)}
                          className={`w-full text-left block text-[13px] font-medium py-2 pl-3 border-l-2 mb-0.5 transition-colors leading-snug ${
                            active
                              ? "border-gold text-navy bg-white/70"
                              : "border-transparent text-navy/55 hover:text-navy hover:bg-white/40"
                          }`}
                        >
                          {it.question || it.title}
                        </button>
                      );
                    })}
                  </div>
                ))}

                <div className="mt-4 px-2 text-[12px] text-navy/45 leading-relaxed">
                  Need more help?{" "}
                  <a href="mailto:support@voxbulk.com" className="text-gold font-semibold hover:underline">
                    support@voxbulk.com
                  </a>
                </div>
              </div>
            </aside>

            {/* Right content panel */}
            <section className="flex-1 min-w-0">
              <div className="rounded-2xl border border-navy/10 bg-white p-6 md:p-10 shadow-[0_1px_2px_rgba(10,22,40,0.03)]">
                {isGuide ? (
                  <>
                    <div className="flex items-center gap-2 text-[12px] uppercase tracking-[0.18em] text-navy/45">
                      <BookOpen size={14} className="text-gold" />
                      Guide
                    </div>
                    <h2 className="mt-3 font-serif text-[28px] md:text-[34px] leading-[1.1] text-navy">
                      Connect VoxBulk to Zoho Recruit
                    </h2>
                    <div className="mt-6 text-[16px] leading-[1.75] text-navy/80 space-y-4">
                      <p>
                        VoxBulk runs AI voice interviews for Zoho Recruit candidates in English and Arabic, then
                        returns a score, status, and report link.
                      </p>
                      <ol className="list-decimal pl-5 space-y-2">
                        <li>Create a VoxBulk account on the dashboard.</li>
                        <li>Install VoxBulk AI Voice Screening from Zoho Marketplace (Recruit).</li>
                        <li>In Admin → Partners → Zoho, generate sandbox keys and map your organisation.</li>
                        <li>Send a test candidate (en or ar) and confirm the score/report returns.</li>
                        <li>Switch to live keys when ready.</li>
                      </ol>
                      <p>
                        Pricing: £1.50 connection + £0.35/min (typical completed screen ~£7–£9). Privacy:{" "}
                        <Link to="/privacy" className="text-gold font-semibold underline-offset-2 hover:underline">
                          voxbulk.com/privacy
                        </Link>
                        .
                      </p>
                      <Link
                        to="/help/zoho-recruit"
                        className="inline-flex items-center gap-2 mt-2 rounded-full bg-navy text-white px-5 py-2.5 text-[13px] font-semibold hover:bg-navy/90 transition-colors"
                      >
                        Open full Zoho guide
                      </Link>
                    </div>
                  </>
                ) : activeFaq ? (
                  <>
                    <div className="text-[12px] uppercase tracking-[0.18em] text-navy/45">
                      {activeFaq.category_name || "FAQ"}
                    </div>
                    <h2 className="mt-3 font-serif text-[28px] md:text-[34px] leading-[1.1] text-navy">
                      {activeFaq.question || activeFaq.title}
                    </h2>
                    <div className="mt-8 pt-6 border-t border-navy/10 text-[16.5px] leading-[1.75] text-navy/85 whitespace-pre-wrap">
                      {activeFaq.answer || activeFaq.meta_description || "Answer coming soon."}
                    </div>
                    <div className="mt-8 flex flex-wrap gap-3 text-[13px]">
                      <Link
                        to="/faq/$slug"
                        params={{ slug: activeFaq.slug }}
                        className="text-gold font-semibold underline-offset-2 hover:underline"
                      >
                        Open shareable FAQ page →
                      </Link>
                    </div>
                  </>
                ) : (
                  <p className="text-navy/60">Select a topic from the left menu.</p>
                )}
              </div>
            </section>
          </div>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
