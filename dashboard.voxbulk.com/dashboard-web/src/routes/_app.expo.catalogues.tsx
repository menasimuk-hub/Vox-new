import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Package, Pencil } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";

type BoothRow = {
  id: string;
  exhibition_name?: string | null;
  name?: string | null;
  booth_code?: string | null;
  company_display_name?: string | null;
  categories?: Array<{ id?: string; products?: unknown[] }>;
};

export const Route = createFileRoute("/_app/expo/catalogues")({
  head: () => ({ meta: [{ title: "Add catalogues — Expo — VoxBulk" }] }),
  component: ExpoCataloguesPage,
});

function ExpoCataloguesPage() {
  const boothsQ = useQuery({
    queryKey: ["expo", "booths", "catalogues"],
    queryFn: () => apiFetch<{ ok: boolean; items: BoothRow[] }>("/expo/booths"),
  });
  const items = boothsQ.data?.items || [];

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="VoxBulk Expo"
        title="Add catalogues"
        description="Group catalogues, price lists, and product sheets on each booth. Assign products when editing a QR — they are not part of the create wizard."
        actions={
          <Button asChild variant="outline">
            <Link to="/expo/new">Create booth</Link>
          </Button>
        }
      />

      {boothsQ.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-28 rounded-xl" />
        </div>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="p-10 text-center text-sm text-muted-foreground">
            No booths yet. Create a booth, then add catalogues from its edit page.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((b) => {
            const cats = b.categories?.length ?? 0;
            const products = (b.categories || []).reduce(
              (n, c) => n + (Array.isArray(c.products) ? c.products.length : 0),
              0,
            );
            const title = b.exhibition_name || b.name || b.booth_code || "Booth";
            return (
              <Card key={b.id} className="overflow-hidden">
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <span className="grid size-9 place-items-center rounded-lg bg-sky-500/15 text-sky-600 dark:text-sky-400">
                      <Package className="size-4" />
                    </span>
                    <span className="truncate">{title}</span>
                  </CardTitle>
                  <CardDescription className="truncate">
                    {b.company_display_name || "—"} · {cats} categor{cats === 1 ? "y" : "ies"} · {products}{" "}
                    product{products === 1 ? "" : "s"}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Button asChild size="sm" variant="outline" className="gap-1.5">
                    <Link to="/expo/$boothId/edit" params={{ boothId: b.id }}>
                      <Pencil className="size-3.5" /> Edit products &amp; files
                    </Link>
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
