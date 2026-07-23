import { createFileRoute, Link } from "@tanstack/react-router";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { ArrowLeft } from "lucide-react";

export const Route = createFileRoute("/help/zoho-recruit")({
  head: () => ({
    meta: [
      { title: "Zoho Recruit AI Voice Screening — VoxBulk Help" },
      {
        name: "description",
        content:
          "How to connect VoxBulk AI Voice Screening to Zoho Recruit: install, API setup, English/Arabic screening, pricing, privacy, and support.",
      },
      { name: "robots", content: "index,follow" },
      { property: "og:title", content: "Zoho Recruit AI Voice Screening — VoxBulk Help" },
      { property: "og:url", content: "https://voxbulk.com/help/zoho-recruit" },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/help/zoho-recruit" }],
    scripts: [
      {
        type: "application/ld+json",
        children: JSON.stringify({
          "@context": "https://schema.org",
          "@type": "HowTo",
          name: "Connect VoxBulk AI Voice Screening to Zoho Recruit",
          description:
            "Install VoxBulk from Zoho Marketplace, connect your account, and run AI voice candidate screening in English or Arabic.",
          step: [
            {
              "@type": "HowToStep",
              name: "Create a VoxBulk account",
              text: "Sign up at dashboard.voxbulk.com and enable interview screening for your organisation.",
            },
            {
              "@type": "HowToStep",
              name: "Install from Zoho Marketplace",
              text: "Open the VoxBulk AI Voice Screening listing for Zoho Recruit and follow the vendor install redirect.",
            },
            {
              "@type": "HowToStep",
              name: "Connect credentials",
              text: "In VoxBulk Admin → Partners → Zoho, generate sandbox keys and map your organisation.",
            },
            {
              "@type": "HowToStep",
              name: "Send a test candidate",
              text: "Send a test job with candidate name, phone, and language en or ar, then confirm score and report return.",
            },
          ],
        }),
      },
    ],
  }),
  component: ZohoRecruitHelp,
});

function ZohoRecruitHelp() {
  return (
    <div className="bg-beige text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[110px] md:pt-[130px] pb-24">
        <article className="max-w-[720px] mx-auto px-5 md:px-8">
          <Link
            to="/help"
            className="inline-flex items-center gap-2 text-[13px] font-semibold text-navy/60 hover:text-gold transition-colors"
          >
            <ArrowLeft size={14} /> Help centre
          </Link>

          <div className="mt-8 text-[12px] uppercase tracking-[0.22em] text-navy/50">Zoho Recruit</div>
          <h1 className="mt-3 font-serif text-[34px] md:text-[46px] leading-[1.08] tracking-[-0.02em] text-navy">
            Connect VoxBulk AI Voice Screening to Zoho Recruit
          </h1>
          <p className="mt-5 text-[17px] leading-[1.75] text-navy/75">
            VoxBulk runs AI voice interviews for candidates in Zoho Recruit — English and Arabic — then returns a
            score, status, and report so recruiters can shortlist faster.
          </p>

          <div className="mt-10 space-y-10 text-[17px] leading-[1.75] text-navy/85">
            <section>
              <h2 className="font-serif text-[26px] text-navy">What you get</h2>
              <ul className="mt-4 list-disc pl-5 space-y-2">
                <li>AI phone screening with your job questions</li>
                <li>Languages: English (en) and Arabic (ar)</li>
                <li>Score 0–100 and status: passed / review / rejected</li>
                <li>Call duration and report link returned to your workflow</li>
              </ul>
            </section>

            <section>
              <h2 className="font-serif text-[26px] text-navy">Setup steps</h2>
              <ol className="mt-4 list-decimal pl-5 space-y-3">
                <li>
                  Create a VoxBulk account at{" "}
                  <a className="text-gold font-semibold underline-offset-2 hover:underline" href="https://dashboard.voxbulk.com">
                    dashboard.voxbulk.com
                  </a>
                  .
                </li>
                <li>Open the VoxBulk AI Voice Screening extension for Zoho Recruit on Zoho Marketplace and install (vendor redirect).</li>
                <li>
                  In VoxBulk Admin → <strong>Partners → Zoho Marketplace</strong>, generate sandbox API keys and map
                  your organisation.
                </li>
                <li>Send a test candidate (name, phone E.164, job title, questions, language en or ar).</li>
                <li>Confirm the result webhook / score appears and review the report link.</li>
                <li>When ready, switch to live keys and go live.</li>
              </ol>
            </section>

            <section>
              <h2 className="font-serif text-[26px] text-navy">Pricing</h2>
              <p className="mt-4">
                £1.50 connection fee + £0.35 per minute. Typical completed screen about £7–£9. No upfront install fee.
                Zoho Marketplace may keep a platform commission on remitted usage.
              </p>
            </section>

            <section>
              <h2 className="font-serif text-[26px] text-navy">Personal data</h2>
              <p className="mt-4">
                We store candidate name, phone, email (if provided), job details, screening Q&amp;A, language, call
                recording/transcript, AI score/status, report URL, and ATS reference IDs. Your organisation is the
                controller; VoxBulk is the processor. See{" "}
                <Link to="/privacy" className="text-gold font-semibold underline-offset-2 hover:underline">
                  Privacy Policy
                </Link>
                .
              </p>
            </section>

            <section>
              <h2 className="font-serif text-[26px] text-navy">Support</h2>
              <p className="mt-4">
                Email{" "}
                <a className="text-gold font-semibold underline-offset-2 hover:underline" href="mailto:support@voxbulk.com">
                  support@voxbulk.com
                </a>
                . Privacy:{" "}
                <a className="text-gold font-semibold underline-offset-2 hover:underline" href="mailto:Data.Pro@voxbulk.com">
                  Data.Pro@voxbulk.com
                </a>
                .
              </p>
              <p className="mt-3">
                More Zoho FAQs:{" "}
                <Link to="/help" className="text-gold font-semibold underline-offset-2 hover:underline">
                  Help centre → Zoho Recruit
                </Link>
                .
              </p>
            </section>
          </div>
        </article>
      </main>
      <SiteFooter />
    </div>
  );
}
