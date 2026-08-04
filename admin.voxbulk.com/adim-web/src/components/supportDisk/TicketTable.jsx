import React, { useMemo, useState } from 'react'
import { ArrowUpDown, Filter, MoreHorizontal, Search, Tag, Trash2, UserPlus, X, Zap } from 'lucide-react'
import { Button } from './Button'
import { Checkbox } from './ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from './ui/dropdown-menu'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from './ui/alert-dialog'
import { InitialsAvatar, PriorityMark, STATUS_META, StatusPill } from './bits'
import { cn, dateLabel } from './utils'

const priorities = ['urgent', 'high', 'normal', 'low']

export default function TicketTable({ tickets = [], onOpen, onBulkStatus, onBulkAssign, onDelete, admins = [], cannedReplies = [], loading }) {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')
  const [priority, setPriority] = useState('all')
  const [channel, setChannel] = useState('all')
  const [sort, setSort] = useState('recent')
  const [selected, setSelected] = useState([])
  const [confirm, setConfirm] = useState(null)
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const rows = tickets.filter((t) => (status === 'all' || t.status === status) && (priority === 'all' || (t.priority || 'normal') === priority) && (channel === 'all' || (t.channel || 'email') === channel) && (!q || `${t.created_by_email} ${t.subject} ${t.public_ref} ${t.organisation_name}`.toLowerCase().includes(q)))
    const order = { urgent: 0, high: 1, normal: 2, low: 3 }
    return [...rows].sort((a, b) => sort === 'priority' ? order[a.priority || 'normal'] - order[b.priority || 'normal'] : sort === 'oldest' ? new Date(a.last_message_at || a.updated_at) - new Date(b.last_message_at || b.updated_at) : new Date(b.last_message_at || b.updated_at) - new Date(a.last_message_at || a.updated_at))
  }, [tickets, query, status, priority, channel, sort])
  const allChecked = filtered.length > 0 && filtered.every((t) => selected.includes(t.id))
  const run = async (fn, value) => { await fn?.(selected, value); setSelected([]) }
  const filtersActive = status !== 'all' || priority !== 'all' || channel !== 'all' || query !== ''
  const clearFilters = () => { setStatus('all'); setPriority('all'); setChannel('all'); setQuery('') }

  return <section className="flex h-full min-h-0 flex-col bg-surface" aria-label="Ticket queue">
    <div className="shrink-0 space-y-2 border-b border-border p-3"><div className="flex flex-wrap items-center gap-2">
      <div className="relative min-w-56 flex-1"><Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" /><input value={query} onChange={(e) => setQuery(e.target.value)} type="search" placeholder="Search this queue…" aria-label="Search tickets" className="h-9 w-full rounded-md border border-input bg-surface-subtle pr-3 pl-8 text-sm outline-none placeholder:text-muted-foreground focus:border-ring focus:bg-surface" /></div>
      <Filter className="size-3.5 shrink-0 text-muted-foreground" />
      <Select value={status} onValueChange={setStatus}><SelectTrigger className="h-8 w-auto gap-1 text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Any status</SelectItem>{Object.entries(STATUS_META).map(([s, m]) => <SelectItem key={s} value={s}>{m.label}</SelectItem>)}</SelectContent></Select>
      <Select value={priority} onValueChange={setPriority}><SelectTrigger className="h-8 w-auto gap-1 text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Any priority</SelectItem>{priorities.map((p) => <SelectItem key={p} value={p}>{p[0].toUpperCase() + p.slice(1)}</SelectItem>)}</SelectContent></Select>
      <Select value={channel} onValueChange={setChannel}><SelectTrigger className="h-8 w-auto gap-1 text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Any channel</SelectItem><SelectItem value="email">Email</SelectItem><SelectItem value="chat">Chat</SelectItem><SelectItem value="web">Web form</SelectItem><SelectItem value="phone">Phone</SelectItem></SelectContent></Select>
      <Select value={sort} onValueChange={setSort}><SelectTrigger className="h-8 w-auto gap-1 text-xs"><ArrowUpDown className="size-3.5 text-muted-foreground" /><SelectValue /></SelectTrigger><SelectContent><SelectItem value="recent">Newest activity</SelectItem><SelectItem value="oldest">Oldest activity</SelectItem><SelectItem value="priority">Priority</SelectItem></SelectContent></Select>
      {filtersActive ? <Button variant="ghost" size="sm" className="h-8 px-2 text-xs" onClick={clearFilters}><X className="size-3.5" /> Clear</Button> : null}
    </div></div>
    {selected.length > 0 ? <div className="flex shrink-0 flex-wrap items-center gap-1.5 border-b border-border bg-accent px-3 py-2">
      <span className="text-xs font-semibold">{selected.length} selected</span>
      <DropdownMenu><DropdownMenuTrigger asChild><Button size="sm" variant="outline" className="h-7 bg-surface text-xs">Change status</Button></DropdownMenuTrigger><DropdownMenuContent align="start">{Object.entries(STATUS_META).map(([s, m]) => <DropdownMenuItem key={s} onSelect={() => run(onBulkStatus, s)}>{m.label}</DropdownMenuItem>)}</DropdownMenuContent></DropdownMenu>
      <DropdownMenu><DropdownMenuTrigger asChild><Button size="sm" variant="outline" className="h-7 bg-surface text-xs"><Zap className="size-3.5" /> Canned reply</Button></DropdownMenuTrigger><DropdownMenuContent align="start" className="w-64"><DropdownMenuLabel>Send to {selected.length} tickets</DropdownMenuLabel>{cannedReplies.slice(0, 4).map((c) => <DropdownMenuItem key={c.id}>{c.title}</DropdownMenuItem>)}</DropdownMenuContent></DropdownMenu>
      <DropdownMenu><DropdownMenuTrigger asChild><Button size="sm" variant="outline" className="h-7 bg-surface text-xs"><UserPlus className="size-3.5" /> Assign</Button></DropdownMenuTrigger><DropdownMenuContent align="start">{admins.map((a) => <DropdownMenuItem key={a.id} onSelect={() => run(onBulkAssign, a.id)}>{a.email}</DropdownMenuItem>)}</DropdownMenuContent></DropdownMenu>
      <Button size="sm" variant="outline" className="h-7 bg-surface text-xs"><Tag className="size-3.5" /> Tag</Button>
      <Button size="sm" variant="outline" className="h-7 bg-surface text-xs text-destructive" onClick={() => setConfirm(selected)}><Trash2 className="size-3.5" /> Delete</Button>
      <Button size="sm" variant="ghost" className="ml-auto h-7 text-xs" onClick={() => setSelected([])}>Cancel</Button>
    </div> : null}
    <div className="min-h-0 flex-1 overflow-auto"><table className="w-full min-w-[820px] border-collapse text-sm">
      <thead className="sticky top-0 z-10 bg-surface-subtle text-left"><tr className="border-b border-border text-[11px] font-semibold tracking-wider text-muted-foreground uppercase"><th className="w-10 px-3 py-2"><Checkbox checked={allChecked} onCheckedChange={(v) => setSelected(v ? filtered.map((t) => t.id) : [])} aria-label="Select all tickets" /></th><th className="px-2 py-2">Requester</th><th className="px-2 py-2">Subject</th><th className="px-2 py-2">Status</th><th className="px-2 py-2">Priority</th><th className="px-2 py-2">Updated</th><th className="px-2 py-2">Agent</th><th className="w-10 px-2 py-2"><span className="sr-only">Actions</span></th></tr></thead>
      <tbody className="divide-y divide-border">{loading ? <tr><td colSpan="8" className="p-10 text-center text-muted-foreground">Loading tickets…</td></tr> : filtered.map((t) => <tr key={t.id} onClick={() => onOpen?.(t.id)} className="cursor-pointer align-middle hover:bg-surface-subtle">
        <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}><Checkbox checked={selected.includes(t.id)} onCheckedChange={() => setSelected((s) => s.includes(t.id) ? s.filter((id) => id !== t.id) : [...s, t.id])} /></td>
        <td className="max-w-44 px-2 py-2.5"><div className="flex items-center gap-2"><InitialsAvatar name={t.created_by_email || t.organisation_name || 'Unknown'} className="size-7" /><div className="min-w-0"><p className={cn('truncate', t.admin_unread ? 'font-bold' : 'font-medium')}>{t.created_by_email || 'Unknown'}</p><p className="truncate text-[11px] text-muted-foreground">{t.public_ref} · {t.channel || 'email'}</p></div></div></td>
        <td className="max-w-[26rem] px-2 py-2.5"><p className="truncate font-medium">{t.subject}</p><p className="truncate text-xs text-muted-foreground">{t.organisation_name || 'No organisation'}</p><div className="mt-1 flex flex-wrap items-center gap-1.5">{t.category ? <span className="rounded-md bg-secondary px-1.5 py-px text-[11px] text-muted-foreground">{t.category}</span> : null}</div></td>
        <td className="px-2 py-2.5"><StatusPill status={t.status} /></td><td className="px-2 py-2.5"><PriorityMark priority={t.priority || 'normal'} /></td><td className="px-2 py-2.5 text-xs whitespace-nowrap text-muted-foreground">{dateLabel(t.last_message_at || t.updated_at)}</td><td className="px-2 py-2.5 text-xs whitespace-nowrap">{t.assigned_admin_email || 'Unassigned'}</td>
        <td className="px-2 py-2.5 text-right" onClick={(e) => e.stopPropagation()}><DropdownMenu><DropdownMenuTrigger asChild><Button size="icon" variant="ghost" className="size-7"><MoreHorizontal className="size-4" /></Button></DropdownMenuTrigger><DropdownMenuContent align="end" className="w-48"><DropdownMenuItem onSelect={() => onOpen?.(t.id)}>Open ticket</DropdownMenuItem><DropdownMenuSeparator /><DropdownMenuLabel className="text-[11px] uppercase">Status</DropdownMenuLabel>{Object.entries(STATUS_META).map(([s, m]) => <DropdownMenuItem key={s} onSelect={() => onBulkStatus?.([t.id], s)}>{m.label}</DropdownMenuItem>)}<DropdownMenuSeparator /><DropdownMenuItem className="text-destructive focus:text-destructive" onSelect={() => setConfirm([t.id])}><Trash2 className="size-4" /> Delete ticket</DropdownMenuItem></DropdownMenuContent></DropdownMenu></td>
      </tr>)}{!loading && filtered.length === 0 ? <tr><td colSpan="8" className="p-10 text-center text-sm text-muted-foreground">No tickets match these filters.</td></tr> : null}</tbody>
    </table></div>
    <AlertDialog open={confirm !== null} onOpenChange={(o) => !o && setConfirm(null)}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Delete {confirm?.length === 1 ? 'this ticket' : `${confirm?.length} tickets`}?</AlertDialogTitle><AlertDialogDescription>The tickets will be closed and removed from active queues.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={() => { onDelete?.(confirm || []); setSelected([]); setConfirm(null) }}>Delete</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </section>
}
