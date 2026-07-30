import { createFileRoute } from "@tanstack/react-router";
import * as React from "react";

const API = (import.meta as any).env?.VITE_API_URL || "https://api.voxbulk.com";

export const Route = createFileRoute("/smart-card/$token")({
  component: PublicSmartCardPage,
});

function PublicSmartCardPage() {
  const { token } = Route.useParams();
  const [meta, setMeta] = React.useState<any>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [channel, setChannel] = React.useState<"choose" | "web" | "done">("choose");
  const [sessionId, setSessionId] = React.useState<string | null>(null);
  const [prompt, setPrompt] = React.useState("");
  const [answer, setAnswer] = React.useState("");
  const [doneMsg, setDoneMsg] = React.useState("");

  React.useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(`${API}/public/smart-card/${encodeURIComponent(token)}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data?.detail || "Not found");
        setMeta(data);
      } catch (e: any) {
        setError(e?.message || "Failed to load");
      }
    })();
  }, [token]);

  const startWeb = async () => {
    const res = await fetch(`${API}/public/smart-card/${encodeURIComponent(token)}/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const data = await res.json();
    if (!res.ok) {
      setError(typeof data?.detail === "string" ? data.detail : "Could not start");
      return;
    }
    setSessionId(data.session_id);
    setPrompt(data.prompt || "");
    setChannel("web");
  };

  const sendAnswer = async () => {
    if (!sessionId) return;
    const res = await fetch(`${API}/public/smart-card/${encodeURIComponent(token)}/answer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, answer }),
    });
    const data = await res.json();
    if (!res.ok) {
      setError(typeof data?.detail === "string" ? data.detail : "Answer failed");
      return;
    }
    setAnswer("");
    if (data.done) {
      setDoneMsg(data.message || "Thank you");
      setChannel("done");
      return;
    }
    setPrompt(data.prompt || "");
  };

  if (error) {
    return (
      <main className="mx-auto max-w-lg p-6">
        <p className="text-rose-700">{error}</p>
      </main>
    );
  }
  if (!meta) {
    return (
      <main className="mx-auto max-w-lg p-6">
        <p>Loading…</p>
      </main>
    );
  }

  if (meta.status === "expired" || meta.status === "preview_exhausted") {
    return (
      <main className="mx-auto max-w-lg space-y-4 p-6">
        <h1 className="text-2xl font-semibold">{meta.company?.name || "Smart Card QR"}</h1>
        <p>{meta.message}</p>
        {meta.renew_url ? (
          <a className="inline-block rounded-md bg-slate-900 px-4 py-2 text-white" href={meta.renew_url}>
            Renew package
          </a>
        ) : null}
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-lg space-y-6 p-6">
      <header className="space-y-1">
        <p className="text-sm uppercase tracking-wide text-slate-500">Smart Card QR</p>
        <h1 className="text-2xl font-semibold">{meta.representative?.name}</h1>
        <p className="text-slate-600">{meta.company?.name}</p>
        {meta.company?.description ? <p className="text-sm text-slate-500">{meta.company.description}</p> : null}
      </header>

      {channel === "choose" ? (
        <div className="grid gap-3">
          {meta.whatsapp_url ? (
            <a className="rounded-md bg-emerald-600 px-4 py-3 text-center text-white" href={meta.whatsapp_url}>
              Continue on WhatsApp
            </a>
          ) : null}
          <button className="rounded-md bg-slate-900 px-4 py-3 text-white" type="button" onClick={() => void startWeb()}>
            Continue on web
          </button>
          {meta.status === "preview" ? (
            <p className="text-xs text-amber-700">Preview mode — {meta.preview_tests_remaining} tests left</p>
          ) : null}
        </div>
      ) : null}

      {channel === "web" ? (
        <div className="space-y-3 rounded-xl border p-4">
          <p className="text-sm font-medium">{prompt}</p>
          <textarea
            className="min-h-[100px] w-full rounded-md border p-2 text-sm"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            placeholder="Type your answer (for contact: Name | Company | email | phone)"
          />
          <label className="block text-xs text-slate-500">
            Or upload business card
            <input
              type="file"
              accept="image/*"
              className="mt-1 block w-full text-sm"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file || !sessionId) return;
                const fd = new FormData();
                fd.append("file", file);
                const res = await fetch(
                  `${API}/public/smart-card/${encodeURIComponent(token)}/card?session_id=${encodeURIComponent(sessionId)}`,
                  { method: "POST", body: fd },
                );
                const data = await res.json();
                if (res.ok) {
                  setPrompt(data.prompt || prompt);
                  const ex = data.extracted || {};
                  setAnswer([ex.name, ex.company, ex.email, ex.phone].filter(Boolean).join(" | "));
                }
              }}
            />
          </label>
          <button className="rounded-md bg-slate-900 px-4 py-2 text-white" type="button" onClick={() => void sendAnswer()}>
            Send
          </button>
        </div>
      ) : null}

      {channel === "done" ? <p className="rounded-xl border bg-emerald-50 p-4 text-emerald-900">{doneMsg}</p> : null}
    </main>
  );
}
