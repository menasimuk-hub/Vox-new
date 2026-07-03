import React, { useCallback, useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Plus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import { apiFetch } from '../../lib/api'
import { formatWaSurveyError } from '../../lib/waSurveyFeedback'
import WaTemplatesTable from './WaTemplatesTable'
import WaTemplatesSystemSection from './WaTemplatesSystemSection'
import { toHubRow } from './waTemplatesUi'

function AddIndustryModal({ open, product, onClose, onSaved, onError }) {
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({ name: '', slug: '', description: '', sort_order: 100, is_active: true })

  useEffect(() => {
    if (open) setForm({ name: '', slug: '', description: '', sort_order: 100, is_active: true })
  }, [open])

  if (!open) return null

  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      const path =
        product === 'feedback' ? '/admin/customer-feedback/industries' : '/admin/wa-survey/industries'
      const body =
        product === 'feedback'
          ? { name: form.name.trim(), slug: form.slug.trim() || undefined, is_active: form.is_active }
          : {
              name: form.name.trim(),
              slug: form.slug.trim() || undefined,
              description: form.description.trim() || undefined,
              sort_order: Number(form.sort_order) || 100,
              is_active: Boolean(form.is_active),
              visibility_mode: 'all',
              org_ids: [],
            }
      await apiFetch(path, { method: 'POST', body: JSON.stringify(body) })
      onSaved?.()
      onClose()
    } catch (err) {
      onError?.(formatWaSurveyError(err, 'Could not add industry').message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4" role="presentation" onClick={onClose}>
      <form
        className="w-full max-w-md rounded-xl border bg-surface p-4 shadow-lg"
        role="dialog"
        aria-modal="true"
        onSubmit={save}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold">Add industry</h3>
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
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" className="h-8 text-xs" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" className="h-8 text-xs" disabled={saving}>
            {saving ? 'Saving…' : 'Add industry'}
          </Button>
        </div>
      </form>
    </div>
  )
}

async function loadSurveyTemplatesForIndustry(industryId) {
  const data = await apiFetch(`/admin/wa-survey/types?industry_id=${encodeURIComponent(industryId)}`)
  const types = Array.isArray(data?.types) ? data.types : []
  const rows = []
  await Promise.all(
    types.map(async (type) => {
      try {
        const detail = await apiFetch(`/admin/wa-survey/types/${encodeURIComponent(type.id)}`)
        const templates = Array.isArray(detail?.templates) ? detail.templates : []
        if (templates.length) {
          for (const tpl of templates) {
            rows.push(
              toHubRow(tpl, {
                rowKind: 'survey_template',
                product: 'survey',
                surveyTypeId: type.id,
                surveyTypeName: type.name,
                name: tpl.name || tpl.display_name,
              }),
            )
          }
        } else {
          rows.push(
            toHubRow(type, {
              rowKind: 'survey_type',
              product: 'survey',
              surveyTypeId: type.id,
              name: type.slug || type.name,
              used: type.template_count ?? 0,
            }),
          )
        }
      } catch {
        rows.push(
          toHubRow(type, {
            rowKind: 'survey_type',
            product: 'survey',
            surveyTypeId: type.id,
            name: type.slug || type.name,
          }),
        )
      }
    }),
  )
  rows.sort((a, b) => String(a.name).localeCompare(String(b.name)))
  return rows
}

async function loadFeedbackTemplatesForIndustry(industryId) {
  const data = await apiFetch(`/admin/customer-feedback/industries/${encodeURIComponent(industryId)}`)
  const types = Array.isArray(data?.item?.survey_types) ? data.item.survey_types : []
  const rows = []
  await Promise.all(
    types.map(async (type) => {
      try {
        const detail = await apiFetch(`/admin/customer-feedback/survey-types/${encodeURIComponent(type.id)}`)
        const templates = Array.isArray(detail?.item?.templates) ? detail.item.templates : []
        if (templates.length) {
          for (const tpl of templates) {
            rows.push(
              toHubRow(
                { ...tpl, body: tpl.body_text, status: tpl.telnyx_sync_status || tpl.status },
                {
                  rowKind: 'feedback_template',
                  product: 'feedback',
                  surveyTypeId: type.id,
                  name: tpl.template_key || tpl.name || tpl.id,
                },
              ),
            )
          }
        } else {
          rows.push(
            toHubRow(type, {
              rowKind: 'feedback_type',
              product: 'feedback',
              surveyTypeId: type.id,
              name: type.slug || type.name,
              used: type.template_count ?? 0,
            }),
          )
        }
      } catch {
        rows.push(
          toHubRow(type, {
            rowKind: 'feedback_type',
            product: 'feedback',
            surveyTypeId: type.id,
            name: type.slug || type.name,
          }),
        )
      }
    }),
  )
  rows.sort((a, b) => String(a.name).localeCompare(String(b.name)))
  return rows
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
  onOpenSystemTemplate,
  onError,
  onMessage,
}) {
  const [industry, setIndustry] = useState(null)
  const [rows, setRows] = useState([])
  const [loadingRows, setLoadingRows] = useState(false)
  const [addOpen, setAddOpen] = useState(false)

  const loadIndustryRows = useCallback(
    async (ind) => {
      setLoadingRows(true)
      try {
        const next =
          product === 'survey'
            ? await loadSurveyTemplatesForIndustry(ind.id)
            : await loadFeedbackTemplatesForIndustry(ind.id)
        setRows(next)
      } catch (e) {
        onError?.(formatWaSurveyError(e, 'Could not load templates').message)
        setRows([])
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

  if (industry) {
    return (
      <div className="animate-fade-in">
        <WaTemplatesSystemSection
          product={product}
          embedded
          onOpenTemplate={onOpenSystemTemplate}
        />
        <div className="flex items-center gap-2 border-b bg-surface-muted/40 px-3 py-2">
          <Button variant="ghost" size="sm" className="-ml-2 h-7 gap-1 text-xs" onClick={() => setIndustry(null)}>
            <ChevronLeft className="h-3.5 w-3.5" /> Industries
          </Button>
          <ChevronRight className="h-3 w-3 text-muted-foreground" />
          <span className="text-sm font-medium">{industry.name}</span>
          <span className="text-xs text-muted-foreground">· {rows.length} templates</span>
        </div>
        <WaTemplatesTable
          templates={rows}
          loading={loadingRows}
          onEdit={onEditRow}
          onSync={onSyncRow}
          onToggle={onToggleRow}
          onDelete={onDeleteRow}
          showNew={false}
          emptyLabel="No templates linked in this industry yet."
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
                  'group relative flex items-center justify-between rounded-lg border bg-surface px-3 py-2.5 text-left',
                  'transition-all hover:border-primary/40 hover:shadow-sm hover-scale',
                )}
                style={{ animation: `wa-hub-fade-in 0.25s ease-out ${i * 15}ms both` }}
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{ind.name}</div>
                  <div className="text-[11px] text-muted-foreground">{typeCountLabel(ind)}</div>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-primary" />
              </button>
            ))}
          </div>
        )}
      </div>
      <AddIndustryModal
        open={addOpen}
        product={product}
        onClose={() => setAddOpen(false)}
        onSaved={() => {
          onMessage?.('Industry added')
          onReloadIndustries?.()
        }}
        onError={onError}
      />
    </div>
  )
}
