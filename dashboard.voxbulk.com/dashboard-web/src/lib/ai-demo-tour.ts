/** Browser moves the spotlight; Leo sells and waits for spoken "done". */

export type DemoTourIntent = "view" | "click";

export type DemoTourBeat = {
  id: string;
  target: string;
  intent: DemoTourIntent;
  route: string;
  label: string;
  /** Sales pitch Leo should deliver for this spotlight. */
  talk: string;
  /** What Leo asks them to do next + say when done. */
  ask: string;
  /** VIEW chip Next. Wizard read cards are outline-only (false). */
  showNext: boolean;
};

export const DEMO_TOUR_BEATS: DemoTourBeat[] = [
  {
    id: "home_kpis",
    target: "home-live-kpis",
    intent: "view",
    route: "/",
    label: "Live KPIs",
    talk: "This strip is your early-warning board — live scores, volume, and alerts as customers reply. Owners who watch this catch a bad day before it becomes a public review.",
    ask: "When you are ready for the next area, tap Next on the white box and tell me you are done.",
    showNext: true,
  },
  {
    id: "home_second_row",
    target: "home-second-row",
    intent: "view",
    route: "/",
    label: "Customer sentiment",
    talk: "Under the KPIs you get sentiment and recent comments without leaving home. That is how managers spot a tone shift in minutes instead of waiting for a weekly report.",
    ask: "Tap Next on the box and say done when you have had a look.",
    showNext: true,
  },
  {
    id: "nav_feedback_results",
    target: "nav-feedback-results",
    intent: "click",
    route: "/",
    label: "Customer Feedback results",
    talk: "Customer Feedback turns table QR scans into WhatsApp replies you can act on. Open results so you see the live scoreboard for your locations.",
    ask: "Please click Customer Feedback in the sidebar — the highlighted menu — and tell me when you have opened it.",
    showNext: false,
  },
  {
    id: "results_tab_overview",
    target: "results-tab-overview",
    intent: "click",
    route: "/feedback/results",
    label: "Overview",
    talk: "Overview is the score snapshot — one place to see how you are doing overall. Use it in morning stand-ups so the team knows if yesterday slipped.",
    ask: "Tap Overview on the highlighted tab, then tell me when you are done.",
    showNext: false,
  },
  {
    id: "results_tab_questions",
    target: "results-tab-questions",
    intent: "click",
    route: "/feedback/results",
    label: "Questions",
    talk: "Questions shows which survey items drag the score down — food, service, wait time, and so on. That is how you fix the real problem instead of guessing.",
    ask: "Open the Questions tab and say done when it is open.",
    showNext: false,
  },
  {
    id: "results_tab_responses",
    target: "results-tab-responses",
    intent: "click",
    route: "/feedback/results",
    label: "Responses",
    talk: "Responses is the live inbox — every reply as it lands. Your team can jump on a unhappy guest while they are still on site.",
    ask: "Open Responses and tell me when you can see it.",
    showNext: false,
  },
  {
    id: "results_tab_details",
    target: "results-tab-details",
    intent: "click",
    route: "/feedback/results",
    label: "Details",
    talk: "Details is the per-response record — who said what, when, and where. Perfect when a manager needs the full story before calling the customer back.",
    ask: "Open Details and say done when you are there.",
    showNext: false,
  },
  {
    id: "nav_feedback_compare",
    target: "nav-feedback-compare",
    intent: "click",
    route: "/feedback/results",
    label: "Compare locations",
    talk: "Compare is where multi-site owners win — locations side by side so you see who is slipping. Without this, head office only hears the loudest branch.",
    ask: "Please click Compare in the sidebar — I have highlighted it — and tell me when you have opened it.",
    showNext: false,
  },
  {
    id: "feedback_compare_title",
    target: "feedback-compare-title",
    intent: "view",
    route: "/feedback/compare",
    label: "Compare",
    talk: "Here you compare branches next to each other. If Leeds dips while Manchester holds, you coach Leeds this week — that is why operators buy this.",
    ask: "Have a look, then tap Next on the box and say done.",
    showNext: true,
  },
  {
    id: "nav_feedback_new",
    target: "nav-feedback-new",
    intent: "click",
    route: "/feedback/compare",
    label: "Create QR",
    talk: "Create QR launches a survey in minutes — industry templates, your branding, print-ready codes. No agency, no waiting weeks for a form.",
    ask: "Click Create QR in the sidebar and tell me when the wizard is open.",
    showNext: false,
  },
  {
    id: "wizard_industry",
    target: "wizard-industry",
    intent: "view",
    route: "/feedback/new",
    label: "Choose industry",
    talk: "Pick your industry so the questions already match how your customers talk. That is why response rates stay high: the survey feels relevant from day one.",
    ask: "Glance at the industries, then tap Next on the form and say done.",
    showNext: false,
  },
  {
    id: "wizard_next_industry",
    target: "wizard-next",
    intent: "click",
    route: "/feedback/new",
    label: "Wizard Next",
    talk: "Move forward when you have picked an industry — the next steps build the survey for you.",
    ask: "Tap Next on the form and tell me when you have moved on.",
    showNext: false,
  },
  {
    id: "wizard_topics",
    target: "wizard-topics",
    intent: "view",
    route: "/feedback/new",
    label: "Choose topics",
    talk: "Topics let you measure what actually drives revenue — service, product, wait time, cleanliness. You only ask what you will act on, so customers finish the chat.",
    ask: "Have a look, tap Next on the form, and say done.",
    showNext: false,
  },
  {
    id: "wizard_next_topics",
    target: "wizard-next",
    intent: "click",
    route: "/feedback/new",
    label: "Wizard Next",
    talk: "Next takes you into look and feel — your brand on the survey.",
    ask: "Tap Next and tell me when you are done.",
    showNext: false,
  },
  {
    id: "wizard_look",
    target: "wizard-look",
    intent: "view",
    route: "/feedback/new",
    label: "Look and feel",
    talk: "Design makes it yours — colours and style so the QR experience matches the brand on the wall. Guests trust a survey that looks like your business.",
    ask: "Have a look, tap Next on the form, and say done.",
    showNext: false,
  },
  {
    id: "wizard_next_look",
    target: "wizard-next",
    intent: "click",
    route: "/feedback/new",
    label: "Wizard Next",
    talk: "Next is branches — where each QR belongs.",
    ask: "Tap Next and tell me when you have moved on.",
    showNext: false,
  },
  {
    id: "wizard_branches",
    target: "wizard-branches",
    intent: "view",
    route: "/feedback/new",
    label: "Branches",
    talk: "Branches tie every scan to a location. That is the difference between 'someone is unhappy' and 'the Leeds lunch shift needs coaching'.",
    ask: "Have a look, tap Next on the form, and say done.",
    showNext: false,
  },
  {
    id: "wizard_next_branches",
    target: "wizard-next",
    intent: "click",
    route: "/feedback/new",
    label: "Wizard Next",
    talk: "Next is follow-up — how you close the loop after a low score.",
    ask: "Tap Next and tell me when you are there.",
    showNext: false,
  },
  {
    id: "wizard_followup",
    target: "wizard-followup",
    intent: "view",
    route: "/feedback/new",
    label: "Follow-up",
    talk: "Follow-up is the recovery engine — alert the right person and reach the customer before they post online. That often pays for the whole subscription.",
    ask: "Have a look, tap Next on the form, and say done.",
    showNext: false,
  },
  {
    id: "wizard_next_followup",
    target: "wizard-next",
    intent: "click",
    route: "/feedback/new",
    label: "Wizard Next",
    talk: "Last step is launch — QR, print, and share.",
    ask: "Tap Next and tell me when launch is open.",
    showNext: false,
  },
  {
    id: "wizard_launch",
    target: "wizard-launch",
    intent: "view",
    route: "/feedback/new",
    label: "Launch",
    talk: "Launch is print, share, and go live — QR on the table tonight if you want. When you are ready we can talk pricing, or wrap and sales will send the best offer.",
    ask: "Have a look. When you are finished say done, or ask me about pricing. If you want to leave, just say goodbye.",
    showNext: true,
  },
];

export function demoTourBeatAt(index: number): DemoTourBeat | null {
  if (index < 0 || index >= DEMO_TOUR_BEATS.length) return null;
  return DEMO_TOUR_BEATS[index] ?? null;
}

export function demoTourLockMessage(beat: DemoTourBeat): string {
  return (
    `Spotlight is "${beat.label}" NOW. ${beat.talk} ` +
    `Sell this like an expert: what it is, why it matters, one benefit. Then: ${beat.ask} ` +
    "STOP and wait for spoken confirmation (done / clicked / open / got it / next). Do not hang up."
  );
}

export function demoTourStartMessage(beat: DemoTourBeat): string {
  return (
    `Tour spotlight ready: "${beat.label}". ${beat.talk} ` +
    `Sell this screen now. Then: ${beat.ask} ` +
    "Wait for their spoken confirmation. Do not hang up."
  );
}

/** Kept for memory sync only — Leo advances conversation on spoken "done", not silent inject. */
export function demoTourAdvanceMessage(beat: DemoTourBeat): string {
  return (
    `Visitor progressed. Spotlight is now "${beat.label}". ${beat.talk} ` +
    `Sell this screen (feature + why). Then: ${beat.ask} ` +
    "Wait for spoken confirmation. Do not hang up. Do not skip ahead."
  );
}

export const DEMO_WRAP_MESSAGE =
  "TIME IS UP. Do not hang up yet. Say a short thank you: our sales team will follow up with the best offer, and they can contact us if they need any help. Then stop talking.";

/** If they tap form Next during a wizard VIEW, skip the following wizard-next click beat. */
export function nextIndexAfterClick(currentIndex: number, clickedTarget: string): number {
  const clicked = String(clickedTarget || "").trim();
  let next = currentIndex + 1;
  if (clicked === "wizard-next") {
    const cur = demoTourBeatAt(currentIndex);
    if (cur && cur.target !== "wizard-next") {
      while (next < DEMO_TOUR_BEATS.length && DEMO_TOUR_BEATS[next]?.target !== "wizard-next") {
        next += 1;
      }
      if (next < DEMO_TOUR_BEATS.length) next += 1;
    }
  }
  return next;
}
