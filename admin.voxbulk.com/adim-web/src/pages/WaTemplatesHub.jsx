import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  BarChart3,
  Building2,
  ClipboardList,
  Megaphone,
  MessageSquareHeart,
  RefreshCw,
  ShoppingBag,
  Sparkles,
  Trash2,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatWaSurveyError } from '../lib/waSurveyFeedback'
import WaIndustryBrowser from '../components/wa-templates/WaIndustryBrowser'
import WaTemplatesTable from '../components/wa-templates/WaTemplatesTable'
import WaEditSheet from '../components/wa-templates/WaEditSheet'
import WaRejectedDialog from '../components/wa-templates/WaRejectedDialog'
import WaJobProgressDialog from '../components/wa-templates/WaJobProgressDialog'
import { summarizeCatalog, toHubRow } from '../components/wa-templates/waTemplatesUi'
import '../styles/wa-templates-hub.css'

const EMPTY_JOB = {
  open: false,
  title: '',
  dryRun: false,
  steps: [],
  phase: 'running',
  summaryRows: [],
  tables: {},
  message: '',
  error: '',
  reportPath: '',
}

const TAGS = [
  { id: 'ai', label: 'AI Interview', icon: Sparkles },
  { id: 'survey', label: 'Survey', icon: ClipboardList },
  { id: 'feedback', label: 'Customer Feedback', icon: MessageSquareHeart },
  { id: 'companies', label: 'Companies', icon: Building2 },
  { id: 'marketing', label: 'Marketing', icon: Megaphone },
  { id: 'sales', label: 'Sales', icon: ShoppingBag },
]

const SALES_TEMPLATE_KEYS = new Set([
  'sales_opt_in',
  'sales_offer',
  'sales_offer_followup',
  'sales_offer_keyword_confirm',
])

/** Lead-sales / marketing only — never interview keys. */
const MARKETING_TEMPLATE_KEYS = new Set([
  'sales_opt_in',
  'sales_offer',
  'sales_offer_followup',
  'sales_offer_keyword_confirm',
])

const INTERVIEW_TEMPLATE_KEYS = new Set([
  'interview_email_sent',
  'interview_booking_confirm',
  'interview_booking_cancel',
  'interview_job_closed',
  'interview_booking_invite',
])

function templateKey(t) {
  return String(t?.sales_template_key || t?.sales_key || '').toLowerCase().trim()
}

function templateName(t) {
  return String(t?.name || t?.telnyx_name || t?.display_name || '').toLowerCase().trim()
}

function isInterviewTemplate(t) {
  const key = templateKey(t)
  const name = templateName(t)
  if (INTERVIEW_TEMPLATE_KEYS.has(key)) return true
  if (key.startsWith('interview_')) return true
  if (name.startsWith('voxbulk_interview_')) return true
  if (name.includes('interview_') || name.includes('_interview')) return true
  return false
}

function isSalesTemplate(t) {
  if (isInterviewTemplate(t)) return false
  const key = templateKey(t)
  const name = templateName(t)
  if (SALES_TEMPLATE_KEYS.has(key)) return true
  if (key.startsWith('sales_')) return true
  if (name.startsWith('voxbulk_sales_')) return true
  return false
}

function isMarketingTemplate(t) {
  if (isInterviewTemplate(t)) return false
  if (isSalesTemplate(t)) return false
  const key = templateKey(t)
  const name = templateName(t)
  if (MARKETING_TEMPLATE_KEYS.has(key)) return true
  return false
}

const TAB_ALIASES = { interview: 'ai', appointment: 'ai' }

export default function WaTemplatesHub() {
  const [searchParams, setSearchParams] = useSearchParams()
  const rawTab = searchParams.get('tab') || 'survey'
  const tab = TAB_ALIASES[rawTab] || (TAGS.some((t) => t.id === rawTab) ? rawTab : 'survey')

  const [syncing, setSyncing] = useState(false)
  const [syncProgress, setSyncProgress] = useState('')
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [templateCounts, setTemplateCounts] = useState({
    total: 0,
    approved: 0,
    localOnly: 0,
    pending: 0,
    rejected: 0,
    utility: 0,
    marketing: 0,
  })

  const [interviewTemplates, setInterviewTemplates] = useState([])
  const [marketingTemplates, setMarketingTemplates] = useState([])
  const [salesTemplates, setSalesTemplates] = useState([])
  const [flatLoading, setFlatLoading] = useState(false)
  const [cleaning, setCleaning] = useState(false)
  const [job, setJob] = useState(EMPTY_JOB)

  const [surveyIndustries, setSurveyIndustries] = useState([])
  const [surveyIndustriesLoading, setSurveyIndustriesLoading] = useState(false)
  const [feedbackIndustries, setFeedbackIndustries] = useState([])
  const [feedbackIndustriesLoading, setFeedbackIndustriesLoading] = useState(false)

  const [editTarget, setEditTarget] = useState(null)
  const [syncingId, setSyncingId] = useState(null)
  const [rejectRow, setRejectRow] = useState(null)

  const setTab = (next) => {
    const params = new URLSearchParams(searchParams)
    params.set('tab', next)
    setSearchParams(params, { replace: true })
  }

  const loadTemplateCounts = useCallback(async () => {
    try {
      // Live Meta/Telnyx statuses — rejected count matches Meta Manager, not stale local rows.
      const data = await apiFetch('/admin/integrations/meta_whatsapp/whatsapp-templates/live-summary', {
        timeoutMs: 120000,
        quietNetworkHint: true,
      })
      if (data?.summary) {
        setTemplateCounts({
          total: data.summary.total ?? 0,
          approved: data.summary.approved ?? 0,
          localOnly: data.summary.localOnly ?? 0,
          pending: data.summary.pending ?? 0,
          rejected: data.summary.rejected ?? 0,
          utility: data.summary.utility ?? 0,
          marketing: data.summary.marketing ?? 0,
        })
        return
      }
      const fallback = await apiFetch('/admin/integrations/telnyx/whatsapp-templates?approved_only=false&live=true', {
        timeoutMs: 120000,
        quietNetworkHint: true,
      })
      if (fallback?.summary) {
        setTemplateCounts(fallback.summary)
        return
      }
      setTemplateCounts(summarizeCatalog(Array.isArray(fallback?.templates) ? fallback.templates : []))
    } catch {
      setTemplateCounts({
        total: 0,
        approved: 0,
        localOnly: 0,
        pending: 0,
        rejected: 0,
        utility: 0,
        marketing: 0,
      })
    }
  }, [])

  const loadInterview = useCallback(async () => {
    setFlatLoading(true)
    try {
      const data = await apiFetch('/admin/wa-interview/templates')
      const rows = (Array.isArray(data?.templates) ? data.templates : []).filter(isInterviewTemplate)
      setInterviewTemplates(rows.map((t) => toHubRow(t, { rowKind: 'interview' })))
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load interview templates').message)
    } finally {
      setFlatLoading(false)
    }
  }, [])

  const loadMarketing = useCallback(async () => {
    setFlatLoading(true)
    try {
      const stored = await apiFetch('/admin/integrations/telnyx/whatsapp-templates?approved_only=false')
      const rows = (Array.isArray(stored?.templates) ? stored.templates : []).filter(isMarketingTemplate)
      setMarketingTemplates(rows.map((t) => toHubRow(t, { rowKind: 'marketing' })))
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load marketing templates').message)
    } finally {
      setFlatLoading(false)
    }
  }, [])

  const loadSales = useCallback(async () => {
    setFlatLoading(true)
    try {
      await apiFetch('/admin/wa-templates/ensure-sales', { method: 'POST', quietNetworkHint: true })
      const stored = await apiFetch('/admin/integrations/telnyx/whatsapp-templates?approved_only=false')
      const rows = (Array.isArray(stored?.templates) ? stored.templates : []).filter(isSalesTemplate)
      setSalesTemplates(rows.map((t) => toHubRow(t, { rowKind: 'sales' })))
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load sales templates').message)
    } finally {
      setFlatLoading(false)
    }
  }, [])

  const loadSurveyIndustries = useCallback(async () => {
    setSurveyIndustriesLoading(true)
    try {
      const data = await apiFetch('/admin/wa-survey/overview')
      setSurveyIndustries(Array.isArray(data?.industries) ? data.industries : [])
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load survey industries').message)
    } finally {
      setSurveyIndustriesLoading(false)
    }
  }, [])

  const loadFeedbackIndustries = useCallback(async () => {
    setFeedbackIndustriesLoading(true)
    try {
      const data = await apiFetch('/admin/customer-feedback/industries')
      setFeedbackIndustries(Array.isArray(data?.items) ? data.items : [])
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load feedback industries').message)
    } finally {
      setFeedbackIndustriesLoading(false)
    }
  }, [])

  const refreshTabData = useCallback(() => {
    if (tab === 'ai') void loadInterview()
    else if (tab === 'marketing') void loadMarketing()
    else if (tab === 'sales') void loadSales()
    else if (tab === 'survey') void loadSurveyIndustries()
    else if (tab === 'feedback') void loadFeedbackIndustries()
  }, [tab, loadInterview, loadMarketing, loadSales, loadSurveyIndustries, loadFeedbackIndustries])

  useEffect(() => {
    let cancelled = false
    setError('')
    ;(async () => {
      // Apply live Meta statuses first so tab lists do not show stale REJECTED.
      await loadTemplateCounts()
      if (!cancelled) refreshTabData()
    })()
    return () => {
      cancelled = true
    }
  }, [loadTemplateCounts, refreshTabData])

  const patchJobStep = (stepId, patch) => {
    setJob((prev) => ({
      ...prev,
      steps: prev.steps.map((s) => (s.id === stepId ? { ...s, ...patch } : s)),
    }))
  }

  const syncFromMeta = async () => {
    const stepDefs = [
      { id: 'catalog', label: '1. Pull Meta catalog' },
      { id: 'link_repair', label: '2. Link & repair survey / feedback' },
      { id: 'push', label: '3. Push pending templates' },
      { id: 'cleanup', label: '4. Clean rejected / orphans' },
    ]
    setSyncing(true)
    setSyncProgress('')
    setError('')
    setMsg('')
    setJob({
      ...EMPTY_JOB,
      open: true,
      title: 'Sync with Meta',
      phase: 'running',
      steps: stepDefs.map((s) => ({ ...s, status: 'pending', detail: '' })),
    })
    const messages = []
    const summaryRows = []
    try {
      let last = null
      for (let i = 0; i < stepDefs.length; i += 1) {
        const step = stepDefs[i]
        const label = `${i + 1}/${stepDefs.length}`
        setSyncProgress(label)
        patchJobStep(step.id, { status: 'running', detail: 'Running…' })
        if (step.id === 'push') {
          const PUSH_BATCH = 5
          const pushScopes = ['survey', 'interview', 'feedback']
          let surveyPushedTotal = 0
          for (const scope of pushScopes) {
            let offset = 0
            let batchNum = 0
            for (;;) {
              batchNum += 1
              patchJobStep(step.id, {
                status: 'running',
                detail: `Pushing ${scope} batch ${batchNum} (offset ${offset})…`,
              })
              last = await apiFetch(`/admin/integrations/meta_whatsapp/whatsapp-templates/sync-step/${step.id}`, {
                method: 'POST',
                body: JSON.stringify({ scope, offset, limit: PUSH_BATCH }),
                timeoutMs: 300000,
                quietNetworkHint: true,
              })
              if (scope === 'survey') {
                surveyPushedTotal += Number(last?.survey_push?.pushed || 0)
                if (last?.has_more) {
                  offset = Number(last?.next_offset ?? offset + PUSH_BATCH)
                  continue
                }
              }
              break
            }
          }
          if (surveyPushedTotal) {
            summaryRows.push({ metric: 'Survey pushed', count: surveyPushedTotal })
          }
          if (last?.interview?.pushed != null) {
            summaryRows.push({ metric: 'Interview pushed', count: last.interview.pushed })
          }
          if (last?.feedback_push?.pushed != null) {
            summaryRows.push({ metric: 'Feedback pushed', count: last.feedback_push.pushed })
          }
        } else {
          last = await apiFetch(`/admin/integrations/meta_whatsapp/whatsapp-templates/sync-step/${step.id}`, {
            method: 'POST',
            timeoutMs: 300000,
            quietNetworkHint: true,
          })
        }
        const detail = last?.message || `Step ${label} done`
        messages.push(detail)
        patchJobStep(step.id, { status: 'done', detail })
        if (last?.catalog?.synced != null) {
          summaryRows.push({ metric: 'Catalog synced', count: last.catalog.synced })
        }
        if (last?.approved != null) summaryRows.push({ metric: 'Approved (step)', count: last.approved })
        if (last?.pending != null) summaryRows.push({ metric: 'Pending (step)', count: last.pending })
        if (last?.rejected != null) summaryRows.push({ metric: 'Rejected (step)', count: last.rejected })
        if (last?.meta_rejected_deleted?.deleted != null) {
          summaryRows.push({ metric: 'Meta rejected deleted', count: last.meta_rejected_deleted.deleted })
        }
        if (last?.clean?.deleted != null) {
          summaryRows.push({ metric: 'Local orphans cleaned', count: last.clean.deleted })
        }
      }
      const result = last || {}
      const fallback = messages.length
        ? messages.join(' · ')
        : `Synced ${result.synced ?? 0} · Approved ${result.approved ?? 0} · Pending ${result.pending ?? 0} · Rejected ${result.rejected ?? 0}`
      const finalMsg = formatActionSuccess(result, fallback).message
      setMsg(finalMsg)
      setJob((prev) => ({
        ...prev,
        phase: 'done',
        message: finalMsg,
        summaryRows: summaryRows.length
          ? summaryRows
          : [
              { metric: 'Synced', count: result.synced ?? 0 },
              { metric: 'Approved', count: result.approved ?? 0 },
              { metric: 'Pending', count: result.pending ?? 0 },
              { metric: 'Rejected', count: result.rejected ?? 0 },
            ],
        tables: {},
      }))
      await loadTemplateCounts()
      refreshTabData()
    } catch (e) {
      const raw = e?.message || String(e)
      const aborted = e?.name === 'AbortError' || /aborted|abort/i.test(raw)
      const errText = aborted
        ? 'Meta sync timed out in the browser. The server may still be finishing — wait 1–2 minutes, refresh this page, and check template statuses.'
        : formatWaSurveyError(e, 'Meta sync failed').detailText || raw || 'Meta sync failed'
      setError(errText)
      if (messages.length) setMsg(messages.join(' · '))
      setJob((prev) => ({
        ...prev,
        phase: 'error',
        error: errText,
        message: messages.join(' · '),
        summaryRows,
      }))
    } finally {
      setSyncing(false)
      setSyncProgress('')
    }
  }

  const openSurveyTypeEditor = async (row) => {
    setError('')
    try {
      if (row.rowKind === 'survey_template') {
        setEditTarget({
          product: 'survey',
          templateId: row.id,
          surveyTypeId: row.surveyTypeId,
        })
        return
      }
      if (row.rowKind === 'feedback_template') {
        setEditTarget({
          product: 'feedback',
          templateId: row.id,
          surveyTypeId: row.surveyTypeId,
        })
        return
      }
      // Empty survey types are no longer listed as fake template rows.
      setError('Select a real WhatsApp template row (not a survey type name).')
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not open editor').message)
    }
  }

  const pushSurveyType = async (row) => {
    setError('')
    setSyncingId(row.id)
    try {
      if (row.rowKind === 'survey_template') {
        const result = await apiFetch(`/admin/wa-survey/templates/${row.id}/push`, {
          method: 'POST',
          body: '{}',
          timeoutMs: 180000,
          quietNetworkHint: true,
        })
        setMsg(formatActionSuccess(result, 'Synced with Meta').message)
        await loadTemplateCounts()
        return
      }
      if (row.rowKind === 'feedback_template') {
        const result = await apiFetch(`/admin/customer-feedback/survey-types/${row.surveyTypeId}/sync-telnyx`, {
          method: 'POST',
          timeoutMs: 180000,
          quietNetworkHint: true,
        })
        setMsg(formatActionSuccess(result, 'Synced with Meta').message)
        return
      }
      // Sync only this survey type / topic (not the whole industry).
      const typeId = row.surveyTypeId || row.id
      const path =
        row.rowKind === 'feedback_type'
          ? `/admin/customer-feedback/survey-types/${typeId}/sync-telnyx`
          : `/admin/wa-survey/types/${typeId}/templates/push-all`
      const result = await apiFetch(path, {
        method: 'POST',
        body: '{}',
        timeoutMs: 300000,
        quietNetworkHint: true,
      })
      setMsg(formatActionSuccess(result, 'Synced survey type with Meta').message)
      await loadTemplateCounts()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Sync failed').detailText)
    } finally {
      setSyncingId(null)
    }
  }

  const toggleSurveyType = async (row) => {
    setError('')
    try {
      if (row.rowKind === 'survey_template') {
        const active = row.raw?.active_for_survey !== false
        await apiFetch(`/admin/wa-survey/templates/${row.id}/set-active`, {
          method: 'POST',
          body: JSON.stringify({ active_for_survey: !active }),
        })
        setMsg(active ? 'Template disabled for surveys' : 'Template enabled for surveys')
        return
      }
      if (row.rowKind === 'feedback_template') {
        await apiFetch('/admin/customer-feedback/wa-templates', {
          method: 'POST',
          body: JSON.stringify({ id: row.id, is_active: row.raw?.is_active === false }),
        })
        setMsg('Template visibility updated')
        return
      }
      if (row.rowKind === 'feedback_type') {
        await apiFetch(`/admin/customer-feedback/survey-types/${row.id}`, {
          method: 'PUT',
          body: JSON.stringify({ is_active: row.raw?.is_active === false }),
        })
        void loadFeedbackIndustries()
        return
      }
      await apiFetch(`/admin/wa-survey/types/${row.id}`, {
        method: 'PUT',
        body: JSON.stringify({ is_active: row.raw?.is_active === false }),
      })
      void loadSurveyIndustries()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not update status').message)
    }
  }

  const deleteSurveyType = async (row) => {
    if (!window.confirm(`Delete “${row.name}”? This removes it from the database and Meta.`)) return
    setError('')
    try {
      if (row.rowKind === 'survey_template' || row.rowKind === 'system_template') {
        const typeId = row.surveyTypeId
        if (row.rowKind === 'system_template') {
          await apiFetch(`/admin/wa-survey/system-templates/${row.id}`, { method: 'DELETE' })
        } else if (typeId) {
          await apiFetch(`/admin/wa-survey/types/${typeId}/templates/${row.id}`, { method: 'DELETE' })
        } else {
          await apiFetch(`/admin/wa-survey/templates/${row.id}`, { method: 'DELETE' })
        }
        setMsg('Template deleted from database and Meta')
        await loadTemplateCounts()
        refreshTabData()
        return
      }
      if (row.rowKind === 'feedback_template') {
        await apiFetch(`/admin/customer-feedback/wa-templates/${row.id}`, { method: 'DELETE' })
        setMsg('Template deleted from database and Meta')
        await loadTemplateCounts()
        refreshTabData()
        return
      }
      if (row.rowKind === 'feedback_type') {
        await apiFetch(`/admin/customer-feedback/survey-types/${row.id}`, { method: 'DELETE' })
        setMsg('Survey type deleted')
        refreshTabData()
        return
      }
      await apiFetch(`/admin/wa-survey/types/${row.id}`, { method: 'DELETE' })
      setMsg('Survey type deleted')
      refreshTabData()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Delete failed').message)
    }
  }

  const pushInterview = async (row) => {
    setError('')
    setSyncingId(row.id)
    try {
      const result = await apiFetch(`/admin/wa-interview/templates/${row.id}/push`, {
        method: 'POST',
        body: '{}',
        timeoutMs: 180000,
        quietNetworkHint: true,
      })
      setMsg(formatActionSuccess(result, 'Synced with Meta').message)
      await loadInterview()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Sync failed').detailText || e?.message)
    } finally {
      setSyncingId(null)
    }
  }

  const toggleInterview = async (row) => {
    try {
      const active = row.raw?.active_for_interview !== false
      await apiFetch(`/admin/wa-interview/templates/${row.id}/set-active`, {
        method: 'POST',
        body: JSON.stringify({ active_for_interview: !active }),
      })
      await loadInterview()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not update status').message)
    }
  }

  const deleteInterview = async (row) => {
    if (!window.confirm(`Delete “${row.name}”?`)) return
    try {
      await apiFetch(`/admin/wa-interview/templates/${row.id}`, { method: 'DELETE' })
      setMsg('Template deleted')
      await loadInterview()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Delete failed').message)
    }
  }

  const marketingAction = async (row, action) => {
    if (action === 'edit') {
      setError('Marketing templates are managed in Lead sales settings.')
      return
    }
    if (action === 'sync') {
      await syncFromMeta()
      return
    }
    setError(`Cannot ${action} marketing templates from this list. Use Lead sales settings.`)
  }

  const salesAction = async (row, action) => {
    if (action === 'edit') {
      setEditTarget({ product: 'survey', templateId: row.id })
      return
    }
    if (action === 'sync') {
      setSyncingId(row.id)
      setError('')
      try {
        await apiFetch(`/admin/wa-survey/templates/${row.id}/push`, {
          method: 'POST',
          timeoutMs: 120000,
          quietNetworkHint: true,
        })
        setMsg(formatActionSuccess(null, 'Sales template submitted to Meta').message)
        await loadSales()
        await loadTemplateCounts()
      } catch (e) {
        setError(formatWaSurveyError(e, 'Sales sync failed').detailText || e?.message)
      } finally {
        setSyncingId(null)
      }
      return
    }
    setError(`Cannot ${action} sales templates from this list yet. Review and sync when ready.`)
  }

  const runCleanupAndSync = async ({ dryRun = false } = {}) => {
    const label = dryRun ? 'Dry-run cleanup' : 'Cleanup + push buttoned'
    if (
      !dryRun &&
      !window.confirm(
        'Delete unused survey/feedback templates from local DB and Meta, then push buttoned keepers only? Interview and Sales are not touched. Local DB is source of truth.',
      )
    ) {
      return
    }
    const stepDefs = [
      { id: 'meta_cleanup', label: '1. Delete unused survey/CF from Meta' },
      { id: 'local_cleanup', label: '2. Delete unused survey/CF from local DB' },
      { id: 'push_buttoned', label: '3. Push buttoned keepers to Meta' },
      { id: 'finalize', label: '4. Build report (local = source of truth)' },
    ]
    setCleaning(true)
    setError('')
    setMsg('')
    setJob({
      ...EMPTY_JOB,
      open: true,
      title: label,
      dryRun,
      phase: 'running',
      steps: stepDefs.map((s) => ({ ...s, status: 'pending', detail: '' })),
    })

    let meta = null
    let local = null
    let push = null
    const PUSH_BATCH = 10
    try {
      for (const step of stepDefs) {
        patchJobStep(step.id, { status: 'running', detail: 'Running…' })

        if (step.id === 'push_buttoned') {
          // Batch pushes — nginx proxy_read_timeout is 300s; one big push always 504s.
          const acc = {
            ok: true,
            dry_run: dryRun,
            pushed_buttoned: [],
            failed: [],
            skipped_buttonless: [],
            skipped_buttonless_total: 0,
            keepers_count: 0,
            buttoned_total: 0,
          }
          let offset = 0
          let batchNum = 0
          for (;;) {
            batchNum += 1
            patchJobStep(step.id, {
              status: 'running',
              detail: `Pushing batch ${batchNum} (offset ${offset})…`,
            })
            const batch = await apiFetch('/admin/wa-templates/cleanup-and-sync', {
              method: 'POST',
              body: JSON.stringify({
                dry_run: dryRun,
                step: 'push_buttoned',
                offset,
                limit: PUSH_BATCH,
              }),
              timeoutMs: 280000,
              quietNetworkHint: true,
            })
            acc.pushed_buttoned.push(...(batch?.pushed_buttoned || []))
            acc.failed.push(...(batch?.failed || []))
            if (offset === 0) {
              acc.skipped_buttonless = batch?.skipped_buttonless || []
              acc.skipped_buttonless_total = batch?.skipped_buttonless_total ?? acc.skipped_buttonless.length
              acc.keepers_count = batch?.keepers_count ?? 0
              acc.buttoned_total = batch?.buttoned_total ?? 0
            }
            const done = acc.pushed_buttoned.length + acc.failed.length
            const total = acc.buttoned_total || done
            patchJobStep(step.id, {
              status: 'running',
              detail: `Pushed ${done} / ${total} buttoned…`,
            })
            if (!batch?.has_more) break
            offset = Number(batch?.next_offset ?? offset + PUSH_BATCH)
          }
          acc.pushed_buttoned_count = acc.pushed_buttoned.length
          acc.failed_count = acc.failed.length
          acc.skipped_buttonless_count = acc.skipped_buttonless.length
          push = acc
          patchJobStep(step.id, {
            status: 'done',
            detail: `Pushed ${acc.pushed_buttoned_count}, failed ${acc.failed_count}, buttonless ${acc.skipped_buttonless_total}`,
          })
          continue
        }

        const body = { dry_run: dryRun, step: step.id }
        if (step.id === 'finalize') {
          body.meta = meta
          body.local = local
          body.push = push
        }
        const result = await apiFetch('/admin/wa-templates/cleanup-and-sync', {
          method: 'POST',
          body: JSON.stringify(body),
          timeoutMs: 280000,
          quietNetworkHint: true,
        })
        if (step.id === 'meta_cleanup') meta = result
        if (step.id === 'local_cleanup') local = result

        const detail =
          result?.message ||
          (step.id === 'meta_cleanup'
            ? `Deleted ${result?.deleted_meta_count ?? 0} from Meta`
            : step.id === 'local_cleanup'
              ? `Deleted ${result?.deleted_local_count ?? 0} from local`
              : 'Report ready')
        patchJobStep(step.id, { status: 'done', detail })

        if (step.id === 'finalize') {
          const parts = [result?.message || label, result?.report_path ? `Report: ${result.report_path}` : null].filter(
            Boolean,
          )
          setMsg(parts.join(' · '))
          setJob((prev) => ({
            ...prev,
            phase: 'done',
            message: parts.join(' · '),
            summaryRows: Array.isArray(result?.summary_rows) ? result.summary_rows : [],
            tables: result?.tables || {},
            reportPath: result?.report_path || '',
          }))
        }
      }
      await loadTemplateCounts()
      refreshTabData()
    } catch (e) {
      const errText = formatWaSurveyError(e, `${label} failed`).detailText || e?.message
      setError(errText)
      setJob((prev) => ({
        ...prev,
        phase: 'error',
        error: errText,
      }))
    } finally {
      setCleaning(false)
    }
  }

  const flatTemplates = useMemo(() => {
    if (tab === 'ai') return interviewTemplates
    if (tab === 'marketing') return marketingTemplates
    if (tab === 'sales') return salesTemplates
    return []
  }, [tab, interviewTemplates, marketingTemplates, salesTemplates])

  const showCleanupActions = tab === 'survey' || tab === 'feedback'

  return (
    <div className="waTemplatesHub ds-scope min-h-full bg-background">
      <header className="sticky top-0 z-30 border-b bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
        <div className="mx-auto flex h-12 max-w-[1400px] items-center gap-3 px-4">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-[#25D366]/15 text-[#128C7E]">
              <MessageSquareHeart className="h-4 w-4" />
            </div>
            <div>
              <div className="text-sm font-semibold leading-none">WA Templates</div>
              <div className="mt-0.5 text-[10px] text-muted-foreground">Internal · WhatsApp Business Templates</div>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-3">
            <div className="hidden items-center gap-3 text-[11px] text-muted-foreground lg:flex">
              <span className="inline-flex items-center gap-1" title="Live Meta: Utility category">
                <span className="font-medium tabular-nums text-foreground">{templateCounts.utility}</span> utility
              </span>
              <span
                className={cn(
                  'inline-flex items-center gap-1',
                  templateCounts.marketing > 0 && 'font-medium text-warning-foreground',
                )}
                title="Live Meta: Marketing category"
              >
                <span className="tabular-nums">{templateCounts.marketing}</span> marketing
              </span>
              <span className="h-3 w-px bg-border" />
              <span className="inline-flex items-center gap-1 text-success" title="Live Meta: approved">
                <ClipboardList className="h-3 w-3" />
                <span className="font-medium tabular-nums">{templateCounts.approved}</span> approved
              </span>
              {templateCounts.rejected > 0 ? (
                <span className="inline-flex items-center gap-1 font-medium text-destructive" title="Live Meta: rejected">
                  <span className="tabular-nums">{templateCounts.rejected}</span> rejected
                </span>
              ) : null}
              <span
                className="inline-flex items-center gap-1"
                title="Local only (buttonless / drafts — not on Meta). Local is source of truth."
              >
                <BarChart3 className="h-3 w-3" />
                <span className="font-medium tabular-nums text-foreground">{templateCounts.localOnly}</span> local-only
              </span>
              <span
                className="inline-flex items-center gap-1"
                title="Live Meta WABA rows + local-only drafts (not the same as Meta Manager alone)"
              >
                <span className="font-medium tabular-nums text-foreground">{templateCounts.total}</span> meta+local
              </span>
            </div>
            <Link
              to="/ai/wa-messages"
              className="inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              Inbound messages
            </Link>
            {showCleanupActions ? (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 gap-1.5 text-xs"
                  onClick={() => void runCleanupAndSync({ dryRun: true })}
                  disabled={cleaning || syncing}
                >
                  <Trash2 className={cn('h-3.5 w-3.5', cleaning && 'animate-pulse')} />
                  Dry-run cleanup
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 gap-1.5 text-xs"
                  onClick={() => void runCleanupAndSync({ dryRun: false })}
                  disabled={cleaning || syncing}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  {cleaning ? 'Cleaning…' : 'Cleanup + push buttoned'}
                </Button>
              </>
            ) : null}
            <Button
              size="sm"
              className="wa-hub-primary-btn h-8 gap-1.5 text-xs"
              onClick={() => void syncFromMeta()}
              disabled={syncing || cleaning}
            >
              <RefreshCw className={cn('h-3.5 w-3.5', syncing && 'animate-spin')} />
              {syncing ? (syncProgress ? `Syncing ${syncProgress}` : 'Syncing…') : 'Sync with Meta'}
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] p-4">
        {error ? (
          <div className="mb-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </div>
        ) : null}
        {msg ? (
          <div className="mb-3 rounded-md border border-success/30 bg-success-soft px-3 py-2 text-xs text-success">
            {msg}
          </div>
        ) : null}

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="h-9 gap-1 rounded-lg border bg-surface-muted p-1">
            {TAGS.map((tg) => {
              const Icon = tg.icon
              return (
                <TabsTrigger
                  key={tg.id}
                  value={tg.id}
                  className="h-7 gap-1.5 rounded-md px-3 text-xs data-[state=active]:bg-background data-[state=active]:shadow-sm"
                >
                  <Icon className="h-3.5 w-3.5" />
                  {tg.label}
                </TabsTrigger>
              )
            })}
          </TabsList>

          {TAGS.map((tg) => (
            <TabsContent key={tg.id} value={tg.id} className="mt-3">
              <div className="overflow-hidden rounded-xl border bg-surface shadow-sm">
                {tg.id === 'survey' ? (
                  <WaIndustryBrowser
                    product="survey"
                    industries={surveyIndustries}
                    loadingIndustries={surveyIndustriesLoading}
                    onReloadIndustries={loadSurveyIndustries}
                    onEditRow={(row) => void openSurveyTypeEditor(row)}
                    onSyncRow={(row) => void pushSurveyType(row)}
                    onToggleRow={(row) => void toggleSurveyType(row)}
                    onDeleteRow={(row) => void deleteSurveyType(row)}
                    onRejectRow={setRejectRow}
                    syncingId={syncingId}
                    onOpenSystemTemplate={setEditTarget}
                    onError={setError}
                    onMessage={setMsg}
                  />
                ) : null}

                {tg.id === 'feedback' ? (
                  <WaIndustryBrowser
                    product="feedback"
                    industries={feedbackIndustries}
                    loadingIndustries={feedbackIndustriesLoading}
                    onReloadIndustries={loadFeedbackIndustries}
                    onEditRow={(row) => void openSurveyTypeEditor(row)}
                    onSyncRow={(row) => void pushSurveyType(row)}
                    onToggleRow={(row) => void toggleSurveyType(row)}
                    onDeleteRow={(row) => void deleteSurveyType(row)}
                    onRejectRow={setRejectRow}
                    syncingId={syncingId}
                    onOpenSystemTemplate={setEditTarget}
                    onError={setError}
                    onMessage={setMsg}
                  />
                ) : null}

                {tg.id === 'ai' ? (
                  <WaTemplatesTable
                    templates={flatTemplates}
                    loading={flatLoading}
                    onEdit={(row) => setEditTarget({ product: 'interview', templateId: row.id })}
                    onSync={(row) => void pushInterview(row)}
                    onToggle={(row) => void toggleInterview(row)}
                    onDelete={(row) => void deleteInterview(row)}
                    onReject={setRejectRow}
                    syncingId={syncingId}
                    plainNames
                    showNew={false}
                    emptyLabel="No templates yet."
                  />
                ) : null}

                {tg.id === 'marketing' ? (
                  <WaTemplatesTable
                    templates={flatTemplates}
                    loading={flatLoading}
                    onEdit={(row) => void marketingAction(row, 'edit')}
                    onSync={(row) => void marketingAction(row, 'sync')}
                    onToggle={(row) => void marketingAction(row, 'disable')}
                    onDelete={(row) => void marketingAction(row, 'delete')}
                    showNew={false}
                    emptyLabel="No templates yet."
                  />
                ) : null}

                {tg.id === 'sales' ? (
                  <WaTemplatesTable
                    templates={flatTemplates}
                    loading={flatLoading}
                    onEdit={(row) => void salesAction(row, 'edit')}
                    onSync={(row) => void salesAction(row, 'sync')}
                    onToggle={(row) => void salesAction(row, 'disable')}
                    onDelete={(row) => void salesAction(row, 'delete')}
                    syncingId={syncingId}
                    showNew={false}
                    emptyLabel="No sales templates yet — open this tab to seed the four lead-sales templates."
                  />
                ) : null}

                {tg.id === 'companies' ? (
                  <div className="flex flex-col items-center gap-3 px-4 py-12 text-center">
                    <Building2 className="h-9 w-9 text-muted-foreground/60" />
                    <p className="max-w-md text-xs text-muted-foreground">
                      Customer Feedback Companies service — WhatsApp templates are not configured yet.
                    </p>
                  </div>
                ) : null}
              </div>
            </TabsContent>
          ))}
        </Tabs>
      </main>

      <WaEditSheet
        editTarget={editTarget}
        onClose={() => setEditTarget(null)}
        onSaved={() => {
          if (editTarget?.product === 'interview') void loadInterview()
          setEditTarget(null)
        }}
      />

      <WaRejectedDialog
        open={Boolean(rejectRow)}
        row={rejectRow}
        onClose={() => setRejectRow(null)}
        onDone={(message) => {
          setMsg(message)
          void loadTemplateCounts()
          if (tab === 'ai') void loadInterview()
          if (tab === 'survey') void loadSurveyIndustries()
          if (tab === 'feedback') void loadFeedbackIndustries()
        }}
        onError={setError}
      />

      <WaJobProgressDialog
        open={job.open}
        title={job.title}
        dryRun={job.dryRun}
        steps={job.steps}
        phase={job.phase}
        summaryRows={job.summaryRows}
        tables={job.tables}
        message={job.message}
        error={job.error}
        reportPath={job.reportPath}
        onClose={() => setJob(EMPTY_JOB)}
      />
    </div>
  )
}
