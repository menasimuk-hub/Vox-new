import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { frontpageApiFetch } from "@/lib/api";

type Article = {
  id: number;
  title: string;
  slug: string;
  body?: string;
  author?: string;
  updated_at?: string;
};

export const Route = createFileRoute("/help/articles/$slug")({
  component: HelpArticlePage,
});

function HelpArticlePage() {
  const { slug } = Route.useParams();
  const q = useQuery({
    queryKey: ["help-article", slug],
    queryFn: async () => (await frontpageApiFetch(`/frontpage/help/articles/${slug}`)) as Article,
  });
  const a = q.data;
  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Link to="/help/articles" className="mb-6 inline-flex items-center gap-2 text-sm text-slate-600">
          <ArrowLeft size={16} /> All articles
        </Link>
        {q.isLoading ? <p className="text-slate-500">Loading…</p> : null}
        {q.isError ? <p className="text-red-600">Article not found.</p> : null}
        {a ? (
          <article>
            <h1 className="text-3xl font-semibold tracking-tight">{a.title}</h1>
            {a.author ? <p className="mt-2 text-sm text-slate-500">By {a.author}</p> : null}
            <div
              className="prose prose-slate mt-8 max-w-none"
              dangerouslySetInnerHTML={{ __html: a.body || "" }}
            />
          </article>
        ) : null}
      </main>
      <SiteFooter />
    </>
  );
}
