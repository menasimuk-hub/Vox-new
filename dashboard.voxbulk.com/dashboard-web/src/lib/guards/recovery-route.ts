import { redirect } from "@tanstack/react-router";
import { showRecoveryModules } from "@/lib/feature-flags";

export function requireRecoveryModules() {
  if (!showRecoveryModules) {
    throw redirect({ to: "/" });
  }
}
