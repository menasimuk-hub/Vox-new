import type { FeedbackSubscription } from "@/lib/queries";

export function isMultiLocationFeedbackPlan(sub?: FeedbackSubscription | null): boolean {
  return Boolean(sub?.active && (sub.max_locations ?? 0) > 1);
}

export function canDuplicateFeedbackSurvey(
  sub?: FeedbackSubscription | null,
  locationCount = 0,
): boolean {
  const max = sub?.max_locations ?? 0;
  return Boolean(sub?.active && max > 1 && locationCount < max);
}
