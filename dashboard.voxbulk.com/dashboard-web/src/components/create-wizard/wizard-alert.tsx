import * as React from "react";
import { AlertCircle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

/** Wizard validation / notice colour — amber, not red. */
export const WIZARD_AMBER = "#B45309";

export const wizardAlertClassName =
  "border-[#B45309]/40 bg-[#B45309]/10 text-[#B45309] [&>svg]:text-[#B45309]";

export const wizardFieldErrorClassName = "border-[#B45309]/50 text-[#B45309]";

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
    <Alert ref={ref} className={cn(wizardAlertClassName, className)}>
      <AlertCircle className="size-4" />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  );
});
