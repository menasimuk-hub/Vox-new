import React, { useMemo, useState } from 'react'
import { ArrowUpDown, Filter, Search, UserPlus, X } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { InitialsAvatar, PriorityMark, STATUS_META, StatusPill } from './bits'
import { dateLabel } from './utils'

const priorities = ['urgent', 'high', 'normal', 'low']
export default function TicketTable({ tickets = [], onOpen, onBulkStatus, onBulkAssign, admins = [], loading }) {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')
  const [priority, setPriority] = useState('all')
  const [channel, setChannel] = useState('all')
  const [sort, setSort] = useState('recent')
  const [selected, setSelected] = useState([])
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    const filtered = tickets.filter((t) => (status === 'all' || t.status === status) && (priority === 'all' || (t.priority || 'normal') === priority) && (channel === 'all' || (t.channel || 'email') === channel) && (!q || `${t.public_ref} ${t.subject} ${t.created_by_email} ${t.organisation_name}`.toLowerCase().includes(q)))
    const order = { urgent: 0, high: 1, normal: 2, low: 3 }
    return [...filtered].sort((a, b) => sort === 'priority' ? order[a.priority || 'normal'] - order[b.priority || 'normal'] : (sort === 'oldest' ? 1 : -1) * (new Date(a.last_message_at || a.updated_at) - new Date(b.last_message_at || b.updated_at)))
  }, [tickets, query, status, priority, channel, sort])
  const selectAll = rows.length > 0 && rows.every((t) => selected.includes(t.id))
  const run = async (fn, value) => { await fn?.(selected, value); setSelected([]) }
  return <section className="flex h-full min-h-0 flex-col bg-surface">
    <div className="shrink-0 space-y-2 border-b border-border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="relative min-w-56 flex-1"><Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search this queue…" className="h-9 w-full rounded-md border border-input bg-surface-subtle pl-8 pr-3 text-sm outline-none focus:border-ring" /></label>
        <Filter className="size-3.5 text-muted-foreground" />
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="h-8 rounded-md border border-input bg-surface px-2 text-xs"><option value="all">Any status</option>{Object.entries(STATUS_META).map(([v, m]) => <option key={v} value={v}>{m.label}</option>)}</select>
        <select value={priority} onChange={(e) => setPriority(e.target.value)} className="h-8 rounded-md border border-input bg-surface px-2 text-xs"><option value="all">Any priority</option>{priorities.map((v) => <option key={v}>{v}</option>)}</select>
        <select value={channel} onChange={(e) => setChannel(e.target.value)} className="h-8 rounded-md border border-input bg-surface px-2 text-xs"><option value="all">Any channel</option><option>email</option><option>web</option><option>phone</option></select>
        <select value={sort} onChange={(e) => setSort(e.target.value)} className="h-8 rounded-md border border-input bg-surface px-2 text-xs"><option value="recent">Newest activity</option><option value="oldest">Oldest activity</option><option value="priority">Priority</option></select>
        <ArrowUpDown className="size-3.5 text-muted-foreground" />
      </div>
    </div>
    {selected.length ? <div className="flex flex-wrap items-center gap-2 border-b border-border bg-accent px-3 py-2 text-xs"><strong>{selected.length} selected</strong>
      <select defaultValue="" onChange={(e) => e.target.value && run(onBulkStatus, e.target.value)} className="h-7 rounded-md border bg-surface px-2"><option value="">Change status</option>{Object.keys(STATUS_META).map((v) => <option key={v}>{v}</option>)}</select>
      <select defaultValue="" onChange={(e) => e.target.value && run(onBulkAssign, e.target.value)} className="h-7 rounded-md border bg-surface px-2"><option value="">Assign</option>{admins.map((a) => <option key={a.id} value={a.id}>{a.email}</option>)}</select><UserPlus className="size-3.5" />
      <Button variant="ghost" size="sm" className="ml-auto h-7" onClick={() => setSelected([])}><X /> Cancel</Button>
    </div> : null}
    <div className="min-h-0 flex-1 overflow-auto"><table className="w-full min-w-[820px] border-collapse text-sm">
      <thead className="sticky top-0 z-10 bg-surface-subtle text-left"><tr className="border-b border-border text-[11px] uppercase tracking-wider text-muted-foreground"><th className="w-10 px-3 py-2"><input type="checkbox" checked={selectAll} onChange={(e) => setSelected(e.target.checked ? rows.map((t) => t.id) : [])} /></th><th>Requester</th><th>Subject</th><th>Status</th><th>Priority</th><th>Updated</th><th>Agent</th></tr></thead>
      <tbody className="divide-y divide-border">{loading ? <tr><td colSpan="7" className="p-10 text-center text-muted-foreground">Loading tickets…</td></tr> : rows.map((t) => <tr key={t.id} onClick={() => onOpen?.(t.id)} className="cursor-pointer hover:bg-surface-subtle">
        <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}><input type="checkbox" checked={selected.includes(t.id)} onChange={() => setSelected((s) => s.includes(t.id) ? s.filter((id) => id !== t.id) : [...s, t.id])} /></td>
        <td className="px-2 py-2.5"><div className="flex items-center gap-2"><InitialsAvatar name={t.created_by_email || t.organisation_name} className="size-7" /><div><p className={t.admin_unread ? 'font-bold' : 'font-medium'}>{t.created_by_email || 'Unknown'}</p><p className="text-[11px] text-muted-foreground">{t.public_ref} · {t.channel || 'email'}</p></div></div></td>
        <td className="max-w-[28rem] px-2 py-2.5"><p className="truncate font-medium">{t.subject}</p><p className="truncate text-xs text-muted-foreground">{t.organisation_name || 'No organisation'}</p></td>
        <td><StatusPill status={t.status} /></td><td><PriorityMark priority={t.priority || 'normal'} /></td><td className="text-xs text-muted-foreground">{dateLabel(t.last_message_at || t.updated_at)}</td><td className="text-xs">{t.assigned_admin_email || 'Unassigned'}</td>
      </tr>)}{!loading && !rows.length ? <tr><td colSpan="7" className="p-10 text-center text-muted-foreground">No tickets match these filters.</td></tr> : null}</tbody>
    </table></div>
  </section>
}
