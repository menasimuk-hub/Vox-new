/** Browser-owned coach tour. The voice agent narrates; it does not pick the next page. */

export type DemoTourIntent = "view" | "click";

export type DemoTourBeat = {
  id: string;
  target: string;
  intent: DemoTourIntent;
  route: string;
  label: string;
  talk: string;
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
    talk: "These live KPIs update as customers reply — scores, volume, and alerts in one strip.",
    showNext: true,
  },
  {
    id: "home_second_row",
    target: "home-second-row",
    intent: "view",
    route: "/",
    label: "Customer sentiment",
    talk: "Sentiment and recent feedback sit under the KPIs so you can scan recent comments without leaving home.",
    showNext: true,
  },
  {
    id: "nav_feedback_results",
    target: "nav-feedback-results",
    intent: "click",
    route: "/",
    label: "Customer Feedback results",
    talk: "Click Customer Feedback in the sidebar to open live results.",
    showNext: false,
  },
  {
    id: "results_tab_overview",
    target: "results-tab-overview",
    intent: "click",
    route: "/feedback/results",
    label: "Overview",
    talk: "Overview is the score snapshot. Tap the Overview tab.",
    showNext: false,
  },
  {
    id: "results_tab_questions",
    target: "results-tab-questions",
    intent: "click",
    route: "/feedback/results",
    label: "Questions",
    talk: "Questions shows how each survey item scored. Tap Questions.",
    showNext: false,
  },
  {
    id: "results_tab_responses",
    target: "results-tab-responses",
    intent: "click",
    route: "/feedback/results",
    label: "Responses",
    talk: "Responses is the live inbox of every reply. Tap Responses.",
    showNext: false,
  },
  {
    id: "results_tab_details",
    target: "results-tab-details",
    intent: "click",
    route: "/feedback/results",
    label: "Details",
    talk: "Details is the per-response record. Tap Details.",
    showNext: false,
  },
  {
    id: "nav_feedback_compare",
    target: "nav-feedback-compare",
    intent: "click",
    route: "/feedback/results",
    label: "Compare branches",
    talk: "Click Compare in the sidebar to see branches side by side.",
    showNext: false,
  },
  {
    id: "feedback_compare_title",
    target: "feedback-compare-title",
    intent: "view",
    route: "/feedback/compare",
    label: "Compare",
    talk: "Compare puts locations next to each other so you can spot which branch is slipping.",
    showNext: true,
  },
  {
    id: "nav_feedback_new",
    target: "nav-feedback-new",
    intent: "click",
    route: "/feedback/compare",
    label: "Create QR",
    talk: "Click Create QR in the sidebar to open the survey wizard.",
    showNext: false,
  },
  {
    id: "wizard_industry",
    target: "wizard-industry",
    intent: "view",
    route: "/feedback/new",
    label: "Choose industry",
    talk: "Take a look at the industry step. I will stay quiet so you can read. Then tap Next on the form.",
    showNext: false,
  },
  {
    id: "wizard_next_industry",
    target: "wizard-next",
    intent: "click",
    route: "/feedback/new",
    label: "Wizard Next",
    talk: "Tap Next on the form when you have had a look.",
    showNext: false,
  },
  {
    id: "wizard_topics",
    target: "wizard-topics",
    intent: "view",
    route: "/feedback/new",
    label: "Choose topics",
    talk: "Have a look at the topics. I will stay quiet. Then tap Next on the form.",
    showNext: false,
  },
  {
    id: "wizard_next_topics",
    target: "wizard-next",
    intent: "click",
    route: "/feedback/new",
    label: "Wizard Next",
    talk: "Tap Next on the form when you are ready.",
    showNext: false,
  },
  {
    id: "wizard_look",
    target: "wizard-look",
    intent: "view",
    route: "/feedback/new",
    label: "Look and feel",
    talk: "Have a look at the design step. I will stay quiet. Then tap Next on the form.",
    showNext: false,
  },
  {
    id: "wizard_next_look",
    target: "wizard-next",
    intent: "click",
    route: "/feedback/new",
    label: "Wizard Next",
    talk: "Tap Next on the form when you are ready.",
    showNext: false,
  },
  {
    id: "wizard_branches",
    target: "wizard-branches",
    intent: "view",
    route: "/feedback/new",
    label: "Branches",
    talk: "Have a look at branches. I will stay quiet. Then tap Next on the form.",
    showNext: false,
  },
  {
    id: "wizard_next_branches",
    target: "wizard-next",
    intent: "click",
    route: "/feedback/new",
    label: "Wizard Next",
    talk: "Tap Next on the form when you are ready.",
    showNext: false,
  },
  {
    id: "wizard_followup",
    target: "wizard-followup",
    intent: "view",
    route: "/feedback/new",
    label: "Follow-up",
    talk: "Have a look at follow-up. I will stay quiet. Then tap Next on the form.",
    showNext: false,
  },
  {
    id: "wizard_next_followup",
    target: "wizard-next",
    intent: "click",
    route: "/feedback/new",
    label: "Wizard Next",
    talk: "Tap Next on the form when you are ready.",
    showNext: false,
  },
  {
    id: "wizard_launch",
    target: "wizard-launch",
    intent: "view",
    route: "/feedback/new",
    label: "Launch",
    talk: "This is launch — QR, print, and share. Have a look. When you are done we can wrap up or talk pricing.",
    showNext: true,
  },
];

export function demoTourBeatAt(index: number): DemoTourBeat | null {
  if (index < 0 || index >= DEMO_TOUR_BEATS.length) return null;
  return DEMO_TOUR_BEATS[index] ?? null;
}

export function demoTourLockMessage(beat: DemoTourBeat): string {
  const wait =
    beat.intent === "view" && beat.showNext
      ? "Wait for them to click Next on the box."
      : beat.intent === "click"
        ? "Wait for them to tap Click here on the box."
        : "Stay quiet so they can read. Do not skip ahead.";
  return (
    `Spotlight is now "${beat.label}". ${beat.talk} ` +
    `Speak only about this. ${wait} Do not change the screen.`
  );
}

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
