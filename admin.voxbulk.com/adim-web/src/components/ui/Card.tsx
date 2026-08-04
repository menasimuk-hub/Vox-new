import * as React from "react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Panel — compact section card from telynx-settings-hub-main
 * (icon + title/description header, border-b, dense body).
 */
interface PanelProps extends React.HTMLAttributes<HTMLElement> {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  description?: React.ReactNode;
  icon?: LucideIcon;
  action?: React.ReactNode;
  bodyClassName?: string;
}

const Panel = React.forwardRef<HTMLElement, PanelProps>(
  (
    { title, subtitle, description, icon: Icon, action, children, className, bodyClassName, ...props },
    ref,
  ) => {
    const desc = description ?? subtitle;
    return (
      <section
        ref={ref}
        className={cn(
          "rounded-xl border border-border bg-card text-card-foreground shadow-sm",
          className,
        )}
        {...props}
      >
        {(title || action || Icon) && (
          <header className="flex items-start justify-between gap-3 border-b border-border/70 px-3.5 py-2.5">
            <div className="flex min-w-0 items-start gap-2">
              {Icon ? (
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
                  <Icon className="h-3.5 w-3.5" />
                </span>
              ) : null}
              <div className="min-w-0">
                {title ? (
                  <h3 className="text-[13px] font-semibold leading-tight tracking-tight text-foreground">
                    {title}
                  </h3>
                ) : null}
                {desc ? (
                  <p className="truncate text-[11px] leading-tight text-muted-foreground">{desc}</p>
                ) : null}
              </div>
            </div>
            {action}
          </header>
        )}
        <div className={cn("p-3", bodyClassName)}>{children}</div>
      </section>
    );
  },
);
Panel.displayName = "Panel";

const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("rounded-xl border bg-card text-card-foreground shadow", className)}
      {...props}
    />
  ),
);
Card.displayName = "Card";

const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col space-y-1.5 p-6", className)} {...props} />
  ),
);
CardHeader.displayName = "CardHeader";

const CardTitle = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("font-semibold leading-none tracking-tight", className)}
      {...props}
    />
  ),
);
CardTitle.displayName = "CardTitle";

const CardDescription = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("text-sm text-muted-foreground", className)} {...props} />
  ),
);
CardDescription.displayName = "CardDescription";

const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
  ),
);
CardContent.displayName = "CardContent";

const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex items-center p-6 pt-0", className)} {...props} />
  ),
);
CardFooter.displayName = "CardFooter";

export { Panel, Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent };
