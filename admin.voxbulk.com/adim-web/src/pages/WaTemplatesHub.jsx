import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Ban,
  BarChart3,
  Building2,
  Calendar,
  ClipboardList,
  Megaphone,
  MessageSquareHeart,
  RefreshCw,
  Sparkles,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatWaSurveyError } from '../lib/waSurveyFeedback'
import DisabledWaTemplatesPanel from '../components/DisabledWaTemplatesPanel'
import WaInterviewTemplateModal from '../components/WaInterviewTemplateModal'
import WaAppointmentTemplateModal from '../components/WaAppointmentTemplateModal'
import WaSurveyTemplateModal from '../components/WaSurveyTemplateModal'
import WaIndustryBrowser from '../components/wa-templates/WaIndustryBrowser'
import WaTemplatesTable from '../components/wa-templates/WaTemplatesTable'
import { formatRelativeWhen, mapApprovalStatus, mapCategory } from '../components/wa-templates/waTemplatesUi'
import '../styles/wa-templates-hub.css'

const HUB_TABS = [
  { id: 'interview', label: 'AI Interview', icon: Sparkles },
  { id: 'survey', label: 'Survey', icon: ClipboardList },
  { id: 'feedback', label: 'Customer Feedback', icon: MessageSquareHeart },
  { id: 'companies', label: 'Companies', icon: Building2 },
  { id: 'marketing', label: 'Marketing', icon: Megaphone },
  { id: 'appointment', label: 'Appointment', icon: Calendar },
  { id: 'disabled', label: 'Disabled', icon: Ban },
]

const SALES_TEMPLATE_KEYS = new Set([
  'sales_offer',
  'sales_offer_followup',
  'sales_subscription',
  'sales_survey',
  'sales_interview',
])

function mapFlatTemplate(tpl, overrides = {}) {
  const langs = tpl.language ? [String(tpl.language).toUpperCase()] : tpl.langs || ['EN']
  return {
    id: tpl.id,
    name: tpl.name || tpl.display_name,
    langs,
    langsTitle: langs.join(' · '),
    category: mapCategory(tpl),
    status: mapApprovalStatus(tpl),
    used: tpl.usage_count ?? tpl.used_count ?? tpl.sent_count ?? 0,
    updated: formatRelativeWhen(tpl.updated_at || tpl.last_pushed_at || tpl.synced_at),
    raw: tpl,
    ...overrides,
  }
}

export default function WaTemplatesHub() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = searchParams.get('tab') || 'survey'

  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [working, setWorking] = useState('')

  const [templateCounts, setTemplateCounts] = useState({ total: 0, sent: 0 })

  const [interviewTemplates, setInterviewTemplates] = useState([])
  const [appointmentTemplates, setAppointmentTemplates] = useState([])
  const [marketingTemplates, setMarketingTemplates] = useState([])
  const [flatLoading, setFlatLoading] = useState(false)

  const [surveyIndustries, setSurveyIndustries] = useState([])
  const [surveyIndustriesLoading, setSurveyIndustriesLoading] = useState(false)

  const [feedbackIndustries, setFeedbackIndustries] = useState([])
  const [feedbackIndustriesLoading, setFeedbackIndustriesLoading] = useState(false)

  const [interviewEditId, setInterviewEditId] = useState(null)
  const [appointmentEditId, setAppointmentEditId] = useState(null)
  const [surveyEdit, setSurveyEdit] = useState(null)

  const setTab = (next) => {
    const params = new URLSearchParams(searchParams)
    params.set('tab', next)
    setSearchParams(params, { replace: true })
  }

  const loadTemplateCounts = useCallback(async () => {
    try {
      const data = await apiFetch('/admin/integrations/telnyx/whatsapp-templates?approved_only=false')
      const rows = Array.isArray(data?.templates) ? data.templates : []
      setTemplateCounts({
        total: rows.length,
        sent: rows.reduce((sum, t) => sum + (Number(t.usage_count) || 0), 0),
      })
    } catch {
      setTemplateCounts({ total: 0, sent: 0 })
    }
  }, [])

  const syncFromMeta = async () => {
    setSyncing(true)
    setError('')
    setMsg('')
    try {
      const result = await apiFetch('/admin/integrations/meta_whatsapp/whatsapp-templates/sync', { method: 'POST' })
      const rows = Array.isArray(result.templates) ? result.templates : []
      setMsg(formatActionSuccess(result, `Synced ${result.synced ?? rows.length} template(s) with Meta`).message)
      await loadTemplateCounts()
      refreshTabData()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Meta sync failed').detailText || e?.message || 'Meta sync failed')
    } finally {
      setSyncing(false)
    }
  }

  const loadInterview = useCallback(async () => {
    setFlatLoading(true)
    try {
      const data = await apiFetch('/admin/wa-interview/templates')
      setInterviewTemplates((Array.isArray(data?.templates) ? data.templates : []).map((t) => mapFlatTemplate(t)))
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load interview templates').message)
    } finally {
      setFlatLoading(false)
    }
  }, [])

  const loadAppointment = useCallback(async () => {
    setFlatLoading(true)
    try {
      const data = await apiFetch('/admin/wa-appointment/templates')
      setAppointmentTemplates((Array.isArray(data?.templates) ? data.templates : []).map((t) => mapFlatTemplate(t)))
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load appointment templates').message)
    } finally {
      setFlatLoading(false)
    }
  }, [])

  const loadMarketing = useCallback(async () => {
    setFlatLoading(true)
    try {
      const [health, stored] = await Promise.all([
        apiFetch('/admin/integrations/telnyx/whatsapp-templates/health'),
        apiFetch('/admin/integrations/telnyx/whatsapp-templates?approved_only=false'),
      ])
      const rows = (Array.isArray(stored?.templates) ? stored.templates : []).filter((t) => {
        const key = String(t.sales_template_key || '').toLowerCase()
        if (key && SALES_TEMPLATE_KEYS.has(key)) return true
        return String(t.name || '').toLowerCase().startsWith('voxbulk_sales_')
      })
      if (!rows.length && Array.isArray(health?.templates)) {
        setMarketingTemplates(
          health.templates.map((t) =>
            mapFlatTemplate({
              id: t.sales_key,
              display_name: t.sales_key,
              name: t.telnyx_name,
              sales_template_key: t.sales_key,
              status: t.status,
              language: t.language,
            }),
          ),
        )
      } else {
        setMarketingTemplates(rows.map((t) => mapFlatTemplate(t)))
      }
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
    if (tab === 'interview') void loadInterview()
    else if (tab === 'appointment') void loadAppointment()
    else if (tab === 'marketing') void loadMarketing()
    else if (tab === 'survey') void loadSurveyIndustries()
    else if (tab === 'feedback') void loadFeedbackIndustries()
  }, [tab, loadInterview, loadAppointment, loadMarketing, loadSurveyIndustries, loadFeedbackIndustries])

  useEffect(() => {
    void loadTemplateCounts()
  }, [loadTemplateCounts])

  useEffect(() => {
    setError('')
    refreshTabData()
  }, [refreshTabData])

  const openSurveyTypeEditor = async (row) => {
    if (row.rowKind === 'feedback_type') {
      navigate(`/customer-feedback/survey-types/${row.id}`)
      return
    }
    setWorking(`edit-${row.id}`)
    try {
      const data = await apiFetch(`/admin/wa-survey/types/${row.id}`)
      const templates = Array.isArray(data?.templates) ? data.templates : []
      if (!templates.length) {
        setError('No templates on this survey type yet.')
        return
      }
      setSurveyEdit({ templateId: templates[0].id, surveyTypeId: row.id, product: row.rowKind })
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not open editor').message)
    } finally {
      setWorking('')
    }
  }

  const pushSurveyType = async (row) => {
    setWorking(`sync-${row.id}`)
    setError('')
    try {
      const path =
        row.rowKind === 'feedback_type'
          ? `/admin/customer-feedback/survey-types/${row.id}/sync-telnyx`
          : `/admin/wa-survey/types/${row.id}/templates/push-all`
      const result = await apiFetch(path, { method: 'POST', body: '{}' })
      setMsg(formatActionSuccess(result, 'Synced with Meta').message)
    } catch (e) {
      setError(formatWaSurveyError(e, 'Sync failed').detailText)
    } finally {
      setWorking('')
    }
  }

  const pushInterview = async (row) => {
    setWorking(`sync-${row.id}`)
    try {
      const result = await apiFetch(`/admin/wa-interview/templates/${row.id}/push`, { method: 'POST', body: '{}' })
      setMsg(formatActionSuccess(result, 'Synced with Meta').message)
      await loadInterview()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Sync failed').detailText)
    } finally {
      setWorking('')
    }
  }

  const pushAppointment = async (row) => {
    setWorking(`sync-${row.id}`)
    try {
      const result = await apiFetch(`/admin/wa-appointment/templates/${row.id}/push`, { method: 'POST', body: '{}' })
      setMsg(formatActionSuccess(result, 'Synced with Meta').message)
      await loadAppointment()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Sync failed').detailText)
    } finally {
      setWorking('')
    }
  }

  const toggleInterview = async (row) => {
    setWorking(`toggle-${row.id}`)
    try {
      const active = row.raw?.active_for_interview !== false
      await apiFetch(`/admin/wa-interview/templates/${row.id}/set-active`, {
        method: 'POST',
        body: JSON.stringify({ active_for_interview: !active }),
      })
      await loadInterview()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not update status').message)
    } finally {
      setWorking('')
    }
  }

  const toggleAppointment = async (row) => {
    setWorking(`toggle-${row.id}`)
    try {
      const active = row.raw?.active_for_appointment !== false
      await apiFetch(`/admin/wa-appointment/templates/${row.id}/set-active`, {
        method: 'POST',
        body: JSON.stringify({ active_for_appointment: !active }),
      })
      await loadAppointment()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not update status').message)
    } finally {
      setWorking('')
    }
  }

  const flatTemplates = useMemo(() => {
    if (tab === 'interview') return interviewTemplates
    if (tab === 'appointment') return appointmentTemplates
    if (tab === 'marketing') return marketingTemplates
    return []
  }, [tab, interviewTemplates, appointmentTemplates, marketingTemplates])

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
            <div className="hidden items-center gap-3 text-[11px] text-muted-foreground md:flex">
              <span className="inline-flex items-center gap-1">
                <ClipboardList className="h-3 w-3" />
                <span className="font-medium tabular-nums text-foreground">{templateCounts.total}</span> templates
              </span>
              <span className="inline-flex items-center gap-1">
                <BarChart3 className="h-3 w-3" />
                <span className="font-medium tabular-nums text-foreground">
                  {templateCounts.sent.toLocaleString()}
                </span>{' '}
                sent
              </span>
            </div>
            <Button size="sm" className="h-8 gap-1.5 text-xs" onClick={() => void syncFromMeta()} disabled={syncing}>
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

        <div className="mb-3 inline-flex h-9 flex-wrap gap-0.5 rounded-lg border bg-surface-muted p-1">
          {HUB_TABS.map((tg) => {
            const Icon = tg.icon
            const active = tab === tg.id
            return (
              <button
                key={tg.id}
                type="button"
                onClick={() => setTab(tg.id)}
                className={cn(
                  'inline-flex h-7 items-center gap-1.5 rounded-md px-3 text-xs font-medium transition',
                  active ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground',
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {tg.label}
              </button>
            )
          })}
        </div>

        <div className="overflow-hidden rounded-xl border bg-surface shadow-sm">
          {tab === 'survey' ? (
            <WaIndustryBrowser
              product="survey"
              industries={surveyIndustries}
              loadingIndustries={surveyIndustriesLoading}
              onReloadIndustries={loadSurveyIndustries}
              onEditRow={(row) => void openSurveyTypeEditor(row)}
              onSyncRow={(row) => void pushSurveyType(row)}
              onError={setError}
              onMessage={setMsg}
            />
          ) : null}

          {tab === 'feedback' ? (
            <WaIndustryBrowser
              product="feedback"
              industries={feedbackIndustries}
              loadingIndustries={feedbackIndustriesLoading}
              onReloadIndustries={loadFeedbackIndustries}
              onEditRow={(row) => void openSurveyTypeEditor(row)}
              onSyncRow={(row) => void pushSurveyType(row)}
              onError={setError}
              onMessage={setMsg}
            />
          ) : null}

          {tab === 'interview' || tab === 'appointment' || tab === 'marketing' ? (
            <WaTemplatesTable
              templates={flatTemplates}
              loading={flatLoading}
              onEdit={(row) => {
                if (tab === 'interview') setInterviewEditId(row.id)
                else if (tab === 'appointment') setAppointmentEditId(row.id)
              }}
              onSync={
                tab === 'interview' ? pushInterview : tab === 'appointment' ? pushAppointment : null
              }
              onToggle={
                tab === 'interview' ? toggleInterview : tab === 'appointment' ? toggleAppointment : null
              }
              showNew={false}
              emptyLabel="No templates yet."
            />
          ) : null}

          {tab === 'companies' ? (
            <div className="flex flex-col items-center gap-3 px-4 py-12 text-center">
              <Building2 className="h-9 w-9 text-muted-foreground/60" />
              <p className="max-w-md text-xs text-muted-foreground">
                Customer Feedback Companies service — WhatsApp templates are not configured yet.
              </p>
            </div>
          ) : null}

          {tab === 'disabled' ? (
            <div className="p-3">
              <DisabledWaTemplatesPanel embedded onToast={(message, isError) => (isError ? setError(message) : setMsg(message))} />
            </div>
          ) : null}
        </div>
      </main>

      <WaInterviewTemplateModal
        templateId={interviewEditId}
        open={Boolean(interviewEditId)}
        onClose={() => setInterviewEditId(null)}
        onSaved={() => void loadInterview()}
      />
      <WaAppointmentTemplateModal
        templateId={appointmentEditId}
        open={Boolean(appointmentEditId)}
        onClose={() => setAppointmentEditId(null)}
        onSaved={() => void loadAppointment()}
      />

      {surveyEdit ? (
        <WaSurveyTemplateModal
          templateId={surveyEdit.templateId}
          surveyTypeId={surveyEdit.surveyTypeId}
          open
          sheetLayout
          onClose={() => setSurveyEdit(null)}
          onSaved={() => setSurveyEdit(null)}
        />
      ) : null}
    </div>
  )
}
