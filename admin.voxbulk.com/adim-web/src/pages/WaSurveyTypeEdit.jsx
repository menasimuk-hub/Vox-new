import React, { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatSyncSummary, formatWaSurveyError } from '../lib/waSurveyFeedback'
import WaSurveyPhonePreview from '../components/WaSurveyPhonePreview'
import WaSurveyTemplateModal from '../components/WaSurveyTemplateModal'

const LENGTH_OPTIONS = [
  { value: 'short', label: 'Short (4 questions)' },
  { value: 'standard', label: 'Standard (5 questions)' },
  { value: 'detailed', label: 'Detailed (6 questions)' },
]

function mappingLabel(tpl) {
  const parts = []
  if (tpl.is_default_standard) parts.push('Default standard')
  else if (tpl.usable_as_standard) parts.push('Standard')
  if (tpl.is_default_anonymous) parts.push('Default anonymous')
  else if (tpl.usable_as_anonymous) parts.push('Anonymous')
  return parts.join(' · ') || 'Linked'
}

export default function WaSurveyTypeEdit() {
  const { typeId } = useParams()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [errorDetail, setErrorDetail] = useState('')
  const [msg, setMsg] = useState('')
  const [msgDetail, setMsgDetail] = useState('')
  const [feedbackTone, setFeedbackTone] = useState('ok')
  const [surveyType, setSurveyType] = useState(null)
  const [templates, setTemplates] = useState([])
  const [modalTemplateId, setModalTemplateId] = useState(null)
  const [genPreview, setGenPreview] = useState(null)
  const [genVariant, setGenVariant] = useState('standard')
  const [genLength, setGenLength] = useState('standard')

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
      const data = await apiFetch(`/admin/wa-survey/types/${encodeURIComponent(typeId)}`)
      setSurveyType(data.type)
      setTemplates(Array.isArray(data.templates) ? data.templates : [])
    } catch (e) {
      showError(e, 'Could not load survey type')
    } finally {
      setLoading(false)
    }
  }, [typeId])

  useEffect(() => {
    load()
  }, [load])

  const saveTypeSettings = async () => {
    if (!surveyType) return
    setSaving(true)
    clearFeedback()
    try {
      const data = await apiFetch(`/admin/wa-survey/types/${encodeURIComponent(typeId)}`, {
        method: 'PUT',
        body: JSON.stringify({
          name: surveyType.name,
          description: surveyType.description,
          is_active: surveyType.is_active,
          default_length: surveyType.default_length,
          min_length: surveyType.min_length,
          max_length: surveyType.max_length,
          supports_anonymous: surveyType.supports_anonymous,
        }),
      })
      setSurveyType(data.type)
      showOk({ message: 'Survey settings saved.' })
    } catch (e) {
      showError(e, 'Save failed')
    } finally {
      setSaving(false)
    }
  }

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

  const createStandard = async () => {
    setWorking('create')
    clearFeedback()
    try {
      const data = await apiFetch(`/admin/wa-survey/types/${encodeURIComponent(typeId)}/templates/standard`, {
        method: 'POST',
        body: '{}',
      })
      setTemplates((rows) => [...rows, data.template])
      setModalTemplateId(data.template.id)
      showOk({ message: 'Standard template draft created and linked.', template_name: data.template?.name })
    } catch (e) {
      showError(e, 'Could not create template')
    } finally {
      setWorking('')
    }
  }

  const runGeneratePreview = async () => {
    setWorking('generate')
    clearFeedback()
    try {
      const data = await apiFetch('/admin/wa-survey/generate-preview', {
        method: 'POST',
        body: JSON.stringify({
          survey_type_id: typeId,
          variant: genVariant,
          length: genLength,
          goal: surveyType?.description || surveyType?.name,
        }),
      })
      setGenPreview(data)
      showOk({ message: 'Generate preview ready.', template_name: data.wa_template_name })
    } catch (e) {
      showError(e, 'Generate preview failed — ensure an APPROVED template exists for this variant.')
    } finally {
      setWorking('')
    }
  }

  if (loading && !surveyType) {
    return <p className="muted">Loading…</p>
  }

  const previewData = genPreview?.template_preview
  const flowSteps = genPreview?.flow_steps || []

  return (
    <>
      <div className="pageTop">
        <div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
            <Link to="/settings/wa-survey" style={{ color: 'var(--grn)' }}>
              WA Survey
            </Link>{' '}
            / {surveyType?.name}
          </div>
          <h1>{surveyType?.name}</h1>
          <p className="pageLead">{surveyType?.description}</p>
        </div>
        <div className="pageTopActions">
          <button type="button" className="btn" onClick={syncTemplates} disabled={working === 'sync'}>
            Sync from Telnyx
          </button>
          <button type="button" className="btn primary" onClick={saveTypeSettings} disabled={saving}>
            Save settings
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

      <div className="waSurveyEditGrid">
        <section className="card">
          <div className="cardHead"><h2>Survey settings</h2></div>
          <div className="cardBody grid2">
            <label className="msgFieldBlock">
              <span className="label">Name</span>
              <input className="input" value={surveyType?.name || ''} onChange={(e) => setSurveyType((s) => ({ ...s, name: e.target.value }))} />
            </label>
            <label className="msgFieldBlock">
              <span className="label">Default length</span>
              <select className="input" value={surveyType?.default_length || 'standard'} onChange={(e) => setSurveyType((s) => ({ ...s, default_length: e.target.value }))}>
                {LENGTH_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </label>
            <label className="msgFieldBlock span2">
              <span className="label">Description</span>
              <textarea className="input" rows={3} value={surveyType?.description || ''} onChange={(e) => setSurveyType((s) => ({ ...s, description: e.target.value }))} />
            </label>
            <label className="checkRow">
              <input type="checkbox" checked={surveyType?.is_active !== false} onChange={(e) => setSurveyType((s) => ({ ...s, is_active: e.target.checked }))} />
              Active
            </label>
            <label className="checkRow">
              <input type="checkbox" checked={surveyType?.supports_anonymous !== false} onChange={(e) => setSurveyType((s) => ({ ...s, supports_anonymous: e.target.checked }))} />
              Anonymous variant enabled
            </label>
          </div>
        </section>

        <section className="card">
          <div className="cardHead">
            <h2>Generate preview</h2>
          </div>
          <div className="cardBody grid2">
            <label className="msgFieldBlock">
              <span className="label">Variant</span>
              <select className="input" value={genVariant} onChange={(e) => setGenVariant(e.target.value)}>
                <option value="standard">Standard</option>
                <option value="anonymous">Anonymous</option>
              </select>
            </label>
            <label className="msgFieldBlock">
              <span className="label">Length</span>
              <select className="input" value={genLength} onChange={(e) => setGenLength(e.target.value)}>
                {LENGTH_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </label>
            <div className="span2">
              <button type="button" className="btn" onClick={runGeneratePreview} disabled={working === 'generate'}>
                Generate preview
              </button>
            </div>
          </div>
        </section>
      </div>

      <section className="card">
        <div className="cardHead">
          <h2>Templates</h2>
          <button type="button" className="btn sm" onClick={createStandard} disabled={working === 'create'}>
            Add standard draft
          </button>
        </div>
        <div className="cardBody">
          <div className="tableWrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Mapping</th>
                  <th>Shared by</th>
                  <th>Language</th>
                  <th>Approval</th>
                  <th>Sync</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {templates.map((tpl) => (
                  <tr key={tpl.id}>
                    <td>{tpl.display_name || tpl.name}</td>
                    <td>{mappingLabel(tpl)}</td>
                    <td>{tpl.linked_survey_type_count || 1} type(s)</td>
                    <td>{tpl.language}</td>
                    <td><span className="pill">{tpl.approval_status}</span></td>
                    <td><span className="pill muted">{tpl.sync_status_label || tpl.sync_status}</span></td>
                    <td>
                      <button type="button" className="btn sm" onClick={() => setModalTemplateId(tpl.id)}>Edit</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {genPreview ? (
        <section className="card waSurveyPreviewCard">
          <div className="cardHead"><h2>Generated flow preview</h2></div>
          <div className="cardBody">
            <WaSurveyPhonePreview
              businessName="Northgate Dental"
              renderedBody={previewData?.rendered_body || ''}
              footer={previewData?.footer || ''}
              buttons={previewData?.buttons || []}
              flowSteps={flowSteps}
              disclaimer={previewData?.disclaimer}
              templateName={genPreview?.wa_template_name}
              approvalStatus="APPROVED"
            />
          </div>
        </section>
      ) : null}

      <WaSurveyTemplateModal
        templateId={modalTemplateId}
        surveyTypeId={typeId}
        open={Boolean(modalTemplateId)}
        onClose={() => setModalTemplateId(null)}
        onSaved={() => void load()}
      />
    </>
  )
}
