import React, { createContext, useContext, useEffect, useRef, useState } from 'react'
import { cn } from '../utils'

const MenuContext = createContext(null)

export function MenuRoot({ children }) {
  const [open, setOpen] = useState(false)
  const root = useRef(null)
  useEffect(() => {
    if (!open) return
    const close = (event) => { if (!root.current?.contains(event.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])
  return <MenuContext.Provider value={{ open, setOpen }}><span ref={root} className="sd-menu-root relative inline-flex">{children}</span></MenuContext.Provider>
}

export function MenuTrigger({ asChild, children }) {
  const { open, setOpen } = useContext(MenuContext)
  if (asChild && React.isValidElement(children)) {
    return React.cloneElement(children, { 'aria-expanded': open, onClick: (e) => { children.props.onClick?.(e); setOpen(!open) } })
  }
  return <button type="button" onClick={() => setOpen(!open)}>{children}</button>
}

export const MenuContent = React.forwardRef(function MenuContent({ className, align = 'center', children, ...props }, ref) {
  const { open } = useContext(MenuContext)
  if (!open) return null
  return <div ref={ref} className={cn('sd-menu-content absolute top-full z-50 mt-1 min-w-[8rem] overflow-y-auto overflow-x-hidden rounded-md border bg-popover p-1 text-popover-foreground shadow-md', align === 'end' ? 'right-0' : align === 'start' ? 'left-0' : 'left-1/2 -translate-x-1/2', className)} {...props}>{children}</div>
})

export const MenuItem = React.forwardRef(function MenuItem({ className, onSelect, onClick, children, ...props }, ref) {
  const { setOpen } = useContext(MenuContext)
  return <button ref={ref} type="button" className={cn('relative flex w-full cursor-default select-none items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground disabled:pointer-events-none disabled:opacity-50 [&>svg]:size-4 [&>svg]:shrink-0', className)} onClick={(e) => { onClick?.(e); onSelect?.(e); setOpen(false) }} {...props}>{children}</button>
})

export const MenuLabel = ({ className, ...props }) => <div className={cn('px-2 py-1.5 text-sm font-semibold', className)} {...props} />
export const MenuSeparator = ({ className, ...props }) => <div className={cn('-mx-1 my-1 h-px bg-muted', className)} {...props} />
