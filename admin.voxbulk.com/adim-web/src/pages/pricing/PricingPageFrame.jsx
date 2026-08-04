import React from 'react'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Label } from '@/components/ui/Label'
import { cn } from '@/lib/utils'

export default function PricingPageFrame({ title, description, children, error, msg, actions }) {
  return (
    <div className="ds-scope">
      <Panel title={title} subtitle={description} action={actions || null} bodyClassName="space-y-3">
        {error ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        ) : null}
        {msg ? (
          <div className="rounded-md border border-success/40 bg-success-soft px-3 py-2 text-sm text-success">
            {msg}
          </div>
        ) : null}
        {children}
      </Panel>
    </div>
  )
}

export function PricingField({ label, hint, children, wide, compact, fullRow }) {
  return (
    <div
      className={cn(
        'flex flex-col gap-1',
        wide && 'sm:col-span-2',
        fullRow && 'col-span-full',
        compact && 'min-w-0',
      )}
    >
      <Label className="text-[11px] text-muted-foreground">{label}</Label>
      {hint ? <span className="text-[10px] leading-tight text-muted-foreground">{hint}</span> : null}
      {children}
    </div>
  )
}

export function PricingLoadGate({ loading, error, title, description, onRetry, children }) {
  if (loading) {
    return (
      <div className="ds-scope text-sm text-muted-foreground">Loading…</div>
    )
  }

  if (error) {
    return (
      <PricingPageFrame
        title={title}
        description={description}
        error={error}
        actions={
          onRetry ? (
            <Button type="button" variant="outline" size="sm" className="h-8" onClick={() => void onRetry()}>
              Retry
            </Button>
          ) : null
        }
      >
        {null}
      </PricingPageFrame>
    )
  }

  return children
}

export function PricingFormulaBox({ items }) {
  return (
    <Panel title="How included amounts are calculated" bodyClassName="space-y-2">
      <ul className="list-inside list-disc space-y-1 text-[12.5px] text-foreground">
        {items.map((item) => (
          <li key={item}>
            <code className="rounded bg-muted px-1 py-0.5 text-[11px]">{item}</code>
          </li>
        ))}
      </ul>
      <p className="text-[11px] text-muted-foreground">
        WA and CV unit prices come from <strong className="text-foreground">Service rates</strong>. Extra minutes use{' '}
        <strong className="text-foreground">Extra min £</strong> when the package is used up.
      </p>
    </Panel>
  )
}
