import React from 'react'
import * as TabsPrimitive from '@radix-ui/react-tabs'
import { cn } from '../utils'

export const Tabs = TabsPrimitive.Root
export const TabsList = React.forwardRef(function TabsList({ className, ...props }, ref) { return <TabsPrimitive.List ref={ref} className={cn('inline-flex h-9 items-center justify-center rounded-lg bg-muted p-1 text-muted-foreground', className)} {...props} /> })
export const TabsTrigger = React.forwardRef(function TabsTrigger({ className, ...props }, ref) { return <TabsPrimitive.Trigger ref={ref} className={cn('inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium ring-offset-background cursor-pointer transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow', className)} {...props} /> })
