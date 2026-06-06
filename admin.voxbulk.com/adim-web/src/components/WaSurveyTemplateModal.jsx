import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatWaSurveyError } from '../lib/waSurveyFeedback'
import {
  LOCAL_STATUS_LABELS,
  TELNYX_SYNC_LABELS,
  WA_TEMPLATE_CATEGORY_OPTIONS,
  formatLastSyncedAt,
  localStatusPillClass,
  resolveLocalStatus,
  resolveSyncStatus,
  telnyxSyncPillClass,
  templateNeedsResync,
  validateCategoryBeforeSync,
} from '../lib/waSurveyTelnyxSync'
import { VAR_LABELS, ensureExampleValues, substituteTemplateVars, varIndexesFromText } from '../lib/waSurveyTemplateVars'
import '../styles/waTemplateEditor.css'

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

function updateBodyInComponents(components, text, exampleValues = ['Alex']) {
  const values = ensureExampleValues(text, '', exampleValues)
  const varIds = varIndexesFromText(text)
  const needed = varIds.length ? Math.max(...varIds) : 1
  const bodyExample = values.slice(0, needed)
  while (bodyExample.length < needed) {
    bodyExample.push(`Sample ${bodyExample.length + 1}`)
  }
  let found = false
  const out = components.map((comp) => {
    if (String(comp?.type || '').toUpperCase() !== 'BODY') return comp
    found = true
    return { ...comp, text, example: { body_text: [bodyExample] } }
  })
  if (!found) out.unshift({ type: 'BODY', text, example: { body_text: [bodyExample] } })
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

function emptyButton() {
  return { text: '', url: '', phone_number: '' }
}

function buttonsMetaFromComponents(components) {
  const comp = (components || []).find((c) => String(c?.type || '').toUpperCase() === 'BUTTONS')
  const list = Array.isArray(comp?.buttons) ? comp.buttons : []
  if (!list.length) return { button_type: 'none', buttons: [] }
  const first = list[0] || {}
  const kind = String(first.type || '').toUpperCase()
  if (kind === 'URL') {
    return {
      button_type: 'url',
      buttons: [{ text: first.text || '', url: first.url || '', phone_number: '' }],
    }
  }
  if (kind === 'PHONE_NUMBER') {
    return {
      button_type: 'phone',
      buttons: [{ text: first.text || '', url: '', phone_number: first.phone_number || '' }],
    }
  }
  return {
    button_type: 'quick_reply',
    buttons: list.map((b) => ({ text: b.text || '', url: '', phone_number: '' })),
  }
}

function updateButtonsInComponents(components, buttonType, buttons) {
  const without = (components || []).filter((c) => String(c?.type || '').toUpperCase() !== 'BUTTONS')
  const bt = buttonType || 'none'
  if (bt === 'none') return without
  const cleaned = (buttons || []).filter((b) => String(b?.text || '').trim())
  if (!cleaned.length) return without
  let built = []
  if (bt === 'quick_reply') {
    built = cleaned.slice(0, 3).map((b) => ({ type: 'QUICK_REPLY', text: String(b.text).trim().slice(0, 25) }))
  } else if (bt === 'url') {
    const b = cleaned[0]
    built = [{
      type: 'URL',
      text: String(b.text).trim().slice(0, 25),
      url: String(b.url || 'https://example.com/survey').trim(),
    }]
  } else if (bt === 'phone') {
    const b = cleaned[0]
    built = [{
      type: 'PHONE_NUMBER',
      text: String(b.text).trim().slice(0, 25),
      phone_number: String(b.phone_number || '+441234567890').trim(),
    }]
  }
  if (!built.length) return without
  return [...without, { type: 'BUTTONS', buttons: built }]
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
  const buttonMeta = buttonsMetaFromComponents(components)
  setDraft({
    display_name: tpl?.display_name || tpl?.name,
    category: tpl?.category || 'MARKETING',
    active_for_survey: tpl?.active_for_survey !== false,
    body: bodyTextFromComponents(components),
    footer: footerTextFromComponents(components) || tpl?.footer || '',
    components,
    button_type: buttonMeta.button_type,
    buttons: buttonMeta.buttons.length ? buttonMeta.buttons : [emptyButton()],
    example_values: tpl?.example_values || ['Alex'],
  })
}

export default function WaSurveyTemplateModal({
  templateId,
  initialTemplate,
  surveyTypeId,
  open,
  onClose,
  onSaved,
  systemTemplateMode = false,
  systemTemplateKind = '',
}) {
  const [loading, setLoading] = useState(false)
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [errorDetail, setErrorDetail] = useState('')
  const [template, setTemplate] = useState(null)
  const [draft, setDraft] = useState(null)
  const [surveyTypes, setSurveyTypes] = useState([])
  const [preview, setPreview] = useState(null)
  const [testMobile, setTestMobile] = useState('')
  const [syncing, setSyncing] = useState(false)
  const [isDirty, setIsDirty] = useState(false)
  const [toast, setToast] = useState('')

  const localStatus = useMemo(
    () => resolveLocalStatus(template, { isDirty }),
    [template, isDirty]
  )
  const syncStatus = useMemo(
    () => resolveSyncStatus(template, { syncing }),
    [template, syncing]
  )
  const lastSynced = formatLastSyncedAt(template?.last_synced_at || template?.last_pushed_at)
  const needsResync = templateNeedsResync(template) || isDirty
  const canRefreshStatus = template && !template.is_local_only

  const patchDraft = (updater) => {
    setIsDirty(true)
    setDraft((current) => (typeof updater === 'function' ? updater(current) : { ...current, ...updater }))
  }

  const showToast = (message) => {
    setToast(message)
    window.setTimeout(() => setToast(''), 2800)
  }

  const clearFeedback = () => {
    setError('')
    setErrorDetail('')
  }

  const showError = (err, fallback = 'Request failed') => {
    const formatted = formatWaSurveyError(err, fallback)
    setError(formatted.message)
    setErrorDetail(formatted.detailText !== formatted.message ? formatted.detailText : '')
  }

  const loadPreview = async (id) => {
    const previewData = await apiFetch(`/admin/wa-survey/templates/${id}/preview`)
    setPreview(previewData)
  }

  const loadFromFallback = async () => {
    if (!initialTemplate) throw new Error('Could not load template')
    setTemplate(initialTemplate)
    applyTemplateDraft(setDraft, initialTemplate)
    setIsDirty(false)
    const typesRes = await apiFetch('/admin/wa-survey/types')
    setSurveyTypes(buildSurveyTypesFallback(typesRes.types, initialTemplate, surveyTypeId))
    await loadPreview(templateId)
    setError('FastAPI on port 8000 is outdated — restart it so shared-template mappings load.')
    setErrorDetail(
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
      const loadedTypes = Array.isArray(data.survey_types) ? data.survey_types : []
      if (systemTemplateMode && surveyTypeId) {
        setSurveyTypes(loadedTypes.filter((row) => String(row.survey_type_id) === String(surveyTypeId)))
      } else {
        setSurveyTypes(loadedTypes)
      }
      applyTemplateDraft(setDraft, data.template)
      setIsDirty(false)
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
    const previewButtons = (draft.buttons || [])
      .filter((b) => String(b?.text || '').trim())
      .map((b) => ({ text: b.text, title: b.text, label: b.text }))
    return {
      businessName: values[1] || 'Northgate Dental',
      renderedBody: substituteTemplateVars(draft.body, values),
      footer: draft.footer,
      values,
      buttons: previewButtons,
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
      components = updateBodyInComponents(components, draft.body, draft.example_values)
      components = updateFooterInComponents(components, draft.footer)
      components = updateButtonsInComponents(components, draft.button_type, draft.buttons)
      const data = await apiFetch(`/admin/wa-survey/templates/${templateId}`, {
        method: 'PUT',
        body: JSON.stringify({
          display_name: draft.display_name,
          category: draft.category,
          active_for_survey: draft.active_for_survey !== false,
          components,
          example_values: ensureExampleValues(draft.body, '', draft.example_values),
        }),
      })
      setTemplate(data.template)
      applyTemplateDraft(setDraft, data.template)
      setIsDirty(false)
      showToast(data.message || 'Template saved')
      onSaved?.(data.template || data)
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
      showToast(`Mappings saved (${data.linked_survey_type_count || mappings.length} types)`)
      onSaved?.()
    } catch (e) {
      showError(e, 'Could not save mappings')
    } finally {
      setWorking('')
    }
  }

  const toggleActiveForSurvey = async () => {
    if (!templateId || !template) return
    const nextActive = template.active_for_survey === false
    setWorking('active')
    clearFeedback()
    try {
      const data = await apiFetch(`/admin/wa-survey/templates/${templateId}/set-active`, {
        method: 'POST',
        body: JSON.stringify({ active: nextActive }),
      })
      setTemplate(data.template)
      setDraft((current) => (current ? { ...current, active_for_survey: nextActive } : current))
      setIsDirty(false)
      showToast(data.message || (nextActive ? 'Template enabled.' : 'Template hidden from surveys.'))
      onSaved?.(data.template || data)
    } catch (e) {
      showError(e, 'Could not update template visibility')
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
      if (isDirty) {
        let components = draft.components?.length ? [...draft.components] : []
        components = updateBodyInComponents(components, draft.body, draft.example_values)
        components = updateFooterInComponents(components, draft.footer)
        components = updateButtonsInComponents(components, draft.button_type, draft.buttons)
        const saved = await apiFetch(`/admin/wa-survey/templates/${templateId}`, {
          method: 'PUT',
          body: JSON.stringify({
            display_name: draft.display_name,
            category: draft.category,
            components,
            example_values: ensureExampleValues(draft.body, '', draft.example_values),
          }),
        })
        setTemplate(saved.template)
        applyTemplateDraft(setDraft, saved.template)
        setIsDirty(false)
      }
      const data = await apiFetch(`/admin/wa-survey/templates/${templateId}/push`, { method: 'POST', body: '{}' })
      setTemplate(data.template)
      const syncMessage = data.sync_message || data.message || TELNYX_SYNC_LABELS.SYNCED
      if (data.template) applyTemplateDraft(setDraft, data.template)
      setIsDirty(false)
      showToast(syncMessage)
      onSaved?.()
    } catch (e) {
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
      if (data.template) applyTemplateDraft(setDraft, data.template)
      setIsDirty(false)
      showToast(data.telnyx_sync_label || data.message || 'Status refreshed')
      onSaved?.()
    } catch (e) {
      showError(e, TELNYX_SYNC_LABELS.FAILED)
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
      showToast('Anonymous variant created')
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
      const formatted = formatActionSuccess(data, 'Test survey sent')
      showToast(formatted.message)
    } catch (e) {
      showError(e, 'Send test survey failed')
    } finally {
      setWorking('')
    }
  }

  const buttons = livePreview?.buttons?.length
    ? livePreview.buttons
    : (preview?.buttons || template?.buttons || [])
  const rejectionReason = template?.rejection_reason
  const syncError = template?.sync_error || template?.last_push_error

  return (
    <div className="waTplEd-overlay" role="dialog" aria-modal="true" aria-label="Edit WhatsApp template">
      <div className="waTplEd">
        <header className="waTplEd-topbar">
          <div className="waTplEd-topbar-left">
            <div className="waTplEd-wa-icon">
              <i className="ti ti-brand-whatsapp" />
            </div>
            <div className="waTplEd-name-wrap">
              <input
                className="waTplEd-name"
                value={draft?.display_name || ''}
                onChange={(e) => patchDraft({ display_name: e.target.value })}
                spellCheck={false}
                placeholder="Template name"
              />
              {draft?.category ? <span className="waTplEd-tag">{draft.category}</span> : null}
            </div>
          </div>
          <div className="waTplEd-topbar-actions">
            <button
              type="button"
              className={`waTplEd-tb-btn${template?.active_for_survey === false ? ' muted-btn' : ''}`}
              onClick={() => void toggleActiveForSurvey()}
              disabled={working === 'active' || loading}
              title={template?.active_for_survey === false ? 'Show in survey flows again' : 'Hide from surveys — Telnyx sync still works'}
            >
              <i className={template?.active_for_survey === false ? 'ti ti-eye' : 'ti ti-eye-off'} />
              {working === 'active'
                ? 'Updating…'
                : template?.active_for_survey === false
                  ? 'Enable for surveys'
                  : 'Hide from surveys'}
            </button>
            <button
              type="button"
              className={`waTplEd-tb-btn sync-btn${syncing ? ' syncing' : ''}`}
              onClick={pushTemplate}
              disabled={working === 'push' || syncing}
            >
              <i className="ti ti-cloud-upload" />
              {syncing ? 'Syncing…' : 'Sync this to Telnyx'}
            </button>
            <div className="waTplEd-divider" />
            <button
              type="button"
              className="waTplEd-tb-btn primary"
              onClick={saveDraft}
              disabled={working === 'save' || loading}
            >
              <i className="ti ti-check" />
              {working === 'save' ? 'Saving…' : 'Save'}
            </button>
            <button type="button" className="waTplEd-tb-btn close-btn" onClick={onClose}>
              <i className="ti ti-x" />
              Close
            </button>
          </div>
        </header>

        {loading ? <p className="waTplEd-hint" style={{ padding: '1rem 1.25rem' }}>Loading…</p> : null}
        {error ? (
          <div className="waTplEd-alert error">
            <strong>{error}</strong>
            {errorDetail ? <pre style={{ marginTop: 8, whiteSpace: 'pre-wrap', fontSize: 12 }}>{errorDetail}</pre> : null}
          </div>
        ) : null}

        {!loading && draft ? (
          <div className="waTplEd-scroll">
            {systemTemplateMode ? (
              <div className="waTplEd-alert" style={{ margin: '0 1.25rem 0.75rem' }}>
                Global system template · <strong>{systemTemplateKind || 'system'}</strong>
                {' '}· editing here does not change industry survey types. Survey-type mappings are locked for system templates.
              </div>
            ) : null}
            <div className="waTplEd-layout">
              <div className="waTplEd-preview-col">
                <div className="waTplEd-preview-label">
                  <i className="ti ti-device-mobile" />
                  Preview
                </div>
                <div className="waTplEd-phone">
                  <div className="waTplEd-phone-notch" />
                  <div className="waTplEd-phone-status">
                    <div className="waTplEd-p-avatar">
                      {String(livePreview?.businessName || 'B').slice(0, 1)}
                    </div>
                    <div>
                      <div className="waTplEd-p-name">{livePreview?.businessName || 'Business'}</div>
                      <div className="waTplEd-p-online">online</div>
                    </div>
                  </div>
                  <div className="waTplEd-phone-body">
                    <div className="waTplEd-wa-bubble">
                      <div className="waTplEd-wa-body">{livePreview?.renderedBody || draft.body}</div>
                      {livePreview?.footer ? <div className="waTplEd-wa-ftr">{livePreview.footer}</div> : null}
                      {buttons.length ? (
                        <div className="waTplEd-wa-btns">
                          {buttons.map((btn, i) => (
                            <div key={i} className="waTplEd-wa-btn">{btn.text || btn.title || 'Button'}</div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>
                <div className="waTplEd-test-row">
                  <input
                    className="waTplEd-input"
                    value={testMobile}
                    onChange={(e) => setTestMobile(e.target.value)}
                    placeholder="+447700900123"
                  />
                  <button
                    type="button"
                    className="waTplEd-tb-btn primary"
                    onClick={sendTest}
                    disabled={working === 'send-test' || !testMobile.trim() || template?.approval_status !== 'APPROVED'}
                  >
                    {working === 'send-test' ? 'Sending…' : 'Send test'}
                  </button>
                </div>
              </div>

              <div className="waTplEd-edit-panel">
                <div className="waTplEd-field-card">
                  <div className="waTplEd-field-hdr">
                    <div className="waTplEd-ficon"><i className="ti ti-tag" /></div>
                    <span className="waTplEd-ftitle">Category</span>
                    <span className="waTplEd-fbadge">required for sync</span>
                  </div>
                  <div className="waTplEd-field-body">
                    <select
                      className="waTplEd-select"
                      value={draft.category || ''}
                      onChange={(e) => patchDraft({ category: e.target.value })}
                    >
                      <option value="">Select category…</option>
                      {WA_TEMPLATE_CATEGORY_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="waTplEd-field-card">
                  <div className="waTplEd-field-hdr">
                    <div className="waTplEd-ficon"><i className="ti ti-align-left" /></div>
                    <span className="waTplEd-ftitle">Body</span>
                    <span className="waTplEd-fbadge">required · max 1024</span>
                  </div>
                  <div className="waTplEd-field-body">
                    <textarea
                      className="waTplEd-textarea"
                      maxLength={1024}
                      value={draft.body}
                      onChange={(e) => patchDraft((d) => ({
                        ...d,
                        body: e.target.value,
                        example_values: ensureExampleValues(e.target.value, '', d.example_values),
                      }))}
                    />
                    <div className="waTplEd-char-count">{draft.body.length}/1024</div>
                  </div>
                </div>

                <div className="waTplEd-field-card">
                  <div className="waTplEd-field-hdr">
                    <div className="waTplEd-ficon"><i className="ti ti-minus" /></div>
                    <span className="waTplEd-ftitle">Footer</span>
                    <span className="waTplEd-fbadge">optional · max 60</span>
                  </div>
                  <div className="waTplEd-field-body">
                    <input
                      className="waTplEd-input"
                      maxLength={60}
                      value={draft.footer}
                      onChange={(e) => patchDraft({ footer: e.target.value })}
                      placeholder="Footer note…"
                    />
                    <div className="waTplEd-char-count">{draft.footer.length}/60</div>
                  </div>
                </div>

                <div className="waTplEd-field-card">
                  <div className="waTplEd-field-hdr">
                    <div className="waTplEd-ficon"><i className="ti ti-click" /></div>
                    <span className="waTplEd-ftitle">Buttons</span>
                    <span className="waTplEd-fbadge">max 25 chars each</span>
                  </div>
                  <div className="waTplEd-field-body">
                    <select
                      className="waTplEd-select"
                      value={draft.button_type || 'none'}
                      onChange={(e) => patchDraft((d) => ({
                        ...d,
                        button_type: e.target.value,
                        buttons: e.target.value === 'none' ? [] : (d.buttons?.length ? d.buttons : [emptyButton()]),
                      }))}
                    >
                      <option value="none">No buttons</option>
                      <option value="quick_reply">Quick reply (up to 3)</option>
                      <option value="url">URL button</option>
                      <option value="phone">Phone button</option>
                    </select>
                    {draft.button_type && draft.button_type !== 'none' ? (
                      <div className="waTplEd-var-rows" style={{ marginTop: 12 }}>
                        {[0, 1, 2].map((i) => {
                          if (draft.button_type !== 'quick_reply' && i > 0) return null
                          const btn = draft.buttons?.[i] || emptyButton()
                          return (
                            <div key={i} className="waTplEd-var-row" style={{ flexWrap: 'wrap', gap: 8 }}>
                              <span className="waTplEd-var-key">Btn {i + 1}</span>
                              <input
                                className="waTplEd-input"
                                maxLength={25}
                                placeholder="Button label"
                                value={btn.text}
                                onChange={(e) => patchDraft((d) => {
                                  const buttons = [...(d.buttons || [emptyButton()])]
                                  while (buttons.length <= i) buttons.push(emptyButton())
                                  buttons[i] = { ...buttons[i], text: e.target.value }
                                  return { ...d, buttons }
                                })}
                              />
                              {draft.button_type === 'url' && i === 0 ? (
                                <input
                                  className="waTplEd-input"
                                  placeholder="https://…"
                                  value={btn.url}
                                  onChange={(e) => patchDraft((d) => {
                                    const buttons = [...(d.buttons || [emptyButton()])]
                                    buttons[0] = { ...buttons[0], url: e.target.value }
                                    return { ...d, buttons }
                                  })}
                                />
                              ) : null}
                              {draft.button_type === 'phone' && i === 0 ? (
                                <input
                                  className="waTplEd-input"
                                  placeholder="+441234567890"
                                  value={btn.phone_number}
                                  onChange={(e) => patchDraft((d) => {
                                    const buttons = [...(d.buttons || [emptyButton()])]
                                    buttons[0] = { ...buttons[0], phone_number: e.target.value }
                                    return { ...d, buttons }
                                  })}
                                />
                              ) : null}
                            </div>
                          )
                        })}
                      </div>
                    ) : null}
                  </div>
                </div>

                <div className="waTplEd-field-card">
                  <div className="waTplEd-field-hdr">
                    <div className="waTplEd-ficon"><i className="ti ti-braces" /></div>
                    <span className="waTplEd-ftitle">Variables</span>
                    <span className="waTplEd-fbadge">sample values</span>
                  </div>
                  <div className="waTplEd-field-body">
                    <div className="waTplEd-var-rows">
                      {(livePreview?.values || ensureExampleValues(draft.body, '', draft.example_values)).map((val, i) => (
                        <div key={i} className="waTplEd-var-row">
                          <span className="waTplEd-var-key">{`{{${i + 1}}}`}</span>
                          <input
                            className="waTplEd-input"
                            value={val}
                            onChange={(e) => patchDraft((d) => {
                              const values = ensureExampleValues(d.body, '', d.example_values)
                              values[i] = e.target.value
                              return { ...d, example_values: values }
                            })}
                          />
                          <span className="waTplEd-hint" style={{ margin: 0, minWidth: 72 }}>{VAR_LABELS[i] || 'Variable'}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {!systemTemplateMode ? (
                <div className="waTplEd-field-card">
                  <div className="waTplEd-field-hdr">
                    <div className="waTplEd-ficon"><i className="ti ti-link" /></div>
                    <span className="waTplEd-ftitle">Survey type usage</span>
                  </div>
                  <div className="waTplEd-field-body">
                    {surveyTypes.map((st) => (
                      <div key={st.survey_type_id} className="waTplEd-mapping-row">
                        <strong>{st.name}</strong>
                        <label><input type="checkbox" checked={Boolean(st.usable_as_standard)} onChange={() => toggleSurveyType(st.survey_type_id, 'usable_as_standard')} /> Std</label>
                        <label><input type="checkbox" checked={Boolean(st.usable_as_anonymous)} onChange={() => toggleSurveyType(st.survey_type_id, 'usable_as_anonymous')} disabled={!st.supports_anonymous} /> Anon</label>
                        <label><input type="checkbox" checked={Boolean(st.is_default_standard)} onChange={() => toggleSurveyType(st.survey_type_id, 'is_default_standard')} /> Def std</label>
                        <label><input type="checkbox" checked={Boolean(st.is_default_anonymous)} onChange={() => toggleSurveyType(st.survey_type_id, 'is_default_anonymous')} disabled={!st.supports_anonymous} /> Def anon</label>
                      </div>
                    ))}
                    <div className="waTplEd-actions-row">
                      <button type="button" className="waTplEd-tb-btn primary" onClick={saveMappings} disabled={working === 'mappings'}>
                        Save mappings
                      </button>
                      {canRefreshStatus ? (
                        <button type="button" className="waTplEd-tb-btn" onClick={refreshTelnyxStatus} disabled={working === 'refresh'}>
                          Refresh Telnyx status
                        </button>
                      ) : null}
                      <button type="button" className="waTplEd-tb-btn" onClick={cloneAnonymous} disabled={working === 'clone'}>
                        Clone anonymous
                      </button>
                    </div>
                  </div>
                </div>
                ) : (
                  <div className="waTplEd-field-card">
                    <div className="waTplEd-field-hdr">
                      <div className="waTplEd-ficon"><i className="ti ti-link" /></div>
                      <span className="waTplEd-ftitle">System template scope</span>
                    </div>
                    <div className="waTplEd-field-body">
                      <p className="waTplEd-hint" style={{ margin: 0 }}>
                        Linked to hidden system survey type
                        {surveyTypeId ? <> <code>{surveyTypeId}</code></> : null}.
                        Use Save above for content changes; mappings stay on this system type.
                      </p>
                      {canRefreshStatus ? (
                        <div className="waTplEd-actions-row" style={{ marginTop: 12 }}>
                          <button type="button" className="waTplEd-tb-btn" onClick={refreshTelnyxStatus} disabled={working === 'refresh'}>
                            Refresh Telnyx status
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : null}

        <footer className="waTplEd-statusbar">
          <span className={`waTplEd-status-dot ${isDirty ? 'unsaved' : 'saved'}`} />
          <span>Local:</span>
          <span className={`waTplEd-status-pill ${localStatusPillClass(localStatus)}`}>{localStatus}</span>
          <span>Telnyx:</span>
          <span className={`waTplEd-status-pill ${telnyxSyncPillClass(syncStatus)}`}>{syncStatus}</span>
          {!isDirty && syncStatus === TELNYX_SYNC_LABELS.NOT_SYNCED ? (
            <span>— not uploaded yet</span>
          ) : null}
          {lastSynced ? <span>Last synced: {lastSynced}</span> : null}
          {template?.telnyx_template_id ? (
            <span>ID: {template.telnyx_template_id}</span>
          ) : null}
          {rejectionReason && syncStatus === TELNYX_SYNC_LABELS.REJECTED ? (
            <span>Rejection: {rejectionReason}</span>
          ) : null}
          {syncError && syncStatus === TELNYX_SYNC_LABELS.FAILED ? (
            <span>Error: {syncError}</span>
          ) : null}
        </footer>

        {toast ? (
          <div className={`waTplEd-toast show`}>
            <i className="ti ti-check" />
            {toast}
          </div>
        ) : null}
      </div>
    </div>
  )
}
