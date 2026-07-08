import * as React from "react";
import { useCurrency } from "@/components/CurrencyContext";
import { apiFetch } from "@/lib/api";

export type PublicPlan = {
  code: string;
  name: string;
  description?: string | null;
  features?: string[];
  price_display: string;
  monthly_price_minor?: number | null;
  monthly_price_display?: string | null;
  yearly_price_minor?: number | null;
  yearly_price_display?: string | null;
  per_min_display: string;
  per_min_minor?: number;
  minutes_included: number;
  whatsapp_included: number;
  cv_scans_included: number;
  is_featured?: boolean;
  is_enterprise?: boolean;
  is_payg?: boolean;
  typical_call_low_display?: string;
  typical_call_high_display?: string;
};

export type PublicFeedbackPlan = {
  code: string;
  name: string;
  description?: string | null;
  features: string[];
  is_featured?: boolean;
  wa_units_included?: number;
  web_units_included?: number;
  max_locations?: number;
  monthly_price_minor?: number | null;
  yearly_price_minor?: number | null;
  monthly_price_display?: string | null;
  yearly_price_display?: string | null;
  market_zone?: string;
};

export type PublicFeedbackPricing = {
  currency: string;
  market_zone: string;
  plans: PublicFeedbackPlan[];
};

export type PublicPricing = {
  market: string;
  currency_symbol: string;
  plans: PublicPlan[];
  services: {
    interview_per_min_display?: string;
    whatsapp_survey_display?: string;
    ats_cv_scan_display?: string;
    connection_fee_display?: string;
  };
  estimator_defaults?: { duration_min?: number; interview_count?: number };
};

export function usePublicPricing() {
  const { currency } = useCurrency();
  const [data, setData] = React.useState<PublicPricing | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void apiFetch<PublicPricing>(`/billing/pricing/public?market=${encodeURIComponent(currency)}`)
      .then((payload) => {
        if (!cancelled) setData(payload);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message || "Could not load pricing");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [currency]);

  return { data, loading, error };
}

export function usePublicFeedbackPricing() {
  const { currency } = useCurrency();
  const [data, setData] = React.useState<PublicFeedbackPricing | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void apiFetch<PublicFeedbackPricing>(
      `/billing/feedback-pricing/public?market=${encodeURIComponent(currency)}`,
    )
      .then((payload) => {
        if (!cancelled) setData(payload);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message || "Could not load feedback pricing");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [currency]);

  return { data, loading, error };
}
