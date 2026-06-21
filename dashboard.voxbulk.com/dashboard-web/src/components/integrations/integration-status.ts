import type { IntegrationView } from "@/components/integrations/provider-tile";
import type { IntegrationStatus } from "@/components/integrations/integration-status-pill";

export function integrationStatusFor(view: IntegrationView): IntegrationStatus {
  if (!view.platform_ready) return "disabled";
  if (view.last_check_ok === false) return "error";
  if (view.connected) {
    if (view.group === "booking" && view.extra?.event_type_configured === false) {
      return "setup_needed";
    }
    return "connected";
  }
  return "not_connected";
}
