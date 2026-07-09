import { createFileRoute } from "@tanstack/react-router";
import { PublicFeedbackSurvey } from "@/components/feedback-survey/PublicFeedbackSurvey";

export const Route = createFileRoute("/survey/$token")({
  head: () => ({
    meta: [
      { title: "Quick survey — Your feedback" },
      { name: "description", content: "A 60-second survey. Tap or talk." },
    ],
  }),
  component: SurveyRoute,
});

function SurveyRoute() {
  const { token } = Route.useParams();
  return <PublicFeedbackSurvey token={token} />;
}
