import React, { useMemo, useRef, useState } from 'react'
import { ArrowLeft, Check, Link2, Lock, Search, Send, Sparkles, Zap } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { InitialsAvatar, STATUS_META, StatusPill, TagChip } from './bits'
import { dateLabel } from './utils'

export default function TicketDetail({ ticket, messages = [], admins = [], cannedReplies = [], helpLinks = [], faqs = [], onBack, onStatusChange, onAssign, onSend, onPolish }) {
  const [mode, setMode] = useState('reply')
  const [draft, setDraft] = useState('')
  const [menu, setMenu] = useState('')
  const [query, setQuery] = useState('')
  const [suggestion, setSuggestion] = useState('')
  const [polishOpen, setPolishOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const ref = useRef(null)
  const requester = ticket.created_by_email || 'Customer'
  const insert = (text) => { setDraft((d) => d ? `${d.trimEnd()}\n\n${text}` : text); setMenu(''); requestAnimationFrame(() => ref.current?.focus()) }
  const options = useMemo(() => {
    const q = query.toLowerCase()
    const list = menu === 'canned' ? cannedReplies.map((x) => ({ id: x.id, title: x.title, body: x.answer || x.body })) : menu === 'faq' ? faqs.map((x) => ({ id: x.id, title: x.question, body: x.answer })) : helpLinks.map((x) => ({ id: x.id, title: x.title || x.label, body: `[${x.title || x.label}](${x.url})` }))
    return list.filter((x) => `${x.title} ${x.body}`.toLowerCase().includes(q))
  }, [menu, query, cannedReplies, faqs, helpLinks])
  const polish = async () => { if (!draft.trim()) return; setBusy(true); try { setSuggestion(await onPolish(draft)); setPolishOpen(true) } finally { setBusy(false) } }
  const send = async () => { if (!draft.trim()) return; setBusy(true); try { await onSend(draft.trim(), mode === 'note'); setDraft('') } finally { setBusy(false) } }
  return <section className="flex h-full min-h-0 flex-col bg-surface">
    <header className="shrink-0 border-b border-border px-4 py-3">
      <Button variant="ghost" size="sm" className="mb-2" onClick={onBack}><ArrowLeft /> Back to tickets</Button>
      <div className="flex flex-wrap items-start gap-3"><div className="min-w-0 flex-1"><h2 className="truncate text-base font-bold">{ticket.subject}</h2><p className="text-xs text-muted-foreground">{ticket.public_ref} · {requester} · via {ticket.channel || 'email'}</p></div>
        <select value={ticket.status} onChange={(e) => onStatusChange(e.target.value)} className="h-8 rounded-md border border-input bg-surface px-2 text-xs">{Object.entries(STATUS_META).map(([v, m]) => <option key={v} value={v}>{m.label}</option>)}</select>
        <select value={ticket.assigned_admin_user_id || ''} onChange={(e) => onAssign(e.target.value)} className="h-8 rounded-md border border-input bg-surface px-2 text-xs"><option value="">Unassigned</option>{admins.map((a) => <option key={a.id} value={a.id}>{a.email}</option>)}</select>
      </div>
      <div className="mt-2 flex items-center gap-2"><StatusPill status={ticket.status} /><TagChip label={ticket.category || 'support'} /></div>
    </header>
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto bg-surface-subtle p-4">{messages.map((m) => <article key={m.id} className={`flex gap-2.5 ${m.sender_type === 'admin' && !m.is_internal_note ? 'flex-row-reverse' : ''}`}><InitialsAvatar name={m.sender_email || m.sender_type} /><div className={`max-w-[42rem] rounded-lg border px-3 py-2.5 shadow-panel ${m.is_internal_note ? 'border-note/30 bg-note-bg' : m.sender_type === 'admin' ? 'border-transparent bg-accent' : 'border-border bg-surface'}`}><p className="text-[11px] text-muted-foreground"><strong className="text-foreground">{m.sender_email || m.sender_type}</strong> · {dateLabel(m.created_at)} {m.is_internal_note ? <span className="ml-1 font-semibold text-note"><Lock className="inline size-3" /> Internal note</span> : null}</p><p className="mt-1 whitespace-pre-wrap text-sm">{m.body}</p></div></article>)}</div>
    <footer className="shrink-0 border-t border-border p-3">
      <div className="mb-2 flex gap-1"><Button size="sm" variant={mode === 'reply' ? 'secondary' : 'ghost'} onClick={() => setMode('reply')}>Reply to customer</Button><Button size="sm" variant={mode === 'note' ? 'secondary' : 'ghost'} onClick={() => setMode('note')}><Lock /> Internal note</Button></div>
      <div className={`rounded-lg border ${mode === 'note' ? 'border-note/40 bg-note-bg' : 'border-border bg-surface'}`}>
        <div className="relative flex flex-wrap gap-1 border-b border-border p-1">
          <Button variant="ghost" size="sm" onClick={() => setMenu(menu === 'canned' ? '' : 'canned')}><Zap /> Canned replies</Button><Button variant="ghost" size="sm" onClick={() => setMenu(menu === 'links' ? '' : 'links')}><Link2 /> Insert help link</Button><Button variant="ghost" size="sm" onClick={() => setMenu(menu === 'faq' ? '' : 'faq')}><Search /> Insert FAQ answer</Button><Button variant="ghost" size="sm" className="text-primary" disabled={busy} onClick={polish}><Sparkles /> AI polish</Button>
          {menu ? <div className="absolute bottom-full left-1 z-20 mb-1 w-80 rounded-lg border border-border bg-popover p-1 shadow-[var(--shadow-pop)]"><input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search…" className="mb-1 h-8 w-full border-b bg-transparent px-2 text-sm outline-none" /><div className="max-h-52 overflow-auto">{options.map((x) => <button key={x.id} className="block w-full rounded px-2 py-1.5 text-left hover:bg-secondary" onClick={() => insert(x.body)}><strong className="block text-sm">{x.title}</strong><span className="line-clamp-1 text-xs text-muted-foreground">{x.body}</span></button>)}{!options.length ? <p className="p-3 text-center text-xs text-muted-foreground">No matches.</p> : null}</div></div> : null}
        </div>
        <textarea ref={ref} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={mode === 'note' ? 'Add a note only your team can see…' : `Reply to ${requester}…`} className="min-h-28 w-full resize-none bg-transparent p-3 text-sm outline-none" />
        <div className="flex justify-end border-t border-border p-2"><Button size="sm" onClick={send} disabled={!draft.trim() || busy}><Send /> {mode === 'note' ? 'Add note' : 'Send reply'}</Button></div>
      </div>
    </footer>
    <Modal open={polishOpen} onOpenChange={setPolishOpen} title={<span className="flex items-center gap-2"><Sparkles className="size-4 text-primary" /> AI-polished reply</span>} description="Review the changes before applying." className="support-disk support-disk-dialog max-w-3xl" footer={<><Button variant="ghost" onClick={() => setPolishOpen(false)}>Keep original</Button><Button onClick={() => { setDraft(suggestion); setPolishOpen(false) }}><Check /> Use this version</Button></>}><div className="grid gap-3 sm:grid-cols-2"><div className="rounded-lg border bg-surface-subtle p-3 text-sm whitespace-pre-wrap">{draft}</div><div className="rounded-lg border border-primary/30 bg-accent p-3 text-sm whitespace-pre-wrap">{suggestion}</div></div></Modal>
  </section>
}
