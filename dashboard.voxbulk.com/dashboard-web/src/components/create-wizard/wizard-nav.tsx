import { ChevronLeft, ChevronRight, Rocket, SkipForward } from "lucide-react";
import { Button } from "@/components/ui/button";

type WizardNavProps = {
  step: number;
  total: number;
  onBack?: () => void;
  backLabel?: string;
  onPrev: () => void;
  onNext: () => void;
  nextDisabled?: boolean;
  finalLabel?: string;
  onFinish?: () => void;
  finishDisabled?: boolean;
  skippable?: boolean;
  onSkip?: () => void;
  skipLabel?: string;
  leftActions?: React.ReactNode;
};

export function WizardNav({
  step,
  total,
  onBack,
  backLabel = "Change channel",
  onPrev,
  onNext,
  nextDisabled,
  finalLabel = "Preview & launch",
  onFinish,
  finishDisabled,
  skippable,
  onSkip,
  skipLabel = "Skip for now",
  leftActions,
}: WizardNavProps) {
  return (
    <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex flex-wrap items-center gap-2">
        {onBack ? (
          <Button variant="ghost" className="gap-1.5" onClick={onBack}>
            <ChevronLeft className="size-4" /> {backLabel}
          </Button>
        ) : null}
        {leftActions}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" className="gap-1.5" onClick={onPrev} disabled={step === 1}>
          <ChevronLeft className="size-4" /> Back
        </Button>
        {skippable && onSkip && step < total ? (
          <Button variant="ghost" className="gap-1.5" onClick={onSkip}>
            <SkipForward className="size-4" /> {skipLabel}
          </Button>
        ) : null}
        {step < total ? (
          <Button className="gap-1.5" onClick={onNext} disabled={nextDisabled}>
            Next <ChevronRight className="size-4" />
          </Button>
        ) : (
          <Button className="gap-1.5" onClick={onFinish} disabled={finishDisabled}>
            <Rocket className="size-4" /> {finalLabel}
          </Button>
        )}
      </div>
    </div>
  );
}
