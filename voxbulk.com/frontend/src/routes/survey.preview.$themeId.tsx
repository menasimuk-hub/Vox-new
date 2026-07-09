import { createFileRoute } from "@tanstack/react-router";
import { PublicFeedbackSurvey } from "@/components/feedback-survey/PublicFeedbackSurvey";

export const Route = createFileRoute("/survey/preview/$themeId")({
  head: () => ({
    meta: [{ title: "Theme preview — Customer feedback" }],
  }),
  component: ThemePreviewRoute,
});

function ThemePreviewRoute() {
  const { themeId } = Route.useParams();
  const company =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("company") || "Preview business"
      : "Preview business";
  return <PublicFeedbackSurvey token="__preview__" previewThemeId={themeId} previewCompanyName={company} />;
}
