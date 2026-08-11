import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { submitLiveDemoResponse } from "@/lib/aiDemo";
import { toast } from "sonner";

export const Route = createFileRoute("/demo/live-expo")({
  validateSearch: (search: Record<string, unknown>) => ({
    session: typeof search.session === "string" ? search.session : "",
    service: typeof search.service === "string" ? search.service : "expo",
  }),
  component: LiveExpoPage,
});

function LiveExpoPage() {
  const { session, service } = Route.useSearch();
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!session) {
      toast.error("Missing demo session");
      return;
    }
    setBusy(true);
    try {
      await submitLiveDemoResponse({
        session_id: session,
        service: service || "expo",
        name,
        company,
        score: 5,
        comment: "Booth scan from live demo QR",
      });
      setDone(true);
      toast.success("Lead sent to the demo dashboard");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not send");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bg-background text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[110px] pb-16 px-5">
        <div className="max-w-md mx-auto rounded-3xl border border-border bg-white p-6 shadow-elegant">
          <h1 className="text-[22px] font-bold text-heading">Booth check-in</h1>
          <p className="text-[14px] text-body mt-2">Live Expo demo — your lead appears on the dashboard.</p>
          {done ? (
            <p className="mt-6 text-emerald-700 font-semibold">You’re in — watch the demo screen.</p>
          ) : (
            <form className="mt-5 space-y-4" onSubmit={(e) => void submit(e)}>
              <label className="block text-[13px] font-semibold">
                Name
                <input className="mt-1 w-full h-11 rounded-xl border border-border px-3" value={name} onChange={(e) => setName(e.target.value)} required />
              </label>
              <label className="block text-[13px] font-semibold">
                Company
                <input className="mt-1 w-full h-11 rounded-xl border border-border px-3" value={company} onChange={(e) => setCompany(e.target.value)} required />
              </label>
              <button type="submit" className="btn-primary h-11 w-full" disabled={busy}>
                {busy ? "Sending…" : "Leave my details"}
              </button>
            </form>
          )}
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
