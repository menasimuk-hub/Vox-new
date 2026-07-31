import { Loader2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";

type Props = {
  /** Product scope for messaging only — redeem API stores pending discount by offer service_kind. */
  serviceHint?: string;
  className?: string;
  compact?: boolean;
  onRedeemed?: (summary: string) => void;
};

export function PromoCodeRedeem({ serviceHint, className, compact, onRedeemed }: Props) {
  const [code, setCode] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  async function apply() {
    const promo = code.trim();
    if (!promo) return;
    setBusy(true);
    try {
      const res = await apiFetch<{ benefit_summary?: string; promo?: { benefit_summary?: string } }>(
        "/promo/redeem",
        { method: "POST", body: JSON.stringify({ promo_code: promo }) },
      );
      const summary = res.benefit_summary || res.promo?.benefit_summary || "Promo applied";
      toast.success(summary);
      setCode("");
      onRedeemed?.(summary);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not apply promo");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={cn("rounded-lg border border-dashed border-border/80 bg-background/70 p-3", className)}>
      {!compact ? (
        <Label className="text-xs text-muted-foreground">
          Promo code{serviceHint ? ` (${serviceHint})` : ""} — apply before you pay
        </Label>
      ) : null}
      <div className={cn("flex gap-2", compact ? "" : "mt-2")}>
        <Input
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          placeholder="PROMOCODE"
          className="font-mono uppercase"
          disabled={busy}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void apply();
            }
          }}
        />
        <Button type="button" variant="outline" disabled={busy || !code.trim()} onClick={() => void apply()}>
          {busy ? <Loader2 className="size-4 animate-spin" /> : "Apply"}
        </Button>
      </div>
    </div>
  );
}
