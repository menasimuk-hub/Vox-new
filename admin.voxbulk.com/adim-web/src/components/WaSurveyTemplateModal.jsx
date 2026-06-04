import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatSyncSummary, formatWaSurveyError } from '../lib/waSurveyFeedback'
import {
  TELNYX_SYNC_LABELS,
  WA_TEMPLATE_CATEGORY_OPTIONS,
  resolveTelnyxSyncLabel,
  telnyxSyncPillClass,
  validateCategoryBeforeSync,
} from '../lib/waSurveyTelnyxSync'
import { VAR_LABELS, ensureExampleValues, substituteTemplateVars } from '../lib/waSurveyTemplateVars'
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

function buildSurveyTypesFallback(allTypes, tpl, currentTypeId) {
  return (allTypes || []).map((t) => {
    const isCurrent = String(t.id) === String(currentTypeId)
    return {
      survey_type_id: t.id,
      name: t.name,
      slug: t.slug,
      supports_anonymous: t.supports_anonymous !== false,
      linked: isCurrent && Boolean(
        tpl?.usable_as_standard || tpl?.usable_as_anonymous || tpl?.is_default_standard || tpl?.is_default_anonymous
      ),
      usable_as_standard: isCurrent ? Boolean(tpl?.usable_as_standard) : false,
      usable_as_anonymous: isCurrent ? Boolean(tpl?.usable_as_anonymous) : false,
      is_default_standard: isCurrent ? Boolean(tpl?.is_default_standard) : false,
      is_default_anonymous: isCurrent ? Boolean(tpl?.is_default_anonymous) : false,
    }
  })
}

function applyTemplateDraft(setDraft, tpl) {
  const components = parseComponents(tpl?.draft_components || tpl?.remote_components)
  setDraft({
    display_name: tpl?.display_name || tpl?.name,
    category: tpl?.category || 'MARKETING',
    body: bodyTextFromComponents(components),
    footer: footerTextFromComponents(components) || tpl?.footer || '',
    components,
    example_values: tpl?.example_values || ['Alex'],
  })
}

export default function WaSurveyTemplateModal({ templateId, initialTemplate, surveyTypeId, open, onClose, onSaved }) {
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
  const [saveNotice, setSaveNotice] = useState('')
  const [syncNotice, setSyncNotice] = useState('')
  const [syncing, setSyncing] = useState(false)

  const telnyxLabel = useMemo(() => {
    if (syncing) return TELNYX_SYNC_LABELS.SYNCING
    return resolveTelnyxSyncLabel(template)
  }, [template, syncing])

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
    setSaveNotice('')
    setSyncNotice('')
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

  const loadPreview = async (id) => {
    const previewData = await apiFetch(`/admin/wa-survey/templates/${id}/preview`)
    setPreview(previewData)
  }

  const loadFromFallback = async () => {
    if (!initialTemplate) throw new Error('Could not load template')
    setTemplate(initialTemplate)
    applyTemplateDraft(setDraft, initialTemplate)
    const typesRes = await apiFetch('/admin/wa-survey/types')
    setSurveyTypes(buildSurveyTypesFallback(typesRes.types, initialTemplate, surveyTypeId))
    await loadPreview(templateId)
    setFeedbackTone('warn')
    setError('')
    setErrorDetail('')
    setMsg('FastAPI on port 8000 is outdated — restart it so shared-template mappings load.')
    setMsgDetail(
      'Run: cd voxbulk-api && python -m alembic upgrade head && python -m uvicorn main:app --host 127.0.0.1 --port 8000'
    )
  }

  const load = useCallback(async () => {
    if (!templateId) return
    setLoading(true)
    clearFeedback()
    try {
      const data = await apiFetch(`/admin/wa-survey/templates/${templateId}`)
      setTemplate(data.template)
      setSurveyTypes(Array.isArray(data.survey_types) ? data.survey_types : [])
      applyTemplateDraft(setDraft, data.template)
      await loadPreview(templateId)
    } catch (e) {
      if (e?.status === 405 && initialTemplate) {
        try {
          await loadFromFallback()
        } catch (fallbackErr) {
          showError(fallbackErr, 'Could not load template')
        }
      } else if (e?.status === 405) {
        showError(
          { ...e, message: 'Template detail API is unavailable (HTTP 405). Restart FastAPI on port 8000 with the latest code.' },
          'Could not load template'
        )
      } else {
        showError(e, 'Could not load template')
      }
    } finally {
      setLoading(false)
    }
  }, [templateId, initialTemplate, surveyTypeId])

  useEffect(() => {
    if (open && templateId) load()
  }, [open, templateId, load])

  useEffect(() => {
    if (!open) return undefined
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [open])

  const livePreview = useMemo(() => {
    if (!draft) return null
    const values = ensureExampleValues(draft.body, '', draft.example_values)
    return {
      businessName: values[1] || 'Northgate Dental',
      renderedBody: substituteTemplateVars(draft.body, values),
      footer: draft.footer,
      values,
    }
  }, [draft])

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
          category: draft.category,
          components,
          example_values: ensureExampleValues(draft.body, '', draft.example_values),
        }),
      })
      setTemplate(data.template)
      setSaveNotice('Template saved')
      showOk({ message: 'Template saved', template_name: data.template?.name })
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
    const categoryError = validateCategoryBeforeSync(draft?.category || template?.category)
    if (categoryError) {
      showError({ message: categoryError }, categoryError)
      return
    }
    setWorking('push')
    setSyncing(true)
    clearFeedback()
    try {
      const data = await apiFetch(`/admin/wa-survey/templates/${templateId}/push`, { method: 'POST', body: '{}' })
      setTemplate(data.template)
      const syncMessage = data.sync_message || data.message || TELNYX_SYNC_LABELS.SYNCED
      setSyncNotice(syncMessage)
      if (syncMessage === TELNYX_SYNC_LABELS.FAILED) {
        showError({ message: syncMessage, data: { detail: data } }, syncMessage)
      } else {
        showOk({ message: syncMessage, template_name: data.template?.name, approval_status: data.approval_status })
      }
      await load()
      onSaved?.()
    } catch (e) {
      setSyncNotice(TELNYX_SYNC_LABELS.FAILED)
      showError(e, TELNYX_SYNC_LABELS.FAILED)
    } finally {
      setSyncing(false)
      setWorking('')
    }
  }

  const refreshTelnyxStatus = async () => {
    setWorking('refresh')
    clearFeedback()
    try {
      const data = await apiFetch(`/admin/wa-survey/templates/${templateId}/refresh-telnyx-status`, {
        method: 'POST',
        body: '{}',
      })
      setTemplate(data.template)
      setSyncNotice(data.telnyx_sync_label || data.message)
      showOk({ message: data.message || data.telnyx_sync_label, approval_status: data.approval_status })
      await load()
      onSaved?.()
    } catch (e) {
      showError(e, TELNYX_SYNC_LABELS.FAILED)
    } finally {
      setWorking('')
    }
  }

  const needsResync = template?.is_local_only || template?.telnyx_sync_label === TELNYX_SYNC_LABELS.FAILED
    || template?.telnyx_sync_label === TELNYX_SYNC_LABELS.REJECTED
    || template?.sync_status === 'local_changes'
  const canRefreshStatus = template && !template.is_local_only

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
    <div className="waSurveyPackBackdrop" role="dialog" aria-modal="true">
      <div className="waSurveyPackShell waSurveyPackShellNoScroll waSurveyTemplateEditShell">
        <header className="waSurveyPackTopBar waSurveyPackTopBarCompact">
          <div className="waSurveyPackTopBarMain">
            <h2>{draft?.display_name || template?.name || 'Template'}</h2>
            <p className="muted">Shared source · {linkedCount || template?.linked_survey_type_count || 0} survey type(s)</p>
          </div>
          <button type="button" className="btn ghost" onClick={onClose}>Close</button>
        </header>

        {loading ? <p className="muted waSurveyPackGlobalAlert">Loading…</p> : null}
        {error ? <div className="alert error waSurveyPackGlobalAlert"><strong>{error}</strong>{errorDetail ? <pre className="waSurveyFeedbackDetail">{errorDetail}</pre> : null}</div> : null}
        {msg ? <div className={`alert ${feedbackTone === 'warn' ? 'warn' : 'ok'} waSurveyPackGlobalAlert`}><strong>{msg}</strong>{msgDetail ? <pre className="waSurveyFeedbackDetail">{msgDetail}</pre> : null}</div> : null}

        {!loading && draft ? (
          <div className="waSurveyTemplateEditMain">
            <section className="waSurveyTemplateEditForm card">
              <div className="cardHead"><h3>Template content</h3></div>
              <div className="cardBody">
                <label className="msgFieldBlock">
                  <span className="label">Display name</span>
                  <input className="input" value={draft.display_name} onChange={(e) => setDraft((d) => ({ ...d, display_name: e.target.value }))} />
                </label>
                <label className="msgFieldBlock">
                  <span className="label">Template Category</span>
                  <select
                    className="input"
                    value={draft.category || ''}
                    onChange={(e) => setDraft((d) => ({ ...d, category: e.target.value }))}
                  >
                    <option value="">Select category…</option>
                    {WA_TEMPLATE_CATEGORY_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                  <p className="fieldHint">Required before syncing to Telnyx — MARKETING, UTILITY, or AUTHENTICATION.</p>
                </label>
                <label className="msgFieldBlock">
                  <span className="label">Body</span>
                  <textarea
                    className="input msgFieldEditorBox"
                    rows={5}
                    value={draft.body}
                    onChange={(e) => setDraft((d) => ({
                      ...d,
                      body: e.target.value,
                      example_values: ensureExampleValues(e.target.value, '', d.example_values),
                    }))}
                  />
                </label>
                <label className="msgFieldBlock">
                  <span className="label">Footer</span>
                  <input className="input" value={draft.footer} onChange={(e) => setDraft((d) => ({ ...d, footer: e.target.value }))} />
                </label>
                <div className="waSurveyPackMetaBlock waSurveyPackMetaBlockVars">
                  <span className="label">Variables (example values)</span>
                  <div className="waSurveyPackVarEditGrid">
                    {(livePreview?.values || ensureExampleValues(draft.body, '', draft.example_values)).map((val, i) => (
                      <label key={i} className="waSurveyPackVarEditRow">
                        <span className="waSurveyPackVarEditLabel">{`{{${i + 1}}} — ${VAR_LABELS[i] || 'Variable'}`}</span>
                        <input
                          className="input"
                          value={val}
                          onChange={(e) => setDraft((d) => {
                            const values = ensureExampleValues(d.body, '', d.example_values)
                            values[i] = e.target.value
                            return { ...d, example_values: values }
                          })}
                        />
                      </label>
                    ))}
                  </div>
                </div>
                <div className="btnRow">
                  <button type="button" className="btn primary" onClick={saveDraft} disabled={working === 'save'}>
                    {working === 'save' ? 'Saving…' : 'Save template'}
                  </button>
                  <button type="button" className="btn" onClick={pushTemplate} disabled={working === 'push' || syncing}>
                    {syncing ? 'Syncing…' : needsResync ? 'Re-sync to Telnyx' : 'Sync to Telnyx'}
                  </button>
                  {canRefreshStatus ? (
                    <button type="button" className="btn" onClick={refreshTelnyxStatus} disabled={working === 'refresh'}>
                      Refresh status
                    </button>
                  ) : null}
                  <button type="button" className="btn" onClick={syncTemplates} disabled={working === 'sync'}>Sync from Telnyx</button>
                  <button type="button" className="btn" onClick={cloneAnonymous} disabled={working === 'clone'}>Clone anonymous</button>
                </div>
                <div className="waSurveyTelnyxStatusRow">
                  {saveNotice ? <span className="waSurveySaveNotice">{saveNotice}</span> : null}
                  {syncNotice ? <span className="waSurveySyncNotice">{syncNotice}</span> : null}
                  <span className={`pill ${telnyxSyncPillClass(telnyxLabel)}`}>{telnyxLabel}</span>
                  {template?.category ? <span className="pill muted">{template.category}</span> : null}
                </div>
                {template?.rejection_reason && telnyxLabel === TELNYX_SYNC_LABELS.REJECTED ? (
                  <p className="fieldHint waSurveyRejectionReason">
                    Rejection reason: <strong>{template.rejection_reason}</strong>
                  </p>
                ) : null}
                {template?.last_push_error && telnyxLabel === TELNYX_SYNC_LABELS.FAILED ? (
                  <p className="fieldHint waSurveyRejectionReason">
                    Sync error: <strong>{template.last_push_error}</strong>
                  </p>
                ) : null}
                <p className="fieldHint">
                  Local content sync: <strong>{template?.sync_status_label || template?.sync_status}</strong>
                  {template?.telnyx_template_id ? <> · Telnyx id: <code>{template.telnyx_template_id}</code></> : null}
                </p>
              </div>
            </section>

            <aside className="waSurveyTemplateEditPreview">
              <div className="waSurveyTemplateEditPreviewInner">
                <WaSurveyPhonePreview
                  businessName={livePreview?.businessName || 'Northgate Dental'}
                  renderedBody={livePreview?.renderedBody || draft.body}
                  footer={livePreview?.footer || draft.footer}
                  buttons={preview?.buttons || template?.buttons || []}
                  templateName={template?.name}
                  approvalStatus={template?.approval_status}
                  syncStatus={template?.sync_status}
                />
                <div className="waSurveyTestSend">
                  <label className="msgFieldBlock">
                    <span className="label">Test mobile</span>
                    <input className="input" value={testMobile} onChange={(e) => setTestMobile(e.target.value)} placeholder="+447700900123" />
                  </label>
                  <button type="button" className="btn primary" onClick={sendTest} disabled={working === 'send-test' || !testMobile.trim() || template?.approval_status !== 'APPROVED'}>
                    {working === 'send-test' ? 'Sending…' : 'Send test'}
                  </button>
                </div>
              </div>
            </aside>

            <section className="waSurveyTemplateEditMappings card">
              <div className="cardHead"><h3>Survey type usage</h3></div>
              <div className="cardBody waSurveyMappingList">
                {surveyTypes.map((st) => (
                  <div key={st.survey_type_id} className="waSurveyMappingRow">
                    <strong>{st.name}</strong>
                    <label className="checkRow"><input type="checkbox" checked={Boolean(st.usable_as_standard)} onChange={() => toggleSurveyType(st.survey_type_id, 'usable_as_standard')} /> Standard</label>
                    <label className="checkRow"><input type="checkbox" checked={Boolean(st.usable_as_anonymous)} onChange={() => toggleSurveyType(st.survey_type_id, 'usable_as_anonymous')} disabled={!st.supports_anonymous} /> Anonymous</label>
                    <label className="checkRow"><input type="checkbox" checked={Boolean(st.is_default_standard)} onChange={() => toggleSurveyType(st.survey_type_id, 'is_default_standard')} /> Default std</label>
                    <label className="checkRow"><input type="checkbox" checked={Boolean(st.is_default_anonymous)} onChange={() => toggleSurveyType(st.survey_type_id, 'is_default_anonymous')} disabled={!st.supports_anonymous} /> Default anon</label>
                  </div>
                ))}
                <button type="button" className="btn primary" onClick={saveMappings} disabled={working === 'mappings'}>Save mappings</button>
              </div>
            </section>
          </div>
        ) : null}
      </div>
    </div>
  )
}
