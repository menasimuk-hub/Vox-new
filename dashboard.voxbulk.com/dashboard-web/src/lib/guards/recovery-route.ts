import { requireEnabledService } from "@/lib/guards/service-route";

export function requireRecoveryModules() {
  return requireEnabledService("recovery");
}

export function requireFollowUpModule() {
  return requireEnabledService("followup");
}
