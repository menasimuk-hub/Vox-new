export type CampaignType = "interview" | "survey" | "recovery" | "followup";
export type CampaignTone =
  | "live"
  | "scheduled"
  | "finished"
  | "archived"
  | "quoted"
  | "awaiting-payment"
  | "payment-failed"
  | "paused";

export type Campaign = {
  id: string;
  name: string;
  type: CampaignType;
  status: CampaignTone;
  responses: number;
  target: number;
  completion: number;
  updatedAt: string;
};
