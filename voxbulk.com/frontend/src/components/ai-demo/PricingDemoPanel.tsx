type PricingData = {
  core_summary?: Array<{ code: string; name: string; blurb: string }>;
  product_notes?: Record<string, string>;
  recommend_rules?: string[];
  source?: string;
  disclaimer?: string;
};

export function PricingDemoPanel({
  data,
  recommendation,
  service,
}: {
  data: PricingData | null;
  recommendation?: string | null;
  service?: string | null;
}) {
  return (
    <div className="rounded-2xl border border-border bg-white p-4 space-y-3" data-demo-target="pricing-panel">
      <div className="flex items-center justify-between gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-text">Pricing</div>
        <a href="/pricing" target="_blank" rel="noreferrer" className="text-[12px] font-semibold text-primary">
          Open full page
        </a>
      </div>
      {recommendation && (
        <div className="rounded-xl bg-primary/10 border border-primary/30 px-3 py-2 text-[13px] text-heading">
          Recommendation: <strong>{recommendation}</strong>
        </div>
      )}
      <div className="grid gap-2">
        {(data?.core_summary || []).map((p) => (
          <div key={p.code} className="rounded-xl border border-border px-3 py-2">
            <div className="font-semibold text-heading text-[14px]">{p.name}</div>
            <p className="text-[12px] text-body mt-0.5">{p.blurb}</p>
          </div>
        ))}
      </div>
      {service && data?.product_notes?.[service] && (
        <p className="text-[12px] text-body">{data.product_notes[service]}</p>
      )}
      <p className="text-[11px] text-muted-text">
        {data?.disclaimer || "Website packages only. Our sales team will send you the best offer — no invented promos on this call."}
      </p>
    </div>
  );
}
