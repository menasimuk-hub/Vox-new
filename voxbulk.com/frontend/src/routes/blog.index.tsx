import { createFileRoute, Link } from "@tanstack/react-router";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { fetchBlogList, type PublicBlogPost } from "@/lib/site-content";
import { ArrowRight, Clock, Feather } from "lucide-react";

export const Route = createFileRoute("/blog/")({
  loader: async () => ({ posts: await fetchBlogList() }),
  head: () => ({
    meta: [
      { title: "VoxBulk Journal — Ideas on AI, hiring, and customer conversations" },
      {
        name: "description",
        content:
          "Field notes from the VoxBulk team on AI-assisted recruitment, multilingual customer feedback, WhatsApp surveys and the future of business conversations.",
      },
      { property: "og:title", content: "VoxBulk Journal" },
      {
        property: "og:description",
        content:
          "Field notes on AI-assisted recruitment, multilingual customer feedback and the future of business conversations.",
      },
      { property: "og:type", content: "website" },
      { property: "og:url", content: "https://voxbulk.com/blog" },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/blog" }],
  }),
  component: BlogIndex,
});

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

function BlogIndex() {
  const { posts } = Route.useLoaderData() as { posts: PublicBlogPost[] };
  if (!posts.length) {
    return (
      <div className="bg-beige text-body antialiased min-h-screen flex flex-col">
        <SiteHeader />
        <main className="flex-1 pt-[130px] pb-24 max-w-[720px] mx-auto px-6 text-center">
          <h1 className="font-serif text-[36px] text-navy">No essays yet</h1>
          <p className="mt-4 text-navy/70">Check back soon for new writing from the VoxBulk team.</p>
        </main>
        <SiteFooter />
      </div>
    );
  }
  const [featured, ...rest] = posts;
  return (
    <div className="bg-beige text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[110px] md:pt-[130px] pb-24">
        <section className="border-b border-navy/10">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10 pb-10 md:pb-14">
            <div className="flex items-center gap-2 text-[12px] uppercase tracking-[0.22em] text-navy/60">
              <Feather size={14} className="text-gold" />
              <span>The VoxBulk Journal</span>
            </div>
            <h1 className="mt-5 font-serif text-[42px] md:text-[68px] leading-[1.02] tracking-[-0.02em] text-navy max-w-[820px]">
              Field notes on <em className="text-gold not-italic">AI, hiring</em>, and the new grammar of business
              conversations.
            </h1>
            <p className="mt-6 max-w-[640px] text-[16px] md:text-[17px] text-navy/70 leading-[1.65]">
              Long-reads, short essays and case notes from the team building VoxBulk. No SEO filler, no
              thought-leadership theatre — just what we're learning as we ship.
            </p>
          </div>
        </section>

        <section className="max-w-[1180px] mx-auto px-5 md:px-10 mt-12 md:mt-16">
          <Link
            to="/blog/$slug"
            params={{ slug: featured.slug }}
            className="group grid md:grid-cols-[1.1fr_1fr] gap-8 md:gap-14 items-start"
          >
            <div className="relative aspect-[4/3] md:aspect-[5/4] rounded-2xl overflow-hidden border border-navy/10 bg-navy">
              {featured.image_url ? (
                <img
                  src={featured.image_url}
                  alt=""
                  className="absolute inset-0 w-full h-full object-cover"
                  loading="eager"
                />
              ) : (
                <>
                  <div
                    className="absolute inset-0 opacity-90"
                    style={{
                      background:
                        "radial-gradient(120% 90% at 15% 20%, rgba(212,169,58,0.28), transparent 55%), radial-gradient(140% 100% at 90% 90%, rgba(42,130,235,0.35), transparent 60%), linear-gradient(160deg, #0A1628 0%, #12233F 100%)",
                    }}
                  />
                  <div
                    className="absolute inset-0 opacity-[0.12] mix-blend-screen"
                    style={{
                      backgroundImage: "radial-gradient(rgba(255,255,255,0.7) 1px, transparent 1px)",
                      backgroundSize: "22px 22px",
                    }}
                  />
                </>
              )}
              <div className="absolute bottom-6 left-6 right-6 flex items-end justify-between text-white">
                <div>
                  <div className="text-[11px] uppercase tracking-[0.2em] text-gold/90">
                    Featured · {featured.category}
                  </div>
                  <div className="mt-2 font-serif text-[26px] md:text-[34px] leading-[1.1] max-w-[420px]">
                    {featured.title}
                  </div>
                </div>
              </div>
            </div>
            <div className="pt-2 md:pt-6">
              <div className="text-[12px] uppercase tracking-[0.18em] text-navy/50">
                {featured.category} · {formatDate(featured.published_at)}
              </div>
              <h2 className="mt-3 font-serif text-[28px] md:text-[38px] leading-[1.1] text-navy tracking-[-0.01em] group-hover:text-gold transition-colors">
                {featured.title}
              </h2>
              <p className="mt-4 text-[15.5px] text-navy/70 leading-[1.7]">{featured.excerpt}</p>
              <div className="mt-6 flex items-center gap-4 text-[13px] text-navy/60">
                <span className="font-medium text-navy">{featured.author}</span>
                <span className="w-1 h-1 rounded-full bg-navy/30" />
                <span className="inline-flex items-center gap-1.5">
                  <Clock size={13} /> {featured.read_mins} min read
                </span>
              </div>
              <div className="mt-6 inline-flex items-center gap-2 text-[14px] font-semibold text-gold group-hover:gap-3 transition-all">
                Read the essay <ArrowRight size={15} />
              </div>
            </div>
          </Link>
        </section>

        <div className="max-w-[1180px] mx-auto px-5 md:px-10 my-16 md:my-20">
          <div className="flex items-center gap-4">
            <div className="h-px flex-1 bg-navy/10" />
            <div className="text-[11px] uppercase tracking-[0.24em] text-navy/50">More reading</div>
            <div className="h-px flex-1 bg-navy/10" />
          </div>
        </div>

        <section className="max-w-[1180px] mx-auto px-5 md:px-10">
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8 md:gap-10">
            {rest.map((p) => (
              <Link key={p.slug} to="/blog/$slug" params={{ slug: p.slug }} className="group flex flex-col">
                {p.image_url ? (
                  <div className="mb-4 aspect-[4/3] rounded-xl overflow-hidden border border-navy/10 bg-navy/5">
                    <img src={p.image_url} alt="" className="w-full h-full object-cover" loading="lazy" />
                  </div>
                ) : null}
                <div className="text-[11px] uppercase tracking-[0.18em] text-gold font-semibold">{p.category}</div>
                <h3 className="mt-3 font-serif text-[22px] md:text-[24px] leading-[1.2] text-navy tracking-[-0.01em] group-hover:text-gold transition-colors">
                  {p.title}
                </h3>
                <p className="mt-3 text-[14.5px] text-navy/65 leading-[1.65] line-clamp-3">{p.excerpt}</p>
                <div className="mt-5 pt-4 border-t border-navy/10 flex items-center justify-between text-[12.5px] text-navy/55">
                  <span>{formatDate(p.published_at)}</span>
                  <span className="inline-flex items-center gap-1.5">
                    <Clock size={12} /> {p.read_mins} min
                  </span>
                </div>
              </Link>
            ))}
          </div>
        </section>

        <section className="max-w-[1180px] mx-auto px-5 md:px-10 mt-20 md:mt-28">
          <div className="rounded-2xl bg-navy text-white p-8 md:p-12 flex flex-col md:flex-row md:items-center gap-6 md:gap-10">
            <div className="flex-1">
              <div className="text-[11px] uppercase tracking-[0.22em] text-gold">The dispatch</div>
              <h3 className="mt-2 font-serif text-[26px] md:text-[32px] leading-[1.15]">
                One thoughtful essay a month. No spam, ever.
              </h3>
              <p className="mt-3 text-white/60 text-[14.5px] max-w-[520px]">
                Field-tested writing on AI, hiring and CX — sent only when we have something worth saying.
              </p>
            </div>
            <Link to="/contact" className="btn-primary self-start md:self-auto shrink-0">
              Subscribe <ArrowRight size={16} />
            </Link>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
