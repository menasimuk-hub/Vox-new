import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowRight, Loader2, RefreshCw, Save, Search, Trash2 } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'

function fmtErr(e) {
  if (!e) return 'Request failed'
  if (typeof e?.data?.detail === 'string') return e.data.detail
  if (e?.data?.detail?.message) return e.data.detail.message
  return e.message || String(e)
}

/** Session cache: Meta marketing list — refetch only on Refresh / after push-cleanup. */
const marketingListCache = new Map()

function marketingCacheKey(product, syncProfileId) {
  return `${String(product || 'all')}|${String(syncProfileId || '')}`
}

export default function WaConvertPanel({ syncProfileId }) {
  const [product, setProduct] = useState('all')
  const [q, setQ] = useState('')
  const [rows, setRows] = useState([])
  const [orphanCount, setOrphanCount] = useState(0)
  const [llm, setLlm] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [activeId, setActiveId] = useState(null)
  const [editor, setEditor] = useState(null)
  const [regenDiff, setRegenDiff] = useState(null)
  const [lintInfo, setLintInfo] = useState(null)
  const [busy, setBusy] = useState('')
  const [overlay, setOverlay] = useState(null)
  const [listFromCache, setListFromCache] = useState(false)
  const [listCachedAt, setListCachedAt] = useState(null)
  const activeIdRef = useRef(activeId)
  activeIdRef.current = activeId

  const applyListPayload = useCallback((data, { fromCache = false, cachedAt = null } = {}) => {
    const list = Array.isArray(data?.templates) ? data.templates : []
    setRows(list)
    setOrphanCount(Number(data?.orphan_cleanup_count || data?.overview?.orphan_cleanup_count || 0))
    setLlm(data?.llm || null)
    setListFromCache(Boolean(fromCache))
    setListCachedAt(cachedAt || (fromCache ? null : new Date().toISOString()))
    if (list.length && !activeIdRef.current) {
      const first = list.find((r) => r.actionable && r.db_id) || list[0]
      if (first?.db_id) setActiveId(String(first.db_id))
    }
  }, [])

  const load = useCallback(
    async ({ force = false } = {}) => {
      const key = marketingCacheKey(product, syncProfileId)
      if (!force && marketingListCache.has(key)) {
        const hit = marketingListCache.get(key)
        applyListPayload(hit.data, { fromCache: true, cachedAt: hit.cachedAt })
        setError('')
        return
      }
      setLoading(true)
      setError('')
      try {
        const params = new URLSearchParams()
        params.set('product', product)
        if (syncProfileId) params.set('connection_profile_id', syncProfileId)
        const data = await apiFetch(`/admin/wa-templates/convert/marketing?${params}`, {
          timeoutMs: 280000,
          quietNetworkHint: true,
        })
        const cachedAt = new Date().toISOString()
        marketingListCache.set(key, { data, cachedAt })
        applyListPayload(data, { fromCache: false, cachedAt })
      } catch (e) {
        setError(fmtErr(e))
        setRows([])
        setOrphanCount(0)
        setListFromCache(false)
        setListCachedAt(null)
      } finally {
        setLoading(false)
      }
    },
    [product, syncProfileId, applyListPayload],
  )

  useEffect(() => {
    void load({ force: false })
  }, [load])

  const active = useMemo(
    () => rows.find((r) => String(r.db_id || r.id) === String(activeId)),
    [rows, activeId],
  )

  useEffect(() => {
    if (!active?.db_id || !active?.product) {
      setEditor(null)
      setRegenDiff(null)
      setLintInfo(null)
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const data = await apiFetch(
          `/admin/wa-templates/convert/${encodeURIComponent(active.product)}/${encodeURIComponent(active.db_id)}`,
          { timeoutMs: 120000 },
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

  const runCleanupOrphans = async () => {
    const count = orphanCount
    if (!count) {
      setMsg('No old Meta versions to clean up (only names superseded by a newer local row).')
      return
    }
    const ok = window.confirm(
      `Delete ${count} old Meta/Telnyx template name(s) that are not in local DB and were replaced by a newer local version?\n\nCurrent local rows are kept. This only removes leftover remote names (e.g. _001 / _002 when local is _003).\n\nYou will see live progress for each name.`,
    )
    if (!ok) return
    setBusy('cleanup')
    setError('')
    setMsg('')

    const pushOverlay = (patch) => {
      setOverlay((prev) => ({ open: true, ...(prev || {}), ...patch }))
    }

    pushOverlay({
      title: 'Cleaning up old Meta versions…',
      sub: 'Loading orphan list…',
      progress: { done: 0, total: count, pct: 0 },
      log: [],
      steps: [
        { id: 'scan', title: 'Load superseded orphans', status: 'active' },
        { id: 'delete', title: 'Delete from Meta / Telnyx', status: 'pending' },
      ],
    })

    try {
      const listParams = new URLSearchParams()
      listParams.set('product', product)
      if (q.trim()) listParams.set('q', q.trim())
      if (syncProfileId) listParams.set('connection_profile_id', syncProfileId)
      const listed = await apiFetch(`/admin/wa-templates/convert/orphans?${listParams}`, {
        timeoutMs: 280000,
        quietNetworkHint: true,
      })
      const orphans = Array.isArray(listed?.orphans) ? listed.orphans : []
      const total = orphans.length
      if (!total) {
        pushOverlay({
          title: 'Nothing to clean',
          sub: 'No superseded Meta orphans found right now.',
          progress: { done: 0, total: 0, pct: 100 },
          steps: [
            { id: 'scan', title: 'Load superseded orphans', status: 'done', detail: '0 found' },
            { id: 'delete', title: 'Delete from Meta / Telnyx', status: 'done', detail: 'Skipped' },
          ],
        })
        setMsg('No old Meta versions to clean up.')
        await load({ force: true })
        return
      }

      pushOverlay({
        title: 'Cleaning up old Meta versions…',
        sub: `0 / ${total} · starting…`,
        progress: { done: 0, total, pct: 0 },
        log: [],
        steps: [
          { id: 'scan', title: 'Load superseded orphans', status: 'done', detail: `${total} name(s)` },
          { id: 'delete', title: 'Delete from Meta / Telnyx', status: 'active', detail: `1 / ${total}` },
        ],
      })

      let deleted = 0
      let failed = 0
      const log = []

      for (let i = 0; i < orphans.length; i += 1) {
        const name = String(orphans[i]?.remote_name || '').trim()
        const n = i + 1
        const pct = Math.round((i / total) * 100)
        pushOverlay({
          title: 'Cleaning up old Meta versions…',
          sub: `${n} / ${total} · ${name}`,
          progress: { done: i, total, pct },
          log: log.slice(-8),
          steps: [
            { id: 'scan', title: 'Load superseded orphans', status: 'done', detail: `${total} name(s)` },
            {
              id: 'delete',
              title: 'Delete from Meta / Telnyx',
              status: 'active',
              detail: `${n} / ${total} · ${name}`,
            },
          ],
        })

        try {
          const data = await apiFetch('/admin/wa-templates/convert/orphans/cleanup', {
            method: 'POST',
            body: JSON.stringify({
              dry_run: false,
              targets: 'all',
              product,
              names: [name],
              connection_profile_id: syncProfileId || undefined,
            }),
            timeoutMs: 180000,
            quietNetworkHint: true,
          })
          const oneDeleted = Number(data?.deleted || 0)
          const oneFailed = Number(data?.failed || 0)
          if (oneDeleted > 0 && oneFailed === 0) {
            deleted += 1
            log.push({ name, ok: true, detail: (data?.results?.[0]?.deleted_on || []).join(', ') || 'deleted' })
          } else {
            failed += 1
            const err =
              data?.results?.[0]?.error || data?.message || `${oneDeleted} deleted / ${oneFailed} failed`
            log.push({ name, ok: false, detail: String(err).slice(0, 160) })
          }
        } catch (e) {
          failed += 1
          log.push({ name, ok: false, detail: fmtErr(e).slice(0, 160) })
        }

        const doneNow = i + 1
        pushOverlay({
          progress: { done: doneNow, total, pct: Math.round((doneNow / total) * 100) },
          log: log.slice(-8),
          sub: `${doneNow} / ${total} · last: ${name}`,
        })
      }

      const pctDone = 100
      pushOverlay({
        title: failed ? 'Cleanup finished with errors' : 'Cleanup complete',
        sub: `Deleted ${deleted}/${total} · failed ${failed}`,
        progress: { done: total, total, pct: pctDone },
        log: log.slice(-12),
        steps: [
          { id: 'scan', title: 'Load superseded orphans', status: 'done', detail: `${total} name(s)` },
          {
            id: 'delete',
            title: 'Delete from Meta / Telnyx',
            status: failed ? 'error' : 'done',
            detail: `${deleted} deleted · ${failed} failed`,
          },
        ],
      })
      setMsg(`Deleted ${deleted}/${total} old version(s)${failed ? ` · ${failed} failed` : ''}.`)
      await load({ force: true })
    } catch (e) {
      setError(fmtErr(e))
      pushOverlay({
        title: 'Cleanup failed',
        sub: fmtErr(e),
        steps: [
          { id: 'scan', title: 'Load superseded orphans', status: 'error', detail: fmtErr(e) },
          { id: 'delete', title: 'Delete from Meta / Telnyx', status: 'pending' },
        ],
      })
    } finally {
      setBusy('')
    }
  }

  const runRegen = async () => {
    if (!editor) return
    setBusy('regen')
    setError('')
    setMsg('')
    setRegenDiff(null)
    try {
      const data = await apiFetch(
        `/admin/wa-templates/convert/${encodeURIComponent(editor.product)}/${encodeURIComponent(editor.db_id)}/regenerate`,
        { method: 'POST', body: JSON.stringify({}), timeoutMs: 180000 },
      )
      const nextBody = data.new_body || data.body || editor.body
      const nextButtons = Array.isArray(data.buttons) ? data.buttons : Array.isArray(data.new_buttons) ? data.new_buttons : editor.buttons
      setEditor((prev) => ({
        ...prev,
        body: nextBody,
        buttons: nextButtons,
        header: data.header ?? prev.header,
        footer: data.footer ?? prev.footer,
        suggested_next_name: data.suggested_next_name || prev.suggested_next_name,
      }))
      setRegenDiff({
        old_body: data.old_body || '',
        new_body: nextBody || '',
        old_buttons: Array.isArray(data.old_buttons) ? data.old_buttons : [],
        new_buttons: Array.isArray(data.new_buttons) ? data.new_buttons : nextButtons,
        changed: Boolean(data.changed),
        buttons_changed: Boolean(data.buttons_changed),
      })
      setLintInfo(data.lint || null)
      if (data.changed) {
        setMsg(
          `Body${data.buttons_changed ? ' + buttons' : ''} rewritten (${data.llm?.source || data.llm?.provider || 'utility'}). Local Utility lint: ${
            data.lint?.ok ? 'PASS' : 'FAIL — fix before Save'
          }. Save, then Push.`,
        )
      } else {
        setMsg(
          `Regenerate returned the same body (already mapped to Utility topic wording). Local lint: ${
            data.lint?.ok ? 'PASS' : 'FAIL'
          }. You can still edit manually, then Save → Push.`,
        )
      }
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
          timeoutMs: 120000,
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
        { method: 'POST', body: JSON.stringify({ targets, force_push: true }), timeoutMs: 300000 },
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
      await load({ force: true })
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
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => void load({ force: true })}
            disabled={loading}
            title="Reload marketing list from Meta (bypasses cache)"
          >
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Refresh
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => void runCleanupOrphans()}
            disabled={loading || busy === 'cleanup' || !orphanCount}
            title="Delete old Meta/Telnyx names not in local DB when a newer local version exists"
          >
            {busy === 'cleanup' ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Trash2 className="h-3.5 w-3.5" />
            )}
            Clean old versions{orphanCount ? ` (${orphanCount})` : ''}
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
              />
            </div>
            <div className="mt-1.5 text-[11px] text-muted-foreground">
              {filtered.length} marketing template{filtered.length === 1 ? '' : 's'}
              {listFromCache ? (
                <span className="ml-1 text-amber-700/90" title={listCachedAt || ''}>
                  · cached (Refresh for live Meta)
                </span>
              ) : listCachedAt ? (
                <span className="ml-1">· live from Meta</span>
              ) : null}
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
                      <span className="text-amber-700">
                        {r.cleanup_eligible
                          ? `old version → local ${r.superseded_by_local || 'newer'}`
                          : 'no local row'}
                      </span>
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
                    Utility copy must confirm a recent visit/stay/service — not promote an offer. Local lint is a guide;
                    Meta still decides APPROVED vs MARKETING after Push.
                  </span>
                </label>
                {regenDiff ? (
                  <div className="rounded-md border bg-muted/30 p-2 text-[11px]">
                    <div className="mb-1 font-semibold uppercase tracking-wide text-muted-foreground">
                      Regenerate result {regenDiff.changed ? '(changed)' : '(unchanged)'}
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <div>
                        <div className="mb-0.5 text-muted-foreground">Before</div>
                        <div className="whitespace-pre-wrap rounded border bg-background p-1.5 text-xs">{regenDiff.old_body || '—'}</div>
                        {(regenDiff.old_buttons || []).length ? (
                          <div className="mt-1 text-[10px] text-muted-foreground">
                            Buttons: {(regenDiff.old_buttons || []).join(' · ')}
                          </div>
                        ) : null}
                      </div>
                      <div>
                        <div className="mb-0.5 text-muted-foreground">After</div>
                        <div className="whitespace-pre-wrap rounded border bg-background p-1.5 text-xs">{regenDiff.new_body || '—'}</div>
                        {(regenDiff.new_buttons || []).length ? (
                          <div className="mt-1 text-[10px] text-muted-foreground">
                            Buttons: {(regenDiff.new_buttons || []).join(' · ')}
                            {regenDiff.buttons_changed ? ' (updated)' : ''}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </div>
                ) : null}
                {lintInfo ? (
                  <div
                    className={cn(
                      'rounded-md border px-2 py-1.5 text-[11px]',
                      lintInfo.ok ? 'border-emerald-200 bg-emerald-50 text-emerald-900' : 'border-red-200 bg-red-50 text-red-900',
                    )}
                  >
                    <div className="font-semibold">Local Utility lint: {lintInfo.ok ? 'PASS' : 'FAIL'}</div>
                    {!lintInfo.ok && Array.isArray(lintInfo.issues) ? (
                      <ul className="mt-1 list-disc pl-4">
                        {lintInfo.issues.slice(0, 6).map((issue, idx) => (
                          <li key={idx}>{issue.message || issue.code || String(issue)}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-0.5 text-muted-foreground">
                        Passes our Meta Utility checks (no promo/recommend-to-others wording; ties to a recent interaction).
                        Meta can still reclassify after review.
                      </p>
                    )}
                  </div>
                ) : null}
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
          <div className="w-full max-w-lg rounded-xl border bg-background p-5 shadow-lg">
            <h4 className="text-sm font-semibold">{overlay.title}</h4>
            <p className="mt-0.5 break-all font-mono text-[11px] text-muted-foreground">{overlay.sub}</p>
            {overlay.progress ? (
              <div className="mt-3">
                <div className="mb-1 flex justify-between text-[11px] text-muted-foreground">
                  <span>
                    {overlay.progress.done} / {overlay.progress.total}
                  </span>
                  <span>{overlay.progress.pct}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-emerald-500 transition-all duration-300"
                    style={{ width: `${Math.min(100, Math.max(0, overlay.progress.pct || 0))}%` }}
                  />
                </div>
              </div>
            ) : null}
            <div className="mt-4 space-y-2">
              {(overlay.steps || []).map((s) => (
                <div key={s.id} className="flex gap-2 text-xs">
                  <span
                    className={cn(
                      'mt-0.5 h-2 w-2 shrink-0 rounded-full',
                      s.status === 'done' && 'bg-emerald-500',
                      s.status === 'error' && 'bg-red-500',
                      s.status === 'active' && 'animate-pulse bg-amber-500',
                      s.status === 'pending' && 'bg-muted-foreground/40',
                    )}
                  />
                  <div className="min-w-0">
                    <div className="font-medium">{s.title}</div>
                    {s.detail ? <div className="break-all text-muted-foreground">{s.detail}</div> : null}
                  </div>
                </div>
              ))}
            </div>
            {Array.isArray(overlay.log) && overlay.log.length ? (
              <div className="mt-3 max-h-40 overflow-y-auto rounded-md border bg-muted/30 p-2 text-[11px]">
                {overlay.log.map((row, idx) => (
                  <div key={`${row.name}-${idx}`} className="mb-1 last:mb-0">
                    <span className={row.ok ? 'text-emerald-700' : 'text-red-700'}>{row.ok ? '✓' : '✗'}</span>{' '}
                    <span className="font-mono">{row.name}</span>
                    {row.detail ? <span className="text-muted-foreground"> — {row.detail}</span> : null}
                  </div>
                ))}
              </div>
            ) : null}
            <div className="mt-4 flex justify-end">
              <Button type="button" size="sm" variant="outline" onClick={() => setOverlay(null)} disabled={busy === 'cleanup'}>
                {busy === 'cleanup' ? 'Working…' : 'Close'}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
