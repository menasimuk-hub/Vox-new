import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  BarChart3,
  Building2,
  ClipboardList,
  Megaphone,
  MessageSquareHeart,
  RefreshCw,
  Sparkles,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatWaSurveyError } from '../lib/waSurveyFeedback'
import WaIndustryBrowser from '../components/wa-templates/WaIndustryBrowser'
import WaTemplatesTable from '../components/wa-templates/WaTemplatesTable'
import WaEditSheet from '../components/wa-templates/WaEditSheet'
import { summarizeCatalog, toHubRow } from '../components/wa-templates/waTemplatesUi'
import '../styles/wa-templates-hub.css'

const TAGS = [
  { id: 'ai', label: 'AI Interview', icon: Sparkles },
  { id: 'survey', label: 'Survey', icon: ClipboardList },
  { id: 'feedback', label: 'Customer Feedback', icon: MessageSquareHeart },
  { id: 'companies', label: 'Companies', icon: Building2 },
  { id: 'marketing', label: 'Marketing', icon: Megaphone },
]

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

function isMarketingTemplate(t) {
  if (isInterviewTemplate(t)) return false
  const key = templateKey(t)
  const name = templateName(t)
  if (MARKETING_TEMPLATE_KEYS.has(key)) return true
  if (key.startsWith('sales_')) return true
  if (name.startsWith('voxbulk_sales_')) return true
  return false
}

const TAB_ALIASES = { interview: 'ai', appointment: 'ai' }

export default function WaTemplatesHub() {
  const [searchParams, setSearchParams] = useSearchParams()
  const rawTab = searchParams.get('tab') || 'survey'
  const tab = TAB_ALIASES[rawTab] || (TAGS.some((t) => t.id === rawTab) ? rawTab : 'survey')

  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [templateCounts, setTemplateCounts] = useState({
    total: 0,
    approved: 0,
    localOnly: 0,
    pending: 0,
    rejected: 0,
  })

  const [interviewTemplates, setInterviewTemplates] = useState([])
  const [marketingTemplates, setMarketingTemplates] = useState([])
  const [flatLoading, setFlatLoading] = useState(false)

  const [surveyIndustries, setSurveyIndustries] = useState([])
  const [surveyIndustriesLoading, setSurveyIndustriesLoading] = useState(false)
  const [feedbackIndustries, setFeedbackIndustries] = useState([])
  const [feedbackIndustriesLoading, setFeedbackIndustriesLoading] = useState(false)

  const [editTarget, setEditTarget] = useState(null)

  const setTab = (next) => {
    const params = new URLSearchParams(searchParams)
    params.set('tab', next)
    setSearchParams(params, { replace: true })
  }

  const loadTemplateCounts = useCallback(async () => {
    try {
      const data = await apiFetch('/admin/integrations/telnyx/whatsapp-templates?approved_only=false')
      const rows = Array.isArray(data?.templates) ? data.templates : []
      setTemplateCounts(summarizeCatalog(rows))
    } catch {
      setTemplateCounts({ total: 0, approved: 0, localOnly: 0, pending: 0, rejected: 0 })
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
    else if (tab === 'survey') void loadSurveyIndustries()
    else if (tab === 'feedback') void loadFeedbackIndustries()
  }, [tab, loadInterview, loadMarketing, loadSurveyIndustries, loadFeedbackIndustries])

  useEffect(() => {
    void loadTemplateCounts()
  }, [loadTemplateCounts])

  useEffect(() => {
    setError('')
    refreshTabData()
  }, [refreshTabData])

  const syncFromMeta = async () => {
    setSyncing(true)
    setError('')
    setMsg('')
    try {
      // Full Meta catalog + link repair can take several minutes (hundreds of templates).
      // Default apiFetch timeout is 90s and aborts with "signal is aborted without reason".
      const result = await apiFetch('/admin/integrations/meta_whatsapp/whatsapp-templates/sync', {
        method: 'POST',
        timeoutMs: 300000,
        quietNetworkHint: true,
      })
      const rows = Array.isArray(result.templates) ? result.templates : []
      const fallback =
        `Synced ${result.synced ?? rows.length} · Approved ${result.approved ?? 0} · Pending ${result.pending ?? 0} · ` +
        `Rejected ${result.rejected ?? 0} · Linked ${result.linked_to_survey_type ?? 0} · ` +
        `Unlinked types ${result.unlinked_survey_types ?? 0}`
      setMsg(formatActionSuccess(result, fallback).message)
      // Prefer summary counts from sync payload (full catalog is not returned — too large).
      if (result.synced != null || result.approved != null) {
        setTemplateCounts({
          total: Number(result.synced ?? rows.length) || 0,
          approved: Number(result.approved ?? 0) || 0,
          localOnly: Number(result.local_only ?? 0) || 0,
          pending: Number(result.pending ?? 0) || 0,
          rejected: Number(result.rejected ?? 0) || 0,
        })
      } else if (rows.length) {
        setTemplateCounts(summarizeCatalog(rows))
      } else {
        await loadTemplateCounts()
      }
      refreshTabData()
    } catch (e) {
      const raw = e?.message || String(e)
      const aborted = e?.name === 'AbortError' || /aborted|abort/i.test(raw)
      setError(
        aborted
          ? 'Meta sync timed out in the browser. The server may still be finishing — wait 1–2 minutes, refresh this page, and check template statuses. If it keeps failing, raise nginx proxy_read_timeout for /api/ to 300s.'
          : formatWaSurveyError(e, 'Meta sync failed').detailText || raw || 'Meta sync failed',
      )
    } finally {
      setSyncing(false)
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
    try {
      if (row.rowKind === 'survey_template') {
        const result = await apiFetch(`/admin/wa-survey/templates/${row.id}/push`, { method: 'POST', body: '{}' })
        setMsg(formatActionSuccess(result, 'Synced with Meta').message)
        await loadTemplateCounts()
        return
      }
      if (row.rowKind === 'feedback_template') {
        const result = await apiFetch(`/admin/customer-feedback/survey-types/${row.surveyTypeId}/sync-telnyx`, {
          method: 'POST',
        })
        setMsg(formatActionSuccess(result, 'Synced with Meta').message)
        return
      }
      const typeId = row.surveyTypeId || row.id
      const path =
        row.rowKind === 'feedback_type'
          ? `/admin/customer-feedback/survey-types/${typeId}/sync-telnyx`
          : `/admin/wa-survey/types/${typeId}/templates/push-all`
      const result = await apiFetch(path, { method: 'POST', body: '{}' })
      setMsg(formatActionSuccess(result, 'Synced with Meta').message)
      await loadTemplateCounts()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Sync failed').detailText)
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
    if (!window.confirm(`Delete “${row.name}”? This cannot be undone.`)) return
    setError('')
    try {
      if (row.rowKind === 'survey_template') {
        const typeId = row.surveyTypeId
        if (typeId) {
          await apiFetch(`/admin/wa-survey/types/${typeId}/templates/${row.id}`, { method: 'DELETE' })
        } else {
          setError('Cannot delete: missing survey type link')
          return
        }
        setMsg('Template deleted')
        await loadTemplateCounts()
        return
      }
      if (row.rowKind === 'feedback_type' || row.rowKind === 'feedback_template') {
        if (row.rowKind === 'feedback_type') {
          await apiFetch(`/admin/customer-feedback/survey-types/${row.id}`, { method: 'DELETE' })
          setMsg('Survey type deleted')
        } else {
          setError('Delete feedback templates from the survey type editor.')
        }
        return
      }
      await apiFetch(`/admin/wa-survey/types/${row.id}`, { method: 'DELETE' })
      setMsg('Survey type deleted')
    } catch (e) {
      setError(formatWaSurveyError(e, 'Delete failed').message)
    }
  }

  const pushInterview = async (row) => {
    try {
      const result = await apiFetch(`/admin/wa-interview/templates/${row.id}/push`, { method: 'POST', body: '{}' })
      setMsg(formatActionSuccess(result, 'Synced with Meta').message)
      await loadInterview()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Sync failed').detailText)
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

  const flatTemplates = useMemo(() => {
    if (tab === 'ai') return interviewTemplates
    if (tab === 'marketing') return marketingTemplates
    return []
  }, [tab, interviewTemplates, marketingTemplates])

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
              <span className="inline-flex items-center gap-1 text-success" title="Approved on Meta">
                <ClipboardList className="h-3 w-3" />
                <span className="font-medium tabular-nums">{templateCounts.approved}</span> approved
              </span>
              {templateCounts.rejected > 0 ? (
                <span className="inline-flex items-center gap-1 font-medium text-destructive" title="Rejected on Meta — needs fix">
                  <span className="tabular-nums">{templateCounts.rejected}</span> rejected
                </span>
              ) : null}
              <span className="inline-flex items-center gap-1" title="Local only — not on Meta yet">
                <BarChart3 className="h-3 w-3" />
                <span className="font-medium tabular-nums text-foreground">{templateCounts.localOnly}</span> local
              </span>
              <span className="inline-flex items-center gap-1" title="All rows in catalog (Meta + local)">
                <span className="font-medium tabular-nums text-foreground">{templateCounts.total}</span> total
              </span>
            </div>
            <Button
              size="sm"
              className="wa-hub-primary-btn h-8 gap-1.5 text-xs"
              onClick={() => void syncFromMeta()}
              disabled={syncing}
            >
              <RefreshCw className={cn('h-3.5 w-3.5', syncing && 'animate-spin')} />
              {syncing ? 'Syncing…' : 'Sync with Meta'}
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
          <TabsList className="h-9 border bg-surface-muted">
            {TAGS.map((tg) => {
              const Icon = tg.icon
              return (
                <TabsTrigger key={tg.id} value={tg.id} className="h-7 gap-1.5 text-xs data-[state=active]:bg-background">
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
    </div>
  )
}
