import React, { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatWaSurveyError } from '../lib/waSurveyFeedback'
import {
  TELNYX_SYNC_LABELS,
  resolveTelnyxSyncLabel,
  telnyxSyncPillClass,
  validateCategoryBeforeSync,
} from '../lib/waSurveyTelnyxSync'
import {
  VAR_LABELS,
  ensureExampleValues,
  previewButtonsFromTemplate,
  substituteTemplateVars,
} from '../lib/waSurveyTemplateVars'
import '../styles/waTemplateGenerator.css'

function buttonTypeLabel(type) {
  const map = {
    quick_reply: 'QUICK_REPLY',
    url: 'URL',
    phone: 'PHONE',
    none: 'NONE',
  }
  return map[type] || type || 'NONE'
}

function emptyButton() {
  return { text: '', url: '', phone_number: '' }
}

function normalizeButtons(tpl) {
  const list = Array.isArray(tpl?.buttons) ? tpl.buttons.map((b) => ({ ...emptyButton(), ...b })) : []
  const type = tpl?.button_type || 'none'
  if (type === 'none') return []
  while (list.length < 1) list.push(emptyButton())
  return list.slice(0, type === 'quick_reply' ? 3 : 1)
}

function WaPackGenPhone({ businessName, body, footer, header, buttons }) {
  return (
    <div className="waTplGen-phone-frame">
      <div className="waTplGen-phone-status">
        <div className="waTplGen-phone-avatar">{String(businessName || 'B').slice(0, 1)}</div>
        <div>
          <div className="waTplGen-phone-contact">{businessName || 'Business'}</div>
          <div className="waTplGen-phone-online">online</div>
        </div>
      </div>
      <div className="waTplGen-phone-body">
        <div className="waTplGen-wa-bubble">
          {header ? <div className="waTplGen-wa-header-txt">{header}</div> : null}
          <div className="waTplGen-wa-body">{body}</div>
          {footer ? <div className="waTplGen-wa-footer">{footer}</div> : null}
          <div className="waTplGen-wa-time">✓✓ 10:42 AM</div>
          {buttons?.length ? (
            <div className="waTplGen-wa-btns">
              {buttons.map((b) => (
                <div key={b.label} className="waTplGen-wa-btn">
                  <i className={`ti ${b.type === 'url' ? 'ti-external-link' : b.type === 'phone' ? 'ti-phone' : 'ti-arrow-back-up'}`} />
                  {b.label}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function WaPackGenEditModal({ open, title, children, onClose, onSave }) {
  if (!open) return null
  return (
    <div
      className={`waTplGen-modal-overlay${open ? ' open' : ''}`}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
      role="dialog"
      aria-modal="true"
    >
      <div className="waTplGen-modal">
        <div className="waTplGen-modal-header">
          <i className="ti ti-pencil" style={{ color: 'var(--wa-green-dark)', fontSize: 14 }} />
          <h3>{title}</h3>
          <button type="button" className="waTplGen-modal-close" onClick={onClose} aria-label="Close">
            <i className="ti ti-x" />
          </button>
        </div>
        <div className="waTplGen-modal-body">{children}</div>
        <div className="waTplGen-modal-footer">
          <button type="button" className="waTplGen-btn-cancel" onClick={onClose}>Cancel</button>
          <button type="button" className="waTplGen-btn-save" onClick={onSave}>
            <i className="ti ti-check" /> Apply Changes
          </button>
        </div>
      </div>
    </div>
  )
}

function WaPackGenCard({
  item,
  saved,
  savedRecord,
  workingKey,
  cardError,
  onOpenEdit,
  onSave,
  onSync,
  onRegenerate,
  onCopyJson,
  onExport,
  onFullPreview,
}) {
  const tpl = item.template
  const isSaving = workingKey === `save-${item.index}`
  const isRegenerating = workingKey === `regen-${item.index}`
  const isSyncing = workingKey === `sync-${item.index}`
  const cardBusy = isSaving || isRegenerating || isSyncing
  const syncLabel = isSyncing
    ? TELNYX_SYNC_LABELS.SYNCING
    : resolveTelnyxSyncLabel(savedRecord || tpl)

  if (!tpl) {
    return (
      <div className="waTplGen-template-card is-invalid" style={{ animationDelay: `${item.index * 55}ms` }}>
        <div className="waTplGen-card-header">
          <div className="waTplGen-card-num">{item.index + 1}</div>
          <div className="waTplGen-card-name">Invalid template</div>
        </div>
        {cardError ? <p className="waTplGen-card-error">{cardError}</p> : null}
        <ul className="waTplGen-card-error">
          {(item.errors || []).map((e) => <li key={e}>{e}</li>)}
        </ul>
        <div className="waTplGen-card-footer">
          <button type="button" className="waTplGen-action-btn waTplGen-btn-regen" disabled={cardBusy} onClick={() => onRegenerate(item)}>
            <i className="ti ti-refresh" /> Regenerate
          </button>
        </div>
      </div>
    )
  }

  const exampleValues = ensureExampleValues(tpl.body, tpl.header, tpl.example_values)
  const liveBody = substituteTemplateVars(tpl.body, exampleValues)
  const liveFooter = substituteTemplateVars(tpl.footer, exampleValues)
  const liveHeader = tpl.header ? substituteTemplateVars(tpl.header, exampleValues) : ''
  const liveBusiness = exampleValues[1] || 'Northgate Dental'
  const previewButtons = previewButtonsFromTemplate(tpl).map((b) => ({
    label: b.label,
    type: tpl.button_type === 'url' ? 'url' : tpl.button_type === 'phone' ? 'phone' : 'quick_reply',
  }))

  return (
    <div
      className={`waTplGen-template-card${saved ? ' is-saved' : ''}${cardBusy ? ' is-busy' : ''}`}
      style={{ animationDelay: `${item.index * 55}ms` }}
    >
      {cardBusy ? <div className="waTplGen-card-busy">{isRegenerating ? 'Regenerating…' : 'Saving…'}</div> : null}

      <div className="waTplGen-card-header">
        <div className="waTplGen-card-num">{item.index + 1}</div>
        <div className="waTplGen-card-name">{tpl.template_name || tpl.title || `template_${item.index + 1}`}</div>
        <span className="waTplGen-card-category">{tpl.step_role || tpl.category || 'MARKETING'}</span>
        <span className={`waTplGen-saved-tag${saved ? ' show' : ''}`}><i className="ti ti-check" /> Saved</span>
        {savedRecord ? (
          <span className={`pill ${telnyxSyncPillClass(syncLabel)}`} style={{ marginLeft: 6, fontSize: 10 }}>
            {syncLabel}
          </span>
        ) : null}
      </div>

      {cardError ? <p className="waTplGen-card-error">{cardError}</p> : null}

      <div className="waTplGen-single-preview">
        <WaPackGenPhone
          businessName={liveBusiness}
          body={liveBody}
          footer={liveFooter}
          header={liveHeader}
          buttons={previewButtons}
        />
        <div className="waTplGen-preview-info">
          {liveHeader ? (
            <div>
              <div className="waTplGen-info-label"><i className="ti ti-heading" style={{ fontSize: 9, marginRight: 3 }} /> Header</div>
              <div className="waTplGen-info-text">{liveHeader}</div>
            </div>
          ) : null}
          <div>
            <div className="waTplGen-info-label"><i className="ti ti-align-left" style={{ fontSize: 9, marginRight: 3 }} /> Body</div>
            <div className="waTplGen-info-text clamp">{liveBody}</div>
          </div>
          {liveFooter ? (
            <div>
              <div className="waTplGen-info-label"><i className="ti ti-minus" style={{ fontSize: 9, marginRight: 3 }} /> Footer</div>
              <div className="waTplGen-info-text" style={{ color: 'var(--wa-muted)', fontSize: 12 }}>{liveFooter}</div>
            </div>
          ) : null}
          {previewButtons.length > 0 ? (
            <div>
              <div className="waTplGen-info-label"><i className="ti ti-click" style={{ fontSize: 9, marginRight: 3 }} /> Buttons</div>
              <div className="waTplGen-vars-list">
                {previewButtons.map((b) => (
                  <span key={b.label} className="waTplGen-btn-chip">
                    {b.label} <span style={{ opacity: 0.6 }}>[{buttonTypeLabel(tpl.button_type)}]</span>
                  </span>
                ))}
              </div>
            </div>
          ) : null}
          <div>
            <div className="waTplGen-info-label"><i className="ti ti-code" style={{ fontSize: 9, marginRight: 3 }} /> Variables</div>
            <div className="waTplGen-vars-list">
              {exampleValues.length ? exampleValues.map((val, i) => (
                <span key={i} className="waTplGen-var-chip">{`{{${i + 1}}} ${val}`}</span>
              )) : <span className="waTplGen-no-vars">No variables</span>}
            </div>
          </div>
        </div>
      </div>

      <div className="waTplGen-edit-tools">
        <div className="waTplGen-tools-label"><i className="ti ti-tools" /> Edit Tools</div>
        <div className="waTplGen-tools-row">
          <button type="button" className="waTplGen-tool-btn" onClick={() => onOpenEdit(item.index, 'header')}><i className="ti ti-heading" /> Header</button>
          <button type="button" className="waTplGen-tool-btn" onClick={() => onOpenEdit(item.index, 'body')}><i className="ti ti-align-left" /> Body</button>
          <button type="button" className="waTplGen-tool-btn" onClick={() => onOpenEdit(item.index, 'footer')}><i className="ti ti-minus" /> Footer</button>
          <button type="button" className="waTplGen-tool-btn" onClick={() => onOpenEdit(item.index, 'buttons')}><i className="ti ti-click" /> Buttons</button>
          <button type="button" className="waTplGen-tool-btn" onClick={() => onOpenEdit(item.index, 'variables')}><i className="ti ti-code" /> Variables</button>
          <button type="button" className="waTplGen-tool-btn" onClick={() => onOpenEdit(item.index, 'name')}><i className="ti ti-tag" /> Name</button>
          <button type="button" className="waTplGen-tool-btn" onClick={() => onCopyJson(item)}><i className="ti ti-copy" /> Copy JSON</button>
          <button type="button" className="waTplGen-tool-btn" onClick={() => onExport(item)}><i className="ti ti-download" /> Export</button>
          <button type="button" className="waTplGen-tool-btn" onClick={() => onFullPreview(item)}><i className="ti ti-arrows-maximize" /> Full Preview</button>
        </div>
      </div>

      <div className="waTplGen-card-footer">
        <button type="button" className="waTplGen-action-btn waTplGen-btn-save-t" disabled={cardBusy || !item.valid} onClick={() => onSave(item)}>
          <i className="ti ti-check" /> {isSaving ? 'Saving…' : 'Save Template'}
        </button>
        {savedRecord?.id ? (
          <button type="button" className="waTplGen-action-btn waTplGen-btn-save-t" disabled={cardBusy} onClick={() => onSync(item)}>
            <i className="ti ti-cloud-upload" /> {isSyncing ? 'Syncing…' : 'Sync to Telnyx'}
          </button>
        ) : null}
        <button type="button" className={`waTplGen-action-btn waTplGen-btn-regen${isRegenerating ? ' loading' : ''}`} disabled={cardBusy} onClick={() => onRegenerate(item)}>
          <i className="ti ti-refresh" /> {isRegenerating ? 'Regenerating…' : 'Regenerate'}
        </button>
      </div>
    </div>
  )
}

export default function WaSurveyTemplatePackModal({ surveyTypeId, surveyTypeName, open, onClose, onSaved }) {
  const [instruction, setInstruction] = useState('')
  const [purpose, setPurpose] = useState('')
  const [categoryHint, setCategoryHint] = useState('MARKETING')
  const [industryHint, setIndustryHint] = useState('healthcare')
  const [privacyMode, setPrivacyMode] = useState('off')
  const [templateCount] = useState(10)
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [pack, setPack] = useState(null)
  const [savedIndices, setSavedIndices] = useState(() => new Set())
  const [savedRecords, setSavedRecords] = useState(() => ({}))
  const [cardErrors, setCardErrors] = useState(() => ({}))
  const [editIndex, setEditIndex] = useState(null)
  const [editField, setEditField] = useState(null)
  const [editDraft, setEditDraft] = useState(null)

  const reset = () => {
    setInstruction('')
    setPurpose('')
    setCategoryHint('MARKETING')
    setIndustryHint('healthcare')
    setPrivacyMode('off')
    setError('')
    setToast('')
    setPack(null)
    setSavedIndices(new Set())
    setSavedRecords({})
    setCardErrors({})
    setEditIndex(null)
    setEditField(null)
    setEditDraft(null)
  }

  useEffect(() => {
    if (!open) reset()
  }, [open])

  useEffect(() => {
    if (!open) return undefined
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [open])

  useEffect(() => {
    if (!toast) return undefined
    const t = setTimeout(() => setToast(''), 2500)
    return () => clearTimeout(t)
  }, [toast])

  const items = useMemo(() => (Array.isArray(pack?.templates) ? pack.templates : []), [pack])

  const buildInstruction = () => {
    const parts = [instruction.trim()]
    if (categoryHint) parts.push(`Template category focus: ${categoryHint}`)
    if (industryHint) parts.push(`Industry context: ${industryHint}`)
    return parts.filter(Boolean).join('\n')
  }

  const showToast = (text) => setToast(text)

  const siblingContext = (excludeIndex) =>
    items
      .filter((i) => i.index !== excludeIndex && i.template)
      .map((i) => ({
        template_name: i.template.template_name,
        purpose: i.template.purpose,
        body: i.template.body,
      }))

  const seenNames = (excludeIndex) =>
    items
      .filter((i) => i.index !== excludeIndex && i.template?.template_name)
      .map((i) => i.template.template_name)

  const packPayloadMeta = () => ({
    privacy_mode: privacyMode,
    theme_variant: [categoryHint, industryHint].filter(Boolean).join(' · '),
    purpose,
    instruction: buildInstruction(),
  })

  const generatePack = async () => {
    setWorking('generate')
    setError('')
    setCardErrors({})
    try {
      const data = await apiFetch(`/admin/wa-survey/types/${encodeURIComponent(surveyTypeId)}/templates/generate-pack`, {
        method: 'POST',
        body: JSON.stringify({
          instruction: buildInstruction(),
          purpose,
          privacy_mode: privacyMode,
          template_count: templateCount,
          theme_variant: [categoryHint, industryHint].filter(Boolean).join(' · '),
        }),
      })
      const stamped = {
        ...data,
        templates: Array.isArray(data.templates)
          ? data.templates.map((row) => (
            row.template
              ? { ...row, template: { ...row.template, category: row.template.category || categoryHint } }
              : row
          ))
          : data.templates,
      }
      setPack(stamped)
      setSavedIndices(new Set())
      setSavedRecords({})
      showToast(formatActionSuccess(data, `Generated ${data.valid_count || 0} templates`).message)
    } catch (e) {
      setError(formatWaSurveyError(e, 'OpenAI template generation failed').message)
    } finally {
      setWorking('')
    }
  }

  const mergeItem = (updatedItem) => {
    setPack((prev) => {
      if (!prev?.templates) return prev
      const templates = prev.templates.map((row) => (row.index === updatedItem.index ? updatedItem : row))
      const valid_count = templates.filter((r) => r.valid && r.template).length
      return { ...prev, templates, valid_count, invalid_count: templates.length - valid_count }
    })
  }

  const editTemplate = (index, patch) => {
    setPack((prev) => {
      if (!prev?.templates) return prev
      return {
        ...prev,
        templates: prev.templates.map((row) => {
          if (row.index !== index || !row.template) return row
          const next = { ...row.template, ...patch }
          if (patch.body !== undefined || patch.header !== undefined) {
            next.example_values = ensureExampleValues(next.body, next.header, next.example_values)
          }
          return { ...row, template: next }
        }),
      }
    })
  }

  const openEdit = (index, field) => {
    const row = items.find((i) => i.index === index)
    if (!row?.template) return
    const tpl = row.template
    setEditIndex(index)
    setEditField(field)
    if (field === 'header') {
      setEditDraft({ header: tpl.header || '' })
    } else if (field === 'body') {
      setEditDraft({ body: tpl.body || '' })
    } else if (field === 'footer') {
      setEditDraft({ footer: tpl.footer || '' })
    } else if (field === 'variables') {
      setEditDraft({ values: ensureExampleValues(tpl.body, tpl.header, tpl.example_values) })
    } else if (field === 'name') {
      setEditDraft({
        template_name: tpl.template_name || '',
        title: tpl.title || '',
        category: tpl.category || 'MARKETING',
      })
    } else if (field === 'buttons') {
      const bt = tpl.button_type || 'none'
      const defs = normalizeButtons(tpl)
      const slots = [0, 1, 2].map((i) => defs[i] || emptyButton())
      setEditDraft({
        button_type: bt,
        slots: slots.map((b) => ({
          text: b.text || '',
          url: b.url || '',
          phone_number: b.phone_number || '',
        })),
      })
    }
  }

  const closeEdit = () => {
    setEditIndex(null)
    setEditField(null)
    setEditDraft(null)
  }

  const applyEdit = () => {
    if (editIndex == null || !editDraft) return
    if (editField === 'header') {
      editTemplate(editIndex, { header: editDraft.header })
    } else if (editField === 'body') {
      editTemplate(editIndex, { body: editDraft.body })
    } else if (editField === 'footer') {
      editTemplate(editIndex, { footer: editDraft.footer })
    } else if (editField === 'variables') {
      setPack((prev) => {
        if (!prev?.templates) return prev
        return {
          ...prev,
          templates: prev.templates.map((row) => {
            if (row.index !== editIndex || !row.template) return row
            return { ...row, template: { ...row.template, example_values: [...editDraft.values] } }
          }),
        }
      })
    } else if (editField === 'name') {
      editTemplate(editIndex, {
        template_name: editDraft.template_name,
        title: editDraft.title || editDraft.template_name,
        category: editDraft.category,
      })
    } else if (editField === 'buttons') {
      const bt = editDraft.button_type || 'none'
      const buttons = bt === 'none'
        ? []
        : editDraft.slots
          .map((b) => ({ text: b.text || '', url: b.url || '', phone_number: b.phone_number || '' }))
          .filter((b, i) => bt === 'quick_reply' ? b.text.trim() : i === 0 && b.text.trim())
      editTemplate(editIndex, { button_type: bt, buttons })
    }
    closeEdit()
    showToast('Changes applied!')
  }

  const saveOne = async (item) => {
    if (!item?.template) return
    const payload = {
      ...item.template,
      privacy_mode: privacyMode,
      example_values: ensureExampleValues(item.template.body, item.template.header, item.template.example_values),
    }
    setWorking(`save-${item.index}`)
    setCardErrors((prev) => ({ ...prev, [item.index]: '' }))
    setError('')
    try {
      const data = await apiFetch(`/admin/wa-survey/types/${encodeURIComponent(surveyTypeId)}/templates/save-pack`, {
        method: 'POST',
        body: JSON.stringify({ templates: [payload], ...packPayloadMeta() }),
      })
      const savedRow = data.templates?.[0]
      setSavedIndices((prev) => new Set(prev).add(item.index))
      if (savedRow?.id) {
        setSavedRecords((prev) => ({ ...prev, [item.index]: savedRow }))
      }
      showToast('Template saved')
      onSaved?.()
    } catch (e) {
      const err = formatWaSurveyError(e, 'Could not save template').message
      setCardErrors((prev) => ({ ...prev, [item.index]: err }))
    } finally {
      setWorking('')
    }
  }

  const syncOne = async (item) => {
    const record = savedRecords[item.index]
    const category = item.template?.category || categoryHint
    const categoryError = validateCategoryBeforeSync(category)
    if (!record?.id) {
      setCardErrors((prev) => ({ ...prev, [item.index]: 'Save the template locally before syncing to Telnyx.' }))
      return
    }
    if (categoryError) {
      setCardErrors((prev) => ({ ...prev, [item.index]: categoryError }))
      return
    }
    setWorking(`sync-${item.index}`)
    setCardErrors((prev) => ({ ...prev, [item.index]: '' }))
    try {
      if (category !== record.category) {
        await apiFetch(`/admin/wa-survey/templates/${record.id}`, {
          method: 'PUT',
          body: JSON.stringify({ category }),
        })
      }
      const data = await apiFetch(`/admin/wa-survey/templates/${record.id}/push`, { method: 'POST', body: '{}' })
      setSavedRecords((prev) => ({ ...prev, [item.index]: data.template || record }))
      showToast(data.sync_message || data.message || TELNYX_SYNC_LABELS.SYNCED)
      onSaved?.()
    } catch (e) {
      const err = formatWaSurveyError(e, TELNYX_SYNC_LABELS.FAILED).message
      setCardErrors((prev) => ({ ...prev, [item.index]: err }))
      showToast(TELNYX_SYNC_LABELS.FAILED)
    } finally {
      setWorking('')
    }
  }

  const regenerateOne = async (item) => {
    setWorking(`regen-${item.index}`)
    setCardErrors((prev) => ({ ...prev, [item.index]: '' }))
    setError('')
    try {
      const data = await apiFetch(`/admin/wa-survey/types/${encodeURIComponent(surveyTypeId)}/templates/regenerate-pack-item`, {
        method: 'POST',
        body: JSON.stringify({
          index: item.index,
          instruction: buildInstruction(),
          purpose: item.template?.purpose || purpose,
          privacy_mode: privacyMode,
          slot_hint: item.template?.step_role || item.template?.purpose || '',
          current_template: item.template || null,
          sibling_summaries: siblingContext(item.index),
          seen_names: seenNames(item.index),
        }),
      })
      mergeItem(data.item)
      setSavedIndices((prev) => {
        const next = new Set(prev)
        next.delete(item.index)
        return next
      })
      setSavedRecords((prev) => {
        const next = { ...prev }
        delete next[item.index]
        return next
      })
      showToast(formatActionSuccess(data, `Template ${item.index + 1} regenerated`).message)
    } catch (e) {
      const err = formatWaSurveyError(e, 'Regenerate failed').message
      setCardErrors((prev) => ({ ...prev, [item.index]: err }))
    } finally {
      setWorking('')
    }
  }

  const saveAllValid = async () => {
    setWorking('save-all')
    setError('')
    try {
      const templates = items.filter((i) => i.template && i.valid).map((i) => ({
        ...i.template,
        privacy_mode: privacyMode,
        example_values: ensureExampleValues(i.template.body, i.template.header, i.template.example_values),
      }))
      const data = await apiFetch(`/admin/wa-survey/types/${encodeURIComponent(surveyTypeId)}/templates/save-pack`, {
        method: 'POST',
        body: JSON.stringify({ templates, ...packPayloadMeta() }),
      })
      setSavedIndices(new Set(items.filter((i) => i.template && i.valid).map((i) => i.index)))
      const nextRecords = {}
      ;(data.templates || []).forEach((row, idx) => {
        const source = items.filter((i) => i.template && i.valid)[idx]
        if (source && row?.id) nextRecords[source.index] = row
      })
      setSavedRecords(nextRecords)
      showToast('Template saved')
      onSaved?.()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not save templates').message)
    } finally {
      setWorking('')
    }
  }

  const copyJson = (item) => {
    if (!item?.template) return
    navigator.clipboard.writeText(JSON.stringify(item.template, null, 2))
      .then(() => showToast('JSON copied!'))
      .catch(() => showToast('Copy failed'))
  }

  const exportJson = (item) => {
    if (!item?.template) return
    const t = item.template
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([JSON.stringify(t, null, 2)], { type: 'application/json' }))
    a.download = `${t.template_name || 'template'}.json`
    a.click()
    showToast('Exported!')
  }

  const fullPreview = (item) => {
    const tpl = item?.template
    if (!tpl) return
    const vals = ensureExampleValues(tpl.body, tpl.header, tpl.example_values)
    const body = substituteTemplateVars(tpl.body, vals)
    const footer = substituteTemplateVars(tpl.footer, vals)
    const header = tpl.header ? substituteTemplateVars(tpl.header, vals) : ''
    const btns = previewButtonsFromTemplate(tpl)
    const w = window.open('', '_blank', 'width=400,height=700')
    if (!w) return
    w.document.write(`<!DOCTYPE html><html><head><title>${tpl.template_name || 'preview'}</title>
<style>body{margin:0;background:#e5ddd5;font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;}
.bubble{background:#fff;border-radius:0 14px 14px 14px;padding:12px 14px;max-width:300px;box-shadow:0 2px 6px rgba(0,0,0,.12);}
.hdr{font-weight:700;font-size:14px;margin-bottom:6px;font-family:sans-serif;}
.bdy{font-size:13px;color:#333;line-height:1.6;margin-bottom:5px;white-space:pre-wrap;}
.ftr{font-size:11px;color:#999;margin-bottom:5px;}
.time{font-size:10px;color:#aaa;text-align:right;}
.btns{margin-top:8px;display:flex;flex-direction:column;gap:5px;}
.btn{border:0.5px solid #ddd;border-radius:8px;padding:8px;text-align:center;font-size:12px;font-weight:600;color:#128C7E;background:#fff;}
</style></head><body><div class="bubble">
${header ? `<div class="hdr">${header.replace(/</g, '&lt;')}</div>` : ''}
<div class="bdy">${body.replace(/</g, '&lt;')}</div>
${footer ? `<div class="ftr">${footer.replace(/</g, '&lt;')}</div>` : ''}
<div class="time">✓✓ 10:42 AM</div>
<div class="btns">${btns.map((b) => `<div class="btn">${b.label.replace(/</g, '&lt;')}</div>`).join('')}</div>
</div></body></html>`)
  }

  const editTitles = {
    header: 'Edit Header',
    body: 'Edit Body',
    footer: 'Edit Footer',
    buttons: 'Edit Buttons',
    variables: 'Edit Variables',
    name: 'Edit Name & Category',
  }

  if (!open) return null

  return (
    <div className="waTplGen-overlay" role="dialog" aria-modal="true">
      <div className="waTplGen-shell">
        <header className="waTplGen-header">
          <div className="logo"><i className="ti ti-brand-whatsapp" /></div>
          <h1>WA Template <span>Generator</span></h1>
          <span className="badge">⚡ AI Powered</span>
          <div className="waTplGen-header-actions">
            <button type="button" className="waTplGen-close" onClick={onClose}>Close</button>
          </div>
        </header>

        <div className="waTplGen-main">
          <div className="waTplGen-input-panel">
            <div className="waTplGen-panel-title"><i className="ti ti-adjustments" /> Configuration</div>
            <div className="waTplGen-field-row">
              <div className="waTplGen-field">
                <label>Purpose / Use Case</label>
                <input
                  type="text"
                  value={purpose}
                  onChange={(e) => setPurpose(e.target.value)}
                  placeholder="e.g. Post-visit feedback, appointment reminder…"
                />
              </div>
              <div className="waTplGen-field">
                <label>Survey type (service type)</label>
                <input type="text" value={surveyTypeName} readOnly />
              </div>
              <div className="waTplGen-field">
                <label>Template count</label>
                <input type="text" value={String(templateCount)} readOnly />
              </div>
              <div className="waTplGen-field">
                <label>Privacy Mode</label>
                <select value={privacyMode} onChange={(e) => setPrivacyMode(e.target.value)} disabled={Boolean(pack)}>
                  <option value="off">Off — identified / normal</option>
                  <option value="on">On — anonymous survey</option>
                </select>
              </div>
              <div className="waTplGen-field">
                <label>Theme / variant</label>
                <input type="text" value={[categoryHint, industryHint].filter(Boolean).join(' · ')} readOnly />
              </div>
              <div className="waTplGen-field">
                <label>Template Category</label>
                <select value={categoryHint} onChange={(e) => setCategoryHint(e.target.value)}>
                  <option value="MARKETING">Marketing</option>
                  <option value="UTILITY">Utility</option>
                  <option value="AUTHENTICATION">Authentication</option>
                </select>
              </div>
              <div className="waTplGen-field">
                <label>Industry (hint)</label>
                <select value={industryHint} onChange={(e) => setIndustryHint(e.target.value)}>
                  <option value="healthcare">Healthcare / Medical</option>
                  <option value="ecommerce">E-commerce / Retail</option>
                  <option value="finance">Finance / Banking</option>
                  <option value="hospitality">Hospitality / Travel</option>
                  <option value="education">Education</option>
                  <option value="saas">SaaS / Tech</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div className="waTplGen-field waTplGen-field-full">
                <label>Admin Instructions (extra context, do&apos;s/don&apos;ts, brand voice…)</label>
                <textarea
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  placeholder="e.g. Always include a discount code. Keep messages under 160 chars. Use warm but professional tone…"
                />
              </div>
            </div>
            <div className="waTplGen-actions-row">
              <button
                type="button"
                className={`waTplGen-generate-btn${working === 'generate' ? ' loading' : ''}`}
                disabled={working === 'generate'}
                onClick={generatePack}
              >
                <div className="spinner" />
                <span className="btn-text"><i className="ti ti-wand" /> {working === 'generate' ? 'Generating…' : 'Generate 10 Templates'}</span>
              </button>
              {pack ? (
                <button type="button" className="waTplGen-secondary-btn" disabled={working === 'save-all'} onClick={saveAllValid}>
                  {working === 'save-all' ? 'Saving all…' : 'Save all valid'}
                </button>
              ) : null}
            </div>
          </div>

          {error ? <div className="waTplGen-alert error">{error}</div> : null}

          {items.length > 0 ? (
            <div>
              <div className="waTplGen-section-hdr">
                <h2>Generated Templates</h2>
                <span className="waTplGen-count-badge">{items.length} templates</span>
              </div>
              <p className="waTplGen-subtitle">{surveyTypeName} · OpenAI step bank · edit with tools below each card</p>
              <div className="waTplGen-templates-grid">
                {items.map((item) => (
                  <WaPackGenCard
                    key={item.index}
                    item={item}
                    saved={savedIndices.has(item.index)}
                    savedRecord={savedRecords[item.index]}
                    workingKey={working}
                    cardError={cardErrors[item.index]}
                    onOpenEdit={openEdit}
                    onSave={saveOne}
                    onSync={syncOne}
                    onRegenerate={regenerateOne}
                    onCopyJson={copyJson}
                    onExport={exportJson}
                    onFullPreview={fullPreview}
                  />
                ))}
              </div>
            </div>
          ) : (
            <div className="waTplGen-empty">
              <p>Configure purpose and instructions above, then generate 10 WhatsApp survey templates.</p>
            </div>
          )}
        </div>
      </div>

      <WaPackGenEditModal
        open={editIndex != null && editDraft != null}
        title={editTitles[editField] || 'Edit'}
        onClose={closeEdit}
        onSave={applyEdit}
      >
        {editField === 'header' && editDraft ? (
          <div className="waTplGen-modal-field">
            <label>Header Text (max 60 chars)</label>
            <input
              maxLength={60}
              value={editDraft.header}
              onChange={(e) => setEditDraft({ ...editDraft, header: e.target.value })}
            />
          </div>
        ) : null}
        {editField === 'body' && editDraft ? (
          <>
            <div className="waTplGen-modal-field">
              <label>Body — use {'{{1}}'}, {'{{2}}'} for variables</label>
              <textarea
                rows={7}
                maxLength={1024}
                value={editDraft.body}
                onChange={(e) => setEditDraft({ ...editDraft, body: e.target.value })}
              />
            </div>
            <p style={{ fontSize: 11, color: 'var(--wa-muted)', marginTop: -6 }}>
              Characters: {(editDraft.body || '').length}/1024
            </p>
          </>
        ) : null}
        {editField === 'footer' && editDraft ? (
          <div className="waTplGen-modal-field">
            <label>Footer Text (max 60 chars)</label>
            <input
              maxLength={60}
              value={editDraft.footer}
              onChange={(e) => setEditDraft({ ...editDraft, footer: e.target.value })}
            />
          </div>
        ) : null}
        {editField === 'variables' && editDraft ? (
          <>
            {editDraft.values.map((val, i) => (
              <div key={i} className="waTplGen-modal-field">
                <label>{`{{${i + 1}}} — ${VAR_LABELS[i] || 'Variable'}`}</label>
                <input
                  value={val}
                  onChange={(e) => {
                    const values = [...editDraft.values]
                    values[i] = e.target.value
                    setEditDraft({ ...editDraft, values })
                  }}
                />
              </div>
            ))}
            <p style={{ fontSize: 11, color: 'var(--wa-muted)' }}>Example values used in live preview</p>
          </>
        ) : null}
        {editField === 'name' && editDraft ? (
          <>
            <div className="waTplGen-modal-field">
              <label>Template Name (snake_case)</label>
              <input
                value={editDraft.template_name}
                onChange={(e) => setEditDraft({ ...editDraft, template_name: e.target.value })}
              />
            </div>
            <div className="waTplGen-modal-field">
              <label>Display title</label>
              <input
                value={editDraft.title}
                onChange={(e) => setEditDraft({ ...editDraft, title: e.target.value })}
              />
            </div>
            <div className="waTplGen-modal-field">
              <label>Category</label>
              <select
                value={editDraft.category}
                onChange={(e) => setEditDraft({ ...editDraft, category: e.target.value })}
              >
                {['MARKETING', 'UTILITY', 'AUTHENTICATION'].map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </>
        ) : null}
        {editField === 'buttons' && editDraft ? (
          <>
            <div className="waTplGen-modal-field">
              <label>Button type</label>
              <select
                value={editDraft.button_type}
                onChange={(e) => setEditDraft({ ...editDraft, button_type: e.target.value })}
              >
                <option value="none">Plain text (no buttons)</option>
                <option value="quick_reply">Quick reply (up to 3)</option>
                <option value="url">URL button</option>
                <option value="phone">Phone button</option>
              </select>
            </div>
            {editDraft.button_type !== 'none' ? [0, 1, 2].map((i) => {
              if (editDraft.button_type !== 'quick_reply' && i > 0) return null
              const slot = editDraft.slots[i] || emptyButton()
              return (
                <div key={i} className="waTplGen-modal-btn-block">
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--wa-muted)', marginBottom: 8 }}>Button {i + 1}</div>
                  <div className="waTplGen-modal-field">
                    <label>Button Text</label>
                    <input
                      maxLength={25}
                      value={slot.text}
                      onChange={(e) => {
                        const slots = [...editDraft.slots]
                        slots[i] = { ...slots[i], text: e.target.value }
                        setEditDraft({ ...editDraft, slots })
                      }}
                    />
                  </div>
                  {editDraft.button_type === 'url' ? (
                    <div className="waTplGen-modal-field">
                      <label>URL</label>
                      <input
                        value={slot.url}
                        onChange={(e) => {
                          const slots = [...editDraft.slots]
                          slots[i] = { ...slots[i], url: e.target.value }
                          setEditDraft({ ...editDraft, slots })
                        }}
                      />
                    </div>
                  ) : null}
                  {editDraft.button_type === 'phone' ? (
                    <div className="waTplGen-modal-field">
                      <label>Phone number</label>
                      <input
                        value={slot.phone_number}
                        onChange={(e) => {
                          const slots = [...editDraft.slots]
                          slots[i] = { ...slots[i], phone_number: e.target.value }
                          setEditDraft({ ...editDraft, slots })
                        }}
                      />
                    </div>
                  ) : null}
                </div>
              )
            }) : null}
          </>
        ) : null}
      </WaPackGenEditModal>

      <div className={`waTplGen-toast${toast ? ' show' : ''}`}>
        <i className="ti ti-circle-check" /> <span>{toast}</span>
      </div>
    </div>
  )
}
