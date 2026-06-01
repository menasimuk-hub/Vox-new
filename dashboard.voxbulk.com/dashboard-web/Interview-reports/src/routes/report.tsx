import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import {
  Printer,
  Download,
  Lock,
  ShieldAlert,
  TrendingUp,
  Sparkles,
  AlertTriangle,
  MessageSquare,
} from "lucide-react";

export const Route = createFileRoute("/report")({
  head: () => ({
    meta: [
      { title: "Candidate Interview Report — Confidential" },
      {
        name: "description",
        content:
          "Internal candidate interview report with ATS, interview, culture fit, and overall scoring.",
      },
      { name: "robots", content: "noindex,nofollow" },
    ],
  }),
  component: ReportPage,
});

/* ---------- Tokens ---------- */
const BLUE = "#185fa5";
const GREEN = "#1d9e75";
const AMBER = "#ba7517";
const RED = "#a32d2d";
const PURPLE = "#3c3489";
const BORDER = "rgba(26,26,24,0.12)";
const CARD = "#f1efe8";
const BG = "#faf9f6";
const TEXT = "#1a1a18";
const MUTED = "#888780";

/* ---------- Data ---------- */
const reportData = {
  meta: {
    jobTaskId: "JT-2026-0481",
    interviewId: "INT-2026-0481",
    issued: "May 28, 2026",
  },
  candidate: {
    name: "Amelia Chen",
    role: "Senior Product Designer",
    location: "Berlin, DE · Remote",
  },
  scores: { ats: 84, interview: 88, culture: 76, overall: 83 },
  atsCriteria: [
    { name: "Experience Match", sub: "8+ years required", pct: 92 },
    { name: "Skills Coverage", sub: "Core toolkit & methods", pct: 81 },
    { name: "Education", sub: "Degree & certifications", pct: 70 },
    { name: "Industry Fit", sub: "SaaS / B2B background", pct: 65 },
    { name: "Location & Availability", sub: "Remote, EU timezone", pct: 55 },
  ],
  keywordsFound: [
    "Figma",
    "Design Systems",
    "User Research",
    "Prototyping",
    "Accessibility",
    "Mentorship",
  ],
  keywordsPartial: ["A/B Testing", "Front-end basics"],
  keywordsMissing: ["Motion design", "Service blueprints", "Workshop facilitation"],
  competencies: [
    { name: "Product Thinking", category: "Strategy", score: 9, notes: "Frames trade-offs clearly, anchors decisions to user and business outcomes." },
    { name: "Craft & Visual Design", category: "Execution", score: 9, notes: "Strong typographic discipline and use of system tokens. Pixel-perfect deliverables." },
    { name: "Collaboration", category: "Teaming", score: 8, notes: "Comfortable pairing with PM and engineering; advocates for design review rituals." },
    { name: "Communication", category: "Soft skills", score: 8, notes: "Articulate, concise, structures answers with situation–action–outcome." },
    { name: "Research Fluency", category: "Discovery", score: 7, notes: "Solid generative & evaluative methods. Less depth on quant analysis." },
    { name: "Leadership", category: "Influence", score: 6, notes: "Mentors juniors but limited experience leading multi-team initiatives." },
  ],
  standout:
    "When asked about a failed launch, Amelia walked through a post-mortem she ran herself, including the metrics that disproved her initial hypothesis. Rare level of intellectual honesty.",
  skillGap:
    "Has not led a 0→1 product end-to-end. Will need partnership with a senior PM during the first quarter on greenfield initiatives.",
  questions: [
    { id: "q1", q: "Walk me through a design system you scaled across multiple product surfaces.", score: 9 },
    { id: "q2", q: "Describe a time research changed your strongly-held assumption.", score: 8 },
    { id: "q3", q: "How do you balance speed vs. craft under shipping pressure?", score: 8 },
    { id: "q4", q: "Tell me about a disagreement with engineering and how it resolved.", score: 7 },
    { id: "q5", q: "Where do you want to grow in the next 18 months?", score: 9 },
  ],
  recommendation: {
    verdict: "Proceed" as "Proceed" | "Hold" | "Reject",
    points: [
      { kind: "+" as const, text: "Exceptional craft and product judgment for the role level." },
      { kind: "+" as const, text: "Mentorship instinct fits the team's growth needs." },
      { kind: "-" as const, text: "Limited 0→1 leadership experience on greenfield work." },
      { kind: "->" as const, text: "Compensation expectations align with band; remote setup confirmed." },
    ],
  },
};

function getBarColor(pct: number) {
  if (pct >= 80) return GREEN;
  if (pct >= 60) return BLUE;
  return AMBER;
}

/* ---------- Primitives ---------- */
function AnimatedBar({ value, color, delay = 0 }: { value: number; color: string; delay?: number }) {
  const v = Math.min(100, Math.max(0, value));
  return (
    <div
      className="relative h-2 w-full overflow-hidden rounded-full"
      style={{ backgroundColor: "rgba(26,26,24,0.07)" }}
    >
      <div
        className="animate-bar animate-bar-shimmer relative h-full rounded-full"
        style={{
          ["--bar-target" as never]: `${v}%`,
          backgroundColor: color,
          animationDelay: `${delay}ms`,
          boxShadow: `0 0 0 1px ${color}22 inset`,
        }}
      />
    </div>
  );
}

function SectionTitle({ kicker, title, hint }: { kicker: string; title: string; hint?: string }) {
  return (
    <div className="mb-4 flex items-end justify-between gap-4">
      <div>
        <div className="text-[10px] font-semibold uppercase tracking-[0.18em]" style={{ color: MUTED }}>
          {kicker}
        </div>
        <h2 className="mt-1 text-lg font-semibold tracking-tight" style={{ color: TEXT }}>
          {title}
        </h2>
      </div>
      {hint && (
        <div className="text-xs" style={{ color: MUTED }}>
          {hint}
        </div>
      )}
    </div>
  );
}

function ScoreCard({
  label,
  score,
  accent,
  delay,
}: {
  label: string;
  score: number;
  accent: string;
  delay: number;
}) {
  return (
    <div
      className="animate-fade-up relative overflow-hidden rounded-xl p-5"
      style={{
        backgroundColor: CARD,
        border: `1px solid ${BORDER}`,
        animationDelay: `${delay}ms`,
      }}
    >
      <div
        className="absolute inset-x-0 top-0 h-[3px]"
        style={{ background: `linear-gradient(90deg, ${accent}, ${accent}99)` }}
      />
      <div className="flex items-center justify-between">
        <div className="text-[10px] font-semibold uppercase tracking-[0.18em]" style={{ color: MUTED }}>
          {label}
        </div>
        <span
          className="rounded-full px-2 py-0.5 text-[10px] font-medium"
          style={{ color: accent, backgroundColor: `${accent}14` }}
        >
          /100
        </span>
      </div>
      <div className="mt-3 flex items-baseline gap-1">
        <div className="text-4xl font-semibold tabular-nums tracking-tight" style={{ color: TEXT }}>
          {score}
        </div>
        <TrendingUp className="ml-1 h-3.5 w-3.5" style={{ color: accent }} />
      </div>
      <div className="mt-4">
        <AnimatedBar value={score} color={accent} delay={delay + 200} />
      </div>
    </div>
  );
}

function CriteriaRow({
  name,
  sub,
  pct,
  idx,
}: {
  name: string;
  sub: string;
  pct: number;
  idx: number;
}) {
  return (
    <div className="py-3.5" style={{ borderTop: idx === 0 ? "none" : `1px solid ${BORDER}` }}>
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <div className="text-sm font-medium" style={{ color: TEXT }}>
            {name}
          </div>
          <div className="text-xs" style={{ color: MUTED }}>
            {sub}
          </div>
        </div>
        <div className="text-sm font-semibold tabular-nums" style={{ color: TEXT }}>
          {pct}%
        </div>
      </div>
      <div className="mt-2">
        <AnimatedBar value={pct} color={getBarColor(pct)} delay={150 + idx * 80} />
      </div>
    </div>
  );
}

function Tag({ text, kind }: { text: string; kind: "found" | "missing" | "partial" }) {
  const s =
    kind === "found"
      ? { bg: "rgba(29,158,117,0.10)", fg: GREEN, br: "rgba(29,158,117,0.28)" }
      : kind === "missing"
        ? { bg: "rgba(163,45,45,0.08)", fg: RED, br: "rgba(163,45,45,0.28)" }
        : { bg: "rgba(186,117,23,0.10)", fg: AMBER, br: "rgba(186,117,23,0.28)" };
  return (
    <span
      className="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium"
      style={{ backgroundColor: s.bg, color: s.fg, border: `1px solid ${s.br}` }}
    >
      {text}
    </span>
  );
}

function CompetencyCard({
  name,
  category,
  score,
  notes,
  delay,
}: {
  name: string;
  category: string;
  score: number;
  notes: string;
  delay: number;
}) {
  const pct = score * 10;
  const color = getBarColor(pct);
  return (
    <div
      className="animate-fade-up rounded-xl p-5"
      style={{ backgroundColor: CARD, border: `1px solid ${BORDER}`, animationDelay: `${delay}ms` }}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold" style={{ color: TEXT }}>
            {name}
          </div>
          <div className="text-[11px] uppercase tracking-wider" style={{ color: MUTED }}>
            {category}
          </div>
        </div>
        <span
          className="rounded-md px-2 py-1 text-xs font-semibold tabular-nums"
          style={{ backgroundColor: `${color}1f`, color }}
        >
          {score}/10
        </span>
      </div>
      <div className="mt-3">
        <AnimatedBar value={pct} color={color} delay={delay + 150} />
      </div>
      <p className="mt-3 text-sm leading-relaxed" style={{ color: TEXT }}>
        {notes}
      </p>
    </div>
  );
}

function generateSmartComment(score: number): string {
  if (score === 10) {
    return "Exceptional response with clear thinking and strong examples. Demonstrates mastery of the subject area.";
  } else if (score === 9) {
    return "Excellent response. Strong command of the topic with relevant insights and minor room for growth.";
  } else if (score === 8) {
    return "Good response. Clear understanding with solid reasoning. Some areas could be elaborated further.";
  } else if (score === 7) {
    return "Adequate response. Demonstrates understanding but could provide more depth or structure to the answer.";
  } else if (score === 6) {
    return "Acceptable response with some gaps. Could benefit from more concrete examples or deeper analysis.";
  } else if (score <= 5) {
    return "Response needs improvement. Consider asking follow-up questions or revisiting this topic.";
  }
  return "";
}

function QuestionBlock({
  index,
  q,
  score,
  comment,
  onChange,
  delay,
}: {
  index: number;
  q: string;
  score: number;
  comment: string;
  onChange: (v: string) => void;
  delay: number;
}) {
  const pct = score * 10;
  const color = getBarColor(pct);
  const suggestedComment = generateSmartComment(score);
  const displayComment = comment || suggestedComment;

  return (
    <div className="py-4" style={{ borderTop: index === 0 ? "none" : `1px solid ${BORDER}` }}>
      <div className="flex items-baseline justify-between gap-4">
        <div className="flex gap-3">
          <span
            className="mt-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-md px-1.5 text-[11px] font-semibold tabular-nums"
            style={{ backgroundColor: "rgba(26,26,24,0.06)", color: MUTED }}
          >
            Q{index + 1}
          </span>
          <div className="text-sm leading-relaxed" style={{ color: TEXT }}>
            {q}
          </div>
        </div>
        <div
          className="rounded-md px-2 py-0.5 text-xs font-semibold tabular-nums"
          style={{ backgroundColor: `${color}1f`, color }}
        >
          {score}/10
        </div>
      </div>
      <div className="mt-2.5">
        <AnimatedBar value={pct} color={color} delay={delay} />
      </div>
      <div className="mt-3 flex items-start gap-2">
        <MessageSquare className="mt-2.5 h-3.5 w-3.5 shrink-0" style={{ color: MUTED }} />
        <textarea
          value={displayComment}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Add interviewer comment…"
          rows={2}
          className="w-full resize-none rounded-md bg-transparent px-3 py-2 text-sm outline-none transition-colors focus:bg-white"
          style={{
            border: `1px solid ${BORDER}`,
            color: TEXT,
            fontStyle: !comment ? "italic" : "normal",
            opacity: !comment ? 0.7 : 1,
          }}
        />
      </div>
    </div>
  );
}

function RecommendationBanner({
  verdict,
  points,
}: {
  verdict: "Proceed" | "Hold" | "Reject";
  points: { kind: "+" | "-" | "->"; text: string }[];
}) {
  const color = verdict === "Proceed" ? GREEN : verdict === "Hold" ? AMBER : RED;
  return (
    <div
      className="relative overflow-hidden rounded-xl p-6 text-white"
      style={{
        background: `linear-gradient(135deg, ${color} 0%, ${color}dd 60%, ${color}b3 100%)`,
        border: `1px solid ${BORDER}`,
      }}
    >
      <div
        className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full"
        style={{ background: "rgba(255,255,255,0.12)" }}
      />
      <div className="relative flex items-center gap-3">
        <span className="text-[10px] font-semibold uppercase tracking-[0.22em] opacity-80">
          Final Recommendation
        </span>
        <span className="text-2xl font-semibold tracking-tight">{verdict}</span>
      </div>
      <ul className="relative mt-4 grid gap-2 sm:grid-cols-2">
        {points.map((p, i) => {
          const glyph = p.kind === "+" ? "+" : p.kind === "-" ? "−" : "→";
          return (
            <li key={i} className="flex gap-3 text-sm">
              <span
                className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-xs font-bold"
                style={{ background: "rgba(255,255,255,0.18)" }}
              >
                {glyph}
              </span>
              <span className="opacity-95">{p.text}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/* ---------- Page ---------- */
function ReportPage() {
  const d = reportData;
  const [comments, setComments] = useState<Record<string, string>>(
    Object.fromEntries(d.questions.map((q) => [q.id, ""])),
  );

  const handlePrint = () => {
    if (typeof window !== "undefined") window.print();
  };

  return (
    <main className="min-h-screen" style={{ backgroundColor: BG, color: TEXT }}>
      {/* Confidential ribbon */}
      <div
        className="no-print w-full"
        style={{
          background: "repeating-linear-gradient(135deg, #1a1a18 0 12px, #2a2a26 12px 24px)",
        }}
      >
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-6 py-1.5 text-[10px] font-semibold uppercase tracking-[0.22em] text-white/90">
          <span className="flex items-center gap-2">
            <Lock className="h-3 w-3" /> Internal Use Only · Confidential
          </span>
          <span className="hidden sm:inline opacity-70">
            Do Not Distribute · Job Task {d.meta.jobTaskId}
          </span>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-6 py-8">
        {/* Header */}
        <header
          className="mb-8 overflow-hidden rounded-2xl"
          style={{ backgroundColor: CARD, border: `1px solid ${BORDER}` }}
        >
          <div className="flex flex-wrap items-start justify-between gap-6 p-6">
            <div className="flex items-start gap-4">
              <div>
                <div
                  className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.22em]"
                  style={{ color: MUTED }}
                >
                  <ShieldAlert className="h-3 w-3" />
                  Candidate Interview Report
                </div>
                <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl" style={{ color: TEXT }}>
                  {d.candidate.name}
                </h1>
                <div className="mt-0.5 text-sm" style={{ color: MUTED }}>
                  {d.candidate.role} · {d.candidate.location}
                </div>
              </div>
            </div>

            <div className="no-print flex flex-wrap items-center gap-2">
              <button
                onClick={handlePrint}
                className="inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-black/5"
                style={{ border: `1px solid ${BORDER}`, color: TEXT }}
              >
                <Printer className="h-4 w-4" /> Print
              </button>
              <button
                onClick={handlePrint}
                className="inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
                style={{ backgroundColor: BLUE }}
              >
                <Download className="h-4 w-4" /> Download PDF
              </button>
            </div>
          </div>

          <div
            className="grid grid-cols-2 gap-px text-xs sm:grid-cols-3"
            style={{ backgroundColor: BORDER, borderTop: `1px solid ${BORDER}` }}
          >
            {[
              ["Job Task ID", d.meta.jobTaskId],
              ["Interview ID", d.meta.interviewId],
              ["Issued", d.meta.issued],
            ].map(([k, v]) => (
              <div key={k} className="px-5 py-3" style={{ backgroundColor: CARD }}>
                <div className="text-[10px] font-semibold uppercase tracking-[0.18em]" style={{ color: MUTED }}>
                  {k}
                </div>
                <div className="mt-0.5 truncate" style={{ color: TEXT }}>
                  {v}
                </div>
              </div>
            ))}
          </div>
        </header>

        {/* Score Summary */}
        <section className="mb-10">
          <SectionTitle kicker="Overview" title="Score Summary" hint="Composite of weighted signals" />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <ScoreCard label="ATS Score" score={d.scores.ats} accent={BLUE} delay={0} />
            <ScoreCard label="Interview Score" score={d.scores.interview} accent={GREEN} delay={80} />
            <ScoreCard label="Culture Fit" score={d.scores.culture} accent={AMBER} delay={160} />
            <ScoreCard label="Overall Score" score={d.scores.overall} accent={PURPLE} delay={240} />
          </div>
        </section>

        {/* ATS Breakdown */}
        <section className="mb-10">
          <SectionTitle kicker="Resume Match" title="ATS Breakdown" hint="Against requisition criteria" />
          <div className="rounded-xl p-6" style={{ backgroundColor: CARD, border: `1px solid ${BORDER}` }}>
            <div>
              {d.atsCriteria.map((c, i) => (
                <CriteriaRow key={c.name} {...c} idx={i} />
              ))}
            </div>

            <div
              className="mt-6 grid gap-5 pt-5 sm:grid-cols-2"
              style={{ borderTop: `1px solid ${BORDER}` }}
            >
              <div>
                <div
                  className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em]"
                  style={{ color: MUTED }}
                >
                  Keywords Found
                </div>
                <div className="flex flex-wrap gap-2">
                  {d.keywordsFound.map((k) => (
                    <Tag key={k} text={k} kind="found" />
                  ))}
                  {d.keywordsPartial.map((k) => (
                    <Tag key={k} text={`${k} (partial)`} kind="partial" />
                  ))}
                </div>
              </div>
              <div>
                <div
                  className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em]"
                  style={{ color: MUTED }}
                >
                  Missing Keywords
                </div>
                <div className="flex flex-wrap gap-2">
                  {d.keywordsMissing.map((k) => (
                    <Tag key={k} text={k} kind="missing" />
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Interview Score Breakdown */}
        <section className="mb-10">
          <SectionTitle
            kicker="Panel Evaluation"
            title="Interview Score Breakdown"
            hint="Per-competency assessment"
          />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {d.competencies.map((c, i) => (
              <CompetencyCard key={c.name} {...c} delay={i * 60} />
            ))}
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
            <div
              className="rounded-xl p-5"
              style={{
                backgroundColor: "rgba(24,95,165,0.08)",
                border: `1px solid rgba(24,95,165,0.22)`,
              }}
            >
              <div
                className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.18em]"
                style={{ color: BLUE }}
              >
                <Sparkles className="h-3 w-3" />
                Standout Moment
              </div>
              <blockquote
                className="mt-2 text-sm italic leading-relaxed"
                style={{ color: TEXT, borderLeft: `3px solid ${BLUE}`, paddingLeft: "0.75rem" }}
              >
                &ldquo;{d.standout}&rdquo;
              </blockquote>
            </div>
            <div
              className="rounded-xl p-5"
              style={{
                backgroundColor: "rgba(186,117,23,0.10)",
                border: `1px solid rgba(186,117,23,0.28)`,
              }}
            >
              <div
                className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.18em]"
                style={{ color: AMBER }}
              >
                <AlertTriangle className="h-3 w-3" />
                Identified Skill Gap
              </div>
              <p className="mt-2 text-sm leading-relaxed" style={{ color: TEXT }}>
                {d.skillGap}
              </p>
            </div>
          </div>
        </section>

        {/* Per-Question Scores */}
        <section className="mb-10">
          <SectionTitle
            kicker="Transcript"
            title="Per-Question Scores & Comments"
            hint="Editable interviewer notes"
          />
          <div className="rounded-xl p-6" style={{ backgroundColor: CARD, border: `1px solid ${BORDER}` }}>
            {d.questions.map((q, i) => (
              <QuestionBlock
                key={q.id}
                index={i}
                q={q.q}
                score={q.score}
                comment={comments[q.id] ?? ""}
                onChange={(v) => setComments((prev) => ({ ...prev, [q.id]: v }))}
                delay={120 + i * 70}
              />
            ))}
          </div>
        </section>

        {/* Recommendation */}
        <section className="mb-6">
          <SectionTitle kicker="Verdict" title="Recommendation" />
          <RecommendationBanner
            verdict={d.recommendation.verdict}
            points={d.recommendation.points}
          />
        </section>

        {/* Decision actions */}
        <footer
          className="mt-12 mb-10 flex flex-col items-center justify-center gap-2 border-t pt-8 text-[11px]"
          style={{ color: MUTED, borderColor: BORDER }}
        >
          <img
            src="/brand/logo-black.svg"
            alt="Voxbulk"
            style={{ height: 24, marginBottom: 4 }}
          />
          <div className="flex flex-wrap items-center justify-center gap-2">
            <span>
              © {new Date().getFullYear()} Voxbulk · Confidential — for authorized reviewers only.
            </span>
            <span aria-hidden>·</span>
            <span>Job Task {d.meta.jobTaskId} · Generated {d.meta.issued}</span>
          </div>
        </footer>
      </div>
    </main>
  );
}