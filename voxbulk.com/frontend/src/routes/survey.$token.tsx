import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { MessageCircle, Smartphone } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { BrandLogo } from "@/components/BrandLogo";
import "./survey.css";

export const Route = createFileRoute("/survey/$token")({
  head: () => ({
    meta: [
      { title: "Quick survey — Your feedback" },
      { name: "description", content: "A 60-second survey. Tap or talk." },
    ],
  }),
  component: PublicFeedbackSurvey,
});

type SurveyQuestion = {
  kind: string;
  title: string;
  body: string;
  input: "choice" | "text";
  options: { label: string; value: string }[];
  allow_voice?: boolean;
};

type SurveyPayload = {
  company_name: string;
  branch_name?: string;
  wa_url?: string;
  step_count: number;
  questions: SurveyQuestion[];
};

type Phase = "choose" | "survey" | "thanks";

function PublicFeedbackSurvey() {
  const { token } = Route.useParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [payload, setPayload] = useState<SurveyPayload | null>(null);
  const [phase, setPhase] = useState<Phase>("choose");
  const [sessionId, setSessionId] = useState("");
  const [stepIndex, setStepIndex] = useState(0);
  const [question, setQuestion] = useState<SurveyQuestion | null>(null);
  const [stepCount, setStepCount] = useState(0);
  const [textAnswer, setTextAnswer] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const data = await apiFetch<{ ok?: boolean } & SurveyPayload>(`/public/feedback/survey/${encodeURIComponent(token)}`);
        if (!cancelled) setPayload(data);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Survey not found");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const progress = useMemo(() => {
    if (!stepCount) return 0;
    return ((stepIndex + 1) / stepCount) * 100;
  }, [stepIndex, stepCount]);

  const startWeb = async () => {
    setBusy(true);
    setError("");
    try {
      const data = await apiFetch<{
        ok?: boolean;
        session_id?: string;
        step_index?: number;
        step_count?: number;
        question?: SurveyQuestion;
      }>(`/public/feedback/survey/${encodeURIComponent(token)}/sessions`, { method: "POST" });
      setSessionId(String(data.session_id || ""));
      setStepIndex(Number(data.step_index ?? 0));
      setStepCount(Number(data.step_count ?? 0));
      setQuestion(data.question || null);
      setPhase("survey");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start survey");
    } finally {
      setBusy(false);
    }
  };

  const submitAnswer = async (answer: string) => {
    if (!sessionId) return;
    setBusy(true);
    setError("");
    try {
      const data = await apiFetch<{
        ok?: boolean;
        completed?: boolean;
        step_index?: number;
        step_count?: number;
        question?: SurveyQuestion;
      }>(`/public/feedback/survey/sessions/${encodeURIComponent(sessionId)}/answer`, {
        method: "POST",
        body: JSON.stringify({ answer }),
      });
      if (data.completed) {
        setPhase("thanks");
        return;
      }
      setStepIndex(Number(data.step_index ?? stepIndex + 1));
      setStepCount(Number(data.step_count ?? stepCount));
      setQuestion(data.question || null);
      setTextAnswer("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save answer");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <main className="fb-survey-page">
        <div className="fb-survey-shell muted">Loading survey…</div>
      </main>
    );
  }

  if (error && !payload) {
    return (
      <main className="fb-survey-page">
        <div className="fb-survey-shell">
          <p className="fb-error">{error}</p>
          <Link to="/" className="fb-link">Back to VoxBulk</Link>
        </div>
      </main>
    );
  }

  if (!payload) return null;

  if (phase === "thanks") {
    return (
      <main className="fb-survey-page">
        <div className="fb-blobs" aria-hidden />
        <div className="fb-survey-shell fb-thanks">
          <h1 className="fb-title">Thank you 🙏</h1>
          <p className="fb-sub">Your feedback helps {payload.company_name} improve.</p>
        </div>
      </main>
    );
  }

  if (phase === "choose") {
    return (
      <main className="fb-survey-page">
        <div className="fb-blobs" aria-hidden />
        <div className="fb-survey-shell">
          <div className="fb-top">
            <Link to="/" className="fb-brand">
              <BrandLogo icon className="fb-brand-icon" />
              <span>VoxBulk Feedback</span>
            </Link>
          </div>
          <div className="fb-hero">
            <p className="fb-kicker">Customer feedback</p>
            <h1 className="fb-title">{payload.company_name}</h1>
            {payload.branch_name ? <p className="fb-sub">{payload.branch_name}</p> : null}
            <p className="fb-lead">A quick survey — under a minute. Choose how you want to respond.</p>
          </div>
          <div className="fb-choices">
            {payload.wa_url ? (
              <a href={payload.wa_url} className="fb-choice" target="_blank" rel="noreferrer">
                <MessageCircle className="fb-choice-icon" />
                <div>
                  <strong>Continue on WhatsApp</strong>
                  <span>Chat-style survey on your phone</span>
                </div>
              </a>
            ) : null}
            <button type="button" className="fb-choice" onClick={startWeb} disabled={busy}>
              <Smartphone className="fb-choice-icon" />
              <div>
                <strong>Take web survey</strong>
                <span>{payload.step_count || payload.questions.length} quick questions</span>
              </div>
            </button>
          </div>
          {error ? <p className="fb-error">{error}</p> : null}
        </div>
      </main>
    );
  }

  const q = question;
  const isText = q?.input === "text";

  return (
    <main className="fb-survey-page">
      <div className="fb-blobs" aria-hidden />
      <div className="fb-survey-shell fb-survey-flow">
        <div className="fb-top">
          <span className="fb-brand">
            <BrandLogo icon className="fb-brand-icon" />
            <span>{payload.company_name}</span>
          </span>
          <span className="fb-step-count">{stepIndex + 1} / {stepCount}</span>
        </div>
        <div className="fb-progress">
          <div className="fb-progress-bar" style={{ width: `${progress}%` }} />
        </div>
        <div className="fb-body">
          <p className="fb-kicker">Question {stepIndex + 1}</p>
          <h1 className="fb-title">{q?.title || "Your feedback"}</h1>
          {q?.body ? <p className="fb-sub">{q.body}</p> : null}
          {isText ? (
            <textarea
              className="fb-textarea"
              rows={4}
              value={textAnswer}
              onChange={(e) => setTextAnswer(e.target.value)}
              placeholder="Type your answer…"
            />
          ) : (
            <div className="fb-options">
              {(q?.options || []).map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  className="fb-option"
                  disabled={busy}
                  onClick={() => submitAnswer(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="fb-footer">
          {isText ? (
            <>
              <button type="button" className="fb-btn ghost" disabled={busy} onClick={() => submitAnswer("skip")}>
                Skip
              </button>
              <button
                type="button"
                className="fb-btn primary"
                disabled={busy || !textAnswer.trim()}
                onClick={() => submitAnswer(textAnswer.trim())}
              >
                {busy ? "Saving…" : "Next"}
              </button>
            </>
          ) : null}
        </div>
        {error ? <p className="fb-error">{error}</p> : null}
      </div>
    </main>
  );
}
