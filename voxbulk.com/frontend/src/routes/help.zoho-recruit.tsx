import { createFileRoute, Link, redirect } from "@tanstack/react-router";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { ArrowLeft } from "lucide-react";
import { frontpageApiFetch } from "@/lib/api";

export const Route = createFileRoute("/help/zoho-recruit")({
  loader: async () => {
    try {
      const data = await frontpageApiFetch<{ visible?: boolean }>(
        "/frontpage/integration-visibility/zoho_recruit",
      );
      if (!data?.visible) {
        throw redirect({ to: "/help" });
      }
    } catch (e) {
      if (e && typeof e === "object" && "to" in e) throw e;
      throw redirect({ to: "/help" });
    }
    return {};
  },
  head: () => ({
    meta: [
      { title: "Zoho Recruit AI Voice Screening — VoxBulk Help" },
      {
        name: "description",
        content:
          "Hybrid Zoho Recruit + VoxBulk: connect OAuth, import candidates in Dashboard, run AI interviews and ATS, scores write back to Zoho Notes.",
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
            "Connect Zoho Recruit in VoxBulk Dashboard, import candidates, run AI interviews, and write scores back to Zoho.",
          step: [
            {
              "@type": "HowToStep",
              name: "Create a VoxBulk account",
              text: "Sign up at dashboard.voxbulk.com and enable interview screening for your organisation.",
            },
            {
              "@type": "HowToStep",
              name: "Connect Zoho Recruit",
              text: "In Dashboard → Settings → Integrations → Recruiting, connect Zoho Recruit and pick your data centre.",
            },
            {
              "@type": "HowToStep",
              name: "Create an interview campaign",
              text: "Open Interviews → New, generate and approve AI questions, then import candidates from Zoho in Step 2.",
            },
            {
              "@type": "HowToStep",
              name: "Launch and write back",
              text: "Run ATS if needed, launch AI interviews. Scores and status write back to Zoho Candidate Notes.",
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
            Use VoxBulk Dashboard for the full interview workflow. Import your Zoho candidate list, run AI questions,
            optional email CV + ATS, then AI calls. When interviews finish, VoxBulk writes score and status back to the
            Zoho Candidate as Notes (English and Arabic).
          </p>

          <div className="mt-10 space-y-10 text-[17px] leading-[1.75] text-navy/85">
            <section>
              <h2 className="font-serif text-[26px] text-navy">What you get</h2>
              <ul className="mt-4 list-disc pl-5 space-y-2">
                <li>Import candidates from Zoho Recruit into a VoxBulk interview campaign</li>
                <li>AI-generated interview questions you approve once per campaign</li>
                <li>Optional careers@ email CV intake and ATS scoring before dial</li>
                <li>Languages: English (en) and Arabic (ar)</li>
                <li>Score 0–100 and status: passed / review / rejected written back to Zoho Notes</li>
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
                <li>
                  Optional: install the VoxBulk extension from Zoho Marketplace (Candidate widget → Open VoxBulk).
                </li>
                <li>
                  In Dashboard → <strong>Settings → Integrations → Recruiting</strong>, connect Zoho Recruit and choose
                  your data centre.
                </li>
                <li>
                  Open <strong>Interviews → New</strong>: generate and approve AI questions, then in Step 2 use{" "}
                  <strong>Import from Zoho Recruit</strong> (filter by job/stage).
                </li>
                <li>Optionally enable email CV collection and run ATS, then launch AI interviews.</li>
                <li>After each completed interview, open the Candidate in Zoho and confirm the VoxBulk Notes writeback.</li>
              </ol>
            </section>

            <section>
              <h2 className="font-serif text-[26px] text-navy">Pricing</h2>
              <p className="mt-4">
                Usage is billed on VoxBulk (interview connection fee + per-minute rate, and ATS CV scan fees where
                applicable). Typical completed voice screen about £7–£9. Marketplace listing is a connector — metered
                voice is not sold as Zoho checkout minutes.
              </p>
            </section>

            <section>
              <h2 className="font-serif text-[26px] text-navy">Personal data</h2>
              <p className="mt-4">
                We store candidate name, phone, email (if provided), job details, screening Q&amp;A, language, call
                recording/transcript, AI score/status, report URL, and ATS reference IDs (including Zoho Candidate ID).
                Your organisation is the controller; VoxBulk is the processor. See{" "}
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
                More help:{" "}
                <Link to="/help" className="text-gold font-semibold underline-offset-2 hover:underline">
                  Help centre
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
