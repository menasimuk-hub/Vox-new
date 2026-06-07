/** Structured console logs for survey launch / save / redirect debugging. */

export type LaunchFlowLogContext = {
  component: string;
  survey_name?: string;
  title?: string;
  draftId?: string | null;
  orderId?: string | null;
  launchOrderId?: string | null;
  selectedCampaignId?: string | null;
  pathname?: string;
  search?: string;
  source?: string;
  extra?: Record<string, unknown>;
};

function snapshot(ctx: LaunchFlowLogContext) {
  return {
    survey_name: ctx.survey_name ?? "",
    title: ctx.title ?? "",
    draftId: ctx.draftId ?? null,
    orderId: ctx.orderId ?? null,
    launchOrderId: ctx.launchOrderId ?? null,
    selectedCampaignId: ctx.selectedCampaignId ?? null,
    pathname: ctx.pathname ?? (typeof window !== "undefined" ? window.location.pathname : ""),
    search: ctx.search ?? (typeof window !== "undefined" ? window.location.search : ""),
    component: ctx.component,
    source: ctx.source ?? ctx.component,
    ...ctx.extra,
  };
}

export function logLaunchFlow(tag: string, ctx: LaunchFlowLogContext) {
  console.info(`[${tag}]`, snapshot(ctx));
}
