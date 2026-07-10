import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowRight, Loader2, RefreshCw, Save, Search } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'

function fmtErr(e) {
  if (!e) return 'Request failed'
  if (typeof e?.data?.detail === 'string') return e.data.detail
  if (e?.data?.detail?.message) return e.data.detail.message
  return e.message || String(e)
}

export default function WaConvertPanel({ syncProfileId }) {
  const [product, setProduct] = useState('all')
  const [q, setQ] = useState('')
  const [rows, setRows] = useState([])
  const [llm, setLlm] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [activeId, setActiveId] = useState(null)
  const [editor, setEditor] = useState(null)
  const [busy, setBusy] = useState('')
  const [overlay, setOverlay] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams()
      params.set('product', product)
      if (q.trim()) params.set('q', q.trim())
      if (syncProfileId) params.set('connection_profile_id', syncProfileId)
      const data = await apiFetch(`/admin/wa-templates/convert/marketing?${params}`)
      const list = Array.isArray(data?.templates) ? data.templates : []
      setRows(list)
      setLlm(data?.llm || null)
      if (list.length && !activeId) {
        const first = list.find((r) => r.actionable && r.db_id) || list[0]
        if (first?.db_id) setActiveId(String(first.db_id))
      }
    } catch (e) {
      setError(fmtErr(e))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [product, q, syncProfileId, activeId])

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [product, syncProfileId])

  const active = useMemo(
    () => rows.find((r) => String(r.db_id || r.id) === String(activeId)),
    [rows, activeId],
  )

  useEffect(() => {
    if (!active?.db_id || !active?.product) {
      setEditor(null)
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const data = await apiFetch(
          `/admin/wa-templates/convert/${encodeURIComponent(active.product)}/${encodeURIComponent(active.db_id)}`,
        )
        if (!cancelled) {
          setEditor({
            product: data.product,
            db_id: data.db_id,
            local_name: data.local_name,
            suggested_next_name: data.suggested_next_name,
            language: data.language,
            header: data.header || '',
            body: data.body || '',
            footer: data.footer || '',
            buttons: Array.isArray(data.buttons) ? data.buttons : [],
            status: data.status,
          })
        }
      } catch (e) {
        if (!cancelled) setError(fmtErr(e))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [active?.db_id, active?.product])

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return rows
    return rows.filter((r) => {
      const hay = `${r.local_name || ''} ${r.remote_name || ''} ${r.name || ''} ${r.survey_type || ''}`.toLowerCase()
      return hay.includes(needle)
    })
  }, [rows, q])

  const runRegen = async () => {
    if (!editor) return
    setBusy('regen')
    setError('')
    setMsg('')
    try {
      const data = await apiFetch(
        `/admin/wa-templates/convert/${encodeURIComponent(editor.product)}/${encodeURIComponent(editor.db_id)}/regenerate`,
        { method: 'POST', body: JSON.stringify({}) },
      )
      setEditor((prev) => ({
        ...prev,
        body: data.body || data.new_body || prev.body,
        buttons: Array.isArray(data.buttons) ? data.buttons : prev.buttons,
        header: data.header ?? prev.header,
        footer: data.footer ?? prev.footer,
        suggested_next_name: data.suggested_next_name || prev.suggested_next_name,
      }))
      setMsg(`Regenerated with ${data.llm?.provider || 'LLM'} (${data.llm?.model || 'default'})`)
    } catch (e) {
      setError(fmtErr(e))
    } finally {
      setBusy('')
    }
  }

  const runSave = async () => {
    if (!editor) return
    setBusy('save')
    setError('')
    setMsg('')
    try {
      const data = await apiFetch(
        `/admin/wa-templates/convert/${encodeURIComponent(editor.product)}/${encodeURIComponent(editor.db_id)}/save`,
        {
          method: 'POST',
          body: JSON.stringify({
            header: editor.header,
            body: editor.body,
            footer: editor.footer,
            buttons: editor.buttons,
          }),
        },
      )
      setEditor((prev) => ({
        ...prev,
        body: data.body || prev.body,
        buttons: Array.isArray(data.buttons) ? data.buttons : prev.buttons,
        suggested_next_name: data.suggested_next_name || prev.suggested_next_name,
      }))
      setMsg('Saved local Utility draft (same DB id)')
    } catch (e) {
      setError(fmtErr(e))
    } finally {
      setBusy('')
    }
  }

  const runPush = async (targets) => {
    if (!editor) return
    setBusy(`push-${targets}`)
    setError('')
    setMsg('')
    setOverlay({
      open: true,
      title: `Push to ${targets === 'all' ? '99 + 55' : targets}`,
      sub: `${editor.local_name} → ${editor.suggested_next_name || '…'} · DB ${editor.db_id}`,
      steps: [
        { id: 'lint', title: 'Utility lint', status: 'active' },
        { id: 'rename', title: 'Rename local (same DB id)', status: 'pending' },
        { id: 'push', title: 'Push new Utility name', status: 'pending' },
        { id: 'delete_old', title: 'Delete old MARKETING name', status: 'pending' },
      ],
    })
    try {
      const data = await apiFetch(
        `/admin/wa-templates/convert/${encodeURIComponent(editor.product)}/${encodeURIComponent(editor.db_id)}/push`,
        { method: 'POST', body: JSON.stringify({ targets, force_push: true }) },
      )
      const steps = Array.isArray(data.steps)
        ? data.steps.map((s) => ({
            id: s.id,
            title: s.title,
            status: s.status === 'error' ? 'error' : 'done',
            detail: s.detail,
          }))
        : []
      setOverlay({
        open: true,
        title: data.ok ? 'Push finished' : 'Push failed',
        sub: `${data.old_name} → ${data.new_name} · DB ${data.db_id}`,
        steps,
      })
      setMsg(
        data.ok
          ? `Pushed ${data.new_name}. Wait for Meta APPROVED before live sends.`
          : 'Push failed — old MARKETING name kept if push did not succeed.',
      )
      setEditor((prev) => ({
        ...prev,
        local_name: data.new_name || prev.local_name,
        suggested_next_name: null,
        status: data.status,
      }))
      await load()
    } catch (e) {
      setError(fmtErr(e))
      setOverlay((prev) =>
        prev
          ? {
              ...prev,
              title: 'Push failed',
              steps: (prev.steps || []).map((s) =>
                s.status === 'active' ? { ...s, status: 'error', detail: fmtErr(e) } : s,
              ),
            }
          : null,
      )
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="wa-convert p-3">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Convert — Marketing → Utility</h3>
          <p className="text-xs text-muted-foreground">
            Survey &amp; Feedback templates Meta marked as MARKETING. Same DB id; bump 001→002; delete old Meta name after push.
          </p>
          {llm?.provider ? (
            <p className="mt-1 text-[11px] text-muted-foreground">
              LLM: {llm.provider} / {llm.model || '—'} ({llm.source || 'config'})
            </p>
          ) : llm?.error ? (
            <p className="mt-1 text-[11px] text-amber-700">{llm.error}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            className="h-8 rounded-md border bg-background px-2 text-xs"
            value={product}
            onChange={(e) => setProduct(e.target.value)}
          >
            <option value="all">All products</option>
            <option value="survey">Survey only</option>
            <option value="feedback">Feedback only</option>
          </select>
          <Button type="button" size="sm" variant="outline" onClick={() => void load()} disabled={loading}>
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Refresh
          </Button>
        </div>
      </div>

      {error ? <div className="mb-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">{error}</div> : null}
      {msg ? <div className="mb-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-900">{msg}</div> : null}

      <div className="grid gap-3 lg:grid-cols-[320px_1fr]">
        <div className="overflow-hidden rounded-lg border">
          <div className="border-b p-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-2 h-3.5 w-3.5 text-muted-foreground" />
              <input
                className="h-8 w-full rounded-md border bg-background pl-7 pr-2 text-xs"
                placeholder="Search…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void load()
                }}
              />
            </div>
            <div className="mt-1.5 text-[11px] text-muted-foreground">
              {filtered.length} marketing template{filtered.length === 1 ? '' : 's'}
            </div>
          </div>
          <div className="max-h-[560px] overflow-y-auto">
            {loading && !filtered.length ? (
              <div className="p-4 text-xs text-muted-foreground">Loading from Meta…</div>
            ) : null}
            {!loading && !filtered.length ? (
              <div className="p-4 text-xs text-muted-foreground">No MARKETING survey/feedback templates found.</div>
            ) : null}
            {filtered.map((r) => {
              const id = String(r.db_id || r.id || r.remote_name)
              const selected = String(activeId) === id
              return (
                <button
                  key={id}
                  type="button"
                  className={cn(
                    'flex w-full flex-col gap-1 border-b px-3 py-2.5 text-left hover:bg-muted/50',
                    selected && 'bg-muted',
                  )}
                  onClick={() => {
                    if (r.db_id) setActiveId(String(r.db_id))
                  }}
                  disabled={!r.db_id}
                >
                  <span className="font-mono text-xs font-semibold">{r.local_name || r.remote_name || r.name}</span>
                  <span className="flex flex-wrap items-center gap-1.5 text-[10px]">
                    <span className="rounded-full bg-amber-100 px-1.5 py-0.5 font-semibold uppercase text-amber-800">
                      Marketing
                    </span>
                    <span className="rounded-full bg-muted px-1.5 py-0.5 uppercase text-muted-foreground">
                      {r.product || '—'}
                    </span>
                    {r.language ? (
                      <span className="rounded-full bg-muted px-1.5 py-0.5 text-muted-foreground">{r.language}</span>
                    ) : null}
                    {!r.actionable ? (
                      <span className="text-amber-700">no local row</span>
                    ) : (
                      <span className="text-muted-foreground">DB {r.db_id}</span>
                    )}
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        <div className="rounded-lg border p-4">
          {!editor ? (
            <p className="text-xs text-muted-foreground">Select an actionable template to convert.</p>
          ) : (
            <>
              <div className="mb-3 flex flex-wrap items-start justify-between gap-2 border-b pb-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2 font-mono text-sm font-semibold">
                    <span>{editor.local_name}</span>
                    <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="text-emerald-700">{editor.suggested_next_name || '—'}</span>
                  </div>
                  <div className="mt-1 font-mono text-[11px] text-muted-foreground">
                    DB ID {editor.db_id} · unchanged on save/push · {editor.language || '—'}
                  </div>
                </div>
                <div className="flex items-center gap-1 text-[10px] font-semibold uppercase">
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-800">Marketing</span>
                  <ArrowRight className="h-3 w-3 text-muted-foreground" />
                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-emerald-800">Utility</span>
                </div>
              </div>

              <div className="space-y-3">
                {editor.product === 'survey' ? (
                  <label className="block text-xs">
                    <span className="mb-1 block font-semibold uppercase tracking-wide text-muted-foreground">Header</span>
                    <input
                      className="h-8 w-full rounded-md border bg-background px-2 text-sm"
                      value={editor.header}
                      onChange={(e) => setEditor((p) => ({ ...p, header: e.target.value }))}
                    />
                  </label>
                ) : null}
                <label className="block text-xs">
                  <span className="mb-1 block font-semibold uppercase tracking-wide text-muted-foreground">Body</span>
                  <textarea
                    className="min-h-[96px] w-full rounded-md border bg-background px-2 py-1.5 text-sm leading-relaxed"
                    value={editor.body}
                    onChange={(e) => setEditor((p) => ({ ...p, body: e.target.value }))}
                  />
                  <span className="mt-1 block text-[11px] text-muted-foreground">
                    Utility copy must confirm a transaction/account action — not promote an offer.
                  </span>
                </label>
                {editor.product === 'survey' ? (
                  <label className="block text-xs">
                    <span className="mb-1 block font-semibold uppercase tracking-wide text-muted-foreground">Footer</span>
                    <input
                      className="h-8 w-full rounded-md border bg-background px-2 text-sm"
                      value={editor.footer}
                      onChange={(e) => setEditor((p) => ({ ...p, footer: e.target.value }))}
                    />
                  </label>
                ) : null}
                <div className="text-xs">
                  <span className="mb-1 block font-semibold uppercase tracking-wide text-muted-foreground">Buttons</span>
                  <div className="space-y-1.5">
                    {(editor.buttons || []).map((b, i) => (
                      <input
                        key={i}
                        className="h-8 w-full rounded-md border bg-background px-2 text-sm"
                        value={b}
                        onChange={(e) => {
                          const next = [...editor.buttons]
                          next[i] = e.target.value
                          setEditor((p) => ({ ...p, buttons: next }))
                        }}
                      />
                    ))}
                  </div>
                </div>
              </div>

              <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t pt-3">
                <div className="text-[11px] text-muted-foreground">
                  Will rename to <span className="font-mono text-foreground">{editor.suggested_next_name || '—'}</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <Button type="button" size="sm" variant="outline" disabled={!!busy} onClick={() => void runRegen()}>
                    {busy === 'regen' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                    Regenerate
                  </Button>
                  <Button type="button" size="sm" variant="outline" disabled={!!busy} onClick={() => void runSave()}>
                    {busy === 'save' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                    Save
                  </Button>
                  <Button type="button" size="sm" variant="outline" disabled={!!busy} onClick={() => void runPush('99')}>
                    Push 99
                  </Button>
                  <Button type="button" size="sm" variant="outline" disabled={!!busy} onClick={() => void runPush('55')}>
                    Push 55
                  </Button>
                  <Button type="button" size="sm" disabled={!!busy} onClick={() => void runPush('all')}>
                    {String(busy).startsWith('push') ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                    Push all
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {overlay?.open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-xl border bg-background p-5 shadow-lg">
            <h4 className="text-sm font-semibold">{overlay.title}</h4>
            <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">{overlay.sub}</p>
            <div className="mt-4 space-y-2">
              {(overlay.steps || []).map((s) => (
                <div key={s.id} className="flex gap-2 text-xs">
                  <span
                    className={cn(
                      'mt-0.5 h-2 w-2 shrink-0 rounded-full',
                      s.status === 'done' && 'bg-emerald-500',
                      s.status === 'error' && 'bg-red-500',
                      s.status === 'active' && 'bg-amber-500',
                      s.status === 'pending' && 'bg-muted-foreground/40',
                    )}
                  />
                  <div>
                    <div className="font-medium">{s.title}</div>
                    {s.detail ? <div className="text-muted-foreground">{s.detail}</div> : null}
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4 flex justify-end">
              <Button type="button" size="sm" variant="outline" onClick={() => setOverlay(null)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
