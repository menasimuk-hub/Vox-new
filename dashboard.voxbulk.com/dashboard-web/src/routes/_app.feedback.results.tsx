import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";
import { QrCode } from "lucide-react";
import { toast } from "sonner";

import { mapFeedbackResults } from "@/components/feedback-results/feedback-results-mappers";
import { FeedbackSurveyResults } from "@/components/feedback-results/feedback-survey-results";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { downloadAuthenticatedFile } from "@/lib/api";
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

  const mapped = React.useMemo(
    () => (resultsQ.data ? mapFeedbackResults(resultsQ.data, insightsQ.data) : null),
    [resultsQ.data, insightsQ.data],
  );

  async function handleExport(kind: "csv" | "pdf") {
    const params = new URLSearchParams();
    if (locationId !== "all") params.set("location_id", locationId);
    if (surveyTypeId !== "all") params.set("survey_type_id", surveyTypeId);
    const qs = params.toString();
    const path = `/customer-feedback/results/export.${kind}${qs ? `?${qs}` : ""}`;
    try {
      await downloadAuthenticatedFile(path, `feedback-results.${kind}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    }
  }

  if (resultsQ.isLoading) {
    return (
      <div className="flex w-full flex-col gap-6">
        <Skeleton className="h-24 rounded-xl" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-96 rounded-xl" />
      </div>
    );
  }

  if (resultsQ.isError || !resultsQ.data || !mapped) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          {resultsQ.error instanceof Error ? resultsQ.error.message : "Unable to load feedback results."}
        </CardContent>
      </Card>
    );
  }

  const locations = resultsQ.data.locations.map((l) => ({ id: l.id, name: l.name }));

  return (
    <FeedbackSurveyResults
      data={mapped}
      locationId={locationId}
      locations={locations}
      onLocationChange={setLocationId}
      onExportPdf={() => void handleExport("pdf")}
      onExportCsv={() => void handleExport("csv")}
      insightsLoading={insightsQ.isLoading}
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
