import { Phone, MessageSquare, ClipboardList } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export function usageServiceIcon(serviceCode?: string | null): LucideIcon | null {
  const code = String(serviceCode || "").toLowerCase();
  if (code === "interview") return Phone;
  if (code === "survey") return MessageSquare;
  return ClipboardList;
}

export const REFUND_TIMING_PROCESSING = "Refunds are processed within 2 working days.";
export const REFUND_TIMING_BANK = "Bank or card refunds may take up to 3 additional working days to appear on your statement.";
