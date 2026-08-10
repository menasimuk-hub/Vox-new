import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { Check, Loader2 } from "lucide-react";
import { resendDemoLink } from "@/lib/aiDemo";

export const Route = createFileRoute("/demo/resend")({
  validateSearch: (search: Record<string, unknown>) => ({
    request: typeof search.request === "string" ? search.request : "",
    sig: typeof search.sig === "string" ? search.sig : "",
  }),
  component: DemoResendPage,
});

function DemoResendPage() {
  const { request, sig } = Route.useSearch();
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!request || !sig) {
        setStatus("error");
        setMessage("Invalid resend link.");
        return;
      }
      try {
        await resendDemoLink(request, sig);
        if (cancelled) return;
        setStatus("ok");
        setMessage("A fresh demo link has been emailed to you. Check your inbox (and spam).");
      } catch (e) {
        if (cancelled) return;
        setStatus("error");
        setMessage(e instanceof Error ? e.message : "Could not resend the demo link.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [request, sig]);

  return (
    <div className="bg-background text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[130px] pb-24">
        <div className="max-w-[520px] mx-auto px-5 text-center">
          {status === "loading" && (
            <div className="inline-flex items-center gap-2 text-muted-text">
              <Loader2 className="animate-spin" size={18} /> Sending a new link…
            </div>
          )}
          {status === "ok" && (
            <>
              <div className="mx-auto w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center mb-4">
                <Check className="text-primary" size={28} />
              </div>
              <h1 className="text-[28px] font-bold text-heading">New link sent</h1>
              <p className="mt-3 text-[15px] text-body">{message}</p>
              <p className="mt-2 text-[13px] text-muted-text">Your previous progress is kept for the AI agent.</p>
            </>
          )}
          {status === "error" && (
            <>
              <h1 className="text-[28px] font-bold text-heading">Could not resend</h1>
              <p className="mt-3 text-[15px] text-red-600">{message}</p>
              <Link to="/demo" className="inline-flex mt-6 text-primary font-semibold">
                Request a demo
              </Link>
            </>
          )}
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
