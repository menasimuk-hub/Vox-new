import {
  Briefcase,
  Building2,
  Car,
  Dumbbell,
  GraduationCap,
  Hotel,
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
        .replace(/&/g, "and")
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

export function normalizeIndustrySlug(slug?: string): string {
  return String(slug || "")
    .trim()
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/-/g, "_")
    .replace(/[\s/]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "");
}

/** Slug-first icon map — checked before fuzzy name matching. */
const SLUG_ICON: Record<string, LucideIcon> = {
  hospitality_food: Hotel,
  hospitality: Hotel,
  hotel_accommodation: Hotel,
  healthcare_dental: Smile,
  healthcare: Stethoscope,
  recruitment_staffing: Briefcase,
  ecommerce: ShoppingBag,
  finance: Landmark,
  education: GraduationCap,
  saas: Sparkles,
  services: Briefcase,
  general: Briefcase,
};

export function isHospitalityFoodIndustry(name?: string, slug?: string): boolean {
  const slugKey = normalizeIndustrySlug(slug);
  if (slugKey === "hospitality_food") return true;

  const nameKey = String(name || "")
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
  if (nameKey.includes("hospitality") && nameKey.includes("food")) return true;

  const key = normalizeIndustryKey(name, slug);
  const tokens = industryTokens(key);
  return (
    includesAny(key, "hospitality_food", "hospitality_and_food") ||
    (hasToken(tokens, "hospitality") && hasToken(tokens, "food"))
  );
}

/** Map industry slug/name to a Lucide icon for the WA survey wizard. */
export function waIndustryIcon(name?: string, slug?: string): LucideIcon {
  const slugKey = normalizeIndustrySlug(slug);
  if (slugKey && SLUG_ICON[slugKey]) {
    return SLUG_ICON[slugKey];
  }

  if (isHospitalityFoodIndustry(name, slug)) {
    return Hotel;
  }

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
    includesAny(key, "hospitality", "hotel", "accommodation", "travel", "resort", "lettings") ||
    hasToken(tokens, "hospitality", "hotel", "accommodation", "travel", "resort", "lettings")
  ) {
    return Hotel;
  }

  if (
    includesAny(key, "restaurant", "food", "cafe", "coffee", "pub", "bar", "catering") ||
    hasToken(tokens, "restaurant", "food", "cafe", "coffee", "pub", "bar", "catering")
  ) {
    return UtensilsCrossed;
  }

  // Never substring-match bare "health" — "hospitality" used to wrongly match and show Stethoscope.
  if (
    hasToken(tokens, "healthcare", "health", "medical", "clinic", "hospital", "gp", "pharmacy", "nhs") ||
    includesAny(key, "healthcare", "medical", "clinical", "hospital", "pharmacy", "nhs")
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

type WaIndustryIconProps = {
  name?: string;
  slug?: string;
  className?: string;
};

/** Renders hotel + food icons for Hospitality & food; otherwise a single industry icon. */
export function WaIndustryIcon({ name, slug, className }: WaIndustryIconProps) {
  if (isHospitalityFoodIndustry(name, slug)) {
    return (
      <span className="inline-flex items-center gap-0.5" aria-hidden>
        <Hotel className={className} />
        <UtensilsCrossed className={className} />
      </span>
    );
  }
  const Icon = waIndustryIcon(name, slug);
  return <Icon className={className} aria-hidden />;
}
