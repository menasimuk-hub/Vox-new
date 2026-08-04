import React from 'react'
import { Bell, Search } from 'lucide-react'
import '../../pages/supportDisk.css'

export default function SupportDiskShell({ title, subtitle, search, onSearch, actions, children }) {
  return <div className="support-disk flex min-h-[calc(100vh-56px)] flex-col">
    <header className="flex min-h-16 shrink-0 flex-wrap items-center gap-3 border-b border-border bg-surface px-4 py-3 sm:px-6">
      <div className="min-w-0">
        <h1 className="truncate text-lg font-extrabold">{title}</h1>
        {subtitle ? <p className="text-xs text-muted-foreground">{subtitle}</p> : null}
      </div>
      <div className="ml-auto flex items-center gap-2">
        {onSearch ? <label className="relative hidden sm:block">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input value={search || ''} onChange={(e) => onSearch(e.target.value)} placeholder="Search Support Disk…" className="h-9 w-64 rounded-md border border-input bg-surface-subtle pl-8 pr-3 text-sm outline-none focus:border-ring" />
        </label> : null}
        {actions}
        <button className="grid size-9 place-items-center rounded-md text-muted-foreground hover:bg-accent" aria-label="Notifications"><Bell className="size-4" /></button>
      </div>
    </header>
    <main className="min-h-0 flex-1">{children}</main>
  </div>
}
