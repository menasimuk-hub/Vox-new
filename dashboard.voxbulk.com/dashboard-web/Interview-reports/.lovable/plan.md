# Candidate Interview Report Page

Create a new route `/report` that renders a complete Candidate Interview Report using the exact color palette provided. All content will use realistic mock data so the page is fully populated and shareable.

## Route

- New file: `src/routes/report.tsx` using `createFileRoute("/report")`
- `head()` with title "Candidate Interview Report" + description for SEO
- Single `<h1>` for the page; semantic `<section>` per block

## Design tokens

Extend `src/styles.css` with the exact palette as CSS variables (oklch equivalents) so Tailwind utilities (`bg-background`, `bg-card`, `border-border`, `text-foreground`, `text-muted-foreground`, plus accents `text-accent-blue`, `bg-accent-green`, etc.) map to:

- background `#faf9f6`
- card `#f1efe8`
- border `rgba(26,26,24,0.12)`
- foreground `#1a1a18`, muted `#888780`
- accent-blue `#185fa5`, accent-green `#1d9e75`, accent-amber `#ba7517`, accent-red `#a32d2d`, accent-purple `#3c3489`

A `@media print` block hides the action bar and forces white background / black text for clean printing.

## Page layout (top → bottom)

1. **Header bar**: candidate name + role on the left; "Print" and "Download PDF" buttons on the right. Both hidden when printing.
2. **Score Summary** — 4 cards in a responsive grid (1/2/4 cols). Each card: label, big numeric score, thin colored top border using the accent (blue / green / amber / purple).
3. **ATS Breakdown** — card containing:
   - List of criteria rows (`name + sub-label`, progress bar, % value). Bar color from `getBarColor(pct)`: green ≥80, blue 60–79, amber <60.
   - Two tag groups below: Keywords Found (green), Missing Keywords (red), with partial matches in amber.
4. **Interview Score Breakdown** — grid (1/2/3 cols) of competency cards: name + category, score badge `9/10`, progress bar, AI notes paragraph. Below the grid:
   - Standout Moment block — blue tinted background, quote styling.
   - Identified Skill Gap block — amber tinted background.
5. **Per-Question Scores** — list rows: question text, progress bar, `8/10` score.
6. **Recommendation Banner** — full-width banner, background color from verdict (`Proceed`=green, `Hold`=amber, `Reject`=red). Bulleted list using `+` strengths, `−` risks, `→` neutral observations.

## Components (small, file-local)

Kept inside `report.tsx` for simplicity:

- `ScoreCard({ label, score, accent })`
- `ProgressBar({ value, color })` — pure div with inline width %, color from variant
- `CriteriaRow`, `KeywordTag`
- `CompetencyCard`
- `QuestionScoreRow`
- `RecommendationBanner({ verdict, points })`

Helper: `getBarColor(pct: number)` returns one of `accent-green | accent-blue | accent-amber`.

## Print & Download

- **Print** button calls `window.print()`.
- **Download PDF** button also calls `window.print()` (browser print dialog allows "Save as PDF") — no extra dependencies, works in the Worker runtime. The plan notes this clearly so the user knows we're using the browser's built-in PDF export rather than adding a heavy client-side PDF library.

## Mock data

A single `reportData` object at the top of the file (candidate, scores, criteria, keywords, competencies, questions, recommendation) so the page renders fully without backend wiring.

## Out of scope

- No backend, no auth, no data fetching, no nav link added elsewhere (page is reachable at `/report`).
- No new npm dependencies.
