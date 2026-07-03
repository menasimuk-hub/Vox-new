import React, { useCallback, useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import { apiFetch } from '../../lib/api'
import { formatActionSuccess, formatWaSurveyError } from '../../lib/waSurveyFeedback'
import WaTemplatesTable from './WaTemplatesTable'
import WaTemplatesSystemSection from './WaTemplatesSystemSection'
import { toHubRow } from './waTemplatesUi'

function industryHealthClass(ind) {
  const health = ind.approval_health
  if (health === 'approved') return 'border-success/40 bg-success/5'
  if (health === 'rejected') return 'border-destructive/40 bg-destructive/5'
  if (health === 'pending') return 'border-warning/40 bg-warning-soft/40'
  return 'bg-surface'
}

function industryHealthDot(ind) {
  const health = ind.approval_health
  if (health === 'approved') return 'bg-success'
  if (health === 'rejected') return 'bg-destructive'
  if (health === 'pending') return 'bg-warning'
  return 'bg-muted-foreground/40'
}

function industryHealthLabel(ind) {
  const health = ind.approval_health
  if (health === 'approved') return 'All approved'
  if (health === 'rejected') return 'Some rejected'
  if (health === 'pending') return 'Pending approval'
  return 'No templates'
}

function AddIndustryModal({ open, product, industry, onClose, onSaved, onError }) {
  const isEdit = Boolean(industry?.id)
  const [saving, setSaving] = useState(false)
  const [orgs, setOrgs] = useState([])
  const [form, setForm] = useState({
    name: '',
    slug: '',
    description: '',
    sort_order: 100,
    is_active: true,
    visibility_mode: 'all',
    org_ids: [],
  })

  useEffect(() => {
    if (!open) return
    if (isEdit) {
      setForm({
        name: industry.name || '',
        slug: industry.slug || '',
        description: industry.description || '',
        sort_order: industry.sort_order ?? 100,
        is_active: industry.is_active !== false,
        visibility_mode: industry.visibility_mode === 'restricted' ? 'restricted' : 'all',
        org_ids: Array.isArray(industry.org_ids) ? industry.org_ids.map(String) : [],
      })
    } else {
      setForm({
        name: '',
        slug: '',
        description: '',
        sort_order: 100,
        is_active: true,
        visibility_mode: 'all',
        org_ids: [],
      })
    }
    apiFetch('/admin/organisations?limit=500')
      .then((data) => {
        const list = Array.isArray(data) ? data : Array.isArray(data?.items) ? data.items : []
        setOrgs(list)
      })
      .catch(() => setOrgs([]))
  }, [open, isEdit, industry, product])

  if (!open) return null

  const toggleOrg = (id) => {
    const oid = String(id)
    setForm((prev) => {
      const has = prev.org_ids.includes(oid)
      return {
        ...prev,
        org_ids: has ? prev.org_ids.filter((x) => x !== oid) : [...prev.org_ids, oid],
      }
    })
  }

  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      const visibility_mode = form.visibility_mode === 'restricted' ? 'restricted' : 'all'
      const body = {
        name: form.name.trim(),
        slug: form.slug.trim() || undefined,
        description: form.description.trim() || undefined,
        sort_order: Number(form.sort_order) || 100,
        is_active: Boolean(form.is_active),
        visibility_mode,
        org_ids: visibility_mode === 'restricted' ? form.org_ids : [],
      }
      if (product === 'feedback') {
        const path = isEdit
          ? `/admin/customer-feedback/industries/${industry.id}`
          : '/admin/customer-feedback/industries'
        await apiFetch(path, {
          method: isEdit ? 'PUT' : 'POST',
          body: JSON.stringify(body),
        })
      } else if (isEdit) {
        await apiFetch(`/admin/wa-survey/industries/${industry.id}`, {
          method: 'PUT',
          body: JSON.stringify(body),
        })
      } else {
        await apiFetch('/admin/wa-survey/industries', {
          method: 'POST',
          body: JSON.stringify(body),
        })
      }
      onSaved?.(isEdit ? 'Industry updated' : 'Industry added')
      onClose()
    } catch (err) {
      onError?.(formatWaSurveyError(err, isEdit ? 'Could not update industry' : 'Could not add industry').message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4" role="presentation" onClick={onClose}>
      <form
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border bg-surface p-4 shadow-lg"
        role="dialog"
        aria-modal="true"
        onSubmit={save}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold">{isEdit ? 'Edit industry' : 'Add industry'}</h3>
        <p className="mt-1 text-[11px] text-muted-foreground">Saved to the database immediately.</p>
        <div className="mt-3 space-y-3">
          <label className="block space-y-1">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground">Name</span>
            <input
              className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
          </label>
          <label className="block space-y-1">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground">Slug (optional)</span>
            <input
              className="h-8 w-full rounded-md border border-input bg-background px-2 font-mono text-xs"
              value={form.slug}
              onChange={(e) => setForm({ ...form, slug: e.target.value })}
            />
          </label>
          <label className="block space-y-1">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground">Description</span>
            <input
              className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </label>
          <div className="space-y-1.5">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground">Who can see this industry</span>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className={cn(
                  'h-7 rounded-md border px-2.5 text-[11px] font-medium',
                  form.visibility_mode === 'all'
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-input bg-background text-muted-foreground',
                )}
                onClick={() => setForm({ ...form, visibility_mode: 'all', org_ids: [] })}
              >
                All organisations
              </button>
              <button
                type="button"
                className={cn(
                  'h-7 rounded-md border px-2.5 text-[11px] font-medium',
                  form.visibility_mode === 'restricted'
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-input bg-background text-muted-foreground',
                )}
                onClick={() => setForm({ ...form, visibility_mode: 'restricted' })}
              >
                Selected organisations only
              </button>
            </div>
            <p className="text-[10px] text-muted-foreground">
              Restricted industries are only visible to the organisations you select (and their users).
            </p>
          </div>
          {form.visibility_mode === 'restricted' ? (
            <div className="max-h-40 space-y-1 overflow-y-auto rounded-md border p-2">
              {orgs.length === 0 ? (
                <p className="text-[11px] text-muted-foreground">No organisations found.</p>
              ) : (
                orgs.map((org) => {
                  const oid = String(org.id)
                  const checked = form.org_ids.includes(oid)
                  return (
                    <label key={oid} className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-xs hover:bg-accent/40">
                      <input type="checkbox" checked={checked} onChange={() => toggleOrg(oid)} />
                      <span className="truncate">{org.name || org.trading_name || org.email || oid}</span>
                    </label>
                  )
                })
              )}
            </div>
          ) : null}
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" className="h-8 text-xs" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" className="h-8 text-xs" disabled={saving}>
            {saving ? 'Saving…' : isEdit ? 'Save changes' : 'Add industry'}
          </Button>
        </div>
      </form>
    </div>
  )
}

async function loadSurveyTemplatesForIndustry(industryId) {
  // Single endpoint includes rejected templates (even if mapping was lost).
  const data = await apiFetch(`/admin/wa-survey/industries/${encodeURIComponent(industryId)}/templates`)
  const templates = Array.isArray(data?.templates) ? data.templates : []
  const unlinkedTypes = Array.isArray(data?.unlinked_types) ? data.unlinked_types : []
  const rows = templates.map((tpl) =>
    toHubRow(tpl, {
      rowKind: 'survey_template',
      product: 'survey',
      surveyTypeId: tpl.survey_type_id,
      surveyTypeName: tpl.survey_type_name,
      name: tpl.display_name || tpl.name || tpl.survey_type_name,
      rejectionReason: tpl.rejection_reason,
      languageCount: tpl.language_count || (tpl.languages || []).length || 1,
      languages: tpl.languages || [],
    }),
  )
  rows.sort((a, b) => {
    if (a.status === 'disabled' && b.status !== 'disabled') return 1
    if (b.status === 'disabled' && a.status !== 'disabled') return -1
    if (a.status === 'rejected' && b.status !== 'rejected') return -1
    if (b.status === 'rejected' && a.status !== 'rejected') return 1
    return String(a.name).localeCompare(String(b.name))
  })
  return { rows, unlinkedTypes }
}

async function loadFeedbackTemplatesForIndustry(industryId) {
  // One primary template per survey type (English preferred) — avoids en/ar duplicates.
  const data = await apiFetch(
    `/admin/customer-feedback/industries/${encodeURIComponent(industryId)}/templates`,
  )
  const templates = Array.isArray(data?.templates) ? data.templates : []
  const unlinkedTypes = Array.isArray(data?.unlinked_types) ? data.unlinked_types : []
  const seen = new Set()
  const rows = []
  for (const tpl of templates) {
    const id = String(tpl.id || '')
    if (!id || seen.has(id)) continue
    seen.add(id)
    rows.push(
      toHubRow(
        {
          ...tpl,
          body: tpl.body_text || tpl.body,
          status: tpl.telnyx_sync_status || tpl.status,
          approval_status: tpl.approval_status || tpl.telnyx_sync_status || tpl.status,
          buttons: Array.isArray(tpl.buttons) ? tpl.buttons : [],
        },
        {
          rowKind: 'feedback_template',
          product: 'feedback',
          surveyTypeId: tpl.survey_type_id,
          surveyTypeName: tpl.survey_type_name,
          name: tpl.display_name || tpl.name || tpl.survey_type_name || tpl.template_key || tpl.id,
          languageCount: tpl.language_count || 1,
          languages: tpl.languages || [tpl.language].filter(Boolean),
        },
      ),
    )
  }
  rows.sort((a, b) => {
    if (a.status === 'rejected' && b.status !== 'rejected') return -1
    if (b.status === 'rejected' && a.status !== 'rejected') return 1
    return String(a.name).localeCompare(String(b.name))
  })
  return { rows, unlinkedTypes }
}

export default function WaIndustryBrowser({
  product,
  industries,
  loadingIndustries,
  onReloadIndustries,
  onEditRow,
  onSyncRow,
  onToggleRow,
  onDeleteRow,
  onRejectRow,
  syncingId,
  onOpenSystemTemplate,
  onError,
  onMessage,
}) {
  const [industry, setIndustry] = useState(null)
  const [rows, setRows] = useState([])
  const [unlinkedTypes, setUnlinkedTypes] = useState([])
  const [loadingRows, setLoadingRows] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [editIndustry, setEditIndustry] = useState(null)
  const [industrySyncing, setIndustrySyncing] = useState(false)
  const [deletingIndustry, setDeletingIndustry] = useState(false)

  const loadIndustryRows = useCallback(
    async (ind) => {
      setLoadingRows(true)
      try {
        const next =
          product === 'survey'
            ? await loadSurveyTemplatesForIndustry(ind.id)
            : await loadFeedbackTemplatesForIndustry(ind.id)
        setRows(next.rows)
        setUnlinkedTypes(next.unlinkedTypes)
      } catch (e) {
        onError?.(formatWaSurveyError(e, 'Could not load templates').message)
        setRows([])
        setUnlinkedTypes([])
      } finally {
        setLoadingRows(false)
      }
    },
    [product, onError],
  )

  const openIndustry = (ind) => {
    setIndustry(ind)
    void loadIndustryRows(ind)
  }

  const typeCountLabel = (ind) => {
    const n = ind.survey_type_count ?? ind.template_count
    if (n != null) return `${n} types`
    return 'Open'
  }

  const syncIndustry = async () => {
    if (!industry?.id) return
    setIndustrySyncing(true)
    try {
      const path =
        product === 'feedback'
          ? `/admin/customer-feedback/industries/${industry.id}/sync-telnyx`
          : `/admin/wa-survey/industries/${industry.id}/templates/push-all`
      // Labels say Meta; endpoints keep legacy paths for compatibility.
      const result = await apiFetch(path, { method: 'POST', body: '{}', timeoutMs: 300000, quietNetworkHint: true })
      onMessage?.(formatActionSuccess(result, `Synced ${industry.name} with Meta`).message)
      await loadIndustryRows(industry)
      onReloadIndustries?.()
    } catch (e) {
      onError?.(formatWaSurveyError(e, 'Industry sync failed').detailText || e?.message)
    } finally {
      setIndustrySyncing(false)
    }
  }

  const deleteIndustry = async () => {
    if (!industry?.id) return
    if (
      !window.confirm(
        `Delete industry “${industry.name}” and ALL its templates from local DB and Meta? This cannot be undone.`,
      )
    ) {
      return
    }
    setDeletingIndustry(true)
    try {
      const path =
        product === 'feedback'
          ? `/admin/customer-feedback/industries/${industry.id}`
          : `/admin/wa-survey/industries/${industry.id}`
      const result = await apiFetch(path, { method: 'DELETE', timeoutMs: 180000, quietNetworkHint: true })
      onMessage?.(
        formatActionSuccess(
          result,
          `Deleted industry and ${result.deleted_templates ?? 0} template(s)`,
        ).message,
      )
      setIndustry(null)
      onReloadIndustries?.()
    } catch (e) {
      onError?.(formatWaSurveyError(e, 'Could not delete industry').message)
    } finally {
      setDeletingIndustry(false)
    }
  }

  if (industry) {
    const rejectedCount = rows.filter((r) => r.status === 'rejected').length
    const approvedCount = rows.filter((r) => r.status === 'approved').length
    const pendingCount = rows.filter((r) => r.status === 'pending' || r.status === 'local').length
    return (
      <div className="animate-fade-in">
        <WaTemplatesSystemSection
          product={product}
          embedded
          onOpenTemplate={onOpenSystemTemplate}
        />
        <div className="flex flex-wrap items-center gap-2 border-b bg-surface-muted/40 px-3 py-2">
          <Button variant="ghost" size="sm" className="-ml-2 h-7 gap-1 text-xs" onClick={() => setIndustry(null)}>
            <ChevronLeft className="h-3.5 w-3.5" /> Industries
          </Button>
          <ChevronRight className="h-3 w-3 text-muted-foreground" />
          <span className="text-sm font-medium">{industry.name}</span>
          <span className="text-xs text-muted-foreground">· {rows.length} linked templates</span>
          <span className="text-xs text-success">· {approvedCount} approved</span>
          {pendingCount > 0 ? <span className="text-xs text-warning">· {pendingCount} pending</span> : null}
          {rejectedCount > 0 ? (
            <span className="text-xs font-medium text-destructive">· {rejectedCount} rejected — fix</span>
          ) : null}
          <div className="ml-auto flex items-center gap-1.5">
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1 text-xs"
              disabled={industrySyncing || deletingIndustry}
              onClick={async () => {
                try {
                  if (product === 'survey') {
                    const detail = await apiFetch(`/admin/wa-survey/industries/${industry.id}`)
                    setEditIndustry(detail?.industry || industry)
                  } else {
                    setEditIndustry(industry)
                  }
                } catch {
                  setEditIndustry(industry)
                }
              }}
            >
              Edit visibility
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1 text-xs"
              disabled={industrySyncing || deletingIndustry}
              onClick={() => void syncIndustry()}
            >
              <RefreshCw className={cn('h-3.5 w-3.5', industrySyncing && 'animate-spin')} />
              {industrySyncing ? 'Syncing industry…' : 'Sync this industry'}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 gap-1 text-xs text-destructive hover:bg-destructive/10 hover:text-destructive"
              disabled={industrySyncing || deletingIndustry}
              onClick={() => void deleteIndustry()}
            >
              <Trash2 className="h-3.5 w-3.5" />
              {deletingIndustry ? 'Deleting…' : 'Delete industry'}
            </Button>
          </div>
        </div>
        {unlinkedTypes.length > 0 ? (
          <div className="border-b bg-warning-soft/40 px-3 py-2 text-[11px] text-muted-foreground">
            <span className="font-medium text-foreground">
              {unlinkedTypes.length} survey type(s) have no WA templates linked.
            </span>{' '}
            Use <span className="font-medium text-foreground">Sync this industry</span> or the hub{' '}
            <span className="font-medium text-foreground">Sync with Meta</span> button — do not sync types one-by-one.
          </div>
        ) : null}
        <WaTemplatesTable
          templates={rows}
          loading={loadingRows}
          onEdit={onEditRow}
          onSync={onSyncRow}
          onToggle={async (row) => {
            await onToggleRow?.(row)
            if (industry) await loadIndustryRows(industry)
          }}
          onDelete={async (row) => {
            await onDeleteRow?.(row)
            if (industry) await loadIndustryRows(industry)
          }}
          onReject={onRejectRow}
          syncingId={syncingId}
          plainNames
          showNew={false}
          emptyLabel="No WhatsApp templates linked in this industry yet. Click Rejected filter if you expected rejected rows."
        />
      </div>
    )
  }

  return (
    <div className="animate-fade-in">
      <WaTemplatesSystemSection
        product={product}
        embedded
        onOpenTemplate={onOpenSystemTemplate}
      />
      <div className="p-3">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <div className="text-sm font-medium">Choose an industry</div>
            <div className="text-xs text-muted-foreground">
              {industries.length} industries · Click to open templates
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">{industries.length} industries</span>
            <Button size="sm" variant="outline" className="h-8 gap-1.5 text-xs" onClick={() => setAddOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> Add industry
            </Button>
          </div>
        </div>
        {loadingIndustries ? (
          <p className="py-8 text-center text-xs text-muted-foreground">Loading industries…</p>
        ) : !industries.length ? (
          <p className="py-8 text-center text-xs text-muted-foreground">No industries yet.</p>
        ) : (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
            {industries.map((ind, i) => (
              <button
                key={ind.id}
                type="button"
                onClick={() => openIndustry(ind)}
                className={cn(
                  'group relative flex items-center justify-between rounded-lg border px-3 py-2.5 text-left',
                  'transition-all hover:shadow-sm hover-scale',
                  industryHealthClass(ind),
                )}
                style={{ animation: `wa-hub-fade-in 0.25s ease-out ${i * 15}ms both` }}
                title={industryHealthLabel(ind)}
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className={cn('h-2 w-2 shrink-0 rounded-full', industryHealthDot(ind))} />
                    <div className="truncate text-sm font-medium">{ind.name}</div>
                  </div>
                  <div className="mt-0.5 text-[11px] text-muted-foreground">{typeCountLabel(ind)}</div>
                  <div className="mt-0.5 text-[10px] text-muted-foreground">{industryHealthLabel(ind)}</div>
                  {ind.visibility_mode === 'restricted' ? (
                    <div className="mt-0.5 text-[10px] font-medium text-primary">
                      {(ind.org_ids || []).length === 1
                        ? '1 organisation only'
                        : `${(ind.org_ids || []).length} organisations only`}
                    </div>
                  ) : null}
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-primary" />
              </button>
            ))}
          </div>
        )}
      </div>
      <AddIndustryModal
        open={addOpen || Boolean(editIndustry)}
        product={product}
        industry={editIndustry}
        onClose={() => {
          setAddOpen(false)
          setEditIndustry(null)
        }}
        onSaved={(message) => {
          onMessage?.(message || 'Industry saved')
          onReloadIndustries?.()
          if (editIndustry && industry?.id === editIndustry.id) {
            // refresh open industry card data from list after edit
            onReloadIndustries?.()
          }
        }}
        onError={onError}
      />
    </div>
  )
}
