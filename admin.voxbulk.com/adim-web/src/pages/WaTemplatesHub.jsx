import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Building2, ChevronRight, RefreshCw } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatWaSurveyError } from '../lib/waSurveyFeedback'
import { resolveTelnyxSyncLabel, telnyxSyncPillClass, templateSyncButtonLabel } from '../lib/waSurveyTelnyxSync'
import DisabledWaTemplatesPanel from '../components/DisabledWaTemplatesPanel'
import SystemTemplatesCard from '../components/SystemTemplatesCard'
import WaInterviewTemplateModal from '../components/WaInterviewTemplateModal'
import WaAppointmentTemplateModal from '../components/WaAppointmentTemplateModal'
import { Panel } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Pill } from '@/components/ui/Badge'
import {
  StripeTable,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableLoading,
  TableRow,
} from '@/components/ui/Table'

const HUB_TABS = [
  { id: 'survey', label: 'Survey' },
  { id: 'feedback', label: 'Customer Feedback' },
  { id: 'interview', label: 'AI Interview' },
  { id: 'appointment', label: 'Appointment' },
  { id: 'marketing', label: 'Marketing' },
  { id: 'companies', label: 'Companies' },
  { id: 'disabled', label: 'Disabled' },
]

const SALES_TEMPLATE_KEYS = new Set([
  'sales_offer',
  'sales_offer_followup',
  'sales_subscription',
  'sales_survey',
  'sales_interview',
])

function formatWhen(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function IndustryGrid({ industries, loading, onSelect, emptyLabel }) {
  if (loading) {
    return <div className="muted py-8 text-center text-sm">Loading industries…</div>
  }
  if (!industries.length) {
    return <div className="muted py-8 text-center text-sm">{emptyLabel}</div>
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {industries.map((ind) => (
        <button
          key={ind.id}
          type="button"
          className="rounded-lg border border-border bg-card p-4 text-left transition hover:border-primary/40 hover:shadow-sm"
          onClick={() => onSelect(ind)}
        >
          <div className="flex items-start justify-between gap-2">
            <strong className="text-sm font-medium">{ind.name}</strong>
            <ChevronRight size={16} className="mt-0.5 shrink-0 text-muted-foreground" />
          </div>
          <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
            {ind.survey_type_count != null ? <span>{ind.survey_type_count} types</span> : null}
            {ind.template_count != null ? <span>{ind.template_count} templates</span> : null}
            {ind.visibility_mode === 'restricted' ? <Pill tone="warning">Restricted</Pill> : null}
            {ind.is_active === false ? <Pill tone="neutral">Inactive</Pill> : null}
          </div>
        </button>
      ))}
    </div>
  )
}

function SurveyTypeList({ types, loading, editBasePath, onPushAll, pushing, productLabel }) {
  if (loading) return <div className="muted py-6 text-center text-sm">Loading survey types…</div>
  if (!types.length) return <div className="muted py-6 text-center text-sm">No survey types in this industry.</div>
  return (
    <StripeTable>
      <TableHeader>
        <TableRow>
          <TableHead>Survey type</TableHead>
          <TableHead>Templates</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {types.map((t) => (
          <TableRow key={t.id}>
            <TableCell>
              <strong className="font-medium">{t.name}</strong>
              <div className="text-[11px] text-muted-foreground">{t.slug}</div>
            </TableCell>
            <TableCell className="text-muted-foreground">
              {t.template_count ?? t.templates_count ?? '—'}
            </TableCell>
            <TableCell>
              <Pill tone={t.is_active === false ? 'neutral' : 'success'}>{t.is_active === false ? 'Inactive' : 'Active'}</Pill>
            </TableCell>
            <TableCell>
              <div className="flex justify-end gap-1">
                <Button type="button" variant="outline" size="sm" className="h-7" asChild>
                  <Link to={`${editBasePath}/${t.id}`}>Edit templates</Link>
                </Button>
                {onPushAll ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-7"
                    disabled={pushing === t.id}
                    onClick={() => onPushAll(t)}
                  >
                    {pushing === t.id ? 'Pushing…' : 'Push all to Meta'}
                  </Button>
                ) : null}
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </StripeTable>
  )
}

function FlatTemplateTable({
  templates,
  loading,
  working,
  onEdit,
  onPush,
  onToggleHidden,
  hiddenField,
  nameLabel = 'Meta name',
}) {
  return (
    <StripeTable>
      <TableHeader>
        <TableRow>
          <TableHead>Template</TableHead>
          <TableHead>{nameLabel}</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Visibility</TableHead>
          <TableHead>Updated</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {loading ? (
          <TableLoading colSpan={6} />
        ) : (
          templates.map((tpl) => (
            <TableRow key={tpl.id}>
              <TableCell>
                <strong className="font-medium">{tpl.display_name || tpl.name}</strong>
                <div className="text-[11px] text-muted-foreground">{tpl.description || tpl.sales_template_key || tpl.category}</div>
              </TableCell>
              <TableCell>
                <code className="text-[11px]">{tpl.name}</code>
              </TableCell>
              <TableCell>
                <span className={telnyxSyncPillClass(resolveTelnyxSyncLabel(tpl))}>{resolveTelnyxSyncLabel(tpl)}</span>
              </TableCell>
              <TableCell>
                {hiddenField ? (
                  <Pill tone={tpl[hiddenField] === false ? 'neutral' : 'success'}>
                    {tpl[hiddenField] === false ? 'Hidden' : 'Active'}
                  </Pill>
                ) : (
                  <Pill tone={String(tpl.status || '').toUpperCase() === 'APPROVED' ? 'success' : 'neutral'}>
                    {tpl.status || '—'}
                  </Pill>
                )}
              </TableCell>
              <TableCell className="whitespace-nowrap text-[11px] text-muted-foreground">
                {formatWhen(tpl.updated_at || tpl.last_pushed_at || tpl.synced_at)}
              </TableCell>
              <TableCell>
                <div className="flex justify-end gap-1">
                  {onEdit ? (
                    <Button type="button" variant="outline" size="sm" className="h-7" onClick={() => onEdit(tpl)}>
                      Edit
                    </Button>
                  ) : null}
                  {onToggleHidden && hiddenField ? (
                    <Button type="button" variant="outline" size="sm" className="h-7" disabled={!!working} onClick={() => onToggleHidden(tpl)}>
                      {tpl[hiddenField] === false ? 'Show' : 'Hide'}
                    </Button>
                  ) : null}
                  {onPush ? (
                    <Button type="button" variant="outline" size="sm" className="h-7" disabled={!!working} onClick={() => onPush(tpl)}>
                      {working === `push-${tpl.id}` ? 'Pushing…' : templateSyncButtonLabel(tpl, { syncing: working === `push-${tpl.id}` })}
                    </Button>
                  ) : null}
                </div>
              </TableCell>
            </TableRow>
          ))
        )}
        {!loading && !templates.length ? <TableEmpty colSpan={6}>No templates yet.</TableEmpty> : null}
      </TableBody>
    </StripeTable>
  )
}

export default function WaTemplatesHub() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = searchParams.get('tab') || 'survey'

  const [metaConfigured, setMetaConfigured] = useState(null)
  const [syncBusy, setSyncBusy] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [working, setWorking] = useState('')
  const [templateCounts, setTemplateCounts] = useState({ total: 0, approved: 0, pending: 0 })

  const [interviewTemplates, setInterviewTemplates] = useState([])
  const [appointmentTemplates, setAppointmentTemplates] = useState([])
  const [marketingTemplates, setMarketingTemplates] = useState([])
  const [interviewEditId, setInterviewEditId] = useState(null)
  const [appointmentEditId, setAppointmentEditId] = useState(null)

  const [surveyIndustries, setSurveyIndustries] = useState([])
  const [surveyIndustry, setSurveyIndustry] = useState(null)
  const [surveyTypes, setSurveyTypes] = useState([])
  const [surveyLoading, setSurveyLoading] = useState(false)

  const [feedbackIndustries, setFeedbackIndustries] = useState([])
  const [feedbackIndustry, setFeedbackIndustry] = useState(null)
  const [feedbackTypes, setFeedbackTypes] = useState([])
  const [feedbackLoading, setFeedbackLoading] = useState(false)

  const setTab = (next) => {
    const params = new URLSearchParams(searchParams)
    params.set('tab', next)
    params.delete('industry')
    setSearchParams(params, { replace: true })
    setSurveyIndustry(null)
    setFeedbackIndustry(null)
  }

  const loadMetaStatus = useCallback(async () => {
    try {
      const data = await apiFetch('/admin/integrations/meta_whatsapp')
      const cfg = data?.config || {}
      const enabled = Boolean(data?.enabled)
      const ready = enabled && Boolean(cfg.waba_id && cfg.phone_number_id && (data?.secret_set?.access_token || cfg.access_token))
      setMetaConfigured(ready)
    } catch {
      setMetaConfigured(false)
    }
  }, [])

  const loadTemplateCounts = useCallback(async () => {
    try {
      const data = await apiFetch('/admin/integrations/telnyx/whatsapp-templates?approved_only=false')
      const rows = Array.isArray(data?.templates) ? data.templates : []
      setTemplateCounts({
        total: rows.length,
        approved: rows.filter((t) => String(t.status || '').toUpperCase() === 'APPROVED').length,
        pending: rows.filter((t) => String(t.status || '').toUpperCase() === 'PENDING').length,
      })
    } catch {
      setTemplateCounts({ total: 0, approved: 0, pending: 0 })
    }
  }, [])

  const syncFromMeta = async () => {
    setSyncBusy(true)
    setError('')
    setMsg('')
    try {
      const result = await apiFetch('/admin/integrations/meta_whatsapp/whatsapp-templates/sync', { method: 'POST' })
      const rows = Array.isArray(result.templates) ? result.templates : []
      setMsg(
        formatActionSuccess(result, `Synced ${result.synced ?? rows.length} template(s) from Meta`).message ||
          `Synced ${result.synced ?? rows.length} template(s) from Meta`,
      )
      await loadTemplateCounts()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Meta sync failed').detailText || e?.message || 'Meta sync failed')
    } finally {
      setSyncBusy(false)
    }
  }

  const loadInterview = useCallback(async () => {
    setSurveyLoading(true)
    try {
      const data = await apiFetch('/admin/wa-interview/templates')
      setInterviewTemplates(Array.isArray(data?.templates) ? data.templates : [])
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load interview templates').message)
    } finally {
      setSurveyLoading(false)
    }
  }, [])

  const loadAppointment = useCallback(async () => {
    setSurveyLoading(true)
    try {
      const data = await apiFetch('/admin/wa-appointment/templates')
      setAppointmentTemplates(Array.isArray(data?.templates) ? data.templates : [])
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load appointment templates').message)
    } finally {
      setSurveyLoading(false)
    }
  }, [])

  const loadMarketing = useCallback(async () => {
    setSurveyLoading(true)
    try {
      const [health, stored] = await Promise.all([
        apiFetch('/admin/integrations/telnyx/whatsapp-templates/health'),
        apiFetch('/admin/integrations/telnyx/whatsapp-templates?approved_only=false'),
      ])
      const rows = (Array.isArray(stored?.templates) ? stored.templates : []).filter((t) => {
        const key = String(t.sales_template_key || '').toLowerCase()
        if (key && SALES_TEMPLATE_KEYS.has(key)) return true
        const name = String(t.name || '').toLowerCase()
        return name.startsWith('voxbulk_sales_')
      })
      if (!rows.length && Array.isArray(health?.templates)) {
        setMarketingTemplates(
          health.templates.map((t) => ({
            id: t.sales_key,
            display_name: t.sales_key,
            name: t.telnyx_name,
            sales_template_key: t.sales_key,
            status: t.status,
            language: t.language,
            synced: t.synced,
          })),
        )
      } else {
        setMarketingTemplates(rows)
      }
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load marketing templates').message)
    } finally {
      setSurveyLoading(false)
    }
  }, [])

  const loadSurveyIndustries = useCallback(async () => {
    setSurveyLoading(true)
    try {
      const data = await apiFetch('/admin/wa-survey/overview')
      setSurveyIndustries(Array.isArray(data?.industries) ? data.industries : [])
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load survey industries').message)
    } finally {
      setSurveyLoading(false)
    }
  }, [])

  const loadFeedbackIndustries = useCallback(async () => {
    setFeedbackLoading(true)
    try {
      const data = await apiFetch('/admin/customer-feedback/industries')
      setFeedbackIndustries(Array.isArray(data?.items) ? data.items : [])
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load feedback industries').message)
    } finally {
      setFeedbackLoading(false)
    }
  }, [])

  const openSurveyIndustry = async (ind) => {
    setSurveyIndustry(ind)
    setSurveyLoading(true)
    try {
      const data = await apiFetch(`/admin/wa-survey/types?industry_id=${encodeURIComponent(ind.id)}`)
      setSurveyTypes(Array.isArray(data?.types) ? data.types : [])
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load survey types').message)
    } finally {
      setSurveyLoading(false)
    }
  }

  const openFeedbackIndustry = async (ind) => {
    setFeedbackIndustry(ind)
    setFeedbackLoading(true)
    try {
      const data = await apiFetch(`/admin/customer-feedback/industries/${encodeURIComponent(ind.id)}`)
      const detail = data?.item || {}
      setFeedbackTypes(Array.isArray(detail.survey_types) ? detail.survey_types : [])
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load feedback survey types').message)
    } finally {
      setFeedbackLoading(false)
    }
  }

  const pushSurveyTypeAll = async (typeRow) => {
    setWorking(typeRow.id)
    setError('')
    try {
      const result = await apiFetch(`/admin/wa-survey/types/${typeRow.id}/templates/push-all`, { method: 'POST', body: '{}' })
      setMsg(formatActionSuccess(result, 'Pushed templates to Meta').message)
    } catch (e) {
      setError(formatWaSurveyError(e, 'Push to Meta failed').detailText)
    } finally {
      setWorking('')
    }
  }

  const pushFeedbackIndustryAll = async () => {
    if (!feedbackIndustry) return
    setWorking('feedback-push-all')
    setError('')
    try {
      const result = await apiFetch(`/admin/customer-feedback/industries/${feedbackIndustry.id}/sync-telnyx`, { method: 'POST' })
      setMsg(formatActionSuccess(result, 'Pushed feedback templates to Meta').message)
    } catch (e) {
      setError(formatWaSurveyError(e, 'Push to Meta failed').detailText)
    } finally {
      setWorking('')
    }
  }

  const pushSurveyIndustryAll = async () => {
    if (!surveyIndustry) return
    setWorking('survey-push-all')
    setError('')
    try {
      const result = await apiFetch(`/admin/wa-survey/industries/${surveyIndustry.id}/templates/push-all`, { method: 'POST', body: '{}' })
      setMsg(formatActionSuccess(result, 'Pushed industry templates to Meta').message)
    } catch (e) {
      setError(formatWaSurveyError(e, 'Push to Meta failed').detailText)
    } finally {
      setWorking('')
    }
  }

  const pushInterview = async (tpl) => {
    setWorking(`push-${tpl.id}`)
    try {
      const result = await apiFetch(`/admin/wa-interview/templates/${tpl.id}/push`, { method: 'POST', body: '{}' })
      setMsg(formatActionSuccess(result, 'Pushed to Meta').message)
      await loadInterview()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Push to Meta failed').detailText)
    } finally {
      setWorking('')
    }
  }

  const pushAppointment = async (tpl) => {
    setWorking(`push-${tpl.id}`)
    try {
      const result = await apiFetch(`/admin/wa-appointment/templates/${tpl.id}/push`, { method: 'POST', body: '{}' })
      setMsg(formatActionSuccess(result, 'Pushed to Meta').message)
      await loadAppointment()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Push to Meta failed').detailText)
    } finally {
      setWorking('')
    }
  }

  const toggleInterviewHidden = async (tpl) => {
    setWorking(`hide-${tpl.id}`)
    try {
      await apiFetch(`/admin/wa-interview/templates/${tpl.id}/set-active`, {
        method: 'POST',
        body: JSON.stringify({ active_for_interview: tpl.active_for_interview === false }),
      })
      await loadInterview()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not update visibility').message)
    } finally {
      setWorking('')
    }
  }

  const toggleAppointmentHidden = async (tpl) => {
    setWorking(`hide-${tpl.id}`)
    try {
      await apiFetch(`/admin/wa-appointment/templates/${tpl.id}/set-active`, {
        method: 'POST',
        body: JSON.stringify({ active_for_appointment: tpl.active_for_appointment === false }),
      })
      await loadAppointment()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not update visibility').message)
    } finally {
      setWorking('')
    }
  }

  useEffect(() => {
    void loadMetaStatus()
    void loadTemplateCounts()
  }, [loadMetaStatus, loadTemplateCounts])

  useEffect(() => {
    setError('')
    if (tab === 'interview') void loadInterview()
    else if (tab === 'appointment') void loadAppointment()
    else if (tab === 'marketing') void loadMarketing()
    else if (tab === 'survey') void loadSurveyIndustries()
    else if (tab === 'feedback') void loadFeedbackIndustries()
  }, [tab, loadInterview, loadAppointment, loadMarketing, loadSurveyIndustries, loadFeedbackIndustries])

  const hubSubtitle = useMemo(() => {
    const parts = [`${templateCounts.total} synced`]
    if (templateCounts.approved) parts.push(`${templateCounts.approved} approved`)
    if (templateCounts.pending) parts.push(`${templateCounts.pending} pending`)
    return parts.join(' · ')
  }, [templateCounts])

  return (
    <div className="ds-scope pageShell space-y-4">
      <div className="pageTop">
        <div>
          <p className="muted text-[11px] font-semibold uppercase tracking-wide">AI / LLM Control</p>
          <h1>WA Templates</h1>
          <p className="muted">
            Unified WhatsApp template catalog — pull and push direct with Meta Graph. Telnyx is used for SMS and voice
            only. {hubSubtitle}
          </p>
        </div>
        <div className="actions flex flex-wrap items-center gap-2">
          {metaConfigured === false ? (
            <Pill tone="warning">Meta not configured</Pill>
          ) : metaConfigured ? (
            <Pill tone="success">Meta connected</Pill>
          ) : null}
          <Button type="button" variant="outline" size="sm" className="h-8" asChild>
            <Link to="/integrations/meta_whatsapp">Meta integration</Link>
          </Button>
          <Button type="button" size="sm" className="h-8" disabled={syncBusy || metaConfigured === false} onClick={() => void syncFromMeta()}>
            <RefreshCw size={14} className={syncBusy ? 'animate-spin' : ''} />
            {syncBusy ? 'Syncing…' : 'Sync from Meta'}
          </Button>
        </div>
      </div>

      {metaConfigured === false ? (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm">
          Configure Meta WhatsApp under{' '}
          <Link to="/integrations/meta_whatsapp" className="font-medium underline">
            Integrations → Meta WhatsApp
          </Link>{' '}
          (WABA id, phone number id, access token) before syncing or pushing templates.
        </div>
      ) : null}

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>
      ) : null}
      {msg ? (
        <div className="rounded-md border border-success/40 bg-success-soft px-3 py-2 text-sm text-success">{msg}</div>
      ) : null}

      <div className="flex flex-wrap gap-1 border-b border-border pb-1">
        {HUB_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
              tab === t.id ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'
            }`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'survey' ? (
        <>
          <SystemTemplatesCard product="survey" />
          <Panel
          title={surveyIndustry ? surveyIndustry.name : 'Survey industries'}
          subtitle={surveyIndustry ? 'Survey types and template editors' : 'Select an industry to manage survey types and templates'}
          action={
            surveyIndustry ? (
              <div className="flex gap-2">
                <Button type="button" variant="outline" size="sm" className="h-8" onClick={() => setSurveyIndustry(null)}>
                  <ArrowLeft size={14} /> All industries
                </Button>
                <Button type="button" size="sm" className="h-8" disabled={working === 'survey-push-all'} onClick={() => void pushSurveyIndustryAll()}>
                  {working === 'survey-push-all' ? 'Pushing…' : 'Push all to Meta'}
                </Button>
              </div>
            ) : null
          }
        >
          {!surveyIndustry ? (
            <IndustryGrid
              industries={surveyIndustries}
              loading={surveyLoading}
              onSelect={(ind) => void openSurveyIndustry(ind)}
              emptyLabel="No survey industries yet."
            />
          ) : (
            <SurveyTypeList
              types={surveyTypes}
              loading={surveyLoading}
              editBasePath="/settings/wa-survey"
              onPushAll={pushSurveyTypeAll}
              pushing={working}
            />
          )}
        </Panel>
        </>
      ) : null}

      {tab === 'feedback' ? (
        <>
          <SystemTemplatesCard product="feedback" />
          <Panel
          title={feedbackIndustry ? feedbackIndustry.name : 'Customer Feedback industries'}
          subtitle={
            feedbackIndustry
              ? 'Survey types — open the type editor for full template management'
              : 'Select an industry to manage feedback WhatsApp templates'
          }
          action={
            feedbackIndustry ? (
              <div className="flex gap-2">
                <Button type="button" variant="outline" size="sm" className="h-8" onClick={() => setFeedbackIndustry(null)}>
                  <ArrowLeft size={14} /> All industries
                </Button>
                <Button type="button" size="sm" className="h-8" disabled={working === 'feedback-push-all'} onClick={() => void pushFeedbackIndustryAll()}>
                  {working === 'feedback-push-all' ? 'Pushing…' : 'Push all to Meta'}
                </Button>
              </div>
            ) : null
          }
        >
          {!feedbackIndustry ? (
            <IndustryGrid
              industries={feedbackIndustries}
              loading={feedbackLoading}
              onSelect={(ind) => void openFeedbackIndustry(ind)}
              emptyLabel="No feedback industries yet."
            />
          ) : (
            <SurveyTypeList
              types={feedbackTypes}
              loading={feedbackLoading}
              editBasePath="/customer-feedback/survey-types"
              onPushAll={null}
            />
          )}
        </Panel>
        </>
      ) : null}

      {tab === 'interview' ? (
        <Panel title="AI Interview templates" subtitle="Launch notice, booking, cancel, and job-closed messages.">
          <FlatTemplateTable
            templates={interviewTemplates}
            loading={surveyLoading}
            working={working}
            onEdit={(tpl) => setInterviewEditId(tpl.id)}
            onPush={pushInterview}
            onToggleHidden={toggleInterviewHidden}
            hiddenField="active_for_interview"
          />
        </Panel>
      ) : null}

      {tab === 'appointment' ? (
        <Panel title="Appointment templates" subtitle="Booking confirmation and reminder WhatsApp templates.">
          <FlatTemplateTable
            templates={appointmentTemplates}
            loading={surveyLoading}
            working={working}
            onEdit={(tpl) => setAppointmentEditId(tpl.id)}
            onPush={pushAppointment}
            onToggleHidden={toggleAppointmentHidden}
            hiddenField="active_for_appointment"
          />
        </Panel>
      ) : null}

      {tab === 'marketing' ? (
        <Panel title="Marketing / sales templates" subtitle="voxbulk_sales_* templates used by lead sales and frontpage flows.">
          <FlatTemplateTable templates={marketingTemplates} loading={surveyLoading} working={working} onPush={null} onEdit={null} />
          <p className="mt-3 text-[11px] text-muted-foreground">
            Manage copy in{' '}
            <Link to="/marketing/lead-sales/settings" className="underline">
              Lead sales settings
            </Link>
            . Sync from Meta after Meta-side edits.
          </p>
        </Panel>
      ) : null}

      {tab === 'companies' ? (
        <Panel title="Companies" subtitle="Customer Feedback Companies service">
          <div className="flex flex-col items-center gap-3 py-12 text-center">
            <Building2 size={36} className="text-muted-foreground/60" />
            <p className="max-w-md text-sm text-muted-foreground">
              Customer Feedback Companies service — WhatsApp templates are not configured yet. This tab will list
              company-specific templates when the CF Companies product is available.
            </p>
          </div>
        </Panel>
      ) : null}

      {tab === 'disabled' ? (
        <Panel title="Disabled blocklist" subtitle="Legacy template names hidden from user dashboards">
          <DisabledWaTemplatesPanel embedded onToast={(message, isError) => (isError ? setError(message) : setMsg(message))} />
        </Panel>
      ) : null}

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
    </div>
  )
}
