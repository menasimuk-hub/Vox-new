/** Platform product visibility (public catalogue) — filters nav, home, routes, pricing. */

import { useEffect, useState } from "react";
import { frontpageApiFetch } from "@/lib/api";

export type ProductVisibilityPayload = {
  enabled_keys: string[];
  enabled_routes: string[];
  disabled_routes: string[];
  enabled_faq_category_slugs: string[];
  enabled_pricing_kinds: string[];
  groups?: Array<{ key: string; enabled: boolean; always_visible?: boolean }>;
};

const EMPTY: ProductVisibilityPayload = {
  enabled_keys: ["interview", "survey", "customer_feedback", "expo", "smart_card", "campaigns", "shared"],
  enabled_routes: ["/recruitment", "/surveys", "/feedback", "/expo", "/smart-card"],
  disabled_routes: [],
  enabled_faq_category_slugs: [
    "getting-started",
    "billing",
    "recruitment",
    "whatsapp-surveys",
    "customer-feedback",
    "ai-calling",
    "integrations",
    "expo",
    "campaigns",
    "security",
    "account",
    "troubleshooting",
  ],
  enabled_pricing_kinds: ["core", "feedback", "expo", "smart_card", "campaign"],
};

let cache: ProductVisibilityPayload | null = null;
let inflight: Promise<ProductVisibilityPayload> | null = null;

export async function fetchProductVisibility(): Promise<ProductVisibilityPayload> {
  if (cache) return cache;
  if (inflight) return inflight;
  inflight = (async () => {
    try {
      const data = await frontpageApiFetch<ProductVisibilityPayload>("/frontpage/product-visibility");
      cache = {
        enabled_keys: Array.isArray(data?.enabled_keys) ? data.enabled_keys : EMPTY.enabled_keys,
        enabled_routes: Array.isArray(data?.enabled_routes) ? data.enabled_routes : EMPTY.enabled_routes,
        disabled_routes: Array.isArray(data?.disabled_routes) ? data.disabled_routes : [],
        enabled_faq_category_slugs: Array.isArray(data?.enabled_faq_category_slugs)
          ? data.enabled_faq_category_slugs
          : EMPTY.enabled_faq_category_slugs,
        enabled_pricing_kinds: Array.isArray(data?.enabled_pricing_kinds)
          ? data.enabled_pricing_kinds
          : EMPTY.enabled_pricing_kinds,
        groups: data?.groups,
      };
      return cache;
    } catch {
      cache = EMPTY;
      return cache;
    } finally {
      inflight = null;
    }
  })();
  return inflight;
}

export function isRouteEnabled(vis: ProductVisibilityPayload, path: string): boolean {
  const p = path.length > 1 && path.endsWith("/") ? path.replace(/\/+$/, "") : path;
  if ((vis.disabled_routes || []).includes(p)) return false;
  // Unbound paths stay visible; bound paths must be in enabled_routes.
  const allBound = new Set([...(vis.enabled_routes || []), ...(vis.disabled_routes || [])]);
  if (!allBound.has(p)) return true;
  return (vis.enabled_routes || []).includes(p);
}

export function isPricingKindEnabled(vis: ProductVisibilityPayload, kind: string): boolean {
  return (vis.enabled_pricing_kinds || []).includes(kind);
}

export function isFaqCategoryEnabled(vis: ProductVisibilityPayload, slug: string): boolean {
  const s = (slug || "").trim().toLowerCase();
  if (!s) return true;
  // Unbound categories (e.g. zoho-recruit) stay visible; shared + product-bound must be enabled.
  const known = new Set(vis.enabled_faq_category_slugs || []);
  // If API failed open (EMPTY), known includes product slugs — filter only when we know it's disabled.
  // Prefer: hide only when slug is a product-bound slug not in enabled set.
  // Without full bound list on FE, use: if enabled list is non-empty and slug is a known product
  // category but missing → hide. Shared/product map:
  const PRODUCT_FAQ = new Set([
    "recruitment",
    "ai-calling",
    "whatsapp-surveys",
    "customer-feedback",
    "expo",
    "campaigns",
    "getting-started",
    "billing",
    "security",
    "account",
    "troubleshooting",
    "integrations",
  ]);
  if (!PRODUCT_FAQ.has(s)) return true;
  return known.has(s);
}

/** Loader helper — throw notFound when a product marketing route is disabled. */
export async function requireEnabledProductRoute(path: string): Promise<ProductVisibilityPayload> {
  const vis = await fetchProductVisibility();
  if (!isRouteEnabled(vis, path)) {
    const { notFound } = await import("@tanstack/react-router");
    throw notFound();
  }
  return vis;
}

export function useProductVisibility(): ProductVisibilityPayload {
  const [vis, setVis] = useState<ProductVisibilityPayload>(cache || EMPTY);
  useEffect(() => {
    let cancelled = false;
    fetchProductVisibility().then((v) => {
      if (!cancelled) setVis(v);
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return vis;
}
