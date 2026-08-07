import { Link } from "@tanstack/react-router";
import { Building2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { formatExpoDay, formatExpoWindow } from "@/lib/expo-qr";
import { cn } from "@/lib/utils";

type ExpoBoothRow = {
  id: string;
  name: string;
  exhibition_name?: string | null;
  company_display_name?: string | null;
  activated_at?: string | null;
  expires_at?: string | null;
  is_paid?: boolean;
  payment_status?: string;
  is_live?: boolean;
  is_expired?: boolean;
  is_before_start?: boolean;
  status?: string | null;
};

function statusLabel(it: ExpoBoothRow) {
  const unpaid = !(it.is_paid || it.payment_status === "paid");
  if (String(it.status || "").toLowerCase() === "archived") return "Archived";
  if (it.is_expired) return "Finished";
  if (unpaid) return "Unpaid";
  if (it.is_before_start) return "Paid · starts soon";
  if (it.is_live) return "Paid · live";
  return "Saved";
}

/** Compact Expo booth windows for Account → Billing (not Packages). */
export function ExpoBillingSummary() {
  const boothsQ = useQuery({
    queryKey: ["expo", "booths", "billing-page"],
    queryFn: () => apiFetch<{ ok?: boolean; items: ExpoBoothRow[] }>("/expo/booths"),
  });
  const booths = (boothsQ.data?.items || [])
    .slice()
    .sort((a, b) => String(b.activated_at || "").localeCompare(String(a.activated_at || "")))
    .slice(0, 6);

  return (
    <Card className="border-sky-200/70 bg-gradient-to-br from-sky-500/5 to-transparent">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Building2 className="size-4 text-sky-600" />
              Expo
            </CardTitle>
            <CardDescription>One-off exhibition packages — start and finish dates for each booth.</CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm" variant="outline">
              <Link to="/account/packages" search={{ tab: "expo" }}>
                Expo packages
              </Link>
            </Button>
            <Button asChild size="sm" variant="outline">
              <Link to="/expo">Saved booths</Link>
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {boothsQ.isLoading ? (
          <Skeleton className="h-16 w-full rounded-lg" />
        ) : booths.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No Expo booths yet.{" "}
            <Link to="/account/packages" search={{ tab: "expo" }} className="font-medium text-sky-700 underline-offset-2 hover:underline">
              Choose an Expo package
            </Link>{" "}
            to create a booth and pay.
          </p>
        ) : (
          booths.map((it) => {
            const unpaid = !(it.is_paid || it.payment_status === "paid");
            return (
              <div
                key={it.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-sky-200/50 bg-background/80 px-3 py-2.5"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{it.name}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {it.exhibition_name || it.company_display_name || "Expo booth"}
                  </p>
                  <p className="mt-0.5 text-xs tabular-nums text-foreground">
                    {formatExpoWindow(it.activated_at, it.expires_at) || "Dates not set"}
                  </p>
                  <p className="text-[11px] text-muted-foreground">
                    Starts {formatExpoDay(it.activated_at) || "—"} · Ends {formatExpoDay(it.expires_at) || "—"}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-1.5">
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[10px] font-semibold",
                      unpaid
                        ? "bg-amber-100 text-amber-900"
                        : it.is_expired
                          ? "bg-muted text-muted-foreground"
                          : "bg-emerald-100 text-emerald-900",
                    )}
                  >
                    {statusLabel(it)}
                  </span>
                  <Button asChild size="sm" variant="ghost" className="h-7 px-2 text-xs">
                    <Link to="/expo/$boothId/edit" params={{ boothId: it.id }}>
                      {unpaid ? "Pay / edit" : "Change dates"}
                    </Link>
                  </Button>
                </div>
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}
