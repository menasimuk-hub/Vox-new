import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { submitLiveDemoResponse } from "@/lib/aiDemo";
import { toast } from "sonner";

export const Route = createFileRoute("/demo/live-feedback")({
  validateSearch: (search: Record<string, unknown>) => ({
    session: typeof search.session === "string" ? search.session : "",
    service: typeof search.service === "string" ? search.service : "feedback",
  }),
  component: LiveFeedbackPage,
});

function LiveFeedbackPage() {
  const { session, service } = Route.useSearch();
  const [score, setScore] = useState(5);
  const [comment, setComment] = useState("");
  const [name, setName] = useState("");
  const [location, setLocation] = useState("Leeds");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!session) {
      toast.error("Missing demo session — scan the QR from the live demo again.");
      return;
    }
    setBusy(true);
    try {
      await submitLiveDemoResponse({
        session_id: session,
        service: service || "feedback",
        score,
        comment,
        name: name || "You",
        location,
      });
      setDone(true);
      toast.success("Sent — watch the dashboard on the other screen");
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
          <h1 className="text-[22px] font-bold text-heading">Quick feedback</h1>
          <p className="text-[14px] text-body mt-2">This is the live demo QR — your answer appears on the dashboard in a few seconds.</p>
          {done ? (
            <p className="mt-6 text-emerald-700 font-semibold">Thanks — look at the demo screen!</p>
          ) : (
            <form className="mt-5 space-y-4" onSubmit={(e) => void submit(e)}>
              <label className="block text-[13px] font-semibold">
                Your name
                <input className="mt-1 w-full h-11 rounded-xl border border-border px-3" value={name} onChange={(e) => setName(e.target.value)} />
              </label>
              <label className="block text-[13px] font-semibold">
                Location
                <select className="mt-1 w-full h-11 rounded-xl border border-border px-3" value={location} onChange={(e) => setLocation(e.target.value)}>
                  <option>Leeds</option>
                  <option>Manchester</option>
                  <option>Bristol</option>
                </select>
              </label>
              <label className="block text-[13px] font-semibold">
                Score {score}/5
                <input type="range" min={1} max={5} value={score} onChange={(e) => setScore(Number(e.target.value))} className="mt-2 w-full" />
              </label>
              <label className="block text-[13px] font-semibold">
                Comment
                <textarea className="mt-1 w-full rounded-xl border border-border px-3 py-2 min-h-[88px]" value={comment} onChange={(e) => setComment(e.target.value)} required />
              </label>
              <button type="submit" className="btn-primary h-11 w-full" disabled={busy}>
                {busy ? "Sending…" : "Send to dashboard"}
              </button>
            </form>
          )}
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
