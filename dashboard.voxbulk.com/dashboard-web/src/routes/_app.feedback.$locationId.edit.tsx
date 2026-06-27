import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, Check, MessageSquarePlus, Sparkles } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  useFeedbackLocations,
  useFeedbackMarketingSubscriberCount,
  useFeedbackSurveyTypes,
  useUpdateFeedbackLocation,
} from "@/lib/queries";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/feedback/$locationId/edit")({
  head: () => ({ meta: [{ title: "Edit QR survey — VoxBulk" }] }),
  component: EditFeedbackSurvey,
});

function EditFeedbackSurvey() {
  const { locationId } = Route.useParams();
  const navigate = useNavigate();
  const locationsQ = useFeedbackLocations();
  const updateM = useUpdateFeedbackLocation();

  const location = (locationsQ.data || []).find((l) => l.id === locationId);

  const [selectedTypeIds, setSelectedTypeIds] = React.useState<string[]>([]);
  const [openQuestion, setOpenQuestion] = React.useState(true);
  const [marketingOptIn, setMarketingOptIn] = React.useState(false);
  const marketingCountQ = useFeedbackMarketingSubscriberCount();
  const initialized = React.useRef(false);

  React.useEffect(() => {
    if (!location || initialized.current) return;
    initialized.current = true;
    setSelectedTypeIds(
      location.selected_survey_type_ids?.length
        ? location.selected_survey_type_ids
        : [location.survey_type_id],
    );
    setOpenQuestion(location.open_question_enabled !== false);
    setMarketingOptIn(Boolean(location.marketing_opt_in_enabled));
  }, [location]);

  const typesQ = useFeedbackSurveyTypes(location?.industry_id || "");
  const surveyTypes = typesQ.data || [];

  React.useEffect(() => {
    if (!location?.industry_id || !typesQ.isFetched) return;
    const validTypeIds = new Set(surveyTypes.map((row) => String(row.id)));
    setSelectedTypeIds((prev) => {
      const next = prev.filter((id) => validTypeIds.has(id));
      if (next.length === prev.length && next.every((id, idx) => id === prev[idx])) return prev;
      return next;
    });
  }, [location?.industry_id, typesQ.isFetched, surveyTypes]);

  const onSave = async () => {
    if (!location || selectedTypeIds.length === 0) {
      toast.error("Select at least one survey topic.");
      return;
    }
    try {
      await updateM.mutateAsync({
        locationId: location.id,
        body: {
          selected_survey_type_ids: selectedTypeIds,
          open_question_enabled: openQuestion,
          marketing_opt_in_enabled: marketingOptIn,
        },
      });
      toast.success("Survey updated. Your existing QR code still works.");
      void navigate({ to: "/feedback" });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not update survey");
    }
  };

  if (locationsQ.isLoading) {
    return (
      <div className="flex w-full flex-col gap-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full rounded-xl" />
      </div>
    );
  }

  if (locationsQ.isError || !location) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-sm text-destructive">
          Survey not found.
          <div className="mt-4">
            <Button asChild variant="outline">
              <Link to="/feedback">Back to saved surveys</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="flex w-full max-w-2xl flex-col gap-6">
      <PageHeader
        eyebrow="Customer feedback"
        title={`Edit survey — ${location.name}`}
        description="Change topics and closing questions. Your printed QR code and trigger message stay the same."
        actions={
          <Button asChild variant="outline" className="gap-1.5">
            <Link to="/feedback">
              <ArrowLeft className="size-4" /> Back
            </Link>
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Survey topics</CardTitle>
          <CardDescription>
            Industry: {location.industry_name || "—"}. Choose up to 6 topics visitors answer on WhatsApp.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {typesQ.isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : typesQ.isError ? (
            <p className="text-sm text-destructive">Could not load survey topics.</p>
          ) : (
            <>
              <p className="text-xs text-muted-foreground">
                Selected:{" "}
                <span
                  className={cn(
                    "font-semibold",
                    selectedTypeIds.length === 0
                      ? "text-muted-foreground"
                      : selectedTypeIds.length >= 6
                        ? "text-warning"
                        : "text-primary",
                  )}
                >
                  {selectedTypeIds.length}
                </span>{" "}
                / 6
              </p>
              <div className="flex flex-wrap gap-2">
                {surveyTypes.map((t) => {
                  const active = selectedTypeIds.includes(t.id);
                  const disabled = !active && selectedTypeIds.length >= 6;
                  return (
                    <button
                      key={t.id}
                      type="button"
                      disabled={disabled}
                      onClick={() => {
                        setSelectedTypeIds((prev) =>
                          prev.includes(t.id) ? prev.filter((x) => x !== t.id) : [...prev, t.id],
                        );
                      }}
                      className={cn(
                        "rounded-full border px-3.5 py-1.5 text-sm transition-all",
                        active && "border-primary bg-primary text-primary-foreground shadow",
                        !active && !disabled && "border-border bg-background hover:border-primary/40 hover:bg-primary/5",
                        disabled && "cursor-not-allowed border-border bg-muted/40 text-muted-foreground/50",
                      )}
                    >
                      {active ? <Check className="mr-1 inline size-3.5" /> : null} {t.name}
                    </button>
                  );
                })}
              </div>
            </>
          )}

          <div
            className={cn(
              "flex items-start gap-3 rounded-xl border p-4 transition",
              marketingOptIn ? "border-primary/40 bg-primary/5" : "border-border bg-background/40",
            )}
          >
            <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/20">
              <Sparkles className="size-4" />
            </div>
            <div className="flex-1">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold">
                  Promo opt-in after survey{" "}
                  <span className="text-xs font-normal text-muted-foreground">(optional)</span>
                </p>
                <Switch checked={marketingOptIn} onCheckedChange={setMarketingOptIn} />
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                Ask customers on WhatsApp if they want occasional offers. Replying STOP unsubscribes them from the VoxBulk feedback number (handled by WhatsApp/Telnyx) and removes them from your promo list.
              </p>
              {marketingOptIn ? (
                <p className="mt-2 text-xs font-medium text-primary">
                  Current promo subscribers: {marketingCountQ.isLoading ? "…" : marketingCountQ.data ?? 0}
                </p>
              ) : null}
            </div>
          </div>

          <div
            className={cn(
              "flex items-start gap-3 rounded-xl border p-4 transition",
              openQuestion ? "border-primary/40 bg-primary/5" : "border-border bg-background/40",
            )}
          >
            <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/20">
              <MessageSquarePlus className="size-4" />
            </div>
            <div className="flex-1">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold">
                  Tell us more about your experience{" "}
                  <span className="text-xs font-normal text-muted-foreground">(optional)</span>
                </p>
                <Switch checked={openQuestion} onCheckedChange={setOpenQuestion} />
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                Adds a final open question. Responses appear in feedback results under more details.
              </p>
            </div>
          </div>

          <p className="text-xs text-muted-foreground">
            To change question wording (not which topics are asked), contact your VoxBulk admin — template text is
            managed centrally and must be approved on WhatsApp.
          </p>

          <div className="flex flex-wrap gap-2 pt-2">
            <Button onClick={onSave} disabled={updateM.isPending || selectedTypeIds.length === 0}>
              {updateM.isPending ? "Saving…" : "Save changes"}
            </Button>
            <Button asChild variant="outline">
              <Link to="/feedback">Cancel</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
