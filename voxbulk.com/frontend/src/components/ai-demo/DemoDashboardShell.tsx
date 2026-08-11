import { FeedbackDemoPanel } from "./FeedbackDemoPanel";
import { ExpoDemoPanel, RecruitmentDemoPanel, SmartCardDemoPanel, SurveysDemoPanel } from "./OtherServicePanels";
import { PricingDemoPanel } from "./PricingDemoPanel";

export function DemoDashboardShell({
  activeService,
  walkthrough,
  highlightTarget,
  filterLocation,
  smartView,
  liveFeedback,
  liveExpo,
  showPricing,
  pricingData,
  pricingRecommendation,
}: {
  activeService: string | null;
  walkthrough: Record<string, unknown> | null;
  highlightTarget?: string | null;
  filterLocation?: string | null;
  smartView: "rep" | "manager";
  liveFeedback: Array<{ score?: number | null; comment?: string; name?: string; location?: string }>;
  liveExpo: Array<{ name?: string; company?: string }>;
  showPricing: boolean;
  pricingData: Record<string, unknown> | null;
  pricingRecommendation?: string | null;
}) {
  const service = activeService || "feedback";
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-border bg-secondary/30 px-4 py-3 flex items-center justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-text">Live demo dashboard</div>
          <div className="font-semibold text-heading capitalize">{service.replace("_", " ")}</div>
        </div>
        <span className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-emerald-700">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" /> Synced
        </span>
      </div>

      {showPricing && (
        <PricingDemoPanel
          data={pricingData as never}
          recommendation={pricingRecommendation}
          service={service}
        />
      )}

      {service === "feedback" && (
        <FeedbackDemoPanel
          data={walkthrough as never}
          highlightTarget={highlightTarget}
          filterLocation={filterLocation}
          liveRows={liveFeedback}
        />
      )}
      {service === "surveys" && <SurveysDemoPanel data={walkthrough as never} highlightTarget={highlightTarget} />}
      {service === "recruitment" && (
        <RecruitmentDemoPanel data={walkthrough as never} highlightTarget={highlightTarget} />
      )}
      {service === "expo" && (
        <ExpoDemoPanel data={walkthrough as never} highlightTarget={highlightTarget} liveRows={liveExpo} />
      )}
      {service === "smart_card" && (
        <SmartCardDemoPanel data={walkthrough as never} highlightTarget={highlightTarget} view={smartView} />
      )}
    </div>
  );
}
