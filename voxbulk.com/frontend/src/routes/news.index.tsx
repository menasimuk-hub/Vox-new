import { createFileRoute, Link } from "@tanstack/react-router";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { fetchNewsList, type PublicNewsItem } from "@/lib/site-content";
import { ArrowRight, Radio } from "lucide-react";

export const Route = createFileRoute("/news/")({
  loader: async () => ({ items: await fetchNewsList() }),
  head: () => ({
    meta: [
      { title: "Newsroom — VoxBulk announcements and product updates" },
      {
        name: "description",
        content: "Official announcements, product launches, integrations and company milestones from VoxBulk.",
      },
      { property: "og:title", content: "VoxBulk Newsroom" },
      { property: "og:description", content: "Announcements, launches and milestones from VoxBulk." },
      { property: "og:type", content: "website" },
      { property: "og:url", content: "https://voxbulk.com/news" },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/news" }],
  }),
  component: NewsPage,
});

function groupByMonth(items: PublicNewsItem[]) {
  const groups = new Map<string, PublicNewsItem[]>();
  for (const item of items) {
    const d = new Date(item.published_at);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(item);
  }
  return Array.from(groups.entries()).sort((a, b) => (a[0] < b[0] ? 1 : -1));
}

function formatMonth(key: string) {
  const [y, m] = key.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
}

function formatDay(iso: string) {
  const d = new Date(iso);
  return {
    day: String(d.getDate()).padStart(2, "0"),
    wd: d.toLocaleDateString("en-GB", { weekday: "short" }),
  };
}

function NewsPage() {
  const { items } = Route.useLoaderData() as { items: PublicNewsItem[] };
  const grouped = groupByMonth(items);
  return (
    <div className="bg-beige text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[110px] md:pt-[130px] pb-24">
        <section className="border-b border-navy/10">
          <div className="max-w-[1080px] mx-auto px-5 md:px-10 pb-10 md:pb-14">
            <div className="flex items-center gap-2 text-[12px] uppercase tracking-[0.22em] text-navy/60">
              <Radio size={14} className="text-gold" />
              <span>Newsroom</span>
            </div>
            <h1 className="mt-5 font-serif text-[42px] md:text-[64px] leading-[1.02] tracking-[-0.02em] text-navy max-w-[820px]">
              What's new at <em className="text-gold not-italic">VoxBulk</em>.
            </h1>
            <p className="mt-6 max-w-[620px] text-[16px] md:text-[17px] text-navy/70 leading-[1.65]">
              Product launches, integrations, milestones and the occasional company update — kept short, dated, and
              easy to scan.
            </p>
          </div>
        </section>

        <section className="max-w-[1080px] mx-auto px-5 md:px-10 mt-12 md:mt-16">
          <div className="space-y-16 md:space-y-20">
            {grouped.map(([month, monthItems]) => (
              <div key={month} className="grid md:grid-cols-[220px_1fr] gap-8 md:gap-14">
                <div className="md:sticky md:top-28 self-start">
                  <div className="text-[11px] uppercase tracking-[0.22em] text-navy/45 font-semibold">Month</div>
                  <div className="mt-2 font-serif text-[26px] md:text-[30px] leading-tight text-navy tracking-[-0.01em]">
                    {formatMonth(month)}
                  </div>
                  <div className="mt-3 h-1 w-10 bg-gold rounded-full" />
                  <div className="mt-3 text-[12.5px] text-navy/50">
                    {monthItems.length} update{monthItems.length === 1 ? "" : "s"}
                  </div>
                </div>

                <ol className="relative border-l border-navy/10 pl-6 md:pl-8 space-y-8">
                  {monthItems.map((it) => {
                    const d = formatDay(it.published_at);
                    const teaser = it.excerpt || it.body;
                    return (
                      <li key={it.slug} className="relative">
                        <span className="absolute -left-[33px] md:-left-[41px] top-2 w-3 h-3 rounded-full bg-gold ring-4 ring-beige" />
                        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                          <span className="text-[11.5px] uppercase tracking-[0.18em] text-navy/45 font-semibold">
                            {d.wd} · {d.day}
                          </span>
                        </div>
                        <Link to="/news/$slug" params={{ slug: it.slug }} className="group block mt-2">
                          <h3 className="font-serif text-[22px] md:text-[26px] leading-[1.2] text-navy tracking-[-0.01em] group-hover:text-gold transition-colors">
                            {it.title}
                          </h3>
                          <p className="mt-2.5 text-[15px] leading-[1.7] text-navy/70 max-w-[640px] line-clamp-3">
                            {teaser}
                          </p>
                          <span className="mt-3 inline-flex items-center gap-1.5 text-[13px] font-semibold text-gold group-hover:gap-2.5 transition-all">
                            Read update <ArrowRight size={13} />
                          </span>
                        </Link>
                      </li>
                    );
                  })}
                </ol>
              </div>
            ))}
          </div>
        </section>

        <section className="max-w-[1080px] mx-auto px-5 md:px-10 mt-24">
          <div className="rounded-2xl border border-navy/10 bg-white p-8 md:p-10 flex flex-col md:flex-row md:items-center gap-6">
            <div className="flex-1">
              <div className="text-[11px] uppercase tracking-[0.22em] text-gold font-semibold">Press & media</div>
              <h3 className="mt-2 font-serif text-[24px] md:text-[28px] leading-[1.2] text-navy">
                Working on a story? We're happy to help.
              </h3>
              <p className="mt-2 text-[14.5px] text-navy/65 max-w-[520px]">
                For interviews, quotes, or product briefings, reach the VoxBulk press team directly.
              </p>
            </div>
            <a href="mailto:press@voxbulk.com" className="btn-primary self-start md:self-auto shrink-0">
              press@voxbulk.com
            </a>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
