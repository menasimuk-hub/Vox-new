import { createFileRoute, Link, notFound, redirect } from "@tanstack/react-router";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { fetchBlogBySlug, fetchBlogList, type PublicBlogPost } from "@/lib/site-content";
import { buildHeadFromSeo, fetchContentSeo, fetchSeoSettings, resolveRedirect } from "@/lib/seo";
import { ArrowLeft, ArrowRight, Clock } from "lucide-react";

export const Route = createFileRoute("/blog/$slug")({
  loader: async ({ params, location }) => {
    const redir = await resolveRedirect(location.pathname);
    if (redir?.to_path) {
      throw redirect({ href: redir.to_path });
    }
    const post = await fetchBlogBySlug(params.slug);
    if (!post) throw notFound();
    let siblings: PublicBlogPost[] = [];
    try {
      siblings = await fetchBlogList();
    } catch {
      siblings = [post];
    }
    const [seo, settings] = await Promise.all([fetchContentSeo("blog", params.slug), fetchSeoSettings()]);
    return { post, siblings, seo, settings };
  },
  head: ({ loaderData }) => {
    if (!loaderData) {
      return { meta: [{ title: "Essay not found — VoxBulk Journal" }, { name: "robots", content: "noindex" }] };
    }
    const p = loaderData.post;
    if (loaderData.seo) {
      return buildHeadFromSeo(
        {
          ...loaderData.seo,
          title: loaderData.seo.title || p.title,
          meta_description: loaderData.seo.meta_description || p.excerpt,
          path: `/blog/${p.slug}`,
          url: `https://voxbulk.com/blog/${p.slug}`,
        },
        loaderData.settings || {},
        { schemaType: "Article" },
      );
    }
    return {
      meta: [
        { title: `${p.title} — VoxBulk Journal` },
        { name: "description", content: p.excerpt },
        { property: "og:title", content: p.title },
        { property: "og:description", content: p.excerpt },
        { property: "og:type", content: "article" },
        { property: "og:url", content: `https://voxbulk.com/blog/${p.slug}` },
        { property: "article:published_time", content: p.published_at },
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
        <p className="mt-4 text-navy/70">
          This piece may have been moved or unpublished. Browse the rest of the journal below.
        </p>
        <Link to="/blog" className="mt-8 inline-flex items-center gap-2 text-gold font-semibold">
          <ArrowLeft size={16} /> Back to the Journal
        </Link>
      </main>
      <SiteFooter />
    </div>
  );
}

function BlogBody({ post }: { post: PublicBlogPost }) {
  if (post.body_mode === "html") {
    return (
      <div
        className="mt-10 space-y-6 text-[16.5px] leading-[1.8] text-navy/85 [&_h2]:mt-10 [&_h2]:font-serif [&_h2]:text-[26px] [&_h2]:md:text-[30px] [&_h2]:leading-[1.2] [&_h2]:text-navy [&_blockquote]:my-8 [&_blockquote]:border-l-2 [&_blockquote]:border-gold [&_blockquote]:pl-6 [&_blockquote]:py-1 [&_blockquote_p]:font-serif [&_blockquote_p]:italic [&_blockquote_p]:text-[22px] [&_ul]:space-y-2.5 [&_ul]:pl-1 [&_li]:list-disc [&_li]:ml-5"
        dangerouslySetInnerHTML={{ __html: post.body }}
      />
    );
  }
  return (
    <div className="mt-10 space-y-6 text-[16.5px] leading-[1.8] text-navy/85 whitespace-pre-wrap">{post.body}</div>
  );
}

function BlogPost() {
  const { post, siblings } = Route.useLoaderData() as { post: PublicBlogPost; siblings: PublicBlogPost[] };
  const idx = siblings.findIndex((p) => p.slug === post.slug);
  const next = siblings.length ? siblings[(Math.max(idx, 0) + 1) % siblings.length] : null;

  return (
    <div className="bg-beige text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[110px] md:pt-[130px] pb-24">
        <article className="max-w-[760px] mx-auto px-5 md:px-8">
          <Link
            to="/blog"
            className="inline-flex items-center gap-2 text-[13px] font-semibold text-navy/60 hover:text-gold transition-colors"
          >
            <ArrowLeft size={14} /> The Journal
          </Link>

          <div className="mt-8 text-[11px] uppercase tracking-[0.22em] text-gold font-semibold">{post.category}</div>
          <h1 className="mt-4 font-serif text-[36px] md:text-[54px] leading-[1.05] tracking-[-0.02em] text-navy">
            {post.title}
          </h1>
          {post.excerpt ? (
            <p className="mt-6 text-[17px] md:text-[19px] text-navy/70 leading-[1.6] font-serif italic">{post.excerpt}</p>
          ) : null}

          {post.image_url ? (
            <div className="mt-8 aspect-[4/3] rounded-2xl overflow-hidden border border-navy/10 bg-navy/5">
              <img src={post.image_url} alt="" className="w-full h-full object-cover" />
            </div>
          ) : null}

          <div className="mt-8 flex items-center gap-4 pb-8 border-b border-navy/10">
            <div className="w-10 h-10 rounded-full bg-navy text-white flex items-center justify-center text-[13px] font-semibold">
              {post.author
                .split(" ")
                .map((n) => n[0])
                .join("")
                .slice(0, 2)}
            </div>
            <div className="flex-1">
              <div className="text-[14px] font-semibold text-navy">{post.author}</div>
              {post.author_role ? <div className="text-[12.5px] text-navy/55">{post.author_role}</div> : null}
            </div>
            <div className="text-[12.5px] text-navy/55 text-right">
              <div>{formatDate(post.published_at)}</div>
              <div className="inline-flex items-center gap-1.5 mt-0.5">
                <Clock size={12} /> {post.read_mins} min read
              </div>
            </div>
          </div>

          <BlogBody post={post} />

          <div className="mt-14 flex items-center gap-3">
            <div className="h-px flex-1 bg-navy/10" />
            <div className="text-gold font-serif text-[20px]">§</div>
            <div className="h-px flex-1 bg-navy/10" />
          </div>

          {next && next.slug !== post.slug ? (
            <div className="mt-14">
              <div className="text-[11px] uppercase tracking-[0.2em] text-navy/50 mb-4">Read next</div>
              <Link
                to="/blog/$slug"
                params={{ slug: next.slug }}
                className="group block rounded-xl border border-navy/10 bg-white p-6 md:p-8 hover:border-gold transition-colors"
              >
                <div className="text-[11px] uppercase tracking-[0.18em] text-gold font-semibold">{next.category}</div>
                <h3 className="mt-3 font-serif text-[24px] md:text-[28px] leading-[1.15] text-navy group-hover:text-gold transition-colors">
                  {next.title}
                </h3>
                <p className="mt-3 text-[14.5px] text-navy/65 leading-[1.6]">{next.excerpt}</p>
                <div className="mt-4 inline-flex items-center gap-2 text-[13.5px] font-semibold text-gold group-hover:gap-3 transition-all">
                  Continue reading <ArrowRight size={14} />
                </div>
              </Link>
            </div>
          ) : null}
        </article>
      </main>
      <SiteFooter />
    </div>
  );
}
