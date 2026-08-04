import React from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { cn } from '../utils'
import { buttonVariants } from '../Button'

export const AlertDialog = DialogPrimitive.Root
export const AlertDialogTrigger = DialogPrimitive.Trigger
export const AlertDialogAction = React.forwardRef(function AlertDialogAction({ className, ...props }, ref) { return <DialogPrimitive.Close ref={ref} className={cn(buttonVariants(), className)} {...props} /> })
export const AlertDialogCancel = React.forwardRef(function AlertDialogCancel({ className, ...props }, ref) { return <DialogPrimitive.Close ref={ref} className={cn(buttonVariants({ variant: 'outline' }), 'mt-2 sm:mt-0', className)} {...props} /> })
export const AlertDialogContent = React.forwardRef(function AlertDialogContent({ className, children, ...props }, ref) {
  return <DialogPrimitive.Portal><DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/80" /><DialogPrimitive.Content ref={ref} className={cn('support-disk support-disk-dialog fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border bg-background p-6 shadow-lg sm:rounded-lg', className)} {...props}>{children}</DialogPrimitive.Content></DialogPrimitive.Portal>
})
export const AlertDialogHeader = ({ className, ...props }) => <div className={cn('flex flex-col space-y-2 text-center sm:text-left', className)} {...props} />
export const AlertDialogFooter = ({ className, ...props }) => <div className={cn('flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2', className)} {...props} />
export const AlertDialogTitle = React.forwardRef(function AlertDialogTitle({ className, ...props }, ref) { return <DialogPrimitive.Title ref={ref} className={cn('text-lg font-semibold', className)} {...props} /> })
export const AlertDialogDescription = React.forwardRef(function AlertDialogDescription({ className, ...props }, ref) { return <DialogPrimitive.Description ref={ref} className={cn('text-sm text-muted-foreground', className)} {...props} /> })
