import type { ComponentType } from "react";

export type Theme = {
  bgClass: string;
  ink: string;
  sub: string;
  card: string;
  border: string;
  accent: string;
  accent2: string;
  cool: string;
  gradientButton: string;
  gradientProgress: string;
  selectedShadow: string;
  ringA: string;
  ringB: string;
};

export type Copy = {
  companyName: string;
  serviceLabel: string;
  metaTitle: string;
  metaDescription: string;
  thankYouTitle: string;
  thankYouSubtitle: string;
};

export type ThemePack = {
  id: string;
  theme: Theme;
  Art: ComponentType;
  copyDefaults: Omit<Copy, "companyName">;
};

export type WebThemeConfig = {
  base_template_id?: string;
  overlay_ids?: string[];
  overlay_mode?: "auto" | "fixed";
  custom_event_label?: string;
};

export type SurveyQuestion = {
  kind: string;
  title: string;
  body: string;
  input: "choice" | "text";
  options: { label: string; value: string }[];
  allow_voice?: boolean;
  is_rating?: boolean;
  low_values?: string[];
  reason_options?: string[];
  reason_prompt?: string;
};

export type SurveyPayload = {
  company_name: string;
  branch_name?: string;
  industry_name?: string;
  industry_slug?: string;
  industry_slug?: string;
  wa_url?: string;
  logo_url?: string;
  step_count: number;
  questions: SurveyQuestion[];
  theme_id?: string;
  web_theme?: WebThemeConfig;
};
