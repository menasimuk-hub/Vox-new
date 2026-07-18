import { createFileRoute, Link } from "@tanstack/react-router";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { frontpageApiFetch } from "@/lib/api";
import { HelpCircle, ArrowRight } from "lucide-react";

type FaqItem = {
  slug: string;
  title: string;
  question?: string;
  meta_description?: string;
  answer?: string;
};

export const Route = createFileRoute("/faq/")({
  loader: async () => {
    try {
      const data = await frontpageApiFetch<{ items: FaqItem[] }>("/frontpage/faq");
      return { items: data.items || [] };
    } catch {
      return { items: [] as FaqItem[] };
    }
  },
  head: () => ({
    meta: [
      { title: "FAQ — VoxBulk" },
      { name: "description", content: "Answers to common questions about VoxBulk products, billing, and support." },
      { property: "og:title", content: "FAQ — VoxBulk" },
      { property: "og:url", content: "https://voxbulk.com/faq" },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/faq" }],
  }),
  component: FaqIndex,
});

function FaqIndex() {
  const { items } = Route.useLoaderData() as { items: FaqItem[] };
  return (
    <div className="bg-beige text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[110px] md:pt-[130px] pb-24">
        <section className="border-b border-navy/10">
          <div className="max-w-[860px] mx-auto px-5 md:px-10 pb-10 md:pb-14">
            <div className="flex items-center gap-2 text-[12px] uppercase tracking-[0.22em] text-navy/60">
              <HelpCircle size={14} className="text-gold" />
              <span>Help centre</span>
            </div>
            <h1 className="mt-5 font-serif text-[42px] md:text-[56px] leading-[1.05] tracking-[-0.02em] text-navy">
              Frequently asked questions
            </h1>
            <p className="mt-5 max-w-[560px] text-[16px] text-navy/70 leading-[1.65]">
              Short answers on product, billing, and support. Pick a topic below.
            </p>
          </div>
        </section>
        <section className="max-w-[860px] mx-auto px-5 md:px-10 mt-12 space-y-4">
          {items.length === 0 ? (
            <p className="text-navy/60">No published FAQ entries yet.</p>
          ) : (
            items.map((it) => (
              <Link
                key={it.slug}
                to="/faq/$slug"
                params={{ slug: it.slug }}
                className="group block rounded-xl border border-navy/10 bg-white p-5 md:p-6 hover:border-gold transition-colors"
              >
                <h2 className="font-serif text-[22px] text-navy group-hover:text-gold transition-colors">
                  {it.question || it.title}
                </h2>
                {(it.meta_description || it.answer) && (
                  <p className="mt-2 text-[14.5px] text-navy/65 line-clamp-2">
                    {it.meta_description || it.answer}
                  </p>
                )}
                <span className="mt-3 inline-flex items-center gap-1.5 text-[13px] font-semibold text-gold">
                  Read answer <ArrowRight size={13} />
                </span>
              </Link>
            ))
          )}
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
