import * as React from "react";
import { AlertCircle } from "lucide-react";

import { dashboardAlertClassName } from "@/lib/dashboard-theme";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

export {
  DASHBOARD_AMBER,
  dashboardAlertClassName,
  dashboardFieldErrorClassName,
  dashboardSummaryNoticeClassName,
  dashboardTextNoticeClassName,
} from "@/lib/dashboard-theme";

/** @deprecated Use DASHBOARD_AMBER */
export const WIZARD_AMBER = "#B45309";

/** @deprecated Use dashboardAlertClassName */
export const wizardAlertClassName = dashboardAlertClassName;

/** @deprecated Use dashboardFieldErrorClassName */
export const wizardFieldErrorClassName = "border-destructive/50 text-destructive";

type WizardAlertProps = {
  title: string;
  children: React.ReactNode;
  className?: string;
};

export const WizardAlert = React.forwardRef<HTMLDivElement, WizardAlertProps>(function WizardAlert(
  { title, children, className },
  ref,
) {
  return (
    <Alert ref={ref} className={cn(dashboardAlertClassName, className)}>
      <AlertCircle className="size-4" />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  );
});
