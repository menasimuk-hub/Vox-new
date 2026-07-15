import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: ReactNode;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 border-b border-border pb-6 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0">
        {eyebrow && (
          <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-primary/80">{eyebrow}</p>
        )}
        <h1 className="mt-1 text-xl font-semibold tracking-tight text-foreground sm:text-2xl md:text-3xl">{title}</h1>
        {description && <p className="mt-1.5 max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && (
        <div className="flex w-full flex-wrap gap-2 sm:ml-auto sm:w-auto sm:justify-end [&_button]:min-h-11 md:[&_button]:min-h-0 [&_a]:min-h-11 md:[&_a]:min-h-0">
          {actions}
        </div>
      )}
    </div>
  );
}
