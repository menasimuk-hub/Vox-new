import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatSyncSummary, formatWaSurveyError } from '../lib/waSurveyFeedback'
import WaSurveyPhonePreview from '../components/WaSurveyPhonePreview'

const LENGTH_OPTIONS = [
  { value: 'short', label: 'Short (4 questions)' },
  { value: 'standard', label: 'Standard (5 questions)' },
  { value: 'detailed', label: 'Detailed (6 questions)' },
]

function parseComponents(raw) {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }
  return []
}

function bodyTextFromComponents(components) {
  const body = components.find((c) => String(c?.type || '').toUpperCase() === 'BODY')
  return body?.text || ''
}

function footerTextFromComponents(components) {
  const footer = components.find((c) => String(c?.type || '').toUpperCase() === 'FOOTER')
  return footer?.text || ''
}

function updateBodyInComponents(components, text) {
  let found = false
  const out = components.map((comp) => {
    if (String(comp?.type || '').toUpperCase() !== 'BODY') return comp
    found = true
    return { ...comp, text }
  })
  if (!found) out.unshift({ type: 'BODY', text, example: { body_text: [['Alex']] } })
  return out
}

function updateFooterInComponents(components, text) {
  let found = false
  const out = components.map((comp) => {
    if (String(comp?.type || '').toUpperCase() !== 'FOOTER') return comp
    found = true
    return { ...comp, text }
  })
  if (!found && text.trim()) out.push({ type: 'FOOTER', text })
  return out
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
  const [testMobile, setTestMobile] = useState('')
  const [sendResult, setSendResult] = useState(null)
  const [surveyType, setSurveyType] = useState(null)
  const [templates, setTemplates] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [draft, setDraft] = useState(null)
  const [preview, setPreview] = useState(null)
  const [genPreview, setGenPreview] = useState(null)
  const [genVariant, setGenVariant] = useState('standard')
  const [genLength, setGenLength] = useState('standard')

  const selected = useMemo(
    () => templates.find((t) => t.id === selectedId) || null,
    [templates, selectedId]
  )

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
      if (!selectedId && data.templates?.[0]) setSelectedId(data.templates[0].id)
    } catch (e) {
      showError(e, 'Could not load survey type')
    } finally {
      setLoading(false)
    }
  }, [typeId, selectedId])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!selected) {
      setDraft(null)
      setPreview(null)
      return
    }
    const components = parseComponents(selected.draft_components || selected.remote_components)
    setDraft({
      display_name: selected.display_name || selected.name,
      language: selected.language || 'en_US',
      category: selected.category || 'MARKETING',
      active_for_survey: selected.active_for_survey !== false,
      body: bodyTextFromComponents(components),
      footer: footerTextFromComponents(components),
      components,
      example_values: selected.example_values || ['Alex'],
    })
    refreshPreview(selected.id)
  }, [selected?.id])

  const refreshPreview = async (templateId) => {
    if (!templateId) return
    try {
      const data = await apiFetch(`/admin/wa-survey/templates/${templateId}/preview`)
      setPreview(data)
    } catch {
      setPreview(null)
    }
  }

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

  const saveTemplateDraft = async () => {
    if (!selected || !draft) return
    setWorking('save')
    clearFeedback()
    try {
      let components = draft.components?.length ? [...draft.components] : []
      components = updateBodyInComponents(components, draft.body)
      components = updateFooterInComponents(components, draft.footer)
      const data = await apiFetch(`/admin/wa-survey/templates/${selected.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          display_name: draft.display_name,
          language: draft.language,
          category: draft.category,
          active_for_survey: draft.active_for_survey,
          components,
          example_values: draft.example_values,
        }),
      })
      setTemplates((rows) => rows.map((r) => (r.id === selected.id ? data.template : r)))
      showOk({ message: 'Template draft saved locally.', template_name: selected.name })
      await refreshPreview(selected.id)
    } catch (e) {
      showError(e, 'Could not save draft')
    } finally {
      setWorking('')
    }
  }

  const pushTemplate = async () => {
    if (!selected) return
    setWorking('push')
    clearFeedback()
    try {
      const data = await apiFetch(`/admin/wa-survey/templates/${selected.id}/push`, { method: 'POST', body: '{}' })
      setTemplates((rows) => rows.map((r) => (r.id === selected.id ? data.template : r)))
      showOk(data, 'Pushed to Telnyx — awaiting Meta approval if status is PENDING.')
      await load()
    } catch (e) {
      showError(e, 'Push to Telnyx failed')
    } finally {
      setWorking('')
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
      setSelectedId(data.template.id)
      showOk({ message: 'Standard template draft created.', template_name: data.template?.name })
    } catch (e) {
      showError(e, 'Could not create template')
    } finally {
      setWorking('')
    }
  }

  const cloneAnonymous = async () => {
    if (!selected) return
    setWorking('clone')
    clearFeedback()
    try {
      const data = await apiFetch(`/admin/wa-survey/templates/${selected.id}/clone-anonymous`, {
        method: 'POST',
        body: '{}',
      })
      setTemplates((rows) => [...rows, data.template])
      setSelectedId(data.template.id)
      showOk({
        message: 'Anonymous variant created — review wording, Save Draft, then Push to Telnyx.',
        template_name: data.template?.name,
      })
    } catch (e) {
      showError(e, 'Clone failed')
    } finally {
      setWorking('')
    }
  }

  const sendTestSurvey = async () => {
    if (!selected) return
    setWorking('send-test')
    clearFeedback()
    setSendResult(null)
    try {
      const data = await apiFetch(`/admin/wa-survey/templates/${selected.id}/send-test`, {
        method: 'POST',
        body: JSON.stringify({
          to_number: testMobile.trim(),
          first_name: draft?.example_values?.[0] || 'Alex',
          business_name: 'Northgate Dental',
        }),
      })
      setSendResult(data)
      showOk(data, 'Test survey sent')
    } catch (e) {
      showError(e, 'Send test survey failed')
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

  const previewData = genPreview?.template_preview || preview
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
                  <th>Variant</th>
                  <th>Language</th>
                  <th>Approval</th>
                  <th>Sync</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {templates.map((tpl) => (
                  <tr key={tpl.id} className={tpl.id === selectedId ? 'row-active' : ''}>
                    <td>{tpl.display_name || tpl.name}</td>
                    <td>{tpl.variant_type || 'standard'}</td>
                    <td>{tpl.language}</td>
                    <td><span className="pill">{tpl.approval_status}</span></td>
                    <td><span className="pill muted">{tpl.sync_status_label || tpl.sync_status}</span></td>
                    <td>
                      <button type="button" className="btn sm" onClick={() => setSelectedId(tpl.id)}>Edit</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {selected && draft ? (
        <div className="waSurveyEditSplit">
          <section className="card">
            <div className="cardHead"><h2>Template editor — {selected.display_name || selected.name}</h2></div>
            <div className="cardBody">
              <label className="msgFieldBlock">
                <span className="label">Display name</span>
                <input className="input" value={draft.display_name} onChange={(e) => setDraft((d) => ({ ...d, display_name: e.target.value }))} />
              </label>
              <label className="msgFieldBlock">
                <span className="label">Body</span>
                <textarea className="input msgFieldEditorBox" rows={8} value={draft.body} onChange={(e) => setDraft((d) => ({ ...d, body: e.target.value }))} />
                <span className="fieldHint">Use {'{{1}}'} for the first name variable. Approved templates cannot be edited on Meta — push creates a new submission.</span>
              </label>
              <label className="msgFieldBlock">
                <span className="label">Footer</span>
                <input className="input" value={draft.footer} onChange={(e) => setDraft((d) => ({ ...d, footer: e.target.value }))} />
              </label>
              <div className="btnRow">
                <button type="button" className="btn" onClick={saveTemplateDraft} disabled={working === 'save'}>Save Draft</button>
                <button type="button" className="btn primary" onClick={pushTemplate} disabled={working === 'push'}>Push to Telnyx</button>
                {selected.variant_type !== 'anonymous' && surveyType?.supports_anonymous ? (
                  <button type="button" className="btn" onClick={cloneAnonymous} disabled={working === 'clone'}>Clone as Anonymous</button>
                ) : null}
                <button type="button" className="btn" onClick={() => refreshPreview(selected.id)}>Preview</button>
              </div>
              {selected.last_push_error ? <p className="fieldHint warn">{selected.last_push_error}</p> : null}
            </div>
          </section>

          <section className="card waSurveyPreviewCard">
            <div className="cardHead"><h2>Phone preview</h2></div>
            <div className="cardBody">
              <WaSurveyPhonePreview
                businessName="Northgate Dental"
                renderedBody={previewData?.rendered_body || draft.body}
                footer={previewData?.footer || draft.footer}
                buttons={previewData?.buttons || selected.buttons || []}
                flowSteps={flowSteps}
                disclaimer={previewData?.disclaimer || genPreview?.template_preview?.disclaimer}
                templateName={selected.name}
                approvalStatus={selected.approval_status}
                syncStatus={selected.sync_status}
              />
              <div className="waSurveyTestSend">
                <label className="msgFieldBlock">
                  <span className="label">Test mobile number</span>
                  <input
                    className="input"
                    value={testMobile}
                    onChange={(e) => setTestMobile(e.target.value)}
                    placeholder="+447700900123"
                    inputMode="tel"
                  />
                  <span className="fieldHint">
                    E.164 format required. Sends the selected APPROVED template with example variables to your phone.
                  </span>
                </label>
                <button
                  type="button"
                  className="btn primary"
                  onClick={sendTestSurvey}
                  disabled={working === 'send-test' || !testMobile.trim() || selected.approval_status !== 'APPROVED'}
                >
                  {working === 'send-test' ? 'Sending…' : 'Send test survey'}
                </button>
                {selected.approval_status !== 'APPROVED' ? (
                  <p className="fieldHint warn">
                    Template must be APPROVED before test send (current: {selected.approval_status}).
                  </p>
                ) : null}
                {sendResult?.success ? (
                  <div className="note ok" style={{ marginTop: 12 }}>
                    <strong>{sendResult.message}</strong>
                    <div className="muted">Template: {sendResult.template_name}</div>
                    <div className="muted">Mode: {sendResult.telnyx_request_mode}</div>
                  </div>
                ) : null}
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </>
  )
}
