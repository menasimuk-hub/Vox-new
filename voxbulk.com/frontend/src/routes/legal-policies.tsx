import { createFileRoute } from "@tanstack/react-router";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";

export const Route = createFileRoute("/legal-policies")({
  head: () => ({
    meta: [
      { title: "Legal & Policies — VoxBulk" },
      { name: "description", content: "Terms, Privacy, Cookies, GDPR and other legal policies for VoxBulk." },
      { property: "og:title", content: "Legal & Policies — VoxBulk" },
      { property: "og:url", content: "https://voxbulk.com/legal-policies" },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/legal-policies" }],
  }),
  component: LegalPoliciesPage,
});

function LegalPoliciesPage() {
  return (
    <div className="bg-background min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[88px]">
        <iframe
          src="/legal-content.html"
          title="Legal & Policies"
          className="w-full border-0"
          style={{ height: "calc(100vh - 88px)" }}
        />
      </main>
      <SiteFooter />
    </div>
  );
}
