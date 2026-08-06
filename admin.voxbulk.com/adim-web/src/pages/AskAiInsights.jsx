import React, { useEffect, useState } from 'react'
import { Check, RefreshCw, Sparkles, ThumbsDown, ThumbsUp, X } from 'lucide-react'
import { apiFetch } from '../lib/api'
import SupportDiskShell from '../components/supportDisk/SupportDiskShell'
import { Button } from '../components/supportDisk/Button'

export default function AskAiInsights() {
  const [insights, setInsights] = useState(null)
  const [suggestions, setSuggestions] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  const refresh = async () => {
    try {
      setError('')
      const [ins, sug] = await Promise.all([
        apiFetch('/admin/assistant/insights'),
        apiFetch('/admin/assistant/suggestions?status=pending'),
      ])
      setInsights(ins)
      setSuggestions(sug || [])
    } catch (e) {
      setError(e.message || 'Could not load Ask AI insights')
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const rebuild = async () => {
    setBusy('rebuild')
    try {
      await apiFetch('/admin/assistant/help/rebuild-index', { method: 'POST' })
      await refresh()
    } catch (e) {
      setError(e.message || 'Rebuild failed')
    } finally {
      setBusy('')
    }
  }

  const setStatus = async (id, status) => {
    setBusy(id)
    try {
      await apiFetch(`/admin/assistant/suggestions/${id}`, {
        method: 'PATCH',
        body: { status },
      })
      await refresh()
    } catch (e) {
      setError(e.message || 'Update failed')
    } finally {
      setBusy('')
    }
  }

  const total = Number(insights?.total_questions || 0)
  const thumbs = Number(insights?.thumbs_up || 0) + Number(insights?.thumbs_down || 0)
  const thumbsUpPct = thumbs ? Math.round((Number(insights?.thumbs_up || 0) / thumbs) * 100) : 0
  const cards = [
    ['Questions', insights?.total_questions ?? '—', Sparkles],
    ['Help Centre hits', insights?.kb_hits ?? '—', Sparkles],
    ['General AI', insights?.general_ai ?? '—', Sparkles],
    ['Thumbs-up %', thumbs ? `${thumbsUpPct}%` : '—', ThumbsUp],
  ]

  return (
    <SupportDiskShell
      title="Ask AI insights"
      subtitle="Usage mix, feedback, and uncovered FAQ suggestions"
      actions={
        <Button variant="outline" size="sm" className="h-9 gap-1.5 text-xs" disabled={busy === 'rebuild'} onClick={rebuild}>
          <RefreshCw className="size-3.5" />
          Rebuild help index
        </Button>
      }
    >
      <div className="h-full overflow-y-auto p-4 sm:p-6">
        <div className="mx-auto max-w-6xl space-y-4">
          {error ? <div className="rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{error}</div> : null}
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {cards.map(([label, value, Icon]) => (
              <div key={label} className="rounded-xl border border-border bg-surface p-4 shadow-panel">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Icon className="size-4" />
                  <span className="text-xs">{label}</span>
                </div>
                <p className="mt-2 font-display text-2xl font-extrabold">{value}</p>
              </div>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            Mix: {total ? `${Math.round((Number(insights?.kb_hits || 0) / Math.max(total, 1)) * 100)}% Help Centre` : '—'} ·{' '}
            {total ? `${Math.round((Number(insights?.general_ai || 0) / Math.max(total, 1)) * 100)}% General AI` : '—'} · thumbs down{' '}
            {insights?.thumbs_down ?? 0} <ThumbsDown className="inline size-3" />
          </p>
          <section className="rounded-xl border border-border bg-surface p-4 shadow-panel">
            <h3 className="text-sm font-bold">Uncovered question suggestions</h3>
            <p className="mb-3 text-xs text-muted-foreground">Accept opens a draft queue item — does not auto-publish FAQs.</p>
            <ul className="divide-y divide-border">
              {suggestions.map((s) => (
                <li key={s.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start">
                  <div className="min-w-0 flex-1">
                    <strong className="block text-sm">{s.question}</strong>
                    <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">{s.sample_answer}</p>
                    <span className="mt-1 block text-[10px] text-muted-foreground">{s.created_at?.slice?.(0, 19)}</span>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" disabled={busy === s.id} onClick={() => setStatus(s.id, 'accepted')}>
                      <Check className="size-3.5" /> Accept
                    </Button>
                    <Button variant="outline" size="sm" disabled={busy === s.id} onClick={() => setStatus(s.id, 'rejected')}>
                      <X className="size-3.5" /> Reject
                    </Button>
                  </div>
                </li>
              ))}
              {!suggestions.length ? <li className="py-8 text-center text-sm text-muted-foreground">No pending suggestions.</li> : null}
            </ul>
          </section>
        </div>
      </div>
    </SupportDiskShell>
  )
}
