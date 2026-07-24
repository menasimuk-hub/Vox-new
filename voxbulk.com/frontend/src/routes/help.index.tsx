import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState, type ComponentType } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Search,
  Rocket,
  CreditCard,
  Users,
  MessageCircle,
  Phone,
  Shield,
  Settings,
  HelpCircle,
  ChevronDown,
  LifeBuoy,
  Mail,
  Building2,
} from "lucide-react";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { frontpageApiFetch } from "@/lib/api";

type FaqItem = {
  slug: string;
  title: string;
  question?: string;
  meta_description?: string;
  answer?: string;
  category_name?: string;
  category_slug?: string;
};

type Tone = "blue" | "teal" | "gold" | "navy";

type CategoryMeta = {
  slug: string;
  title: string;
  desc: string;
  Icon: ComponentType<{ size?: number }>;
  tone: Tone;
};

type HelpCategory = CategoryMeta & {
  faqs: { q: string; a: string; slug?: string }[];
};

const CATEGORY_META: CategoryMeta[] = [
  {
    slug: "getting-started",
    title: "Getting started",
    desc: "Create your account, invite your team and launch your first workflow.",
    Icon: Rocket,
    tone: "blue",
  },
  {
    slug: "billing",
    title: "Billing & pricing",
    desc: "Plans, invoices, pay-as-you-go credits and how billing works.",
    Icon: CreditCard,
    tone: "gold",
  },
  {
    slug: "recruitment",
    title: "AI Recruitment",
    desc: "Screening, scoring and voice interviews with your AI recruiter.",
    Icon: Users,
    tone: "blue",
  },
  {
    slug: "whatsapp-surveys",
    title: "WhatsApp Surveys",
    desc: "Smart surveys, voice notes and high response rates.",
    Icon: MessageCircle,
    tone: "teal",
  },
  {
    slug: "ai-calling",
    title: "AI Calling",
    desc: "Automated voice conversations that score every answer.",
    Icon: Phone,
    tone: "teal",
  },
  {
    slug: "security",
    title: "Security & privacy",
    desc: "How we protect your data — GDPR, encryption and hosting.",
    Icon: Shield,
    tone: "navy",
  },
  {
    slug: "account",
    title: "Account & settings",
    desc: "Profile, team roles, integrations and workspace settings.",
    Icon: Settings,
    tone: "blue",
  },
  {
    slug: "troubleshooting",
    title: "Troubleshooting",
    desc: "Common issues and how to fix them fast.",
    Icon: HelpCircle,
    tone: "gold",
  },
  {
    slug: "zoho-recruit",
    title: "Zoho Recruit",
    desc: "AI voice screening for Zoho Recruit — setup, pricing and Arabic/English.",
    Icon: Building2,
    tone: "navy",
  },
];

const DEFAULT_META: Omit<CategoryMeta, "slug" | "title"> = {
  desc: "Answers from the VoxBulk help centre.",
  Icon: HelpCircle,
  tone: "blue",
};

const toneStyles: Record<Tone, { bg: string; text: string; ring: string }> = {
  blue: { bg: "bg-primary/10", text: "text-primary", ring: "group-hover:ring-primary/30" },
  teal: { bg: "bg-teal/15", text: "text-teal", ring: "group-hover:ring-teal/30" },
  gold: { bg: "bg-gold/20", text: "text-[#8a6a1a]", ring: "group-hover:ring-gold/40" },
  navy: { bg: "bg-navy/10", text: "text-navy", ring: "group-hover:ring-navy/25" },
};

const FALLBACK_ITEMS: FaqItem[] = [
  {
    slug: "what-exactly-does-voxbulk-do",
    title: "What exactly does VoxBulk do?",
    question: "What exactly does VoxBulk do?",
    category_name: "Getting started",
    category_slug: "getting-started",
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

function buildCategories(items: FaqItem[]): HelpCategory[] {
  const bySlug = new Map<string, FaqItem[]>();
  for (const it of items) {
    const key = (it.category_slug || "getting-started").trim().toLowerCase() || "getting-started";
    if (!bySlug.has(key)) bySlug.set(key, []);
    bySlug.get(key)!.push(it);
  }

  const ordered: HelpCategory[] = [];
  const seen = new Set<string>();

  for (const meta of CATEGORY_META) {
    const rows = bySlug.get(meta.slug) || [];
    seen.add(meta.slug);
    ordered.push({
      ...meta,
      faqs: rows.map((r) => ({
        q: r.question || r.title,
        a: r.answer || r.meta_description || "Answer coming soon.",
        slug: r.slug,
      })),
    });
  }

  for (const [slug, rows] of bySlug) {
    if (seen.has(slug)) continue;
    ordered.push({
      slug,
      title: rows[0]?.category_name || slug,
      ...DEFAULT_META,
      faqs: rows.map((r) => ({
        q: r.question || r.title,
        a: r.answer || r.meta_description || "Answer coming soon.",
        slug: r.slug,
      })),
    });
  }

  return ordered;
}

export const Route = createFileRoute("/help/")({
  validateSearch: (search: Record<string, unknown>) => ({
    q: typeof search.q === "string" ? search.q : undefined,
    category: typeof search.category === "string" ? search.category : undefined,
  }),
  loader: async () => {
    let zohoVisible = false;
    try {
      const vis = await frontpageApiFetch<{ visible?: boolean }>(
        "/frontpage/integration-visibility/zoho_recruit",
      );
      zohoVisible = Boolean(vis?.visible);
    } catch {
      zohoVisible = false;
    }
    try {
      const data = await frontpageApiFetch<{ items: FaqItem[] }>("/frontpage/faq");
      let items = data.items?.length ? data.items : FALLBACK_ITEMS;
      if (!zohoVisible) {
        items = items.filter(
          (i) =>
            i.category_slug !== "zoho-recruit" &&
            !String(i.slug || "").startsWith("zoho-recruit"),
        );
      }
      return { items, categories: buildCategories(items), zohoVisible };
    } catch {
      let items = FALLBACK_ITEMS;
      if (!zohoVisible) {
        items = items.filter(
          (i) =>
            i.category_slug !== "zoho-recruit" &&
            !String(i.slug || "").startsWith("zoho-recruit"),
        );
      }
      return { items, categories: buildCategories(items), zohoVisible };
    }
  },
  head: () => ({
    meta: [
      { title: "Help Center — VoxBulk" },
      {
        name: "description",
        content:
          "Answers to common questions about VoxBulk — AI recruitment, WhatsApp surveys, AI calling, billing, security, Zoho Recruit and account settings.",
      },
      { name: "robots", content: "index,follow" },
      { property: "og:title", content: "Help Center — VoxBulk" },
      { property: "og:description", content: "Find answers, guides and troubleshooting tips for VoxBulk." },
      { property: "og:type", content: "website" },
      { property: "og:url", content: "https://voxbulk.com/help" },
      { name: "twitter:card", content: "summary" },
      { name: "twitter:title", content: "Help Center — VoxBulk" },
      { name: "twitter:description", content: "Find answers, guides and troubleshooting tips for VoxBulk." },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/help" }],
  }),
  component: HelpPage,
});

function HelpPage() {
  const { categories, zohoVisible } = Route.useLoaderData() as {
    items: FaqItem[];
    categories: HelpCategory[];
    zohoVisible?: boolean;
  };
  const search = Route.useSearch();
  const [active, setActive] = useState<string | null>(search.category || null);
  const [q, setQ] = useState(search.q || "");

  const current = categories.find((c) => c.slug === active) ?? null;

  const filtered = useMemo(() => {
    if (!q.trim()) return categories;
    const s = q.toLowerCase();
    return categories
      .map((c) => ({
        ...c,
        faqs: c.faqs.filter((f) => f.q.toLowerCase().includes(s) || f.a.toLowerCase().includes(s)),
      }))
      .filter((c) => c.title.toLowerCase().includes(s) || c.desc.toLowerCase().includes(s) || c.faqs.length > 0);
  }, [q, categories]);

  return (
    <div className="bg-background text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1">
        <section className="relative overflow-hidden pt-[120px] md:pt-[140px] pb-14 md:pb-20">
          <AnimatedBackdrop />
          <div className="relative max-w-[1180px] mx-auto px-5 md:px-10 text-center">
            <span className="eyebrow inline-flex items-center gap-2 text-gold">
              <LifeBuoy size={14} /> Help Center
            </span>
            <h1 className="mt-3 text-[36px] md:text-[56px] font-bold tracking-[-0.03em] text-white leading-[1.05]">
              How can we help?
            </h1>
            <p className="mt-4 text-[15px] md:text-[17px] text-white/70 max-w-[620px] mx-auto leading-[1.65]">
              Search the knowledge base or browse by category. Still stuck? Our team replies within one business hour.
            </p>

            <div className="mt-8 max-w-[620px] mx-auto relative">
              <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-white/50" />
              <input
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setActive(null);
                }}
                placeholder="Search for answers — e.g. billing, WhatsApp, GDPR, Zoho"
                className="w-full h-14 pl-12 pr-4 rounded-xl bg-white/[0.06] border border-white/15 text-white placeholder:text-white/40 text-[15px] focus:outline-none focus:border-gold/60 focus:bg-white/[0.09] transition-all backdrop-blur-sm"
              />
            </div>
          </div>
        </section>

        <section className="relative -mt-6 md:-mt-10 pb-24">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            {!current ? (
              <>
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
                  {filtered.map((c) => {
                    const tone = toneStyles[c.tone];
                    return (
                      <button
                        key={c.slug}
                        type="button"
                        onClick={() => setActive(c.slug)}
                        className={`group text-left bg-white rounded-2xl border border-border p-6 hover:shadow-[0_20px_50px_-15px_rgba(10,22,40,0.18)] hover:-translate-y-0.5 transition-all ring-1 ring-transparent ${tone.ring}`}
                      >
                        <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${tone.bg} ${tone.text}`}>
                          <c.Icon size={22} />
                        </div>
                        <h3 className="mt-5 text-[17px] font-semibold text-heading tracking-[-0.01em]">{c.title}</h3>
                        <p className="mt-1.5 text-[13.5px] text-muted-text leading-[1.6]">{c.desc}</p>
                        <div className="mt-5 flex items-center justify-between">
                          <span className="text-[12px] text-muted-text">
                            {c.faqs.length} article{c.faqs.length === 1 ? "" : "s"}
                          </span>
                          <span className="inline-flex items-center gap-1 text-[13px] font-semibold text-primary group-hover:gap-2 transition-all">
                            View <ArrowRight size={14} />
                          </span>
                        </div>
                      </button>
                    );
                  })}
                </div>

                {filtered.length === 0 && (
                  <div className="text-center py-16">
                    <p className="text-muted-text">
                      No results for &quot;{q}&quot;. Try a different keyword or{" "}
                      <Link to="/contact" className="text-primary font-semibold">
                        contact support
                      </Link>
                      .
                    </p>
                  </div>
                )}
              </>
            ) : (
              <CategoryDetail category={current} onBack={() => setActive(null)} zohoVisible={Boolean(zohoVisible)} />
            )}

            <div className="mt-16 rounded-2xl bg-dark text-white p-8 md:p-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-6 overflow-hidden relative">
              <div className="absolute inset-0 opacity-30 pointer-events-none">
                <AnimatedBackdrop compact />
              </div>
              <div className="relative">
                <h3 className="text-[22px] md:text-[26px] font-bold tracking-[-0.02em]">Still need help?</h3>
                <p className="mt-2 text-white/70 text-[14.5px] max-w-[520px] leading-[1.6]">
                  Our support team replies within one business hour, Monday to Friday. For urgent issues, email is
                  fastest.
                </p>
              </div>
              <div className="relative flex flex-wrap gap-3">
                <Link
                  to="/contact"
                  className="inline-flex items-center gap-2 h-11 px-5 rounded-lg bg-gold text-navy font-semibold text-[14px] hover:bg-gold/90 transition-colors"
                >
                  <Mail size={16} /> Contact support
                </Link>
              </div>
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}

function CategoryDetail({
  category,
  onBack,
  zohoVisible,
}: {
  category: HelpCategory;
  onBack: () => void;
  zohoVisible?: boolean;
}) {
  const [openIdx, setOpenIdx] = useState<number | null>(0);
  const tone = toneStyles[category.tone];
  return (
    <div className="animate-fade-in">
      <button
        type="button"
        onClick={onBack}
        className="inline-flex items-center gap-2 text-[13.5px] font-semibold text-muted-text hover:text-heading mb-6 transition-colors"
      >
        <ArrowLeft size={15} /> All categories
      </button>

      <div className="bg-white rounded-2xl border border-border overflow-hidden">
        <div className="p-6 md:p-8 flex items-start gap-4 border-b border-border">
          <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${tone.bg} ${tone.text} shrink-0`}>
            <category.Icon size={22} />
          </div>
          <div>
            <h2 className="text-[22px] md:text-[26px] font-bold text-heading tracking-[-0.02em]">{category.title}</h2>
            <p className="mt-1.5 text-[14px] text-muted-text leading-[1.6] max-w-[620px]">{category.desc}</p>
            {category.slug === "zoho-recruit" && zohoVisible ? (
              <Link
                to="/help/zoho-recruit"
                className="inline-flex items-center gap-1 mt-3 text-[13px] font-semibold text-primary hover:gap-2 transition-all"
              >
                Open full Zoho setup guide <ArrowRight size={14} />
              </Link>
            ) : null}
          </div>
        </div>

        <ul className="divide-y divide-border">
          {category.faqs.length === 0 ? (
            <li className="px-6 md:px-8 py-8 text-[14.5px] text-muted-text">No articles in this category yet.</li>
          ) : (
            category.faqs.map((f, i) => {
              const open = openIdx === i;
              return (
                <li key={f.slug || i}>
                  <button
                    type="button"
                    onClick={() => setOpenIdx(open ? null : i)}
                    className="w-full text-left px-6 md:px-8 py-5 flex items-start justify-between gap-6 hover:bg-beige/40 transition-colors"
                  >
                    <span className="text-[15.5px] font-semibold text-heading leading-[1.4]">{f.q}</span>
                    <ChevronDown
                      size={18}
                      className={`text-muted-text shrink-0 mt-0.5 transition-transform ${open ? "rotate-180" : ""}`}
                    />
                  </button>
                  {open && (
                    <div className="px-6 md:px-8 pb-6 -mt-1 animate-fade-in">
                      <p className="text-[14.5px] text-body leading-[1.7] max-w-[720px] whitespace-pre-wrap">{f.a}</p>
                      {f.slug ? (
                        <Link
                          to="/faq/$slug"
                          params={{ slug: f.slug }}
                          className="inline-block mt-3 text-[13px] font-semibold text-primary hover:underline underline-offset-2"
                        >
                          Open shareable page →
                        </Link>
                      ) : null}
                    </div>
                  )}
                </li>
              );
            })
          )}
        </ul>
      </div>
    </div>
  );
}

/** Animated navy backdrop: soft floating blobs + moving grid + drifting orbs. */
function AnimatedBackdrop({ compact = false }: { compact?: boolean }) {
  return (
    <div aria-hidden className={`absolute inset-0 pointer-events-none overflow-hidden ${compact ? "" : "bg-dark"}`}>
      {!compact && (
        <div
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse 80% 60% at 50% 0%, rgba(42,130,235,0.22), transparent 60%), radial-gradient(ellipse 60% 50% at 80% 100%, rgba(212,169,58,0.18), transparent 60%), linear-gradient(180deg, #0A1628 0%, #0E1A2E 100%)",
          }}
        />
      )}
      <div
        className="absolute inset-0 opacity-[0.10] help-grid-move"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.35) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.35) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
          maskImage: "radial-gradient(ellipse 70% 60% at 50% 40%, #000 30%, transparent 85%)",
          WebkitMaskImage: "radial-gradient(ellipse 70% 60% at 50% 40%, #000 30%, transparent 85%)",
        }}
      />
      <div
        className="absolute -top-24 left-[8%] w-[420px] h-[420px] rounded-full blur-3xl opacity-40 help-drift-a"
        style={{ background: "radial-gradient(circle at 30% 30%, #2A82EB, transparent 70%)" }}
      />
      <div
        className="absolute -bottom-32 right-[6%] w-[520px] h-[520px] rounded-full blur-3xl opacity-30 help-drift-b"
        style={{ background: "radial-gradient(circle at 70% 70%, #D4A93A, transparent 70%)" }}
      />
      <div
        className="absolute top-[30%] right-[30%] w-[280px] h-[280px] rounded-full blur-3xl opacity-25 help-drift-c"
        style={{ background: "radial-gradient(circle at 50% 50%, #14B8A6, transparent 70%)" }}
      />

      <span className="absolute top-[22%] left-[14%] w-2 h-2 rounded-full bg-white/70 help-orb-a" />
      <span className="absolute top-[70%] left-[20%] w-1.5 h-1.5 rounded-full bg-gold help-orb-b" />
      <span className="absolute top-[40%] right-[18%] w-2 h-2 rounded-full bg-primary help-orb-c" />
      <span className="absolute bottom-[20%] right-[30%] w-1.5 h-1.5 rounded-full bg-teal help-orb-a" />
    </div>
  );
}
