import React, { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ChevronLeft, ChevronRight, FileUp, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import { apiFetch } from '../../lib/api'
import { formatActionSuccess, formatWaSurveyError } from '../../lib/waSurveyFeedback'
import {
  buildIndustrySyncJobDone,
  buildIndustrySyncJobCancelled,
  buildIndustrySyncJobProgress,
  createIndustrySyncJob,
  EMPTY_INDUSTRY_SYNC_JOB,
  runWaFeedbackIndustryPushAll,
  runWaFeedbackIndustryMirror,
  runWaIndustryPushAll,
  runWaIndustryMirror,
} from '../../lib/waIndustrySync'
import WaTemplatesTable from './WaTemplatesTable'
import WaTemplatesSystemSection from './WaTemplatesSystemSection'
import WaJobProgressDialog from './WaJobProgressDialog'
import WaIndustryJobPanel from './WaIndustryJobPanel'
import {
  toHubRow,
  LangCountBadge,
  MetaSyncNamingNote,
  patchHubRowHidden,
  sortHubTemplateRows,
} from './waTemplatesUi'

function industryHealthClass(ind) {
  const health = ind.approval_health
  if (health === 'approved') return 'border-success/40 bg-success/5'
  if (health === 'rejected') return 'border-destructive/40 bg-destructive/5'
  if (health === 'pending') return 'border-warning/40 bg-warning-soft/40'
  if (health === 'local') return 'border-info/40 bg-info-soft/40'
  return 'bg-surface'
}

function industryHealthDot(ind) {
  const health = ind.approval_health
  if (health === 'approved') return 'bg-success'
  if (health === 'rejected') return 'bg-destructive'
  if (health === 'pending') return 'bg-warning'
  if (health === 'local') return 'bg-info'
  return 'bg-muted-foreground/40'
}

function industryHealthLabel(ind) {
  const health = ind.approval_health
  if (health === 'approved') return 'All approved'
  if (health === 'rejected') return 'Some rejected'
  if (health === 'pending') return 'Pending on Meta/Telnyx'
  if (health === 'local') return 'Local only — not pushed yet'
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

  return createPortal(
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" role="presentation" onClick={onClose}>
      <form
        className="flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-xl border bg-surface shadow-lg"
        role="dialog"
        aria-modal="true"
        onSubmit={save}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="shrink-0 border-b px-4 py-3">
          <h3 className="text-sm font-semibold">{isEdit ? 'Edit visibility' : 'Add industry'}</h3>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {isEdit
              ? 'Choose which organisations can see and use this industry.'
              : 'Create a new industry. Saved to the database immediately.'}
          </p>
        </div>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
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
        <div className="flex shrink-0 justify-end gap-2 border-t bg-surface px-4 py-3">
          <Button type="button" variant="ghost" size="sm" className="h-8 text-xs" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" className="h-8 text-xs" disabled={saving}>
            {saving ? 'Saving…' : isEdit ? 'Save visibility' : 'Add industry'}
          </Button>
        </div>
      </form>
    </div>,
    document.body,
  )
}

function AddIndustryTemplateModal({ open, product, industry, onClose, onCreated, onError }) {
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState('')
  const [language, setLanguage] = useState('en_GB')

  useEffect(() => {
    if (open) {
      setName('')
      setLanguage('en_GB')
    }
  }, [open])

  if (!open || !industry?.id) return null

  const save = async (e) => {
    e.preventDefault()
    const topic = name.trim()
    if (!topic) return
    setSaving(true)
    try {
      if (product === 'feedback') {
        const typeRes = await apiFetch('/admin/customer-feedback/survey-types', {
          method: 'POST',
          body: JSON.stringify({ industry_id: industry.id, name: topic }),
        })
        const typeId = typeRes?.item?.id
        if (!typeId) throw new Error('Could not create survey topic')
        const bodyText =
          language.startsWith('ar')
            ? `📋 كيف كانت هذه الخدمة في زيارتك الأخيرة معنا؟ اختر أحد الخيارات أدناه.`
            : `📋 How was ${topic.toLowerCase()} for your recent visit with us? Reply with one option below.`
        const buttons = language.startsWith('ar')
          ? [
              { type: 'QUICK_REPLY', text: 'ممتاز' },
              { type: 'QUICK_REPLY', text: 'جيد' },
              { type: 'QUICK_REPLY', text: 'ضعيف' },
            ]
          : [
              { type: 'QUICK_REPLY', text: 'Excellent' },
              { type: 'QUICK_REPLY', text: 'Good' },
              { type: 'QUICK_REPLY', text: 'Poor' },
            ]
        const tplRes = await apiFetch('/admin/customer-feedback/wa-templates', {
          method: 'POST',
          body: JSON.stringify({
            industry_id: industry.id,
            survey_type_id: typeId,
            template_key: topic.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || 'topic',
            body_text: bodyText,
            language,
            meta_category: 'utility',
            buttons,
            is_active: true,
          }),
        })
        const templateId = tplRes?.item?.id
        onCreated?.({
          product: 'feedback',
          templateId,
          surveyTypeId: typeId,
          rowKind: 'feedback_template',
        })
      } else {
        const typeRes = await apiFetch('/admin/wa-survey/types', {
          method: 'POST',
          body: JSON.stringify({ industry_id: industry.id, name: topic }),
        })
        const typeId = typeRes?.type?.id
        if (!typeId) throw new Error('Could not create survey topic')
        const tplRes = await apiFetch(`/admin/wa-survey/types/${typeId}/templates/standard`, {
          method: 'POST',
          body: JSON.stringify({ language, category: 'UTILITY' }),
        })
        const templateId = tplRes?.template?.id
        onCreated?.({
          product: 'survey',
          templateId,
          surveyTypeId: typeId,
          rowKind: 'survey_template',
        })
      }
      onClose()
    } catch (err) {
      onError?.(formatWaSurveyError(err, 'Could not add template').message)
    } finally {
      setSaving(false)
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" role="presentation" onClick={onClose}>
      <form
        className="flex w-full max-w-md flex-col overflow-hidden rounded-xl border bg-surface shadow-lg"
        role="dialog"
        aria-modal="true"
        onSubmit={save}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b px-4 py-3">
          <h3 className="text-sm font-semibold">Add template</h3>
          <p className="mt-1 text-[11px] text-muted-foreground">
            New topic + WhatsApp template in <span className="font-medium text-foreground">{industry.name}</span>.
          </p>
        </div>
        <div className="space-y-3 px-4 py-3">
          <label className="block space-y-1">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground">Topic name</span>
            <input
              className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Staff friendliness"
              required
              autoFocus
            />
          </label>
          <label className="block space-y-1">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground">Language</span>
            <select
              className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              <option value="en_GB">English (UK)</option>
              <option value="ar">Arabic</option>
            </select>
          </label>
        </div>
        <div className="flex justify-end gap-2 border-t px-4 py-3">
          <Button type="button" variant="ghost" size="sm" className="h-8 text-xs" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" className="h-8 text-xs" disabled={saving || !name.trim()}>
            {saving ? 'Creating…' : 'Add template'}
          </Button>
        </div>
      </form>
    </div>,
    document.body,
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
  return { rows: sortHubTemplateRows(rows), unlinkedTypes }
}

async function loadFeedbackTemplatesForIndustry(industryId) {
  const data = await apiFetch(
    `/admin/customer-feedback/industries/${encodeURIComponent(industryId)}/templates`,
  )
  const templates = Array.isArray(data?.templates) ? data.templates : []
  const unlinkedTypes = Array.isArray(data?.unlinked_types) ? data.unlinked_types : []
  const rows = templates.map((tpl) => {
    const langs = tpl.languages || [tpl.language].filter(Boolean)
    const metaName = String(tpl.meta_name || tpl.telnyx_name || '').trim()
    return toHubRow(
      {
        ...tpl,
        body: tpl.body_text || tpl.body,
        status: tpl.aggregated_status || tpl.telnyx_sync_status || tpl.status,
        approval_status: tpl.approval_status || tpl.telnyx_sync_status || tpl.status,
        buttons: Array.isArray(tpl.buttons) ? tpl.buttons : [],
        telnyx_name: metaName,
      },
      {
        rowKind: 'feedback_template',
        product: 'feedback',
        surveyTypeId: tpl.survey_type_id,
        surveyTypeName: tpl.survey_type_name,
        name: tpl.display_name || tpl.name || tpl.survey_type_name || tpl.template_key || tpl.id,
        metaName,
        languageCount: tpl.language_count || langs.length || 1,
        languages: langs,
        variants: tpl.variants || [],
      },
    )
  })
  return { rows: sortHubTemplateRows(rows), unlinkedTypes }
}

export default function WaIndustryBrowser({
  product,
  industries,
  loadingIndustries,
  industriesError = '',
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
  syncProfileId = null,
  syncProfile = null,
  backupSyncProfileId = null,
  onRequestSyncConfirm,
}) {
  const [industry, setIndustry] = useState(null)
  const [rows, setRows] = useState([])
  const [unlinkedTypes, setUnlinkedTypes] = useState([])
  const [loadingRows, setLoadingRows] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [editIndustry, setEditIndustry] = useState(null)
  const [addTemplateOpen, setAddTemplateOpen] = useState(false)
  const [jobPanelOpen, setJobPanelOpen] = useState(false)
  const [lastDryRun, setLastDryRun] = useState(null)
  const [industrySyncing, setIndustrySyncing] = useState(false)
  const [deletingIndustry, setDeletingIndustry] = useState(false)
  const [syncJob, setSyncJob] = useState(EMPTY_INDUSTRY_SYNC_JOB)
  const syncAbortRef = useRef(null)
  const syncAccRef = useRef(null)

  const stopIndustrySync = () => {
    syncAbortRef.current?.abort()
  }

  const patchSyncJobStep = (id, patch) => {
    setSyncJob((prev) => ({
      ...prev,
      steps: prev.steps.map((s) => (s.id === id ? { ...s, ...patch } : s)),
    }))
  }

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

  const openEditVisibility = async () => {
    if (!industry?.id) return
    try {
      if (product === 'survey') {
        const detail = await apiFetch(`/admin/wa-survey/industries/${industry.id}`)
        setEditIndustry(detail?.industry || industry)
      } else {
        const detail = await apiFetch(`/admin/customer-feedback/industries/${industry.id}`)
        setEditIndustry(detail?.item || industry)
      }
    } catch {
      setEditIndustry(industry)
    }
  }

  const modals = (
    <>
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
        }}
        onError={onError}
      />
      <AddIndustryTemplateModal
        open={addTemplateOpen}
        product={product}
        industry={industry}
        onClose={() => setAddTemplateOpen(false)}
        onCreated={(target) => {
          onMessage?.('Template added — edit body and sync to Meta')
          onReloadIndustries?.()
          if (industry) void loadIndustryRows(industry)
          if (target?.templateId) {
            onEditRow?.({
              id: target.templateId,
              surveyTypeId: target.surveyTypeId,
              product: target.product,
              rowKind: target.rowKind,
            })
          }
        }}
        onError={onError}
      />
      <WaIndustryJobPanel
        open={jobPanelOpen}
        product={product}
        industry={industry}
        onClose={() => setJobPanelOpen(false)}
        busy={industrySyncing}
        lastDryRun={lastDryRun}
        onDryRunDone={(result) => {
          setLastDryRun(result)
          onMessage?.(result?.ok ? 'Dry-run OK — review plan below' : 'Dry-run found errors')
        }}
        onImportDone={(result) => {
          onMessage?.(result?.message || 'Import complete')
          onReloadIndustries?.()
          if (industry) void loadIndustryRows(industry)
          setJobPanelOpen(false)
        }}
        onStartSync={({ batchSize, delaySec }) => {
          void (async () => {
            if (delaySec > 0 && product === 'feedback') {
              // delay between batches handled server-side in future; client batches sequentially
            }
            await syncIndustry({ batchSize })
          })()
        }}
      />
    </>
  )

  const typeCountLabel = (ind) => {
    const topics = ind.topic_count ?? ind.template_count ?? ind.survey_type_count
    const langs = ind.language_row_count
    if (topics != null && langs != null && Number(langs) > Number(topics)) {
      return `${topics} topics · ${langs} langs`
    }
    if (topics != null) return `${topics} topics`
    return 'Open'
  }

  const syncIndustry = async ({ batchSize = 5 } = {}) => {
    if (!industry?.id) return
    try {
      await onRequestSyncConfirm?.({
        title: `Sync ${industry.name}`,
        action: 'Sync',
        detail: `Push changed templates for ${industry.name}, then refresh approval status from Meta.`,
      })
    } catch (e) {
      if (e?.message !== 'cancelled') onError?.(e?.message || 'Sync cancelled')
      return
    }

    syncAbortRef.current?.abort()
    const controller = new AbortController()
    syncAbortRef.current = controller
    syncAccRef.current = null

    setIndustrySyncing(true)
    setSyncJob(createIndustrySyncJob(`Sync ${industry.name} with Meta`))
    patchSyncJobStep('push', { status: 'running', detail: 'Pushing templates to Meta…' })

    const applyProgress = (acc, { running = true } = {}) => {
      syncAccRef.current = acc
      const progress = buildIndustrySyncJobProgress(acc, { running, industryName: industry.name })
      setSyncJob((prev) => ({
        ...prev,
        ...progress,
        open: true,
        title: prev.title || `Sync ${industry.name} with Meta`,
        steps: prev.steps,
      }))
    }

    try {
      const acc =
        product === 'feedback'
          ? await runWaFeedbackIndustryPushAll(apiFetch, industry.id, {
              signal: controller.signal,
              batchSize,
              connectionProfileId: syncProfileId,
              onProgress: ({ batchNum, flat, acc: partial, step, done, running }) => {
                if (partial) syncAccRef.current = partial
                if (step === 'pull') {
                  patchSyncJobStep('push', { status: 'done', detail: 'Push complete' })
                  patchSyncJobStep('pull', {
                    status: running ? 'running' : done ? 'done' : 'running',
                    detail: running
                      ? 'Pulling status from Meta…'
                      : partial?.pull?.message || 'Status refreshed from Meta',
                  })
                } else {
                  patchSyncJobStep('push', {
                    status: done && step !== 'pull' ? 'done' : 'running',
                    detail: flat?.message || `Batch ${batchNum}…`,
                  })
                }
                if (partial) {
                  const stillRunning = !(step === 'pull' && done === true)
                  applyProgress(partial, { running: stillRunning })
                }
              },
            })
          : await runWaIndustryPushAll(apiFetch, industry.id, {
              signal: controller.signal,
              connectionProfileId: syncProfileId,
              onProgress: ({ batchNum, flat, acc: partial, step, done, running }) => {
                if (partial) syncAccRef.current = partial
                if (step === 'pull') {
                  patchSyncJobStep('push', { status: 'done', detail: 'Push complete' })
                  patchSyncJobStep('pull', {
                    status: running ? 'running' : done ? 'done' : 'running',
                    detail: running
                      ? 'Pulling status from Meta…'
                      : partial?.pull?.message || 'Status refreshed from Meta',
                  })
                } else {
                  patchSyncJobStep('push', {
                    status: done && step !== 'pull' ? 'done' : 'running',
                    detail: flat?.message || `Batch ${batchNum}…`,
                  })
                }
                if (partial) {
                  const stillRunning = !(step === 'pull' && done === true)
                  applyProgress(partial, { running: stillRunning })
                }
              },
            })

      if (product !== 'feedback') {
        patchSyncJobStep('push', { status: acc.error_count ? 'error' : 'done', detail: 'Complete' })
        patchSyncJobStep('pull', {
          status: acc.pull ? (acc.error_count ? 'error' : 'done') : 'done',
          detail: acc.pull?.message || 'Status refreshed from Meta',
        })
      } else {
        patchSyncJobStep('push', { status: acc.error_count ? 'error' : 'done', detail: 'Complete' })
        patchSyncJobStep('pull', {
          status: acc.pull ? (acc.error_count ? 'error' : 'done') : 'done',
          detail: acc.pull?.message || 'Status refreshed from Meta',
        })
      }

      const doneState = buildIndustrySyncJobDone(acc, industry.name)
      setSyncJob((prev) => ({ ...prev, ...doneState, open: true }))
      onMessage?.(doneState.message)
      await loadIndustryRows(industry)
      onReloadIndustries?.()
    } catch (e) {
      if (e?.name === 'IndustrySyncCancelledError' || controller.signal.aborted) {
        const partial = syncAccRef.current || {
          total: 0,
          results: [],
          errors: [],
          content_updated: 0,
          error_count: 0,
        }
        const doneState = buildIndustrySyncJobCancelled(partial, { industryName: industry.name })
        patchSyncJobStep('push', { status: 'error', detail: 'Stopped' })
        patchSyncJobStep('pull', { status: 'pending', detail: 'Skipped — sync stopped before pull' })
        setSyncJob((prev) => ({ ...prev, ...doneState, open: true, steps: prev.steps }))
        onMessage?.(doneState.message)
        return
      }
      const errText = formatWaSurveyError(e, 'Industry sync failed').detailText || e?.message
      onError?.(errText)
      setSyncJob((prev) => ({
        ...prev,
        phase: 'error',
        error: errText,
        open: true,
      }))
    } finally {
      if (syncAbortRef.current === controller) syncAbortRef.current = null
      setIndustrySyncing(false)
    }
  }

  const mirrorIndustry = async ({ batchSize = 5 } = {}) => {
    if (!industry?.id || !backupSyncProfileId) return
    try {
      await onRequestSyncConfirm?.({
        title: `Mirror ${industry.name} to backup`,
        action: 'Mirror',
        detail: `Force-push every template in ${industry.name} to the Telnyx backup profile.`,
        profile: { id: backupSyncProfileId },
      })
    } catch (e) {
      if (e?.message !== 'cancelled') onError?.(e?.message || 'Mirror cancelled')
      return
    }

    syncAbortRef.current?.abort()
    const controller = new AbortController()
    syncAbortRef.current = controller
    syncAccRef.current = null

    setIndustrySyncing(true)
    setSyncJob({
      ...createIndustrySyncJob(`Mirror ${industry.name} to backup`),
      steps: [{ id: 'push', label: '1. Mirror templates to backup', status: 'running', detail: '' }],
    })

    const applyProgress = (acc, { running = true } = {}) => {
      syncAccRef.current = acc
      const progress = buildIndustrySyncJobProgress(acc, { running, industryName: industry.name })
      setSyncJob((prev) => ({
        ...prev,
        ...progress,
        open: true,
        title: prev.title || `Mirror ${industry.name} to backup`,
        steps: prev.steps,
      }))
    }

    try {
      const mirrorFn =
        product === 'feedback' ? runWaFeedbackIndustryMirror : runWaIndustryMirror
      const acc = await mirrorFn(apiFetch, industry.id, {
        signal: controller.signal,
        batchSize,
        connectionProfileId: backupSyncProfileId,
        onProgress: ({ batchNum, flat, acc: partial, done, running }) => {
          if (partial) syncAccRef.current = partial
          patchSyncJobStep('push', {
            status: done ? 'done' : 'running',
            detail: flat?.message || `Batch ${batchNum}…`,
          })
          if (partial) applyProgress(partial, { running: Boolean(running) && !done })
        },
      })

      patchSyncJobStep('push', { status: acc.error_count ? 'error' : 'done', detail: 'Complete' })
      const doneState = buildIndustrySyncJobDone(acc, industry.name)
      setSyncJob((prev) => ({ ...prev, ...doneState, open: true }))
      onMessage?.(doneState.message)
      await loadIndustryRows(industry)
      onReloadIndustries?.()
    } catch (e) {
      if (e?.name === 'IndustrySyncCancelledError' || controller.signal.aborted) {
        const partial = syncAccRef.current || {
          total: 0,
          results: [],
          errors: [],
          content_updated: 0,
          error_count: 0,
        }
        const doneState = buildIndustrySyncJobCancelled(partial, { industryName: industry.name })
        patchSyncJobStep('push', { status: 'error', detail: 'Stopped' })
        setSyncJob((prev) => ({ ...prev, ...doneState, open: true, steps: prev.steps }))
        onMessage?.(doneState.message)
        return
      }
      const errText = formatWaSurveyError(e, 'Industry mirror failed').detailText || e?.message
      onError?.(errText)
      setSyncJob((prev) => ({
        ...prev,
        phase: 'error',
        error: errText,
        open: true,
      }))
    } finally {
      if (syncAbortRef.current === controller) syncAbortRef.current = null
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
    const pendingCount = rows.filter((r) => r.status === 'pending').length
    const localCount = rows.filter((r) => r.status === 'local').length
    const exampleMetaName = rows.find((r) => r.metaName)?.metaName || ''
    return (
      <div className="animate-fade-in">
        <WaTemplatesSystemSection
          product={product}
          embedded
          onOpenTemplate={onOpenSystemTemplate}
          syncProfileId={syncProfileId}
          syncProfile={syncProfile}
          onRequestSyncConfirm={onRequestSyncConfirm}
        />
        <div className="flex flex-wrap items-center gap-2 border-b bg-surface-muted/40 px-3 py-2">
          <Button variant="ghost" size="sm" className="-ml-2 h-7 gap-1 text-xs" onClick={() => setIndustry(null)}>
            <ChevronLeft className="h-3.5 w-3.5" /> Industries
          </Button>
          <ChevronRight className="h-3 w-3 text-muted-foreground" />
          <span className="text-sm font-medium">{industry.name}</span>
          <span className="text-xs text-muted-foreground">
            · {rows.length} topics
            {industry.language_row_count ? ` · ${industry.language_row_count} language versions` : ''}
          </span>
          <span className="text-xs text-success">· {approvedCount} approved</span>
          {localCount > 0 ? <span className="text-xs text-info">· {localCount} local</span> : null}
          {pendingCount > 0 ? <span className="text-xs text-warning">· {pendingCount} pending on Meta</span> : null}
          {rejectedCount > 0 ? (
            <span className="text-xs font-medium text-destructive">· {rejectedCount} rejected — fix</span>
          ) : null}
          <div className="ml-auto flex flex-wrap items-center gap-1.5">
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1 text-xs"
              disabled={industrySyncing || deletingIndustry}
              onClick={() => setAddTemplateOpen(true)}
            >
              <Plus className="h-3.5 w-3.5" />
              Add template
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1 text-xs"
              disabled={industrySyncing || deletingIndustry}
              onClick={() => void openEditVisibility()}
            >
              Edit visibility
            </Button>
            <Button
              size="sm"
              variant="default"
              className="h-7 gap-1 text-xs"
              disabled={industrySyncing || deletingIndustry}
              onClick={() => setJobPanelOpen(true)}
            >
              <FileUp className="h-3.5 w-3.5" />
              {product === 'feedback' ? 'Upload MD / dry-run' : 'Industry actions'}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1 text-xs"
              disabled={industrySyncing || deletingIndustry}
              onClick={() => void syncIndustry({ batchSize: 5 })}
            >
              <RefreshCw className={cn('h-3.5 w-3.5', industrySyncing && 'animate-spin')} />
              {industrySyncing ? 'Syncing industry…' : 'Sync this industry'}
            </Button>
            {backupSyncProfileId ? (
              <Button
                size="sm"
                variant="outline"
                className="h-7 gap-1 text-xs"
                disabled={industrySyncing || deletingIndustry}
                onClick={() => void mirrorIndustry({ batchSize: 5 })}
              >
                Mirror this industry
              </Button>
            ) : null}
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
            Use <span className="font-medium text-foreground">Sync this industry</span> for templates in this
            industry only, or <span className="font-medium text-foreground">Sync with Meta</span> on the hub header
            for all templates. Row Sync pushes one template only.
          </div>
        ) : null}
        {product === 'feedback' ? (
          <div className="border-b px-3 py-2">
            <MetaSyncNamingNote industrySlug={industry.slug} exampleMetaName={exampleMetaName} />
          </div>
        ) : null}
        <WaTemplatesTable
          templates={rows}
          loading={loadingRows}
          onEdit={onEditRow}
          onSync={onSyncRow}
          onToggle={async (row) => {
            const prevRows = rows
            const nextHidden = !row.hiddenFromSurvey
            setRows(sortHubTemplateRows(
              rows.map((r) =>
                String(r.id) === String(row.id) ? patchHubRowHidden(r, nextHidden, product) : r,
              ),
            ))
            try {
              await onToggleRow?.(row)
            } catch {
              setRows(prevRows)
            }
          }}
          onDelete={async (row) => {
            await onDeleteRow?.(row)
            if (industry) await loadIndustryRows(industry)
          }}
          onReject={onRejectRow}
          syncingId={syncingId}
          plainNames
          showMetaNameColumn={product === 'feedback'}
          showNew={false}
          emptyLabel="No WhatsApp templates linked in this industry yet. Use Add template."
        />
        {modals}
        <WaJobProgressDialog
          open={syncJob.open}
          title={syncJob.title}
          dryRun={syncJob.dryRun}
          steps={syncJob.steps}
          phase={syncJob.phase}
          summaryRows={syncJob.summaryRows}
          tables={syncJob.tables}
          message={syncJob.message}
          error={syncJob.error}
          reportPath={syncJob.reportPath}
          progressPct={syncJob.progressPct}
          onStop={stopIndustrySync}
          onClose={() => setSyncJob(EMPTY_INDUSTRY_SYNC_JOB)}
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
        syncProfileId={syncProfileId}
        syncProfile={syncProfile}
        onRequestSyncConfirm={onRequestSyncConfirm}
      />
      <div className="p-3">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <div className="text-sm font-medium">Choose an industry</div>
            <div className="text-xs text-muted-foreground">
              {industries.length} industries · Click an industry to open templates
              {product === 'feedback' ? ' · then Upload MD / dry-run to import a file' : ''}
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
        ) : industriesError ? (
          <div className="py-8 text-center text-xs">
            <p className="text-destructive">{industriesError}</p>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="mt-3 h-8 text-xs"
              onClick={() => onReloadIndustries?.()}
            >
              Retry
            </Button>
          </div>
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
                      {(ind.org_names || []).length
                        ? `Only: ${(ind.org_names || []).slice(0, 2).join(', ')}${(ind.org_names || []).length > 2 ? '…' : ''}`
                        : (ind.org_ids || []).length === 1
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
      {modals}
    </div>
  )
}
