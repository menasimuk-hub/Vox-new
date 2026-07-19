import { createFileRoute } from "@tanstack/react-router";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import {
  Hero, WhoItsFor, BeforeAfter, Capabilities, LiveServices, CVIntake, HowItWorks,
  Proof, Metrics, Integrations, Pricing, RiskReversal, FAQ, BottomCTA, TalkToUs,
} from "@/components/VOXBULKHome";
import { pageMeta } from "@/lib/seo-defaults";

export const Route = createFileRoute("/recruitment")({
  head: () => ({
    meta: pageMeta("recruitment"),
    links: [{ rel: "canonical", href: "https://voxbulk.com/recruitment" }],
  }),
  component: RecruitmentPage,
});

function RecruitmentPage() {
  return (
    <div className="bg-background text-body antialiased">
      <SiteHeader />
      <main>
        <Hero
          badgeText="Live now · Recruitment Automation"
          headline={<>Post one job. <span className="serif-italic text-gold">Wake up to a shortlist</span>.</>}
          sub={
            <>
              Built for agencies and in-house TA teams hiring <strong className="text-white">20+ roles a month</strong>.
              CV intake, ATS scoring, WhatsApp booking and 10–12 minute AI phone interviews — scored, transcribed and
              ranked so your team only meets the top candidates.
            </>
          }
          primaryHref="/contact"
          primaryLabel="See a 2-min demo"
          secondaryLabel="Book a 20-min walkthrough"
        />
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
