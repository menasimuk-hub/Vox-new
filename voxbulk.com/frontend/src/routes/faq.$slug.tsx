import { createFileRoute, Link, notFound, redirect } from "@tanstack/react-router";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { buildHeadFromSeo, fetchContentSeo, fetchSeoSettings, resolveRedirect } from "@/lib/seo";
import { ArrowLeft } from "lucide-react";

export const Route = createFileRoute("/faq/$slug")({
  loader: async ({ params, location }) => {
    const redir = await resolveRedirect(location.pathname);
    if (redir?.to_path) {
      throw redirect({ href: redir.to_path, statusCode: redir.status_code || 301 });
    }
    const item = await fetchContentSeo("faq", params.slug);
    if (!item) throw notFound();
    const settings = await fetchSeoSettings();
    return { item, settings };
  },
  head: ({ loaderData }) => {
    if (!loaderData) {
      return { meta: [{ title: "FAQ not found — VoxBulk" }, { name: "robots", content: "noindex" }] };
    }
    return buildHeadFromSeo(loaderData.item, loaderData.settings, { schemaType: "FAQPage" });
  },
  notFoundComponent: () => (
    <div className="bg-beige min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[130px] pb-24 max-w-[720px] mx-auto px-6 text-center">
        <h1 className="font-serif text-[36px] text-navy">FAQ not found</h1>
        <Link to="/help" className="mt-8 inline-flex items-center gap-2 text-gold font-semibold">
          <ArrowLeft size={16} /> Back to Help
        </Link>
      </main>
      <SiteFooter />
    </div>
  ),
  component: FaqDetail,
});

function FaqDetail() {
  const { item } = Route.useLoaderData();
  return (
    <div className="bg-beige text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[110px] md:pt-[130px] pb-24">
        <article className="max-w-[720px] mx-auto px-5 md:px-8">
          <Link
            to="/help"
            className="inline-flex items-center gap-2 text-[13px] font-semibold text-navy/60 hover:text-gold transition-colors"
          >
            <ArrowLeft size={14} /> Help centre
          </Link>
          <h1 className="mt-8 font-serif text-[34px] md:text-[46px] leading-[1.08] tracking-[-0.02em] text-navy">
            {item.question || item.title}
          </h1>
          <div className="mt-8 pt-8 border-t border-navy/10 text-[17px] leading-[1.75] text-navy/85 whitespace-pre-wrap">
            {item.answer}
          </div>
        </article>
      </main>
      <SiteFooter />
    </div>
  );
}
