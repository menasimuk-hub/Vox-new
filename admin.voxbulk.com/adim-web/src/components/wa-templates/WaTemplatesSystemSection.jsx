import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ChevronRight, Layers, Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Sheet, SheetContent, SheetClose } from '@/components/ui/Sheet'
import { apiFetch } from '../../lib/api'
import { formatWaSurveyError } from '../../lib/waSurveyFeedback'
import WaTemplatesTable from './WaTemplatesTable'
import WaSyncConfirmDialog from './WaSyncConfirmDialog'
import { toHubRow } from './waTemplatesUi'

const SURVEY_CATEGORIES = [
  { kind: 'welcome', label: 'Welcome', privacy_mode: 'off' },
  { kind: 'welcome', label: 'Anonymous survey welcome', anonymousOnly: true, privacy_mode: 'on' },
  { kind: 'thank_you', label: 'Thank you', privacy_mode: 'off' },
  { kind: 'tell_us_more', label: 'Tell us more', privacy_mode: 'off' },
  { kind: 'final_feedback', label: 'Closing question', privacy_mode: 'off' },
]

/** Every system card option for Add template (including anonymous welcome). */
const SURVEY_ADD_OPTIONS = [
  { value: 'welcome', label: 'Welcome', kind: 'welcome', privacy_mode: 'off', display_name: 'Welcome' },
  {
    value: 'welcome_anonymous',
    label: 'Anonymous survey welcome',
    kind: 'welcome',
    privacy_mode: 'on',
    display_name: 'Anonymous survey welcome',
  },
  { value: 'thank_you', label: 'Thank you', kind: 'thank_you', privacy_mode: 'off', display_name: 'Thank you' },
  { value: 'tell_us_more', label: 'Tell us more', kind: 'tell_us_more', privacy_mode: 'off', display_name: 'Tell us more' },
  {
    value: 'final_feedback',
    label: 'Closing question',
    kind: 'final_feedback',
    privacy_mode: 'off',
    display_name: 'Closing question',
  },
]

function optionForCategory(category, product) {
  if (product === 'feedback') {
    return { kind: category.key, privacy_mode: 'off', display_name: category.label, value: category.key }
  }
  if (category.anonymousOnly || category.privacy_mode === 'on') {
    return SURVEY_ADD_OPTIONS.find((o) => o.value === 'welcome_anonymous')
  }
  return (
    SURVEY_ADD_OPTIONS.find((o) => o.kind === category.kind && o.privacy_mode === (category.privacy_mode || 'off')) ||
    SURVEY_ADD_OPTIONS.find((o) => o.kind === category.kind)
  )
}

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

export default function WaTemplatesSystemSection({
  product = 'survey',
  embedded = false,
  onOpenTemplate,
  syncProfileId = null,
  syncProfile = null,
  onRequestSyncConfirm,
}) {
  const [loading, setLoading] = useState(true)
  const [kinds, setKinds] = useState([])
  const [error, setError] = useState('')
  const [sheetOpen, setSheetOpen] = useState(false)
  const [sheetCategory, setSheetCategory] = useState(null)
  const [sheetRows, setSheetRows] = useState([])
  const [addOpen, setAddOpen] = useState(false)
  const [addKind, setAddKind] = useState(product === 'feedback' ? 'thank_you' : 'welcome')
  const [adding, setAdding] = useState(false)
  const [syncingId, setSyncingId] = useState(null)
  const [metaSyncSavingId, setMetaSyncSavingId] = useState(null)
  const [syncConfirm, setSyncConfirm] = useState(null)
  const prevSyncProfileRef = useRef(syncProfileId)

  /** Wait for the system-templates list sheet to unmount before opening the hub edit drawer. */
  const openTemplateAfterSheetClose = useCallback(
    (target) => {
      if (!target?.templateId) return
      setSheetOpen(false)
      window.setTimeout(() => onOpenTemplate?.(target), 280)
    },
    [onOpenTemplate],
  )

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

  /** Profile switch should not leave a stale confirm overlay or half-open sheet. */
  useEffect(() => {
    if (prevSyncProfileRef.current === syncProfileId) return
    prevSyncProfileRef.current = syncProfileId
    setSyncConfirm(null)
    setSheetOpen(false)
    setSheetCategory(null)
    setSheetRows([])
  }, [syncProfileId])

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
    setError('')
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
    openTemplateAfterSheetClose({
      product: product === 'feedback' ? 'feedback' : 'system',
      templateId: row.id,
      surveyTypeId: row.raw?.survey_type_id,
      systemMode: true,
      systemKind: row.systemKind,
    })
  }

  const addSystemTemplate = async (e, forcedOption) => {
    if (e?.preventDefault) e.preventDefault()
    setAdding(true)
    setError('')
    try {
      if (product === 'feedback') {
        const key = forcedOption?.kind || forcedOption?.value || addKind
        const labels = {
          thank_you: 'Thank you',
          tell_us_more: 'Tell us more',
          marketing_opt_in: 'Opt in',
          open_question: 'Share your feedback',
        }
        const noButtons = ['thank_you', 'tell_us_more', 'open_question'].includes(key)
        const bodyText = noButtons
          ? `📋 ${labels[key] || 'Thanks for your feedback.'}`
          : `📋 ${labels[key] || 'Thanks for your feedback.'} Reply with one option below.`
        const tplRes = await apiFetch('/admin/customer-feedback/wa-templates', {
          method: 'POST',
          body: JSON.stringify({
            template_key: key,
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
        if (sheetCategory) {
          setSheetRows(templatesForCategory(kinds, product, sheetCategory))
          // reload kinds then refresh sheet
          const path = '/admin/customer-feedback/system-templates'
          const data = await apiFetch(path)
          const nextKinds = Array.isArray(data?.kinds) ? data.kinds : []
          setKinds(nextKinds)
          setSheetRows(templatesForCategory(nextKinds, product, sheetCategory))
        }
        if (templateId) {
          openTemplateAfterSheetClose({
            product: 'feedback',
            templateId,
            systemMode: true,
            systemKind: key,
          })
        }
      } else {
        const option =
          forcedOption ||
          SURVEY_ADD_OPTIONS.find((o) => o.value === addKind) || {
            kind: addKind,
            privacy_mode: 'off',
            display_name: undefined,
          }
        const data = await apiFetch('/admin/wa-survey/system-templates', {
          method: 'POST',
          body: JSON.stringify({
            system_template_kind: option.kind || addKind,
            category: 'UTILITY',
            language: 'en_GB',
            privacy_mode: option.privacy_mode || 'off',
            display_name: option.display_name || option.label,
          }),
        })
        const templateId = data?.template?.id
        const surveyTypeId = data?.survey_type_id || data?.template?.survey_type_id
        setAddOpen(false)
        const listData = await apiFetch('/admin/wa-survey/system-templates')
        const nextKinds = Array.isArray(listData?.kinds) ? listData.kinds : []
        setKinds(nextKinds)
        if (sheetCategory) {
          setSheetRows(templatesForCategory(nextKinds, product, sheetCategory))
        }
        if (templateId) {
          openTemplateAfterSheetClose({
            product: 'system',
            templateId,
            surveyTypeId,
            systemMode: true,
            systemKind: option.kind || addKind,
          })
        }
      }
    } catch (err) {
      setError(formatWaSurveyError(err, 'Could not add system template').message)
    } finally {
      setAdding(false)
    }
  }

  const addInsideCategory = async () => {
    if (!sheetCategory) return
    const option = optionForCategory(sheetCategory, product)
    await addSystemTemplate(null, option)
  }

  const deleteSystemRow = async (row) => {
    if (!window.confirm(`Delete “${row.name}”? This removes it from the database and Meta.`)) return
    setError('')
    try {
      if (product === 'feedback') {
        await apiFetch(`/admin/customer-feedback/wa-templates/${row.id}`, { method: 'DELETE' })
      } else {
        await apiFetch(`/admin/wa-survey/system-templates/${row.id}`, { method: 'DELETE' })
      }
      setSheetRows((rows) => rows.filter((r) => String(r.id) !== String(row.id)))
      await load()
      if (sheetCategory) {
        const path =
          product === 'feedback'
            ? '/admin/customer-feedback/system-templates'
            : '/admin/wa-survey/system-templates'
        const data = await apiFetch(path)
        const nextKinds = Array.isArray(data?.kinds) ? data.kinds : []
        setKinds(nextKinds)
        setSheetRows(templatesForCategory(nextKinds, product, sheetCategory))
      }
    } catch (e) {
      setError(formatWaSurveyError(e, 'Delete failed').message)
    }
  }

  const refreshSheetRows = async () => {
    if (!sheetCategory) return
    const listPath =
      product === 'feedback'
        ? '/admin/customer-feedback/system-templates'
        : '/admin/wa-survey/system-templates'
    const data = await apiFetch(listPath)
    const nextKinds = Array.isArray(data?.kinds) ? data.kinds : []
    setKinds(nextKinds)
    setSheetRows(templatesForCategory(nextKinds, product, sheetCategory))
  }

  const toggleMetaSyncRow = async (row, syncFromMeta) => {
    setMetaSyncSavingId(row.id)
    setError('')
    try {
      const path =
        product === 'feedback'
          ? `/admin/customer-feedback/system-templates/${row.id}/sync-from-meta`
          : `/admin/wa-survey/system-templates/${row.id}/sync-from-meta`
      await apiFetch(path, {
        method: 'PATCH',
        body: JSON.stringify({ sync_from_meta: syncFromMeta }),
      })
      await load()
      await refreshSheetRows()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not update Meta sync').message)
    } finally {
      setMetaSyncSavingId(null)
    }
  }

  const requestLocalSyncConfirm = useCallback(
    ({ title, action, detail }) =>
      new Promise((resolve, reject) => {
        setSyncConfirm({
          title,
          action,
          detail,
          onConfirm: () => {
            setSyncConfirm(null)
            resolve(true)
          },
          onCancel: () => {
            setSyncConfirm(null)
            reject(new Error('cancelled'))
          },
        })
      }),
    [],
  )

  const syncSystemRow = async (row) => {
    try {
      const confirm = sheetOpen ? requestLocalSyncConfirm : onRequestSyncConfirm
      await confirm?.({
        title: 'Push to Meta',
        action: 'Push',
        detail: 'Submit this system template from the database to the selected connection profile.',
      })
    } catch (e) {
      if (e?.message !== 'cancelled') setError(e?.message || 'Sync cancelled')
      return
    }
    setSyncingId(row.id)
    setError('')
    try {
      const profileBody = syncProfileId ? { connection_profile_id: syncProfileId } : {}
      const path =
        product === 'feedback'
          ? `/admin/customer-feedback/wa-templates/${row.id}/push`
          : `/admin/wa-survey/templates/${row.id}/push`
      const result = await apiFetch(path, {
        method: 'POST',
        body: JSON.stringify({ force_push: false, ...profileBody }),
        timeoutMs: 180000,
        quietNetworkHint: true,
      })
      const branch = result?.sync_branch ? ` (${result.sync_branch})` : ''
      if (result?.message) setError('')
      await load()
      await refreshSheetRows()
      if (result?.sync_branch && result.sync_branch !== 'status_refreshed') {
        setError('')
      }
      if (result?.message && branch) {
        // surface sync branch in inline error slot only on failure — success is silent reload
      }
    } catch (e) {
      const err = formatWaSurveyError(e, 'Push to Meta failed')
      const branch = e?.payload?.sync_branch || e?.sync_branch
      setError(branch ? `${err.message} [${branch}]` : err.message)
    } finally {
      setSyncingId(null)
    }
  }

  const toggleSystemRow = async (row) => {
    setError('')
    const nextActive = Boolean(row.hiddenFromSurvey)
    try {
      if (product === 'feedback') {
        await apiFetch(`/admin/customer-feedback/wa-templates/${row.id}`, {
          method: 'POST',
          body: JSON.stringify({ is_active: nextActive }),
        })
      } else {
        await apiFetch(`/admin/wa-survey/templates/${row.id}/set-active`, {
          method: 'POST',
          body: JSON.stringify({ active_for_survey: nextActive }),
        })
      }
      await load()
      if (sheetCategory) {
        const listPath =
          product === 'feedback'
            ? '/admin/customer-feedback/system-templates'
            : '/admin/wa-survey/system-templates'
        const data = await apiFetch(listPath)
        const nextKinds = Array.isArray(data?.kinds) ? data.kinds : []
        setSheetRows(templatesForCategory(nextKinds, product, sheetCategory))
      }
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not update visibility').message)
    }
  }

  const kindOptions =
    product === 'feedback'
      ? FEEDBACK_CATEGORIES.map((c) => ({ value: c.key, label: c.label }))
      : SURVEY_ADD_OPTIONS.map((o) => ({ value: o.value, label: o.label }))

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
                industries. Use the per-template Meta sync toggle (e.g. Opt in with buttons) when Meta should be the
                source; default is local — Admin edits push to Meta.
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

      <Sheet modal open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent
          side="right"
          overlay={!embedded}
          hideDefaultClose
          overlayClassName="z-[1190]"
          className="z-[1200] !fixed inset-y-0 right-0 left-auto h-[100dvh] max-h-[100dvh] w-[min(720px,100vw)] max-w-[100vw] overflow-hidden border-l p-0 shadow-xl duration-200 data-[state=closed]:duration-150 data-[state=open]:duration-200 sm:max-w-[min(720px,100vw)]"
        >
          <div className="flex h-12 items-center gap-3 border-b bg-surface-muted/50 px-4">
            <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Layers className="h-3.5 w-3.5" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold">System templates</div>
              <div className="truncate text-[11px] text-muted-foreground">{sheetCategory?.label}</div>
            </div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7 gap-1 text-xs"
              disabled={adding}
              onClick={() => void addInsideCategory()}
            >
              <Plus className="h-3.5 w-3.5" />
              {adding ? 'Adding…' : 'Add template'}
            </Button>
            <SheetClose asChild>
              <Button size="sm" variant="ghost" className="h-7 gap-1 text-xs">
                <X className="h-3.5 w-3.5" /> Close
              </Button>
            </SheetClose>
          </div>
          {error ? (
            <div className="border-b border-destructive/30 bg-destructive/10 px-4 py-2 text-[11px] text-destructive">
              {error}
            </div>
          ) : null}
          <div className="overflow-y-auto">
            <WaTemplatesTable
              templates={sheetRows}
              onEdit={handleEdit}
              onSync={(row) => void syncSystemRow(row)}
              onToggle={(row) => void toggleSystemRow(row)}
              onDelete={(row) => void deleteSystemRow(row)}
              onMetaSyncToggle={(row, checked) => void toggleMetaSyncRow(row, checked)}
              syncingId={syncingId}
              metaSyncSavingId={metaSyncSavingId}
              onNew={() => void addInsideCategory()}
              newLabel="Add template"
              plainNames
              showMetaSyncColumn
              useHiddenToggle
              showNew
              emptyLabel="No system templates in this category. Use Add template."
            />
          </div>
          <WaSyncConfirmDialog
            embedded
            open={Boolean(syncConfirm)}
            title={syncConfirm?.title}
            action={syncConfirm?.action}
            detail={syncConfirm?.detail}
            profile={syncProfile}
            onConfirm={syncConfirm?.onConfirm}
            onCancel={syncConfirm?.onCancel}
          />
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
