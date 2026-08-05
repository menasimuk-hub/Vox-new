import { createFileRoute } from "@tanstack/react-router";
import { ServiceHero } from "@/components/HeroSlider";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import {
  WhoItsFor, BeforeAfter, Capabilities, LiveServices, CVIntake, HowItWorks,
  Proof, Metrics, Integrations, Pricing, RiskReversal, FAQ, BottomCTA, TalkToUs,
} from "@/components/VOXBULKHome";
import { fetchSeoSettings } from "@/lib/seo";
import { pageMeta } from "@/lib/seo-defaults";

export const Route = createFileRoute("/recruitment")({
  loader: async () => {
    const { requireEnabledProductRoute } = await import("@/lib/product-visibility");
    await requireEnabledProductRoute("/recruitment");
    return { settings: await fetchSeoSettings() };
  },
  head: ({ loaderData }) => ({
    meta: pageMeta("recruitment", { override: loaderData?.settings?.marketing_pages?.recruitment }),
    links: [{ rel: "canonical", href: "https://voxbulk.com/recruitment" }],
  }),
  component: RecruitmentPage,
});

function RecruitmentPage() {
  return (
    <div className="bg-background text-body antialiased">
      <SiteHeader />
      <main>
        <ServiceHero service="recruitment" />
        <WhoItsFor />
        <BeforeAfter />
        <Capabilities />
        <LiveServices />
        <CVIntake />
        <HowItWorks />
        <Proof />
        <Metrics />
        <Integrations />
        <Pricing />
        <RiskReversal />
        <FAQ />
        <TalkToUs />
        <BottomCTA />
      </main>
      <SiteFooter />
    </div>
  );
}
