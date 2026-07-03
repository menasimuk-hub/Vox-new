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
import {
  ensureExampleValues,
  interviewVarLabels,
  substituteTemplateVars,
} from '../lib/waInterviewTemplateVars'
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

function updateBodyInComponents(components, text) {
  let found = false
  const out = components.map((comp) => {
    if (String(comp?.type || '').toUpperCase() !== 'BODY') return comp
    found = true
    return { ...comp, text }
  })
  if (!found) out.unshift({ type: 'BODY', text, example: { body_text: [['James']] } })
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
      url: String(b.url || 'https://example.com/book').trim(),
    }]
  }
  if (!built.length) return without
  return [...without, { type: 'BUTTONS', buttons: built }]
}

function applyTemplateDraft(setDraft, tpl) {
  const components = parseComponents(tpl?.draft_components || tpl?.remote_components)
  const buttonMeta = buttonsMetaFromComponents(components)
  setDraft({
    display_name: tpl?.display_name || tpl?.name,
    category: tpl?.category || 'UTILITY',
    language: tpl?.language || 'en_GB',
    active_for_interview: tpl?.active_for_interview !== false,
    body: bodyTextFromComponents(components),
    components,
    button_type: buttonMeta.button_type,
    buttons: buttonMeta.buttons.length ? buttonMeta.buttons : [emptyButton()],
    example_values: tpl?.example_values || ['James'],
  })
}

export default function WaInterviewTemplateModal({ templateId, open, onClose, onSaved }) {
  const [loading, setLoading] = useState(false)
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [errorDetail, setErrorDetail] = useState('')
  const [syncFix, setSyncFix] = useState(null)
  const [template, setTemplate] = useState(null)
  const [draft, setDraft] = useState(null)
  const [preview, setPreview] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [isDirty, setIsDirty] = useState(false)
  const [toast, setToast] = useState('')

  const localStatus = useMemo(() => resolveLocalStatus(template, { isDirty }), [template, isDirty])
  const syncStatus = useMemo(() => resolveSyncStatus(template, { syncing }), [template, syncing])
  const lastSynced = formatLastSyncedAt(template?.last_synced_at || template?.last_pushed_at)
  const needsResync = templateNeedsResync(template) || isDirty
  const varLabels = interviewVarLabels(template?.sales_template_key)

  const showSyncError = (err, fallback) => {
    const formatted = formatWaSurveyError(err, fallback)
    setError(formatted.message)
    setErrorDetail(formatted.detailText !== formatted.message ? formatted.detailText : '')
    setSyncFix(
      formatted.requiresRename || formatted.requiresLanguageFix
        ? {
            suggestedTemplateName: formatted.suggestedTemplateName,
            suggestedLanguage: formatted.suggestedLanguage,
            requiresRename: formatted.requiresRename,
            requiresLanguageFix: formatted.requiresLanguageFix,
          }
        : null,
    )
  }

  const clearSyncError = () => {
    setError('')
    setErrorDetail('')
    setSyncFix(null)
  }

  const applySuggestedRename = async () => {
    if (!templateId || !syncFix?.suggestedTemplateName) return
    setWorking('rename')
    clearSyncError()
    try {
      const data = await apiFetch(`/admin/wa-interview/templates/${templateId}/rename-for-sync`, {
        method: 'POST',
        body: JSON.stringify({ new_name: syncFix.suggestedTemplateName }),
      })
      setTemplate(data?.template || template)
      applyTemplateDraft(setDraft, data?.template || template)
      setIsDirty(false)
      setToast(data?.message || `Renamed to ${data?.template_name}`)
      onSaved?.(data?.template)
    } catch (e) {
      showSyncError(e, 'Rename failed')
    } finally {
      setWorking('')
    }
  }

  const applySuggestedLanguage = async () => {
    if (!draft || !templateId || !syncFix?.suggestedLanguage) return
    setWorking('save')
    clearSyncError()
    try {
      const components = updateButtonsInComponents(
        updateBodyInComponents(parseComponents(draft.components), draft.body),
        draft.button_type,
        draft.buttons,
      )
      const data = await apiFetch(`/admin/wa-interview/templates/${templateId}`, {
        method: 'PUT',
        body: JSON.stringify({
          display_name: draft.display_name,
          category: draft.category,
          language: syncFix.suggestedLanguage,
          active_for_interview: draft.active_for_interview,
          components,
          example_values: ensureExampleValues(draft.body, '', draft.example_values),
        }),
      })
      setTemplate(data?.template || template)
      applyTemplateDraft(setDraft, data?.template || template)
      setIsDirty(false)
      setToast(`Language set to ${syncFix.suggestedLanguage}. Sync again when ready.`)
      onSaved?.(data?.template)
    } catch (e) {
      showSyncError(e, 'Could not save language')
    } finally {
      setWorking('')
    }
  }

  const patchDraft = (updater) => {
    setIsDirty(true)
    setDraft((current) => (typeof updater === 'function' ? updater(current) : { ...current, ...updater }))
  }

  const loadTemplate = useCallback(async () => {
    if (!templateId) return
    setLoading(true)
    clearSyncError()
    try {
      const data = await apiFetch(`/admin/wa-interview/templates/${templateId}`)
      const tpl = data?.template
      setTemplate(tpl)
      applyTemplateDraft(setDraft, tpl)
      setIsDirty(false)
      const previewData = await apiFetch(`/admin/wa-interview/templates/${templateId}/preview`)
      setPreview(previewData?.preview || null)
    } catch (e) {
      showSyncError(e, 'Could not load template')
    } finally {
      setLoading(false)
    }
  }, [templateId])

  useEffect(() => {
    if (!open || !templateId) return
    void loadTemplate()
  }, [open, templateId, loadTemplate])

  if (!open) return null

  const saveDraft = async () => {
    if (!draft || !templateId) return
    setWorking('save')
    clearSyncError()
    try {
      const components = updateButtonsInComponents(
        updateBodyInComponents(parseComponents(draft.components), draft.body),
        draft.button_type,
        draft.buttons,
      )
      const example_values = ensureExampleValues(draft.body, '', draft.example_values)
      const data = await apiFetch(`/admin/wa-interview/templates/${templateId}`, {
        method: 'PUT',
        body: JSON.stringify({
          display_name: draft.display_name,
          category: draft.category,
          language: draft.language || 'en_GB',
          active_for_interview: draft.active_for_interview,
          components,
          example_values,
        }),
      })
      setTemplate(data?.template || template)
      applyTemplateDraft(setDraft, data?.template || template)
      setIsDirty(false)
      setToast(formatActionSuccess(data, 'Template saved').message)
      onSaved?.(data?.template)
    } catch (e) {
      showSyncError(e, 'Could not save template')
    } finally {
      setWorking('')
    }
  }

  const pushToTelnyx = async () => {
    if (!templateId) return
    const categoryErr = validateCategoryBeforeSync(draft?.category || template?.category)
    if (categoryErr) {
      setError(categoryErr)
      setErrorDetail('')
      setSyncFix(null)
      return
    }
    setWorking('push')
    setSyncing(true)
    clearSyncError()
    try {
      if (isDirty) await saveDraft()
      const data = await apiFetch(`/admin/wa-interview/templates/${templateId}/push`, { method: 'POST', body: '{}' })
      setTemplate(data?.template || template)
      applyTemplateDraft(setDraft, data?.template || template)
      setIsDirty(false)
      setToast(formatActionSuccess(data, 'Pushed to Telnyx').message)
      onSaved?.(data?.template)
    } catch (e) {
      showSyncError(e, 'Push to Meta failed')
    } finally {
      setWorking('')
      setSyncing(false)
    }
  }

  const toggleHidden = async () => {
    if (!templateId || !draft) return
    setWorking('hide')
    try {
      const data = await apiFetch(`/admin/wa-interview/templates/${templateId}/set-active`, {
        method: 'POST',
        body: JSON.stringify({ active_for_interview: !draft.active_for_interview }),
      })
      setTemplate(data?.template || template)
      applyTemplateDraft(setDraft, data?.template || template)
      setToast(data?.message || 'Updated visibility')
      onSaved?.(data?.template)
    } catch (e) {
      showSyncError(e, 'Could not update visibility')
    } finally {
      setWorking('')
    }
  }

  const renderedPreview = draft
    ? substituteTemplateVars(draft.body, ensureExampleValues(draft.body, '', draft.example_values))
    : ''

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <div className="modal-card wa-template-modal">
        <div className="modal-header">
          <div>
            <h2>{draft?.display_name || template?.display_name || 'Interview template'}</h2>
            <p className="text-muted">{template?.description || template?.name}</p>
          </div>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">×</button>
        </div>

        {toast ? <div className="alert ok">{toast}</div> : null}
        {error ? (
          <div className="alert err">
            <strong>{error}</strong>
            {errorDetail ? <pre style={{ marginTop: 8, whiteSpace: 'pre-wrap', fontSize: 12 }}>{errorDetail}</pre> : null}
            {syncFix?.requiresRename && syncFix.suggestedTemplateName ? (
              <button
                type="button"
                className="btn secondary"
                style={{ marginTop: 10 }}
                onClick={() => void applySuggestedRename()}
                disabled={working === 'rename'}
              >
                {working === 'rename' ? 'Renaming…' : `Rename to ${syncFix.suggestedTemplateName}`}
              </button>
            ) : null}
            {syncFix?.requiresLanguageFix && syncFix.suggestedLanguage ? (
              <button
                type="button"
                className="btn secondary"
                style={{ marginTop: 10 }}
                onClick={() => void applySuggestedLanguage()}
                disabled={working === 'save'}
              >
                {working === 'save' ? 'Saving…' : `Use language ${syncFix.suggestedLanguage}`}
              </button>
            ) : null}
          </div>
        ) : null}

        {loading || !draft ? (
          <p className="text-muted">Loading template…</p>
        ) : (
          <div className="wa-template-editor-grid">
            <div className="wa-template-editor-main">
              <label className="field-label">Display name</label>
              <input
                className="input"
                value={draft.display_name || ''}
                onChange={(e) => patchDraft({ display_name: e.target.value })}
              />

              <label className="field-label">Meta category</label>
              <select
                className="input"
                value={draft.category || 'UTILITY'}
                onChange={(e) => patchDraft({ category: e.target.value })}
              >
                {WA_TEMPLATE_CATEGORY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>

              <label className="field-label">Telnyx template name</label>
              <input className="input" value={template?.name || ''} readOnly spellCheck={false} />

              <label className="field-label">Template language</label>
              <input
                className="input"
                value={draft.language || 'en_GB'}
                onChange={(e) => patchDraft({ language: e.target.value.trim() })}
                placeholder="en_GB"
                spellCheck={false}
              />
              <p className="text-muted" style={{ marginTop: 4, fontSize: 12 }}>
                Meta locale code — UK WhatsApp accounts usually need <code>en_GB</code>, not <code>en_US</code>.
              </p>

              <label className="field-label">Body</label>
              <textarea
                className="input wa-template-body"
                rows={10}
                value={draft.body}
                onChange={(e) => patchDraft({ body: e.target.value })}
              />

              <div className="wa-var-grid">
                {ensureExampleValues(draft.body, '', draft.example_values).map((value, idx) => (
                  <label key={idx} className="wa-var-field">
                    <span>{varLabels[idx] || `Variable ${idx + 1}`} · {'{{' + (idx + 1) + '}}'}</span>
                    <input
                      className="input"
                      value={value}
                      onChange={(e) => {
                        const next = [...ensureExampleValues(draft.body, '', draft.example_values)]
                        next[idx] = e.target.value
                        patchDraft({ example_values: next })
                      }}
                    />
                  </label>
                ))}
              </div>

              <label className="field-label">Buttons</label>
              <select
                className="input"
                value={draft.button_type}
                onChange={(e) => patchDraft({ button_type: e.target.value, buttons: [emptyButton()] })}
              >
                <option value="none">None</option>
                <option value="quick_reply">Quick reply</option>
                <option value="url">URL button</option>
              </select>
              {draft.button_type !== 'none' ? (
                <div className="wa-button-editor">
                  {(draft.buttons || []).map((btn, idx) => (
                    <div key={idx} className="wa-button-row">
                      <input
                        className="input"
                        placeholder="Button label"
                        value={btn.text || ''}
                        onChange={(e) => {
                          const next = [...draft.buttons]
                          next[idx] = { ...next[idx], text: e.target.value }
                          patchDraft({ buttons: next })
                        }}
                      />
                      {draft.button_type === 'url' ? (
                        <input
                          className="input"
                          placeholder="https://…"
                          value={btn.url || ''}
                          onChange={(e) => {
                            const next = [...draft.buttons]
                            next[idx] = { ...next[idx], url: e.target.value }
                            patchDraft({ buttons: next })
                          }}
                        />
                      ) : null}
                    </div>
                  ))}
                  {draft.button_type === 'quick_reply' && (draft.buttons || []).length < 3 ? (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => patchDraft({ buttons: [...(draft.buttons || []), emptyButton()] })}
                    >
                      Add button
                    </button>
                  ) : null}
                </div>
              ) : null}
            </div>

            <aside className="wa-template-editor-side">
              <div className="wa-status-stack">
                <span className={localStatusPillClass(localStatus)}>{LOCAL_STATUS_LABELS[localStatus] || localStatus}</span>
                <span className={telnyxSyncPillClass(syncStatus)}>{TELNYX_SYNC_LABELS[syncStatus] || syncStatus}</span>
              </div>
              <p className="text-muted text-sm">Last synced: {lastSynced}</p>
              <p className="text-muted text-sm">
                {draft.active_for_interview ? 'Visible to AI Interview' : 'Hidden from AI Interview'}
              </p>
              <div className="wa-phone-preview">
                <p className="wa-phone-preview-title">Preview</p>
                <div className="wa-phone-preview-body">{renderedPreview || 'No body yet'}</div>
                {(draft.buttons || []).filter((b) => b.text).map((b, i) => (
                  <div key={i} className="wa-phone-preview-button">{b.text}</div>
                ))}
              </div>
              {preview?.rendered_body ? (
                <p className="text-muted text-sm">Server preview loaded.</p>
              ) : null}
            </aside>
          </div>
        )}

        <div className="modal-footer">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Close</button>
          <button type="button" className="btn btn-outline" disabled={working} onClick={() => void toggleHidden()}>
            {draft?.active_for_interview ? 'Hide' : 'Show'}
          </button>
          <button type="button" className="btn btn-outline" disabled={working} onClick={() => void saveDraft()}>
            {working === 'save' ? 'Saving…' : 'Save draft'}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!!working}
            onClick={() => void pushToTelnyx()}
          >
            {working === 'push' ? 'Pushing…' : 'Push to Meta'}
          </button>
        </div>
      </div>
    </div>
  )
}
