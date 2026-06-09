import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatSyncSummary, formatWaSurveyError } from '../lib/waSurveyFeedback'
import { buildWaSurveySimulatorUrl } from '../lib/waSurveySimulatorLink'
import { resolveTelnyxSyncLabel, telnyxSyncPillClass, validateCategoryBeforeSync } from '../lib/waSurveyTelnyxSync'
import WaSurveyTemplateModal from '../components/WaSurveyTemplateModal'
import WaSurveyTemplatePackModal from '../components/WaSurveyTemplatePackModal'

const MIDDLE_STEP_ROLES = [
  'rating',
  'yes_no',
  'helpfulness',
  'abc_choice',
  'reason',
  'final_feedback_text',
  'feeling_word',
  'follow_up',
  'improvement',
]

function mappingLabel(tpl) {
  const parts = []
  if (tpl.is_default_standard) parts.push('Default standard')
  else if (tpl.usable_as_standard) parts.push('Standard')
  if (tpl.is_default_anonymous) parts.push('Default anonymous')
  else if (tpl.usable_as_anonymous) parts.push('Anonymous')
  return parts.join(' · ') || 'Linked'
}

function templateSearchHaystack(tpl) {
  return [
    tpl.display_name,
    tpl.name,
    tpl.language,
    tpl.approval_status,
    tpl.sync_status_label,
    tpl.sync_status,
    tpl.privacy_mode,
    mappingLabel(tpl),
    tpl.linked_survey_type_count != null ? String(tpl.linked_survey_type_count) : '',
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}

function matchesTemplateSearch(tpl, query) {
  const q = String(query || '').trim().toLowerCase()
  if (!q) return true
  return templateSearchHaystack(tpl).includes(q)
}

export default function WaSurveyTypeEdit() {
  const { typeId } = useParams()
  const isSimulatorAlias = typeId === 'simulator'
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [errorDetail, setErrorDetail] = useState('')
  const [msg, setMsg] = useState('')
  const [msgDetail, setMsgDetail] = useState('')
  const [feedbackTone, setFeedbackTone] = useState('ok')
  const [surveyType, setSurveyType] = useState(null)
  const [templates, setTemplates] = useState([])
  const [modalTemplateId, setModalTemplateId] = useState(null)
  const [modalTemplate, setModalTemplate] = useState(null)
  const [packModalOpen, setPackModalOpen] = useState(false)
  const [templateSearch, setTemplateSearch] = useState('')
  const [templatePrivacyFilter, setTemplatePrivacyFilter] = useState('off')
  const [manualStepRole, setManualStepRole] = useState('rating')

  const clearFeedback = () => {
    setError('')
    setErrorDetail('')
    setMsg('')
    setMsgDetail('')
    setFeedbackTone('ok')
  }

  const showError = (err, fallback = 'Request failed') => {
    const formatted = formatWaSurveyError(err, fallback)
    setFeedbackTone('error')
    setError(formatted.message)
    setErrorDetail(formatted.detailText !== formatted.message ? formatted.detailText : '')
    setMsg('')
    setMsgDetail('')
  }

  const showOk = (result, fallback = 'Done') => {
    const formatted = formatActionSuccess(result, fallback)
    setFeedbackTone('ok')
    setError('')
    setErrorDetail('')
    setMsg(formatted.message)
    setMsgDetail(formatted.detailText !== formatted.message ? formatted.detailText : '')
  }

  const showSyncResult = (summary) => {
    const formatted = formatSyncSummary(summary)
    setFeedbackTone(formatted.severity === 'error' ? 'error' : formatted.severity === 'warn' ? 'warn' : 'ok')
    if (formatted.severity === 'error') {
      setError(formatted.message)
      setErrorDetail(formatted.detailText !== formatted.message ? formatted.detailText : '')
      setMsg('')
      setMsgDetail('')
      return
    }
    setError('')
    setErrorDetail('')
    setMsg(formatted.message)
    setMsgDetail(formatted.detailText !== formatted.message ? formatted.detailText : '')
  }

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const qs = templatePrivacyFilter ? `?privacy_mode=${encodeURIComponent(templatePrivacyFilter)}` : ''
      const data = await apiFetch(`/admin/wa-survey/types/${encodeURIComponent(typeId)}${qs}`)
      setSurveyType(data.type)
      setTemplates(Array.isArray(data.templates) ? data.templates : [])
    } catch (e) {
      showError(e, 'Could not load survey type')
    } finally {
      setLoading(false)
    }
  }, [typeId, templatePrivacyFilter])

  useEffect(() => {
    load()
  }, [load])

  const syncTemplates = async () => {
    setWorking('sync')
    clearFeedback()
    try {
      const summary = await apiFetch('/admin/wa-survey/sync', {
        method: 'POST',
        body: JSON.stringify({ survey_type_id: typeId }),
      })
      showSyncResult(summary)
      await load()
    } catch (e) {
      showError(e, 'Sync from Telnyx failed')
    } finally {
      setWorking('')
    }
  }

  const deleteTemplate = async (tpl) => {
    const templateId = tpl?.id
    if (templateId == null || templateId === '') return
    if (!window.confirm(`Remove "${tpl.display_name || tpl.name}" from this survey type?`)) return
    setWorking(`delete-${templateId}`)
    clearFeedback()
    const path = `/admin/wa-survey/types/${encodeURIComponent(typeId)}/templates/${encodeURIComponent(templateId)}`
    try {
      let result
      try {
        result = await apiFetch(`${path}/unlink`, { method: 'POST', body: '{}' })
      } catch (postErr) {
        if (postErr?.status === 404) {
          result = await apiFetch(path, { method: 'DELETE' })
        } else {
          throw postErr
        }
      }
      showOk(result, 'Template removed from this survey type.')
      await load()
    } catch (e) {
      const hint =
        e?.status === 404
          ? ' Delete endpoint not found — restart the API server (uvicorn) so it loads the latest code, then try again.'
          : ''
      showError(e, `Could not delete template.${hint}`)
    } finally {
      setWorking('')
    }
  }

  const toggleTemplateActive = async (tpl) => {
    const templateId = tpl?.id
    if (templateId == null || templateId === '') return
    const nextActive = tpl.active_for_survey === false
    setWorking(`active-${templateId}`)
    clearFeedback()
    try {
      const result = await apiFetch(`/admin/wa-survey/templates/${encodeURIComponent(templateId)}/set-active`, {
        method: 'POST',
        body: JSON.stringify({ active: nextActive }),
      })
      showOk(result, nextActive ? 'Template enabled.' : 'Template hidden from surveys.')
      await load()
    } catch (e) {
      showError(e, 'Could not update template visibility')
    } finally {
      setWorking('')
    }
  }

  const pushOneToTelnyx = async (tpl) => {
    const templateId = tpl?.id
    if (templateId == null || templateId === '') return
    const categoryError = validateCategoryBeforeSync(tpl?.category)
    if (categoryError) {
      showError(new Error(categoryError), categoryError)
      return
    }
    setWorking(`push-${templateId}`)
    clearFeedback()
    try {
      const data = await apiFetch(`/admin/wa-survey/templates/${templateId}/push`, { method: 'POST', body: '{}' })
      showOk({ message: data.sync_message || data.message || `Synced “${tpl.display_name || tpl.name}” to Telnyx.` })
      await load()
    } catch (e) {
      showError(e, `Could not sync “${tpl.display_name || tpl.name}” to Telnyx`)
    } finally {
      setWorking('')
    }
  }

  const pushAllToTelnyx = async () => {
    setWorking('push-all')
    clearFeedback()
    try {
      const summary = await apiFetch(`/admin/wa-survey/types/${encodeURIComponent(typeId)}/templates/push-all`, {
        method: 'POST',
        body: '{}',
      })
      if (summary.error_count) {
        setFeedbackTone('warn')
        setError('')
        setErrorDetail('')
        setMsg(summary.message || `Pushed ${summary.pushed} template(s)`)
        setMsgDetail(
          (summary.errors || [])
            .map((item) => `${item.template_name || item.template_id}: ${item.error}`)
            .join('\n')
        )
      } else {
        showOk({ message: summary.message || `Pushed ${summary.pushed} template(s) to Telnyx.` })
      }
      await load()
    } catch (e) {
      showError(e, 'Sync all to Telnyx failed')
    } finally {
      setWorking('')
    }
  }

  const createManualTemplate = async () => {
    setWorking('create')
    clearFeedback()
    try {
      const data = await apiFetch(`/admin/wa-survey/types/${encodeURIComponent(typeId)}/templates/custom`, {
        method: 'POST',
        body: JSON.stringify({
          step_role: manualStepRole,
          privacy_mode: templatePrivacyFilter,
          display_name: `${surveyType?.name || 'Survey'} — ${manualStepRole.replace(/_/g, ' ')}`,
        }),
      })
      setTemplates((rows) => [...rows, data.template])
      setModalTemplate(data.template)
      setModalTemplateId(data.template.id)
      showOk({ message: 'Blank survey question template created — edit body, buttons, and variables below.', template_name: data.template?.name })
    } catch (e) {
      showError(e, 'Could not create template')
    } finally {
      setWorking('')
    }
  }

  const filteredTemplates = useMemo(
    () => templates.filter((tpl) => matchesTemplateSearch(tpl, templateSearch)),
    [templates, templateSearch]
  )
  const templateSearchActive = Boolean(templateSearch.trim())

  if (isSimulatorAlias) {
    return <Navigate to="/settings/wa-survey/simulator" replace />
  }

  if (loading && !surveyType) {
    return <p className="muted">Loading…</p>
  }

  return (
    <>
      <div className="pageTop">
        <div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
            <Link to="/settings/wa-survey" style={{ color: 'var(--grn)' }}>
              WA Survey
            </Link>
            {surveyType?.industry_id ? (
              <>
                {' / '}
                <Link to={`/settings/wa-survey/industries/${surveyType.industry_id}`} style={{ color: 'var(--grn)' }}>
                  {surveyType.industry_name || 'Industry'}
                </Link>
              </>
            ) : null}
            {' / '}
            {surveyType?.name}
          </div>
          <h1>{surveyType?.name}</h1>
          <p className="pageLead">
            {surveyType?.description}
            {surveyType?.industry_name ? (
              <span className="muted"> · Industry: {surveyType.industry_name}</span>
            ) : null}
          </p>
        </div>
        <div className="pageTopActions">
          <Link
            className="btn primary"
            to={buildWaSurveySimulatorUrl({
              surveyTypeId: typeId,
              privacyMode: templatePrivacyFilter,
              industryId: surveyType?.industry_id,
              autoStart: true,
            })}
          >
            Simulate workflow
          </Link>
          <Link className="btn" to={`/settings/wa-survey/${typeId}/flows`}>
            Flows
          </Link>
          <Link
            className="btn"
            to={buildWaSurveySimulatorUrl({
              surveyTypeId: typeId,
              privacyMode: templatePrivacyFilter,
              industryId: surveyType?.industry_id,
              autoStart: false,
            })}
          >
            Simulator setup
          </Link>
          <button type="button" className="btn" onClick={syncTemplates} disabled={working === 'sync'}>
            Sync from Telnyx
          </button>
          <button type="button" className="btn" onClick={pushAllToTelnyx} disabled={working === 'push-all'} title="Push every linked template — use row Sync for one template only">
            {working === 'push-all' ? 'Syncing all…' : 'Sync all to Telnyx'}
          </button>
        </div>
      </div>

      {error ? (
        <div className="alert error">
          <strong>{error}</strong>
          {errorDetail ? <pre className="waSurveyFeedbackDetail">{errorDetail}</pre> : null}
        </div>
      ) : null}
      {msg ? (
        <div className={`alert ${feedbackTone === 'warn' ? 'warn' : 'ok'}`}>
          <strong>{msg}</strong>
          {msgDetail ? <pre className="waSurveyFeedbackDetail">{msgDetail}</pre> : null}
        </div>
      ) : null}

      <section className="card">
        <div className="cardHead waSurveyTemplatesHead">
          <div>
            <h2>Templates</h2>
            <p className="muted waSurveyTemplatesMeta">
              {templateSearchActive
                ? `${filteredTemplates.length} of ${templates.length} shown`
                : `${templates.length} linked template${templates.length === 1 ? '' : 's'}`}
              {' · '}
              Create manually or generate survey question templates with OpenAI (not start/welcome messages).
            </p>
          </div>
          <div className="waSurveyTemplatesActions">
            <select
              className="input"
              value={templatePrivacyFilter}
              onChange={(e) => setTemplatePrivacyFilter(e.target.value)}
              aria-label="Privacy mode filter"
            >
              <option value="off">Privacy Off templates</option>
              <option value="on">Privacy On templates</option>
            </select>
            <select
              className="input"
              value={manualStepRole}
              onChange={(e) => setManualStepRole(e.target.value)}
              aria-label="Question type for manual create"
              title="Step role for a new blank template"
            >
              {MIDDLE_STEP_ROLES.map((role) => (
                <option key={role} value={role}>{role.replace(/_/g, ' ')}</option>
              ))}
            </select>
            <input
              className="input waSurveyTemplateSearch"
              type="search"
              placeholder="Search name, language, status…"
              value={templateSearch}
              onChange={(e) => setTemplateSearch(e.target.value)}
            />
            <button type="button" className="btn sm primary" onClick={createManualTemplate} disabled={working === 'create'}>
              {working === 'create' ? 'Creating…' : 'Create template manually'}
            </button>
            <button type="button" className="btn sm" onClick={() => setPackModalOpen(true)}>
              Generate survey questions (AI)
            </button>
            <Link
              className="btn sm primary"
              to={buildWaSurveySimulatorUrl({
                surveyTypeId: typeId,
                privacyMode: templatePrivacyFilter,
                industryId: surveyType?.industry_id,
                autoStart: true,
              })}
            >
              Simulate workflow
            </Link>
          </div>
        </div>
        <div className="cardBody">
          <div className="tableWrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Step</th>
                  <th>Status</th>
                  <th>Category</th>
                  <th>Mapping</th>
                  <th>Shared by</th>
                  <th>Language</th>
                  <th>Privacy</th>
                  <th>Telnyx</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredTemplates.length ? filteredTemplates.map((tpl) => (
                  <tr key={tpl.id} className={tpl.active_for_survey === false ? 'waIndustryRowMuted' : ''}>
                    <td>{tpl.display_name || tpl.name}</td>
                    <td>{tpl.step_role ? tpl.step_role.replace(/_/g, ' ') : '—'}</td>
                    <td>
                      <span className={`pill ${tpl.active_for_survey === false ? 'muted' : 'ok'}`}>
                        {tpl.active_for_survey === false ? 'Hidden' : 'Active'}
                      </span>
                    </td>
                    <td>{tpl.category || '—'}</td>
                    <td>{mappingLabel(tpl)}</td>
                    <td>{tpl.linked_survey_type_count || 1} type(s)</td>
                    <td>{tpl.language}</td>
                    <td>{tpl.privacy_mode === 'on' ? 'On' : 'Off'}</td>
                    <td>
                      <span className={`pill ${telnyxSyncPillClass(resolveTelnyxSyncLabel(tpl))}`}>
                        {resolveTelnyxSyncLabel(tpl)}
                      </span>
                    </td>
                    <td>
                      <div className="runningSurveyRowActions">
                        <button
                          type="button"
                          className="btn sm"
                          onClick={() => {
                            setModalTemplate(tpl)
                            setModalTemplateId(tpl.id)
                          }}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          className="btn sm soft"
                          disabled={working === `active-${tpl.id}`}
                          onClick={() => void toggleTemplateActive(tpl)}
                          title={tpl.active_for_survey === false ? 'Show in survey flows again' : 'Hide from surveys — Telnyx sync still works'}
                        >
                          {working === `active-${tpl.id}`
                            ? 'Updating…'
                            : tpl.active_for_survey === false
                              ? 'Enable'
                              : 'Hide'}
                        </button>
                        <button
                          type="button"
                          className="btn sm soft"
                          disabled={working === `push-${tpl.id}`}
                          onClick={() => pushOneToTelnyx(tpl)}
                          title="Push only this template to Telnyx"
                        >
                          {working === `push-${tpl.id}` ? 'Syncing…' : 'Sync'}
                        </button>
                        <button
                          type="button"
                          className="btn sm soft"
                          disabled={working === `delete-${tpl.id}`}
                          onClick={() => deleteTemplate(tpl)}
                        >
                          {working === `delete-${tpl.id}` ? 'Deleting…' : 'Delete'}
                        </button>
                      </div>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={10} className="muted">
                      {templates.length
                        ? 'No templates match your search.'
                        : 'No templates yet — create one manually or generate survey questions with AI.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <WaSurveyTemplatePackModal
        surveyTypeId={typeId}
        surveyTypeName={surveyType?.name}
        industryId={surveyType?.industry_id}
        open={packModalOpen}
        onClose={() => setPackModalOpen(false)}
        onSaved={() => void load()}
      />

      <WaSurveyTemplateModal
        templateId={modalTemplateId}
        initialTemplate={modalTemplate}
        surveyTypeId={typeId}
        open={Boolean(modalTemplateId)}
        onClose={() => {
          setModalTemplateId(null)
          setModalTemplate(null)
        }}
        onSaved={() => void load()}
      />
    </>
  )
}
