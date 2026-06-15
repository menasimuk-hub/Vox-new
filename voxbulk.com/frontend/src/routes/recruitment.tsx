import { createFileRoute } from "@tanstack/react-router";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import {
  Hero, WhoItsFor, BeforeAfter, Capabilities, LiveServices, CVIntake, HowItWorks,
  Proof, Metrics, Integrations, Pricing, RiskReversal, FAQ, BottomCTA, TalkToUs,
} from "@/components/VOXBULKHome";

export const Route = createFileRoute("/recruitment")({
  head: () => ({
    meta: [
      { title: "Recruitment Automation — VoxBulk" },
      { name: "description", content: "AI screens every CV, books interviews on WhatsApp and runs the voice screening call — so your team only meets the top 5%." },
      { property: "og:title", content: "Recruitment Automation — VoxBulk" },
      { property: "og:description", content: "AI screening, scheduling and voice interviews — fully automated. Built for agencies and in-house TA teams hiring 20+ roles a month." },
    ],
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
          headline={<>Recruitment, fully <span className="serif-italic text-gold">automated</span>.</>}
          sub={
            <>
              Built for agencies and in-house TA teams hiring <strong className="text-white">20+ roles a month</strong>.
              VoxBulk scores every CV, books interviews on WhatsApp and runs the screening call — your
              team only meets the top 5%.
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
