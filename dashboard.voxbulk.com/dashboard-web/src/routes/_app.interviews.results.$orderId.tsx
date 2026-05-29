import { createFileRoute } from "@tanstack/react-router";

import { InterviewCampaignResultsPage } from "@/components/interview-campaign-results-page";

export const Route = createFileRoute("/_app/interviews/results/$orderId")({
  head: () => ({ meta: [{ title: "Campaign results — VoxBulk" }] }),
  component: CampaignResultsRoute,
});

function CampaignResultsRoute() {
  const { orderId } = Route.useParams();
  return <InterviewCampaignResultsPage orderId={orderId} />;
}
