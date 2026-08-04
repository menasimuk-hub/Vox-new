import React from 'react'
import { Check } from 'lucide-react'
import { cn } from '../utils'

export const Checkbox = React.forwardRef(function Checkbox({ className, checked, onCheckedChange, ...props }, ref) {
  return (
    <button
      ref={ref}
      type="button"
      role="checkbox"
      aria-checked={Boolean(checked)}
      data-state={checked ? 'checked' : 'unchecked'}
      onClick={() => onCheckedChange?.(!checked)}
      className={cn('grid place-content-center peer h-4 w-4 shrink-0 rounded-sm border border-primary shadow cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground', className)}
      {...props}
    >
      {checked ? <Check className="h-4 w-4" /> : null}
    </button>
  )
})
