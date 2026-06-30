import React, { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Pencil, RefreshCw, Check, Ban, Trash2 } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { Panel } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Pill } from '@/components/ui/Badge'
import { Switch } from '@/components/ui/Switch'
import {
  StripeTable,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'

function rowBadge(row) {
  if (!row?.is_active) return <Pill tone="neutral">Disabled</Pill>
  const s = String(row?.status || 'draft').toLowerCase()
  if (['approved', 'synced', 'live', 'active'].includes(s)) {
    return <Pill tone="success">Approved</Pill>
  }
  return <Pill tone="warning">Draft</Pill>
}

export default function FeedbackIndustryEdit() {
  const { industryId } = useParams()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [item, setItem] = useState(null)

  const load = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      const data = await apiFetch(`/admin/customer-feedback/industries/${industryId}`)
      setItem(data?.item || null)
    } catch (e) {
      setError(e?.message || 'Could not load industry')
    } finally {
      setLoading(false)
    }
  }, [industryId])

  useEffect(() => {
    load()
  }, [load])

  const save = async () => {
    if (!item) return
    setBusy(true)
    setError('')
    try {
      await apiFetch('/admin/customer-feedback/industries', {
        method: 'POST',
        body: JSON.stringify(item),
      })
      setMsg('Saved.')
      await load()
    } catch (e) {
      setError(e?.message || 'Could not save')
    } finally {
      setBusy(false)
    }
  }

  const syncTelnyx = async () => {
    setBusy(true)
    setError('')
    try {
      const data = await apiFetch(`/admin/customer-feedback/industries/${industryId}/sync-telnyx`, { method: 'POST' })
      const approved = data?.approved ?? data?.refresh?.approved ?? 0
      const pending = data?.pending ?? data?.refresh?.pending ?? 0
      const pushed = data?.pushed ?? data?.push?.pushed ?? 0
      const linked = data?.linked ?? data?.push?.linked ?? 0
      const failed = data?.failed ?? data?.push?.failed ?? 0
      const parts = []
      if (pushed) parts.push(`${pushed} pushed${linked ? ` (${linked} already on Meta)` : ''}`)
      if (approved) parts.push(`${approved} approved in DB`)
      if (pending) parts.push(`${pending} pending Meta review`)
      if (failed) parts.push(`${failed} failed`)
      setMsg(parts.length ? parts.join(' · ') : (data?.message || 'Templates synced with Telnyx.'))
      await load()
    } catch (e) {
      setError(e?.message || 'Sync failed')
    } finally {
      setBusy(false)
    }
  }

  const addType = async () => {
    const name = window.prompt('Survey type name')
    if (!name?.trim()) return
    setBusy(true)
    try {
      await apiFetch('/admin/customer-feedback/survey-types', {
        method: 'POST',
        body: JSON.stringify({ industry_id: industryId, name: name.trim() }),
      })
      await load()
    } catch (e) {
      setError(e?.message || 'Could not add survey type')
    } finally {
      setBusy(false)
    }
  }

  const syncType = async (row) => {
    setBusy(true)
    setError('')
    try {
      const data = await apiFetch(`/admin/customer-feedback/survey-types/${row.id}/sync-telnyx`, { method: 'POST' })
      setMsg(`Sync queued for “${row.name}” · ${data?.submitted ?? 0} template(s) submitted.`)
      await load()
    } catch (e) {
      setError(e?.message || 'Sync failed')
    } finally {
      setBusy(false)
    }
  }

  const toggleType = async (row) => {
    setBusy(true)
    setError('')
    try {
      await apiFetch('/admin/customer-feedback/survey-types', {
        method: 'POST',
        body: JSON.stringify({ id: row.id, industry_id: industryId, is_active: !row.is_active }),
      })
      setMsg(`“${row.name}” ${row.is_active ? 'disabled' : 'enabled'}.`)
      await load()
    } catch (e) {
      setError(e?.message || 'Could not update survey type')
    } finally {
      setBusy(false)
    }
  }

  const removeType = async (row) => {
    if (!window.confirm(`Remove survey type “${row.name}”? It will be archived (reversible).`)) return
    setBusy(true)
    setError('')
    try {
      await apiFetch('/admin/customer-feedback/survey-types', {
        method: 'POST',
        body: JSON.stringify({ id: row.id, industry_id: industryId, archive: true }),
      })
      setMsg(`“${row.name}” removed.`)
      await load()
    } catch (e) {
      setError(e?.message || 'Could not remove survey type')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="ds-scope">
        <Panel>
          <div className="text-[12px] text-muted-foreground">Loading…</div>
        </Panel>
      </div>
    )
  }

  if (!item) {
    return (
      <div className="ds-scope">
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error || 'Industry not found'}
        </div>
      </div>
    )
  }

  const surveyTypes = (item.survey_types || []).filter((row) => !row.archived_at)

  return (
    <div className="ds-scope space-y-4">
      <Link to="/customer-feedback/industries" className="inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground">
        ← <span>Industries</span>
      </Link>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>
      ) : null}
      {msg ? (
        <div className="rounded-md border border-success/40 bg-success-soft px-3 py-2 text-sm text-success">{msg}</div>
      ) : null}

      <Panel
        title="Industry details"
        action={
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="sm" className="h-8" disabled={busy} onClick={syncTelnyx}>
              <RefreshCw size={14} /> Sync all templates (Telnyx)
            </Button>
            <Button type="button" size="sm" className="h-8" disabled={busy} onClick={save}>
              Save changes
            </Button>
          </div>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label className="text-[12px]">Name</Label>
            <Input className="h-8" value={item.name || ''} onChange={(e) => setItem((f) => ({ ...f, name: e.target.value }))} />
          </div>
          <div className="space-y-1">
            <Label className="text-[12px]">Slug</Label>
            <Input className="h-8" value={item.slug || ''} onChange={(e) => setItem((f) => ({ ...f, slug: e.target.value }))} />
          </div>
          <div className="space-y-1">
            <Label className="text-[12px]">Sort order</Label>
            <Input className="h-8" type="number" value={item.sort_order ?? 100} onChange={(e) => setItem((f) => ({ ...f, sort_order: Number(e.target.value) }))} />
          </div>
          <div className="space-y-1">
            <Label className="text-[12px]">Description</Label>
            <Input className="h-8" value={item.description || ''} onChange={(e) => setItem((f) => ({ ...f, description: e.target.value }))} placeholder="Optional…" />
          </div>
          <div className="flex items-center gap-2 text-[12px]">
            <Switch checked={Boolean(item.is_active)} onCheckedChange={(v) => setItem((f) => ({ ...f, is_active: v }))} />
            <span className="text-muted-foreground">{item.is_active ? 'Active' : 'Inactive'}</span>
          </div>
        </div>
      </Panel>

      <Panel
        title="Survey types"
        action={
          <Button type="button" size="sm" className="h-8" onClick={addType}>
            + Add type
          </Button>
        }
      >
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Survey type</TableHead>
              <TableHead>Templates</TableHead>
              <TableHead>Approved</TableHead>
              <TableHead>Pending</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {surveyTypes.map((row) => {
              const disabled = !row.is_active
              return (
                <TableRow key={row.id} className={disabled ? 'opacity-45' : undefined}>
                  <TableCell><strong className="font-medium">{row.name}</strong></TableCell>
                  <TableCell>
                    <button
                      type="button"
                      className="text-info hover:underline"
                      onClick={() => navigate(`/customer-feedback/survey-types/${row.id}`)}
                    >
                      {row.template_count ?? 0}
                    </button>
                  </TableCell>
                  <TableCell>{row.approved_count ?? 0}</TableCell>
                  <TableCell>{row.pending_count ?? 0}</TableCell>
                  <TableCell>{rowBadge(row)}</TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-0.5">
                      <Button type="button" variant="ghost" size="sm" className="h-7 w-7 px-0" title="Open" onClick={() => navigate(`/customer-feedback/survey-types/${row.id}`)}>
                        <Pencil size={14} />
                      </Button>
                      <Button type="button" variant="ghost" size="sm" className="h-7 w-7 px-0" title="Sync (Telnyx)" disabled={busy} onClick={() => syncType(row)}>
                        <RefreshCw size={14} />
                      </Button>
                      <Button type="button" variant="ghost" size="sm" className="h-7 w-7 px-0" title={disabled ? 'Enable' : 'Disable'} disabled={busy} onClick={() => toggleType(row)}>
                        {disabled ? <Check size={14} /> : <Ban size={14} />}
                      </Button>
                      <Button type="button" variant="ghost" size="sm" className="h-7 w-7 px-0 text-destructive hover:text-destructive" title="Remove" disabled={busy} onClick={() => removeType(row)}>
                        <Trash2 size={14} />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              )
            })}
            {!surveyTypes.length ? <TableEmpty colSpan={6}>No survey types yet.</TableEmpty> : null}
          </TableBody>
        </StripeTable>
      </Panel>
    </div>
  )
}
