import {
  Briefcase,
  Building2,
  Car,
  Dumbbell,
  GraduationCap,
  Landmark,
  Scale,
  Scissors,
  ShoppingBag,
  Smile,
  Sparkles,
  Stethoscope,
  UtensilsCrossed,
  type LucideIcon,
} from "lucide-react";

/** Normalize slug/name for industry icon matching (lowercase, trim, spaces/hyphens → _). */
export function normalizeIndustryKey(name?: string, slug?: string): string {
  return [slug, name]
    .filter((value) => String(value || "").trim())
    .map((value) =>
      String(value)
        .toLowerCase()
        .trim()
        .replace(/[\s\-/]+/g, "_")
        .replace(/_+/g, "_")
        .replace(/^_|_$/g, ""),
    )
    .join(" ");
}

function industryTokens(key: string): string[] {
  return key.split(/[^a-z0-9]+/).filter(Boolean);
}

function hasToken(tokens: string[], ...needles: string[]): boolean {
  return needles.some((needle) => tokens.includes(needle));
}

function includesAny(key: string, ...needles: string[]): boolean {
  return needles.some((needle) => key.includes(needle));
}

/** Map industry slug/name to a Lucide icon for the WA survey wizard. */
export function waIndustryIcon(name?: string, slug?: string): LucideIcon {
  const key = normalizeIndustryKey(name, slug);
  const tokens = industryTokens(key);
  if (!key) return Briefcase;

  if (
    includesAny(key, "dental", "dentist", "orthodont") ||
    hasToken(tokens, "dental", "dentist", "tooth", "orthodont")
  ) {
    return Smile;
  }

  if (
    includesAny(key, "healthcare", "health", "medical", "clinic", "hospital", "pharmacy", "nhs") ||
    hasToken(tokens, "healthcare", "health", "medical", "clinic", "hospital", "gp", "pharmacy", "nhs")
  ) {
    return Stethoscope;
  }

  if (
    includesAny(key, "beauty", "salon", "spa", "cosmetic", "hair", "nail") ||
    hasToken(tokens, "beauty", "salon", "spa", "cosmetic", "hair", "nails", "nail")
  ) {
    return Scissors;
  }

  if (
    includesAny(key, "fitness", "gym", "wellness", "yoga", "pilates") ||
    hasToken(tokens, "fitness", "gym", "sport", "wellness", "yoga", "pilates")
  ) {
    return Dumbbell;
  }

  if (
    includesAny(key, "restaurant", "food", "cafe", "coffee", "pub", "bar", "catering") ||
    hasToken(tokens, "restaurant", "food", "cafe", "coffee", "pub", "bar", "catering")
  ) {
    return UtensilsCrossed;
  }

  if (
    includesAny(key, "hospitality", "hotel", "accommodation", "travel", "resort", "lettings") ||
    hasToken(tokens, "hospitality", "hotel", "accommodation", "travel", "resort", "lettings")
  ) {
    return Building2;
  }

  if (
    includesAny(key, "retail", "ecommerce", "e_commerce", "shop", "store", "fashion") ||
    hasToken(tokens, "retail", "ecommerce", "shop", "store", "fashion", "mall")
  ) {
    return ShoppingBag;
  }

  if (
    includesAny(key, "automotive", "motor", "vehicle", "garage", "mot", "car_dealer", "car_service") ||
    hasToken(tokens, "automotive", "motor", "vehicle", "garage", "mot", "dealer")
  ) {
    return Car;
  }

  if (
    includesAny(key, "legal", "law", "solicitor", "barrister", "accountancy") ||
    hasToken(tokens, "legal", "law", "solicitor", "barrister", "accountancy")
  ) {
    return Scale;
  }

  if (
    includesAny(key, "education", "school", "university", "college", "training", "academy") ||
    hasToken(tokens, "education", "school", "university", "college", "training", "academy")
  ) {
    return GraduationCap;
  }

  if (
    includesAny(key, "property", "estate", "realtor", "letting") ||
    hasToken(tokens, "property", "estate", "realtor", "lettings", "letting")
  ) {
    return Building2;
  }

  if (
    includesAny(key, "finance", "bank", "insurance", "mortgage", "investment") ||
    hasToken(tokens, "finance", "bank", "insurance", "mortgage", "investment", "fintech")
  ) {
    return Landmark;
  }

  if (
    includesAny(key, "recruit", "staffing", "talent", "hiring", "employment") ||
    hasToken(tokens, "recruitment", "recruit", "staffing", "talent", "hiring", "employment", "hr")
  ) {
    return Briefcase;
  }

  if (
    includesAny(key, "services", "professional", "consumer") ||
    hasToken(tokens, "services", "professional", "consumer")
  ) {
    return Briefcase;
  }

  if (includesAny(key, "general", "other") || hasToken(tokens, "general", "other")) {
    return Briefcase;
  }

  if (includesAny(key, "luxury", "premium") || hasToken(tokens, "luxury", "premium")) {
    return Sparkles;
  }

  if (includesAny(key, "saas", "technology", "software", "tech") || hasToken(tokens, "saas", "technology", "software", "tech")) {
    return Sparkles;
  }

  return Briefcase;
}
