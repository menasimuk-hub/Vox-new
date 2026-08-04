import React from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { cn } from '../utils'

export const Dialog = DialogPrimitive.Root
export const DialogTrigger = DialogPrimitive.Trigger
export const DialogClose = DialogPrimitive.Close

export const DialogContent = React.forwardRef(function DialogContent({ className, children, ...props }, ref) {
  return <DialogPrimitive.Portal>
    <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/80" />
    <DialogPrimitive.Content ref={ref} className={cn('support-disk support-disk-dialog fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border bg-background p-6 shadow-lg sm:rounded-lg', className)} {...props}>
      {children}
      <DialogPrimitive.Close className="absolute right-4 top-4 rounded-sm opacity-70 hover:opacity-100"><X className="h-4 w-4" /><span className="sr-only">Close</span></DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </DialogPrimitive.Portal>
})

export const DialogHeader = ({ className, ...props }) => <div className={cn('flex flex-col space-y-1.5 text-center sm:text-left', className)} {...props} />
export const DialogFooter = ({ className, ...props }) => <div className={cn('flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2', className)} {...props} />
export const DialogTitle = React.forwardRef(function DialogTitle({ className, ...props }, ref) { return <DialogPrimitive.Title ref={ref} className={cn('text-lg font-semibold leading-none tracking-tight', className)} {...props} /> })
export const DialogDescription = React.forwardRef(function DialogDescription({ className, ...props }, ref) { return <DialogPrimitive.Description ref={ref} className={cn('text-sm text-muted-foreground', className)} {...props} /> })
