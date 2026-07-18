import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { posts, type BlogPost as BlogPostT } from "@/lib/blog-data";
import { ArrowLeft, ArrowRight, Clock } from "lucide-react";

export const Route = createFileRoute("/blog/$slug")({
  loader: ({ params }) => {
    const post = posts.find((p) => p.slug === params.slug);
    if (!post) throw notFound();
    return { post };
  },
  head: ({ loaderData }) => {
    if (!loaderData) {
      return { meta: [{ title: "Essay not found — VoxBulk Journal" }, { name: "robots", content: "noindex" }] };
    }
    const p = loaderData.post;
    return {
      meta: [
        { title: `${p.title} — VoxBulk Journal` },
        { name: "description", content: p.excerpt },
        { property: "og:title", content: p.title },
        { property: "og:description", content: p.excerpt },
        { property: "og:type", content: "article" },
        { property: "og:url", content: `https://voxbulk.com/blog/${p.slug}` },
        { property: "article:published_time", content: p.date },
        { property: "article:author", content: p.author },
      ],
      links: [{ rel: "canonical", href: `https://voxbulk.com/blog/${p.slug}` }],
    };
  },
  notFoundComponent: BlogNotFound,
  component: BlogPost,
});

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

function BlogNotFound() {
  return (
    <div className="bg-beige min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[130px] pb-24 max-w-[720px] mx-auto px-6 text-center">
        <div className="text-[11px] uppercase tracking-[0.2em] text-navy/50">VoxBulk Journal</div>
        <h1 className="mt-4 font-serif text-[42px] text-navy">Essay not found</h1>
        <p className="mt-4 text-navy/70">This piece may have been moved or unpublished. Browse the rest of the journal below.</p>
        <Link to="/blog" className="mt-8 inline-flex items-center gap-2 text-gold font-semibold">
          <ArrowLeft size={16} /> Back to the Journal
        </Link>
      </main>
      <SiteFooter />
    </div>
  );
}

function BlogPost() {
  const { post } = Route.useLoaderData() as { post: BlogPostT };
  const idx = posts.findIndex((p) => p.slug === post.slug);
  const next = posts[(idx + 1) % posts.length];

  return (
    <div className="bg-beige text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[110px] md:pt-[130px] pb-24">
        <article className="max-w-[760px] mx-auto px-5 md:px-8">
          <Link to="/blog" className="inline-flex items-center gap-2 text-[13px] font-semibold text-navy/60 hover:text-gold transition-colors">
            <ArrowLeft size={14} /> The Journal
          </Link>

          <div className="mt-8 text-[11px] uppercase tracking-[0.22em] text-gold font-semibold">{post.category}</div>
          <h1 className="mt-4 font-serif text-[36px] md:text-[54px] leading-[1.05] tracking-[-0.02em] text-navy">
            {post.title}
          </h1>
          <p className="mt-6 text-[17px] md:text-[19px] text-navy/70 leading-[1.6] font-serif italic">
            {post.excerpt}
          </p>

          <div className="mt-8 flex items-center gap-4 pb-8 border-b border-navy/10">
            <div className="w-10 h-10 rounded-full bg-navy text-white flex items-center justify-center text-[13px] font-semibold">
              {post.author.split(" ").map((n) => n[0]).join("").slice(0, 2)}
            </div>
            <div className="flex-1">
              <div className="text-[14px] font-semibold text-navy">{post.author}</div>
              <div className="text-[12.5px] text-navy/55">{post.authorRole}</div>
            </div>
            <div className="text-[12.5px] text-navy/55 text-right">
              <div>{formatDate(post.date)}</div>
              <div className="inline-flex items-center gap-1.5 mt-0.5"><Clock size={12} /> {post.readMins} min read</div>
            </div>
          </div>

          <div className="mt-10 space-y-6 text-[16.5px] leading-[1.8] text-navy/85">
            {post.content.map((block, i) => {
              if (block.type === "h2") {
                return (
                  <h2 key={i} className="mt-10 font-serif text-[26px] md:text-[30px] leading-[1.2] text-navy tracking-[-0.01em]">
                    {block.text}
                  </h2>
                );
              }
              if (block.type === "quote") {
                return (
                  <blockquote key={i} className="my-8 border-l-2 border-gold pl-6 py-1">
                    <p className="font-serif italic text-[22px] md:text-[24px] leading-[1.4] text-navy">
                      "{block.text}"
                    </p>
                    {block.cite && <cite className="mt-3 block text-[13px] not-italic text-navy/55">— {block.cite}</cite>}
                  </blockquote>
                );
              }
              if (block.type === "list") {
                return (
                  <ul key={i} className="space-y-2.5 pl-1">
                    {block.items.map((it, j) => (
                      <li key={j} className="flex gap-3">
                        <span className="mt-2.5 w-1.5 h-1.5 rounded-full bg-gold shrink-0" />
                        <span>{it}</span>
                      </li>
                    ))}
                  </ul>
                );
              }
              return <p key={i}>{block.text}</p>;
            })}
          </div>

          {/* End rule */}
          <div className="mt-14 flex items-center gap-3">
            <div className="h-px flex-1 bg-navy/10" />
            <div className="text-gold font-serif text-[20px]">§</div>
            <div className="h-px flex-1 bg-navy/10" />
          </div>

          {/* Next up */}
          <div className="mt-14">
            <div className="text-[11px] uppercase tracking-[0.2em] text-navy/50 mb-4">Read next</div>
            <Link to="/blog/$slug" params={{ slug: next.slug }} className="group block rounded-xl border border-navy/10 bg-white p-6 md:p-8 hover:border-gold transition-colors">
              <div className="text-[11px] uppercase tracking-[0.18em] text-gold font-semibold">{next.category}</div>
              <h3 className="mt-3 font-serif text-[24px] md:text-[28px] leading-[1.15] text-navy group-hover:text-gold transition-colors">{next.title}</h3>
              <p className="mt-3 text-[14.5px] text-navy/65 leading-[1.6]">{next.excerpt}</p>
              <div className="mt-4 inline-flex items-center gap-2 text-[13.5px] font-semibold text-gold group-hover:gap-3 transition-all">
                Continue reading <ArrowRight size={14} />
              </div>
            </Link>
          </div>
        </article>
      </main>
      <SiteFooter />
    </div>
  );
}
