import { createFileRoute, Link } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { ServicePicker } from "@/components/ai-demo/ServicePicker";
import { startDemoSession, verifyDemoToken, type AiDemoVerifyResponse } from "@/lib/aiDemo";

export const Route = createFileRoute("/demo/session")({
  validateSearch: (search: Record<string, unknown>) => ({
    token: typeof search.token === "string" ? search.token : "",
  }),
  component: DemoSessionPage,
});

function DemoSessionPage() {
  const { token } = Route.useSearch();
  const [phase, setPhase] = useState<"loading" | "ready" | "redirecting" | "ended" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [verified, setVerified] = useState<AiDemoVerifyResponse | null>(null);
  const [selected, setSelected] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!token) {
        setError("Missing demo link token.");
        setPhase("error");
        return;
      }
      try {
        const v = await verifyDemoToken(token);
        if (cancelled) return;
        setVerified(v);
        const mem =
          v.memory && typeof v.memory === "object"
            ? (v.memory as { selected_services?: string[] })
            : null;
        if (Array.isArray(mem?.selected_services) && mem.selected_services.length) {
          setSelected(mem.selected_services.map(String));
        }
        setPhase("ready");
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Invalid demo link");
        setPhase("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const startCall = useCallback(async () => {
    if (!verified) return;
    if (!selected.length) {
      toast.error("Pick at least one service to demo");
      return;
    }
    setPhase("redirecting");
    try {
      // Prove mic access before leaving this origin (dashboard will reconnect).
      try {
        const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
        mic.getTracks().forEach((t) => t.stop());
      } catch {
        throw new Error("Microphone access is required — allow mic access and try again.");
      }

      const started = await startDemoSession(verified.session_id, selected);
      const url = String(started.dashboard_url || "").trim();
      if (!url) {
        throw new Error("Demo dashboard handoff URL missing — ask Admin to Ensure Voxbulk Demo org.");
      }
      try {
        sessionStorage.setItem(
          `voxbulk_ai_demo_${started.session_id}`,
          JSON.stringify({
            session_id: started.session_id,
            soft_cap_minutes: started.soft_cap_minutes,
            selected_services: started.selected_services || selected,
            telnyx: started.telnyx,
          }),
        );
      } catch {
        /* ignore quota */
      }
      toast.success("Opening the real VoxBulk dashboard…");
      window.location.assign(url);
    } catch (e) {
      setPhase("ready");
      const msg = e instanceof Error ? e.message : "Could not start demo";
      setError(msg);
      toast.error(msg);
    }
  }, [selected, verified]);

  return (
    <div className="flex min-h-screen flex-col bg-[#0b0b0c] text-white">
      <SiteHeader />
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 py-10">
        {phase === "loading" && (
          <div className="flex items-center gap-2 text-white/70">
            <Loader2 className="h-5 w-5 animate-spin" /> Checking your demo invite…
          </div>
        )}
        {phase === "error" && (
          <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-6">
            <h1 className="text-xl font-semibold">Demo link unavailable</h1>
            <p className="mt-2 text-sm text-white/70">{error}</p>
            <Link to="/demo" className="mt-4 inline-block text-sm text-amber-300 underline">
              Request a new demo
            </Link>
          </div>
        )}
        {phase === "ready" && verified && (
          <>
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.14em] text-[var(--primary,#1e6fd9)]">
                AI product demo
              </p>
              <h1 className="mt-1 text-3xl font-semibold tracking-tight text-white">
                Hi {verified.contact_name} — start in the real dashboard
              </h1>
              <p className="mt-3 text-sm text-white/65">
                Pick the live products you care about. When you start, we open the real VoxBulk dashboard (
                <span className="text-white/90">Voxbulk Demo</span>) and Leo joins on a floating call — real
                menus, real sample data, and a guided walkthrough.
              </p>
            </div>
            <ServicePicker
              selected={selected}
              onToggle={(code) =>
                setSelected((prev) =>
                  prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code],
                )
              }
            />
            {error && <p className="text-sm text-red-300">{error}</p>}
            <button
              type="button"
              onClick={() => void startCall()}
              className="inline-flex h-12 items-center justify-center rounded-full bg-[var(--primary,#1e6fd9)] px-8 text-sm font-semibold text-white hover:brightness-110"
            >
              Start demo call
            </button>
          </>
        )}
        {phase === "redirecting" && (
          <div className="flex items-center gap-2 text-white/70">
            <Loader2 className="h-5 w-5 animate-spin" /> Opening the real dashboard…
          </div>
        )}
        {phase === "ended" && (
          <div className="rounded-xl border border-white/10 bg-white/5 p-6">
            <h1 className="text-xl font-semibold">Thanks for the demo</h1>
            <p className="mt-2 text-sm text-white/70">Our sales team can follow up with the best offer for your volumes.</p>
          </div>
        )}
      </main>
      <SiteFooter />
    </div>
  );
}
