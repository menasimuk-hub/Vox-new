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

function normalizeIndustryKey(name: string, slug?: string): string {
  return `${slug || ""} ${name || ""}`.toLowerCase();
}

/** Map industry slug/name to a Lucide icon for the WA survey wizard. */
export function waIndustryIcon(name: string, slug?: string): LucideIcon {
  const key = normalizeIndustryKey(name, slug);
  if (/dental|dentist|tooth|orthodont/.test(key)) return Smile;
  if (/medical|clinic|health|hospital|gp|care|pharmacy|nhs/.test(key)) return Stethoscope;
  if (/beauty|salon|spa|cosmetic|hair|nail/.test(key)) return Scissors;
  if (/fitness|gym|sport|wellness|yoga|pilates/.test(key)) return Dumbbell;
  if (/restaurant|food|cafe|coffee|hospitality|hotel|pub|bar/.test(key)) return UtensilsCrossed;
  if (/hospitality|hotel|travel|resort/.test(key)) return Building2;
  if (/retail|shop|store|ecommerce|e-commerce|fashion/.test(key)) return ShoppingBag;
  if (/automotive|car dealer|car service|motor|vehicle|garage|mot/.test(key)) return Car;
  if (/legal|law|solicitor|barrister/.test(key)) return Scale;
  if (/education|school|university|college|training|academy/.test(key)) return GraduationCap;
  if (/finance|bank|insurance|accounting|mortgage|investment/.test(key)) return Landmark;
  if (/recruit|hr|staffing|talent|hiring|employment/.test(key)) return Briefcase;
  if (/beauty|luxury|premium/.test(key)) return Sparkles;
  return Briefcase;
}
