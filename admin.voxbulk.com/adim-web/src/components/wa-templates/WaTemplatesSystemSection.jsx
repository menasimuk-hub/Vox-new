import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { ChevronRight, Layers, Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Sheet, SheetContent, SheetClose } from '@/components/ui/Sheet'
import { apiFetch } from '../../lib/api'
import { formatWaSurveyError } from '../../lib/waSurveyFeedback'
import WaTemplatesTable from './WaTemplatesTable'
import { toHubRow } from './waTemplatesUi'

const SURVEY_CATEGORIES = [
  { kind: 'welcome', label: 'Welcome' },
  { kind: 'welcome', label: 'Anonymous survey welcome', anonymousOnly: true },
  { kind: 'thank_you', label: 'Thank you' },
  { kind: 'tell_us_more', label: 'Tell us more' },
  { kind: 'final_feedback', label: 'Closing question' },
  { kind: 'welcome', label: 'Quick anonymous survey', anonymousOnly: true },
]

const FEEDBACK_CATEGORIES = [
  { key: 'thank_you', label: 'Thank you' },
  { key: 'tell_us_more', label: 'Tell us more' },
  { key: 'marketing_opt_in', label: 'Opt in' },
  { key: 'open_question', label: 'Share your feedback' },
]

function isAnonymousTemplate(tpl) {
  const variant = String(tpl?.variant_type || '').toLowerCase()
  const privacy = String(tpl?.privacy_mode || '').toLowerCase()
  return variant === 'anonymous' || privacy === 'on'
}

function countForSurveyCategory(section, category) {
  const templates = Array.isArray(section?.templates) ? section.templates : []
  if (category.anonymousOnly) return templates.filter(isAnonymousTemplate).length
  if (category.kind === 'welcome') return templates.filter((t) => !isAnonymousTemplate(t)).length
  return templates.length
}

function templatesForCategory(kinds, product, category) {
  const sectionKey = product === 'feedback' ? category.key : category.kind
  const section = (kinds || []).find((s) => (product === 'feedback' ? s.key : s.kind) === sectionKey)
  let templates = Array.isArray(section?.templates) ? section.templates : []
  if (product === 'survey' && category.anonymousOnly) {
    templates = templates.filter(isAnonymousTemplate)
  } else if (product === 'survey' && category.kind === 'welcome' && !category.anonymousOnly) {
    templates = templates.filter((t) => !isAnonymousTemplate(t))
  }
  return templates.map((tpl) =>
    toHubRow(tpl, {
      rowKind: 'system_template',
      product,
      systemKind: sectionKey,
      name:
        tpl.display_name ||
        tpl.name ||
        tpl.template_key ||
        category.label ||
        'Template',
    }),
  )
}

export default function WaTemplatesSystemSection({ product = 'survey', embedded = false, onOpenTemplate }) {
  const [loading, setLoading] = useState(true)
  const [kinds, setKinds] = useState([])
  const [error, setError] = useState('')
  const [sheetOpen, setSheetOpen] = useState(false)
  const [sheetCategory, setSheetCategory] = useState(null)
  const [sheetRows, setSheetRows] = useState([])
  const [addOpen, setAddOpen] = useState(false)
  const [addKind, setAddKind] = useState(product === 'feedback' ? 'thank_you' : 'welcome')
  const [adding, setAdding] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const path =
        product === 'feedback'
          ? '/admin/customer-feedback/system-templates'
          : '/admin/wa-survey/system-templates'
      const data = await apiFetch(path)
      setKinds(Array.isArray(data?.kinds) ? data.kinds : [])
    } catch (e) {
      setError(e?.message || 'Could not load system templates')
      setKinds([])
    } finally {
      setLoading(false)
    }
  }, [product])

  useEffect(() => {
    void load()
  }, [load])

  const kindMap = useMemo(() => {
    const map = {}
    for (const section of kinds) {
      const key = product === 'feedback' ? section.key : section.kind
      if (key) map[key] = section
    }
    return map
  }, [kinds, product])

  const categories = product === 'feedback' ? FEEDBACK_CATEGORIES : SURVEY_CATEGORIES
  const totalCount = useMemo(() => kinds.reduce((sum, k) => sum + (k.count || 0), 0), [kinds])

  const openCategory = (category) => {
    setSheetCategory(category)
    setSheetRows(templatesForCategory(kinds, product, category))
    setSheetOpen(true)
  }

  const openAll = () => {
    const all = []
    for (const category of categories) {
      all.push(...templatesForCategory(kinds, product, category))
    }
    const seen = new Set()
    const unique = all.filter((r) => {
      if (seen.has(r.id)) return false
      seen.add(r.id)
      return true
    })
    setSheetCategory({ label: 'All system templates' })
    setSheetRows(unique)
    setSheetOpen(true)
  }

  const handleEdit = (row) => {
    setSheetOpen(false)
    onOpenTemplate?.({
      product: product === 'feedback' ? 'feedback' : 'system',
      templateId: row.id,
      surveyTypeId: row.raw?.survey_type_id,
      systemMode: true,
      systemKind: row.systemKind,
    })
  }

  const addSystemTemplate = async (e) => {
    e.preventDefault()
    setAdding(true)
    setError('')
    try {
      if (product === 'feedback') {
        const labels = {
          thank_you: 'Thank you',
          tell_us_more: 'Tell us more',
          marketing_opt_in: 'Opt in',
          open_question: 'Share your feedback',
        }
        const noButtons = ['thank_you', 'tell_us_more', 'open_question'].includes(addKind)
        const bodyText = noButtons
          ? `📋 ${labels[addKind] || 'Thanks for your feedback.'}`
          : `📋 ${labels[addKind] || 'Thanks for your feedback.'} Reply with one option below.`
        const tplRes = await apiFetch('/admin/customer-feedback/wa-templates', {
          method: 'POST',
          body: JSON.stringify({
            template_key: addKind,
            body_text: bodyText,
            language: 'en_GB',
            meta_category: 'utility',
            buttons: noButtons
              ? []
              : [
                  { type: 'QUICK_REPLY', text: 'Excellent' },
                  { type: 'QUICK_REPLY', text: 'Good' },
                  { type: 'QUICK_REPLY', text: 'Poor' },
                ],
            is_active: true,
          }),
        })
        const templateId = tplRes?.item?.id
        setAddOpen(false)
        await load()
        if (templateId) {
          onOpenTemplate?.({
            product: 'feedback',
            templateId,
            systemMode: true,
            systemKind: addKind,
          })
        }
      } else {
        const data = await apiFetch('/admin/wa-survey/system-templates', {
          method: 'POST',
          body: JSON.stringify({
            system_template_kind: addKind,
            category: 'UTILITY',
            language: 'en_GB',
          }),
        })
        const templateId = data?.template?.id
        const surveyTypeId = data?.survey_type_id || data?.template?.survey_type_id
        setAddOpen(false)
        await load()
        if (templateId) {
          onOpenTemplate?.({
            product: 'system',
            templateId,
            surveyTypeId,
            systemMode: true,
            systemKind: addKind,
          })
        }
      }
    } catch (err) {
      setError(formatWaSurveyError(err, 'Could not add system template').message)
    } finally {
      setAdding(false)
    }
  }

  const kindOptions =
    product === 'feedback'
      ? FEEDBACK_CATEGORIES.map((c) => ({ value: c.key, label: c.label }))
      : [
          { value: 'welcome', label: 'Welcome' },
          { value: 'thank_you', label: 'Thank you' },
          { value: 'tell_us_more', label: 'Tell us more' },
          { value: 'final_feedback', label: 'Closing question' },
        ]

  return (
    <>
      <div className={embedded ? 'border-b bg-surface-muted/20 p-3' : 'rounded-lg border bg-surface p-3'}>
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Layers className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold">System templates</h3>
              <p className="mt-0.5 max-w-2xl text-[11px] text-muted-foreground">
                Shared {product === 'feedback' ? 'Customer Feedback' : 'Survey'} WhatsApp templates used across all
                industries.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {totalCount ? (
              <span className="rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                {totalCount} saved
              </span>
            ) : null}
            <Button type="button" variant="outline" size="sm" className="h-8 gap-1 text-xs" onClick={() => setAddOpen(true)}>
              <Plus className="h-3.5 w-3.5" />
              Add template
            </Button>
            <Button type="button" variant="outline" size="sm" className="h-8 text-xs" onClick={openAll}>
              Manage
              <ChevronRight className="ml-1 h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        {error ? <p className="mb-2 text-[11px] text-destructive">{error}</p> : null}

        {loading ? (
          <p className="text-[11px] text-muted-foreground">Loading system template library…</p>
        ) : (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
            {categories.map((category) => {
              const sectionKey = product === 'feedback' ? category.key : category.kind
              const section = kindMap[sectionKey]
              const count =
                product === 'survey'
                  ? countForSurveyCategory(section, category)
                  : section?.count ?? (section?.templates || []).length
              return (
                <button
                  key={`${sectionKey}-${category.label}`}
                  type="button"
                  onClick={() => openCategory(category)}
                  className="inline-flex h-8 items-center justify-between gap-2 rounded-md border bg-background px-2.5 text-left text-xs font-medium shadow-sm transition hover:border-primary/40 hover:bg-accent/40"
                >
                  <span className="truncate">{category.label}</span>
                  <span
                    className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                      count > 0 ? 'bg-success-soft text-success' : 'bg-surface-muted text-muted-foreground'
                    }`}
                  >
                    {count}
                  </span>
                </button>
              )
            })}
          </div>
        )}
      </div>

      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent side="right" className="w-full overflow-hidden border-l p-0 sm:max-w-[720px]">
          <div className="flex h-12 items-center gap-3 border-b bg-surface-muted/50 px-4">
            <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Layers className="h-3.5 w-3.5" />
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">System templates</div>
              <div className="truncate text-[11px] text-muted-foreground">{sheetCategory?.label}</div>
            </div>
            <SheetClose asChild>
              <Button size="sm" variant="ghost" className="ml-auto h-7 gap-1 text-xs">
                <X className="h-3.5 w-3.5" /> Close
              </Button>
            </SheetClose>
          </div>
          <div className="overflow-y-auto">
            <WaTemplatesTable
              templates={sheetRows}
              onEdit={handleEdit}
              onSync={handleEdit}
              onToggle={handleEdit}
              onDelete={async (row) => {
                if (!window.confirm(`Delete “${row.name}”? This removes it from the database and Meta.`)) return
                try {
                  if (product === 'feedback') {
                    await apiFetch(`/admin/customer-feedback/wa-templates/${row.id}`, { method: 'DELETE' })
                  } else {
                    await apiFetch(`/admin/wa-survey/system-templates/${row.id}`, { method: 'DELETE' })
                  }
                  setSheetRows((rows) => rows.filter((r) => String(r.id) !== String(row.id)))
                  await load()
                } catch (e) {
                  setError(formatWaSurveyError(e, 'Delete failed').message)
                }
              }}
              plainNames
              showNew={false}
              emptyLabel="No system templates in this category."
            />
          </div>
        </SheetContent>
      </Sheet>

      {addOpen
        ? createPortal(
            <div
              className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4"
              role="presentation"
              onClick={() => setAddOpen(false)}
            >
              <form
                className="w-full max-w-md rounded-xl border bg-surface shadow-lg"
                role="dialog"
                aria-modal="true"
                onSubmit={addSystemTemplate}
                onClick={(e) => e.stopPropagation()}
              >
                <div className="border-b px-4 py-3">
                  <h3 className="text-sm font-semibold">Add system template</h3>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Creates a new shared Utility template. Edit body and sync to Meta after.
                  </p>
                </div>
                <div className="space-y-3 px-4 py-3">
                  <label className="block space-y-1">
                    <span className="text-[11px] uppercase tracking-wider text-muted-foreground">Category</span>
                    <select
                      className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs"
                      value={addKind}
                      onChange={(e) => setAddKind(e.target.value)}
                    >
                      {kindOptions.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="flex justify-end gap-2 border-t px-4 py-3">
                  <Button type="button" variant="ghost" size="sm" className="h-8 text-xs" onClick={() => setAddOpen(false)}>
                    Cancel
                  </Button>
                  <Button type="submit" size="sm" className="h-8 text-xs" disabled={adding}>
                    {adding ? 'Creating…' : 'Add template'}
                  </Button>
                </div>
              </form>
            </div>,
            document.body,
          )
        : null}
    </>
  )
}
