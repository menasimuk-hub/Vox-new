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
  url?: string;
};

export const Route = createFileRoute("/help/articles/")({
  component: HelpArticlesIndex,
});

function HelpArticlesIndex() {
  const q = useQuery({
    queryKey: ["help-articles"],
    queryFn: async () => {
      const data = await frontpageApiFetch("/frontpage/help/articles");
      return (data?.items || []) as Article[];
    },
  });
  const items = q.data || [];
  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Link to="/help" className="mb-6 inline-flex items-center gap-2 text-sm text-slate-600">
          <ArrowLeft size={16} /> Back to Help
        </Link>
        <h1 className="text-3xl font-semibold tracking-tight">Help Centre</h1>
        <p className="mt-2 text-slate-600">Guides and articles from Support Disk.</p>
        {q.isLoading ? <p className="mt-8 text-slate-500">Loading…</p> : null}
        <ul className="mt-8 divide-y rounded-xl border bg-white">
          {items.map((a) => (
            <li key={a.id}>
              <Link
                to="/help/articles/$slug"
                params={{ slug: a.slug }}
                className="block px-4 py-3 text-left hover:bg-slate-50"
              >
                <span className="font-medium text-slate-900">{a.title}</span>
              </Link>
            </li>
          ))}
          {!q.isLoading && items.length === 0 ? (
            <li className="px-4 py-8 text-center text-slate-500">No published articles yet.</li>
          ) : null}
        </ul>
      </main>
      <SiteFooter />
    </>
  );
}
