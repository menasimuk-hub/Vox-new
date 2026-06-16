import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";
import { QrCode } from "lucide-react";

import { FeedbackResultsView } from "@/components/feedback-results/feedback-results-view";
import { Button } from "@/components/ui/button";
import { useFeedbackResults, useFeedbackResultsInsights } from "@/lib/queries";

export const Route = createFileRoute("/_app/feedback/results")({
  head: () => ({ meta: [{ title: "Feedback results — VoxBulk" }] }),
  validateSearch: (search: Record<string, unknown>) => ({
    location_id: typeof search.location_id === "string" ? search.location_id : undefined,
    survey_type_id: typeof search.survey_type_id === "string" ? search.survey_type_id : undefined,
  }),
  component: FeedbackResults,
});

function FeedbackResults() {
  const { location_id: initialLocationId, survey_type_id: initialSurveyTypeId } = Route.useSearch();
  const [locationId, setLocationId] = React.useState(initialLocationId || "all");
  const [surveyTypeId, setSurveyTypeId] = React.useState(initialSurveyTypeId || "all");

  React.useEffect(() => {
    if (initialLocationId) setLocationId(initialLocationId);
  }, [initialLocationId]);

  React.useEffect(() => {
    if (initialSurveyTypeId) setSurveyTypeId(initialSurveyTypeId);
  }, [initialSurveyTypeId]);

  const filters = {
    ...(locationId !== "all" ? { location_id: locationId } : {}),
    ...(surveyTypeId !== "all" ? { survey_type_id: surveyTypeId } : {}),
  };

  const resultsQ = useFeedbackResults(filters);
  const insightsQ = useFeedbackResultsInsights(filters);

  return (
    <FeedbackResultsView
      data={resultsQ.data}
      insights={insightsQ.data}
      isLoading={resultsQ.isLoading}
      insightsLoading={insightsQ.isLoading}
      isError={resultsQ.isError}
      error={resultsQ.error instanceof Error ? resultsQ.error : null}
      locationId={locationId}
      surveyTypeId={surveyTypeId}
      onLocationChange={setLocationId}
      onSurveyTypeChange={setSurveyTypeId}
      headerActions={
        <Button asChild variant="outline" size="sm" className="gap-1.5">
          <Link to="/feedback">
            <QrCode className="size-4" /> Saved QR surveys
          </Link>
        </Button>
      }
    />
  );
}
