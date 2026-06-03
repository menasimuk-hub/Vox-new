import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatSyncSummary, formatWaSurveyError } from '../lib/waSurveyFeedback'
import WaSurveyPhonePreview from './WaSurveyPhonePreview'

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

export default function WaSurveyTemplateModal({ templateId, surveyTypeId, open, onClose, onSaved }) {
  const [loading, setLoading] = useState(false)
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [errorDetail, setErrorDetail] = useState('')
  const [msg, setMsg] = useState('')
  const [msgDetail, setMsgDetail] = useState('')
  const [feedbackTone, setFeedbackTone] = useState('ok')
  const [template, setTemplate] = useState(null)
  const [draft, setDraft] = useState(null)
  const [surveyTypes, setSurveyTypes] = useState([])
  const [preview, setPreview] = useState(null)
  const [testMobile, setTestMobile] = useState('')

  const linkedCount = useMemo(
    () => surveyTypes.filter((st) => st.linked || st.usable_as_standard || st.usable_as_anonymous || st.is_default_standard || st.is_default_anonymous).length,
    [surveyTypes]
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

  const load = useCallback(async () => {
    if (!templateId) return
    setLoading(true)
    clearFeedback()
    try {
      const data = await apiFetch(`/admin/wa-survey/templates/${templateId}`)
      setTemplate(data.template)
      setSurveyTypes(Array.isArray(data.survey_types) ? data.survey_types : [])
      const components = parseComponents(data.template?.draft_components || data.template?.remote_components)
      setDraft({
        display_name: data.template?.display_name || data.template?.name,
        body: bodyTextFromComponents(components),
        footer: footerTextFromComponents(components),
        components,
        example_values: data.template?.example_values || ['Alex'],
      })
      const previewData = await apiFetch(`/admin/wa-survey/templates/${templateId}/preview`)
      setPreview(previewData)
    } catch (e) {
      showError(e, 'Could not load template')
    } finally {
      setLoading(false)
    }
  }, [templateId])

  useEffect(() => {
    if (open && templateId) load()
  }, [open, templateId, load])

  if (!open) return null

  const toggleSurveyType = (id, field) => {
    setSurveyTypes((rows) =>
      rows.map((row) => {
        if (row.survey_type_id !== id) return row
        const next = { ...row, linked: true, [field]: !row[field] }
        if (field === 'is_default_standard' && next.is_default_standard) next.usable_as_standard = true
        if (field === 'is_default_anonymous' && next.is_default_anonymous) next.usable_as_anonymous = true
        if (!next.usable_as_standard && !next.usable_as_anonymous && !next.is_default_standard && !next.is_default_anonymous) {
          next.linked = false
        }
        return next
      })
    )
  }

  const saveDraft = async () => {
    if (!draft) return
    setWorking('save')
    clearFeedback()
    try {
      let components = draft.components?.length ? [...draft.components] : []
      components = updateBodyInComponents(components, draft.body)
      components = updateFooterInComponents(components, draft.footer)
      const data = await apiFetch(`/admin/wa-survey/templates/${templateId}`, {
        method: 'PUT',
        body: JSON.stringify({
          display_name: draft.display_name,
          components,
          example_values: draft.example_values,
        }),
      })
      setTemplate(data.template)
      showOk({ message: 'Template content saved. Linked survey types use this shared source.', template_name: data.template?.name })
      await load()
      onSaved?.()
    } catch (e) {
      showError(e, 'Could not save draft')
    } finally {
      setWorking('')
    }
  }

  const saveMappings = async () => {
    setWorking('mappings')
    clearFeedback()
    try {
      const mappings = surveyTypes
        .filter((st) => st.linked || st.usable_as_standard || st.usable_as_anonymous || st.is_default_standard || st.is_default_anonymous)
        .map((st) => ({
          survey_type_id: st.survey_type_id,
          usable_as_standard: Boolean(st.usable_as_standard),
          usable_as_anonymous: Boolean(st.usable_as_anonymous),
          is_default_standard: Boolean(st.is_default_standard),
          is_default_anonymous: Boolean(st.is_default_anonymous),
        }))
      const data = await apiFetch(`/admin/wa-survey/templates/${templateId}/mappings`, {
        method: 'PUT',
        body: JSON.stringify({ mappings }),
      })
      setSurveyTypes(data.survey_types || [])
      showOk({ message: `Mappings saved for ${data.linked_survey_type_count || mappings.length} survey type(s).`, template_name: template?.name })
      onSaved?.()
    } catch (e) {
      showError(e, 'Could not save mappings')
    } finally {
      setWorking('')
    }
  }

  const pushTemplate = async () => {
    setWorking('push')
    clearFeedback()
    try {
      const data = await apiFetch(`/admin/wa-survey/templates/${templateId}/push`, { method: 'POST', body: '{}' })
      showOk(data, 'Pushed to Telnyx')
      await load()
      onSaved?.()
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
        body: JSON.stringify({ survey_type_id: surveyTypeId || undefined }),
      })
      const formatted = formatSyncSummary(summary)
      setFeedbackTone(formatted.severity === 'error' ? 'error' : formatted.severity === 'warn' ? 'warn' : 'ok')
      if (formatted.severity === 'error') {
        setError(formatted.message)
        setErrorDetail(formatted.detailText)
      } else {
        setMsg(formatted.message)
        setMsgDetail(formatted.detailText !== formatted.message ? formatted.detailText : '')
      }
      await load()
      onSaved?.()
    } catch (e) {
      showError(e, 'Sync from Telnyx failed')
    } finally {
      setWorking('')
    }
  }

  const cloneAnonymous = async () => {
    setWorking('clone')
    clearFeedback()
    try {
      await apiFetch(`/admin/wa-survey/templates/${templateId}/clone-anonymous`, {
        method: 'POST',
        body: JSON.stringify({ survey_type_id: surveyTypeId }),
      })
      showOk({ message: 'Anonymous content variant created as a separate shared template.' })
      onSaved?.()
    } catch (e) {
      showError(e, 'Clone failed')
    } finally {
      setWorking('')
    }
  }

  const sendTest = async () => {
    setWorking('send-test')
    clearFeedback()
    try {
      const data = await apiFetch(`/admin/wa-survey/templates/${templateId}/send-test`, {
        method: 'POST',
        body: JSON.stringify({ to_number: testMobile.trim(), first_name: draft?.example_values?.[0] || 'Alex' }),
      })
      showOk(data, 'Test survey sent')
    } catch (e) {
      showError(e, 'Send test survey failed')
    } finally {
      setWorking('')
    }
  }

  return (
    <div className="waSurveyModalBackdrop" role="dialog" aria-modal="true">
      <div className="waSurveyModal">
        <div className="waSurveyModalHead">
          <div>
            <h2>{draft?.display_name || template?.name || 'Template'}</h2>
            <p className="muted">Shared source template · used by {linkedCount || template?.linked_survey_type_count || 0} survey type(s)</p>
          </div>
          <button type="button" className="btn ghost" onClick={onClose}>Close</button>
        </div>

        {loading ? <p className="muted">Loading…</p> : null}
        {error ? <div className="alert error"><strong>{error}</strong>{errorDetail ? <pre className="waSurveyFeedbackDetail">{errorDetail}</pre> : null}</div> : null}
        {msg ? <div className={`alert ${feedbackTone === 'warn' ? 'warn' : 'ok'}`}><strong>{msg}</strong>{msgDetail ? <pre className="waSurveyFeedbackDetail">{msgDetail}</pre> : null}</div> : null}

        {!loading && draft ? (
          <div className="waSurveyModalBody">
            <section className="card">
              <div className="cardHead"><h3>Template content</h3></div>
              <div className="cardBody">
                <p className="fieldHint">Content edits update the shared source for every linked survey type. Mapping-only changes do not require Telnyx resubmission.</p>
                <label className="msgFieldBlock">
                  <span className="label">Display name</span>
                  <input className="input" value={draft.display_name} onChange={(e) => setDraft((d) => ({ ...d, display_name: e.target.value }))} />
                </label>
                <label className="msgFieldBlock">
                  <span className="label">Body</span>
                  <textarea className="input msgFieldEditorBox" rows={7} value={draft.body} onChange={(e) => setDraft((d) => ({ ...d, body: e.target.value }))} />
                </label>
                <label className="msgFieldBlock">
                  <span className="label">Footer</span>
                  <input className="input" value={draft.footer} onChange={(e) => setDraft((d) => ({ ...d, footer: e.target.value }))} />
                </label>
                <div className="btnRow">
                  <button type="button" className="btn" onClick={saveDraft} disabled={working === 'save'}>Save Draft</button>
                  <button type="button" className="btn primary" onClick={pushTemplate} disabled={working === 'push'}>Push to Telnyx</button>
                  <button type="button" className="btn" onClick={syncTemplates} disabled={working === 'sync'}>Sync from Telnyx</button>
                  <button type="button" className="btn" onClick={cloneAnonymous} disabled={working === 'clone'}>Clone as Anonymous</button>
                </div>
                <p className="fieldHint">Approval: <strong>{template?.approval_status}</strong> · Sync: <strong>{template?.sync_status_label || template?.sync_status}</strong></p>
              </div>
            </section>

            <section className="card">
              <div className="cardHead"><h3>Survey type usage</h3></div>
              <div className="cardBody waSurveyMappingList">
                {surveyTypes.map((st) => (
                  <div key={st.survey_type_id} className="waSurveyMappingRow">
                    <strong>{st.name}</strong>
                    <label className="checkRow"><input type="checkbox" checked={Boolean(st.usable_as_standard)} onChange={() => toggleSurveyType(st.survey_type_id, 'usable_as_standard')} /> Standard</label>
                    <label className="checkRow"><input type="checkbox" checked={Boolean(st.usable_as_anonymous)} onChange={() => toggleSurveyType(st.survey_type_id, 'usable_as_anonymous')} disabled={!st.supports_anonymous} /> Anonymous</label>
                    <label className="checkRow"><input type="checkbox" checked={Boolean(st.is_default_standard)} onChange={() => toggleSurveyType(st.survey_type_id, 'is_default_standard')} /> Default standard</label>
                    <label className="checkRow"><input type="checkbox" checked={Boolean(st.is_default_anonymous)} onChange={() => toggleSurveyType(st.survey_type_id, 'is_default_anonymous')} disabled={!st.supports_anonymous} /> Default anonymous</label>
                  </div>
                ))}
                <button type="button" className="btn primary" onClick={saveMappings} disabled={working === 'mappings'}>Save mappings</button>
              </div>
            </section>

            <section className="card waSurveyPreviewCard">
              <div className="cardHead"><h3>Preview & test send</h3></div>
              <div className="cardBody">
                <WaSurveyPhonePreview
                  businessName="Northgate Dental"
                  renderedBody={preview?.rendered_body || draft.body}
                  footer={preview?.footer || draft.footer}
                  buttons={preview?.buttons || template?.buttons || []}
                  templateName={template?.name}
                  approvalStatus={template?.approval_status}
                  syncStatus={template?.sync_status}
                />
                <div className="waSurveyTestSend">
                  <label className="msgFieldBlock">
                    <span className="label">Test mobile number</span>
                    <input className="input" value={testMobile} onChange={(e) => setTestMobile(e.target.value)} placeholder="+447700900123" />
                  </label>
                  <button type="button" className="btn primary" onClick={sendTest} disabled={working === 'send-test' || !testMobile.trim() || template?.approval_status !== 'APPROVED'}>
                    {working === 'send-test' ? 'Sending…' : 'Send test survey'}
                  </button>
                </div>
              </div>
            </section>
          </div>
        ) : null}
      </div>
    </div>
  )
}
