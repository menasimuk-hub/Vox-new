import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";
import { ArrowLeft, ChevronDown, Search } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useFaq } from "@/lib/queries";

export const Route = createFileRoute("/_app/account/support/faq")({
  head: () => ({ meta: [{ title: "Documentation & FAQ — VoxBulk" }] }),
  component: FaqPage,
});

type FaqItem = { id: number | string; question: string; answer: string };
type FaqCategory = { id: number | string | null; name: string; items: FaqItem[] };

function FaqPage() {
  const faqQ = useFaq();
  const [search, setSearch] = React.useState("");

  const categories = React.useMemo(() => {
    const raw = (faqQ.data || []) as Array<Record<string, unknown>>;
    return raw.map((cat) => ({
      id: cat.id as number | string | null,
      name: String(cat.name || "General"),
      items: ((cat.items || []) as Array<Record<string, unknown>>).map((item) => ({
        id: item.id as number | string,
        question: String(item.question || ""),
        answer: String(item.answer || ""),
      })),
    })) as FaqCategory[];
  }, [faqQ.data]);

  const filtered = categories
    .map((c) => ({
      ...c,
      items: c.items.filter((q) => (q.question + q.answer).toLowerCase().includes(search.toLowerCase())),
    }))
    .filter((c) => c.items.length > 0);

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow={<Link to="/account/support" className="inline-flex items-center gap-1 hover:text-foreground"><ArrowLeft className="size-3" /> Support</Link>}
        title="Documentation & FAQ"
        description="Browse help articles published by the VoxBulk team."
      />

      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search FAQ…" className="h-10 pl-8" />
      </div>

      {faqQ.isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center text-sm text-muted-foreground">
            {search ? "No FAQ entries match your search." : "No FAQ articles published yet."}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {filtered.map((cat) => (
            <Card key={String(cat.id ?? cat.name)}>
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold">{cat.name}</h3>
                  <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">{cat.items.length}</span>
                </div>
                <div className="mt-3 space-y-2">
                  {cat.items.map((q) => (
                    <Collapsible key={String(q.id)} className="rounded-md border border-border">
                      <div className="flex items-center gap-2 px-3 py-2">
                        <CollapsibleTrigger className="group flex flex-1 items-center gap-2 text-left text-sm">
                          <ChevronDown className="size-3.5 text-muted-foreground transition group-data-[state=open]:rotate-180" />
                          <span className="font-medium">{q.question}</span>
                        </CollapsibleTrigger>
                      </div>
                      <CollapsibleContent>
                        <p className="border-t border-border bg-muted/30 px-3 py-3 text-sm text-muted-foreground whitespace-pre-wrap">{q.answer}</p>
                      </CollapsibleContent>
                    </Collapsible>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
