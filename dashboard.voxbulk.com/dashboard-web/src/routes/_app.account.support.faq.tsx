import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";
import { ArrowLeft, BookOpen, ChevronDown, Search } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { useFaq } from "@/lib/queries";
import { BUILT_IN_DOCS, type DocsArticle, type DocsCategory } from "@/lib/docs/built-in";

export const Route = createFileRoute("/_app/account/support/faq")({
  head: () => ({ meta: [{ title: "Documentation & FAQ — VoxBulk" }] }),
  component: FaqPage,
});

type ApiFaqItem = { id: number | string; question: string; answer: string };
type ApiFaqCategory = { id: number | string | null; name: string; items: ApiFaqItem[] };

function mergeWithApi(apiCategories: ApiFaqCategory[]): DocsCategory[] {
  if (apiCategories.length === 0) return BUILT_IN_DOCS;
  const extra: DocsCategory[] = apiCategories.map((cat, idx) => ({
    id: `api-${cat.id ?? idx}`,
    name: cat.name || "Articles",
    description: "Articles published by the VoxBulk team.",
    Icon: BookOpen,
    articles: cat.items.map((item) => ({
      id: `api-${item.id}`,
      title: item.question,
      body: item.answer,
    })),
  }));
  return [...BUILT_IN_DOCS, ...extra];
}

function groupArticles(articles: DocsArticle[]): { group: string; items: DocsArticle[] }[] {
  const map = new Map<string, DocsArticle[]>();
  for (const a of articles) {
    const key = a.group || "Articles";
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(a);
  }
  return Array.from(map.entries()).map(([group, items]) => ({ group, items }));
}

function FaqPage() {
  const faqQ = useFaq();
  const [search, setSearch] = React.useState("");
  const [activeCategoryId, setActiveCategoryId] = React.useState<string>(BUILT_IN_DOCS[0]?.id ?? "");
  const [openArticleId, setOpenArticleId] = React.useState<string | null>(null);

  const apiCategories: ApiFaqCategory[] = React.useMemo(() => {
    const raw = (faqQ.data || []) as Array<Record<string, unknown>>;
    return raw.map((cat) => ({
      id: cat.id as number | string | null,
      name: String(cat.name || "General"),
      items: ((cat.items || []) as Array<Record<string, unknown>>).map((item) => ({
        id: item.id as number | string,
        question: String(item.question || ""),
        answer: String(item.answer || ""),
      })),
    }));
  }, [faqQ.data]);

  const allCategories = React.useMemo(() => mergeWithApi(apiCategories), [apiCategories]);

  const q = search.trim().toLowerCase();

  const filteredCategories = React.useMemo(() => {
    if (!q) return allCategories;
    return allCategories
      .map((c) => ({
        ...c,
        articles: c.articles.filter((a) => (a.title + " " + a.body + " " + (a.group || "")).toLowerCase().includes(q)),
      }))
      .filter((c) => c.articles.length > 0);
  }, [allCategories, q]);

  React.useEffect(() => {
    if (filteredCategories.length === 0) return;
    if (!filteredCategories.some((c) => c.id === activeCategoryId)) {
      setActiveCategoryId(filteredCategories[0].id);
      setOpenArticleId(null);
    }
  }, [filteredCategories, activeCategoryId]);

  const activeCategory = filteredCategories.find((c) => c.id === activeCategoryId) ?? filteredCategories[0];
  const grouped = activeCategory ? groupArticles(activeCategory.articles) : [];

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow={<Link to="/account/support" className="inline-flex items-center gap-1 hover:text-foreground"><ArrowLeft className="size-3" /> Support</Link>}
        title="Documentation & FAQ"
        description="Categories and step-by-step guides for every VoxBulk service."
      />

      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search documentation…"
          className="h-10 pl-8"
        />
      </div>

      {faqQ.isLoading ? (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-[120px] w-full" />
          <Skeleton className="h-[420px] w-full" />
        </div>
      ) : filteredCategories.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center text-sm text-muted-foreground">
            No documentation entries match your search.
          </CardContent>
        </Card>
      ) : (
        <div className="flex flex-col gap-4">
          <CategoryGrid
            categories={filteredCategories}
            activeId={activeCategory?.id ?? ""}
            onSelect={(id) => {
              setActiveCategoryId(id);
              setOpenArticleId(null);
            }}
          />

          <Card>
            <CardContent className="p-0">
              {activeCategory && (
                <>
                  <div className="flex items-start gap-3 border-b border-border p-4">
                    <div className="grid size-11 shrink-0 place-items-center rounded-lg border border-border bg-muted/60 text-foreground">
                      <activeCategory.Icon className="size-5" strokeWidth={1.75} />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold">{activeCategory.name}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">{activeCategory.description}</p>
                    </div>
                    <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
                      {activeCategory.articles.length} {activeCategory.articles.length === 1 ? "article" : "articles"}
                    </span>
                  </div>

                  <div className="space-y-4 p-4">
                    {grouped.map((g) => (
                      <div key={g.group}>
                        <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                          {g.group}
                        </p>
                        <div className="space-y-2">
                          {g.items.map((a) => {
                            const isOpen = openArticleId === a.id;
                            return (
                              <Collapsible
                                key={a.id}
                                open={isOpen}
                                onOpenChange={(o) => setOpenArticleId(o ? a.id : null)}
                                className="rounded-md border border-border"
                              >
                                <CollapsibleTrigger className="group flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm">
                                  <ChevronDown className="size-3.5 shrink-0 text-muted-foreground transition group-data-[state=open]:rotate-180" />
                                  <span className="font-medium">{a.title}</span>
                                </CollapsibleTrigger>
                                <CollapsibleContent>
                                  <p className="border-t border-border bg-muted/30 px-3 py-3 text-sm leading-relaxed text-muted-foreground whitespace-pre-wrap">
                                    {a.body}
                                  </p>
                                </CollapsibleContent>
                              </Collapsible>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

function CategoryGrid({
  categories,
  activeId,
  onSelect,
}: {
  categories: DocsCategory[];
  activeId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <Card>
      <CardContent className="p-2 sm:p-3">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {categories.map((c) => {
            const isActive = c.id === activeId;
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => onSelect(c.id)}
                title={c.name}
                className={cn(
                  "group flex h-full flex-col items-start gap-2 rounded-md border p-2.5 text-left transition-colors",
                  isActive
                    ? "border-border bg-accent text-foreground shadow-sm"
                    : "border-border/60 bg-card text-foreground/80 hover:border-border hover:bg-accent/40 hover:text-foreground",
                )}
              >
                <span
                  className={cn(
                    "grid size-8 shrink-0 place-items-center rounded-md border transition-colors",
                    isActive
                      ? "border-border bg-background text-foreground"
                      : "border-border/60 bg-muted/40 text-foreground/70 group-hover:border-border group-hover:text-foreground",
                  )}
                >
                  <c.Icon className="size-4" strokeWidth={1.75} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium leading-tight">
                    {c.shortName || c.name}
                  </span>
                  <span className="mt-0.5 block text-[10px] text-muted-foreground">
                    {c.articles.length} {c.articles.length === 1 ? "article" : "articles"}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
