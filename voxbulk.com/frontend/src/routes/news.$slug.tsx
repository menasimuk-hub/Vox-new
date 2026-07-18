import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { newsItems, type NewsItem } from "@/lib/blog-data";
import { ArrowLeft, ArrowRight } from "lucide-react";

export const Route = createFileRoute("/news/$slug")({
  loader: ({ params }) => {
    const item = newsItems.find((n) => n.slug === params.slug);
    if (!item) throw notFound();
    return { item };
  },
  head: ({ loaderData }) => {
    if (!loaderData) {
      return { meta: [{ title: "Update not found — VoxBulk Newsroom" }, { name: "robots", content: "noindex" }] };
    }
    const n = loaderData.item;
    return {
      meta: [
        { title: `${n.title} — VoxBulk Newsroom` },
        { name: "description", content: n.body },
        { property: "og:title", content: n.title },
        { property: "og:description", content: n.body },
        { property: "og:type", content: "article" },
        { property: "og:url", content: `https://voxbulk.com/news/${n.slug}` },
        { property: "article:published_time", content: n.date },
      ],
      links: [{ rel: "canonical", href: `https://voxbulk.com/news/${n.slug}` }],
    };
  },
  notFoundComponent: NewsNotFound,
  component: NewsDetail,
});

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

function NewsNotFound() {
  return (
    <div className="bg-beige min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[130px] pb-24 max-w-[720px] mx-auto px-6 text-center">
        <div className="text-[11px] uppercase tracking-[0.2em] text-navy/50">Newsroom</div>
        <h1 className="mt-4 font-serif text-[42px] text-navy">Update not found</h1>
        <p className="mt-4 text-navy/70">This announcement may have been moved. Browse the newsroom below.</p>
        <Link to="/news" className="mt-8 inline-flex items-center gap-2 text-gold font-semibold">
          <ArrowLeft size={16} /> Back to Newsroom
        </Link>
      </main>
      <SiteFooter />
    </div>
  );
}

function NewsDetail() {
  const { item } = Route.useLoaderData() as { item: NewsItem };
  const idx = newsItems.findIndex((n) => n.slug === item.slug);
  const next = newsItems[(idx + 1) % newsItems.length];

  return (
    <div className="bg-beige text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[110px] md:pt-[130px] pb-24">
        <article className="max-w-[720px] mx-auto px-5 md:px-8">
          <Link to="/news" className="inline-flex items-center gap-2 text-[13px] font-semibold text-navy/60 hover:text-gold transition-colors">
            <ArrowLeft size={14} /> Newsroom
          </Link>

          <div className="mt-8 text-[11px] uppercase tracking-[0.22em] text-gold font-semibold">Announcement</div>
          <h1 className="mt-4 font-serif text-[34px] md:text-[48px] leading-[1.08] tracking-[-0.02em] text-navy">
            {item.title}
          </h1>
          <div className="mt-5 text-[13.5px] text-navy/55">{formatDate(item.date)}</div>

          <div className="mt-8 pt-8 border-t border-navy/10">
            <p className="text-[17px] leading-[1.75] text-navy/85">{item.body}</p>
          </div>

          <div className="mt-14">
            <div className="text-[11px] uppercase tracking-[0.2em] text-navy/50 mb-4">Next update</div>
            <Link
              to="/news/$slug"
              params={{ slug: next.slug }}
              className="group block rounded-xl border border-navy/10 bg-white p-6 hover:border-gold transition-colors"
            >
              <div className="text-[12px] text-navy/50">{formatDate(next.date)}</div>
              <h3 className="mt-2 font-serif text-[22px] leading-[1.2] text-navy group-hover:text-gold transition-colors">
                {next.title}
              </h3>
              <div className="mt-4 inline-flex items-center gap-2 text-[13.5px] font-semibold text-gold group-hover:gap-3 transition-all">
                Read update <ArrowRight size={14} />
              </div>
            </Link>
          </div>
        </article>
      </main>
      <SiteFooter />
    </div>
  );
}
