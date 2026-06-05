import * as React from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export type WizardStepDef = {
  id: number;
  title: string;
  subtitle?: string;
  icon: React.ComponentType<{ className?: string }>;
};

type StepperProps = {
  steps: WizardStepDef[];
  current: number;
  onStepClick: (step: number) => void;
  /** When true, only completed steps (id < current) are clickable */
  guardForward?: boolean;
};

export function Stepper({ steps, current, onStepClick, guardForward = true }: StepperProps) {
  const progress = steps.length > 1 ? ((current - 1) / (steps.length - 1)) * 100 : 0;

  return (
    <div className="rounded-2xl border border-border bg-gradient-to-br from-background/80 via-background/40 to-accent/10 p-5 shadow-sm">
      <div className="relative">
        <div className="absolute left-5 right-5 top-5 hidden h-0.5 bg-border sm:block" aria-hidden />
        <div
          className="absolute left-5 top-5 hidden h-0.5 bg-gradient-to-r from-primary to-primary/60 transition-all duration-500 ease-out sm:block"
          style={{ width: `calc((100% - 2.5rem) * ${progress / 100})` }}
          aria-hidden
        />
        <ol className="relative grid gap-2" style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }}>
          {steps.map((s) => {
            const isDone = s.id < current;
            const isActive = s.id === current;
            const Icon = s.icon;
            const clickable = !guardForward || s.id <= current;

            return (
              <li key={s.id} className="flex flex-col items-center text-center">
                <button
                  type="button"
                  disabled={!clickable}
                  onClick={() => clickable && onStepClick(s.id)}
                  className={cn(
                    "group relative grid size-10 place-items-center rounded-full border transition-all duration-300",
                    isActive && "scale-110 border-primary bg-primary text-primary-foreground shadow-lg shadow-primary/30",
                    isDone && "border-primary bg-primary/15 text-primary",
                    !isActive && !isDone && "border-border bg-background text-muted-foreground hover:border-primary/40",
                    !clickable && "cursor-not-allowed opacity-60",
                  )}
                  aria-label={`Step ${s.id}: ${s.title}`}
                >
                  {isActive && (
                    <span className="absolute inset-0 rounded-full bg-primary/30 motion-safe:animate-ping" aria-hidden />
                  )}
                  <span className="relative">{isDone ? <Check className="size-5" /> : <Icon className="size-5" />}</span>
                </button>
                <div className="mt-2 min-h-[2.25rem]">
                  <p className={cn("text-xs font-semibold sm:text-sm", isActive ? "text-foreground" : "text-muted-foreground")}>
                    {s.id}. {s.title}
                  </p>
                  {s.subtitle ? (
                    <p className="hidden text-[11px] text-muted-foreground sm:block">{s.subtitle}</p>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
