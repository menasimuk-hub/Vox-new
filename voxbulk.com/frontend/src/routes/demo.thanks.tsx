import { createFileRoute, Link } from "@tanstack/react-router";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { CheckCircle2 } from "lucide-react";
import { pageMeta } from "@/lib/seo-defaults";

export const Route = createFileRoute("/demo/thanks")({
  validateSearch: (search: Record<string, unknown>) => ({
    session: typeof search.session === "string" ? search.session : "",
  }),
  head: () => ({
    meta: pageMeta("contact", {
      override: {
        title: "Thanks for your demo | VoxBulk",
        description: "Your AI product demo has ended. Book a sales call or request another demo.",
      },
    }),
    links: [{ rel: "canonical", href: "https://voxbulk.com/demo/thanks" }],
  }),
  component: DemoThanksPage,
});

function DemoThanksPage() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 px-4 py-14">
        <div className="rounded-2xl border border-navy/15 bg-white p-8 text-center shadow-xl">
          <CheckCircle2 className="mx-auto h-12 w-12 text-emerald-600" aria-hidden />
          <h1 className="mt-4 text-3xl font-semibold tracking-tight text-navy">Thank you</h1>
          <p className="mt-3 text-sm leading-relaxed text-navy/80">
            Your live AI demo session has ended and access to the demo dashboard is closed. A VoxBulk
            specialist can follow up with pricing and a tailored rollout plan.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              to="/demo"
              className="inline-flex items-center justify-center rounded-full bg-[var(--primary,#1e6fd9)] px-5 py-2.5 text-sm font-semibold text-white"
            >
              Request another demo
            </Link>
            <Link
              to="/"
              className="inline-flex items-center justify-center rounded-full border border-navy/25 px-5 py-2.5 text-sm font-medium text-navy"
            >
              Back to homepage
            </Link>
          </div>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
