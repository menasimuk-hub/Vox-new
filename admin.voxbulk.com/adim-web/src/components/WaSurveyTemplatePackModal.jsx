import React, { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatWaSurveyError } from '../lib/waSurveyFeedback'
import WaSurveyPhonePreview from './WaSurveyPhonePreview'

const PAGE_SIZE = 2

function buttonTypeLabel(type) {
  const map = {
    quick_reply: 'Quick reply',
    url: 'URL button',
    phone: 'Phone CTA',
    none: 'Plain text',
  }
  return map[type] || type || 'Plain text'
}

function formatButtons(tpl) {
  const preview = tpl?.preview || {}
  const raw = preview.buttons || tpl?.buttons_preview || []
  if (Array.isArray(raw) && raw.length) {
    return raw.map((b, i) => ({
      key: `${b.label || b.text || i}`,
      label: b.label || b.text || 'Button',
      url: b.url || '',
      phone: b.phone_number || '',
      type: b.type || tpl?.button_type,
    }))
  }
  const bt = tpl?.button_type
  const defs = Array.isArray(tpl?.buttons) ? tpl.buttons : []
  if (bt === 'none' || !defs.length) return []
  return defs.map((b, i) => ({
    key: `${b.text || i}`,
    label: b.text || 'Button',
    url: b.url || '',
    phone: b.phone_number || '',
    type: bt,
  }))
}

function PackTemplateGalleryCard({
  item,
  editing,
  saved,
  workingKey,
  cardError,
  onToggleEdit,
  onEdit,
  onSave,
  onRegenerate,
}) {
  const tpl = item.template
  const preview = tpl?.preview || {}
  const buttons = formatButtons(tpl)
  const isSaving = workingKey === `save-${item.index}`
  const isRegenerating = workingKey === `regen-${item.index}`
  const cardBusy = isSaving || isRegenerating

  if (!tpl) {
    return (
      <article className="waSurveyPackGalleryCard waSurveyPackGalleryCardInvalid">
        <header className="waSurveyPackGalleryHead">
          <div>
            <span className="waSurveyPackSlotLabel">Template {item.index + 1}</span>
            <h4>Invalid draft</h4>
          </div>
        </header>
        {cardError ? <div className="alert error waSurveyPackCardAlert">{cardError}</div> : null}
        <ul className="waSurveyPackErrorList">
          {(item.errors || []).map((e) => <li key={e}>{e}</li>)}
        </ul>
        <footer className="waSurveyPackGalleryActions">
          <button type="button" className="btn" disabled={cardBusy} onClick={() => onRegenerate(item)}>
            {isRegenerating ? 'Regenerating this template…' : 'Regenerate this template'}
          </button>
        </footer>
      </article>
    )
  }

  return (
    <article className={`waSurveyPackGalleryCard${saved ? ' is-saved' : ''}${cardBusy ? ' is-busy' : ''}`}>
      {cardBusy ? <div className="waSurveyPackGalleryBusy">{isRegenerating ? 'Regenerating…' : 'Saving…'}</div> : null}

      <header className="waSurveyPackGalleryHead">
        <div>
          <span className="waSurveyPackSlotLabel">Template {item.index + 1}</span>
          <h4>{tpl.title || tpl.template_name}</h4>
          <div className="waSurveyPackBadgeRow">
            <span className="waSurveyPackBadge">{tpl.variant_type}</span>
            <span className="waSurveyPackBadge">{tpl.purpose}</span>
            <span className="waSurveyPackBadge is-accent">{buttonTypeLabel(tpl.button_type)}</span>
          </div>
        </div>
        {saved ? <span className="waSurveyPackSavedBadge">Saved as draft</span> : null}
      </header>

      {cardError ? <div className="alert error waSurveyPackCardAlert">{cardError}</div> : null}
      {item.errors?.length ? (
        <ul className="waSurveyPackErrorList">
          {item.errors.map((e) => <li key={e}>{e}</li>)}
        </ul>
      ) : null}

      <div className="waSurveyPackGalleryBody">
        <div className="waSurveyPackGalleryPhone">
          <WaSurveyPhonePreview
            businessName={tpl.example_values?.[1] || 'Northgate Dental'}
            renderedBody={preview.rendered_body || tpl.body}
            footer={preview.footer || tpl.footer}
            buttons={preview.buttons || tpl.buttons_preview || []}
            templateName={tpl.telnyx_name}
            approvalStatus="LOCAL_DRAFT"
          />
        </div>

        <div className="waSurveyPackGalleryMeta">
          <div className="waSurveyPackMetaBlock">
            <span className="label">Body</span>
            {editing ? (
              <textarea className="input msgFieldEditorBox" rows={6} value={tpl.body} onChange={(e) => onEdit(item.index, { body: e.target.value })} />
            ) : (
              <p className="waSurveyPackCopy">{tpl.body}</p>
            )}
          </div>

          <div className="waSurveyPackMetaBlock">
            <span className="label">Footer</span>
            {editing ? (
              <input className="input" value={tpl.footer} onChange={(e) => onEdit(item.index, { footer: e.target.value })} />
            ) : (
              <p className="waSurveyPackCopy waSurveyPackCopyFooter">{tpl.footer}</p>
            )}
          </div>

          <div className="waSurveyPackMetaBlock">
            <span className="label">Variables</span>
            <div className="waSurveyPackChipRow">
              {(tpl.example_values || []).map((val, i) => (
                <span key={i} className="waSurveyPackVarChip">{`{{${i + 1}}} → ${val}`}</span>
              ))}
            </div>
          </div>

          <div className="waSurveyPackMetaBlock">
            <span className="label">Buttons / CTA</span>
            {buttons.length ? (
              <ul className="waSurveyPackButtonList">
                {buttons.map((b) => (
                  <li key={b.key}>
                    <strong>{b.label}</strong>
                    {b.url ? <span className="fieldHint">{b.url}</span> : null}
                    {b.phone ? <span className="fieldHint">{b.phone}</span> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">No buttons — plain text message</p>
            )}
          </div>

          <p className="fieldHint waSurveyPackTelnyxName">Telnyx: {tpl.telnyx_name}</p>
        </div>
      </div>

      <footer className="waSurveyPackGalleryActions">
        <button type="button" className="btn primary" disabled={cardBusy || !item.valid} onClick={() => onSave(item)}>
          {isSaving ? 'Saving draft…' : 'Save this template'}
        </button>
        <button type="button" className="btn" disabled={cardBusy} onClick={() => onRegenerate(item)}>
          {isRegenerating ? 'Regenerating…' : 'Regenerate this template'}
        </button>
        <button type="button" className="btn ghost" disabled={cardBusy} onClick={() => onToggleEdit(item.index)}>
          {editing ? 'Done editing' : 'Edit body/footer'}
        </button>
      </footer>
    </article>
  )
}

export default function WaSurveyTemplatePackModal({ surveyTypeId, surveyTypeName, open, onClose, onSaved }) {
  const [instruction, setInstruction] = useState('')
  const [purpose, setPurpose] = useState('')
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [pack, setPack] = useState(null)
  const [page, setPage] = useState(0)
  const [editing, setEditing] = useState(() => new Set())
  const [savedIndices, setSavedIndices] = useState(() => new Set())
  const [cardErrors, setCardErrors] = useState(() => ({}))

  const reset = () => {
    setInstruction('')
    setPurpose('')
    setError('')
    setMsg('')
    setPack(null)
    setPage(0)
    setEditing(new Set())
    setSavedIndices(new Set())
    setCardErrors({})
  }

  useEffect(() => {
    if (!open) reset()
  }, [open])

  const items = useMemo(() => (Array.isArray(pack?.templates) ? pack.templates : []), [pack])
  const totalPages = Math.max(1, Math.ceil(items.length / PAGE_SIZE))
  const pageItems = useMemo(
    () => items.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE),
    [items, page],
  )

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

  const generatePack = async () => {
    setWorking('generate')
    setError('')
    setMsg('')
    setCardErrors({})
    try {
      const data = await apiFetch(`/admin/wa-survey/types/${encodeURIComponent(surveyTypeId)}/templates/generate-pack`, {
        method: 'POST',
        body: JSON.stringify({ instruction, purpose }),
      })
      setPack(data)
      setPage(0)
      setEditing(new Set())
      setSavedIndices(new Set())
      setMsg(formatActionSuccess(data, `Generated ${data.valid_count || 0} valid template(s) with OpenAI`).message)
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
          return { ...row, template: { ...row.template, ...patch } }
        }),
      }
    })
  }

  const toggleEdit = (index) => {
    setEditing((prev) => {
      const next = new Set(prev)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }

  const saveOne = async (item) => {
    if (!item?.template) return
    setWorking(`save-${item.index}`)
    setCardErrors((prev) => ({ ...prev, [item.index]: '' }))
    setError('')
    try {
      const data = await apiFetch(`/admin/wa-survey/types/${encodeURIComponent(surveyTypeId)}/templates/save-pack`, {
        method: 'POST',
        body: JSON.stringify({ templates: [item.template] }),
      })
      setSavedIndices((prev) => new Set(prev).add(item.index))
      setMsg(formatActionSuccess(data, `Saved “${item.template.title || item.template.template_name}” as local draft`).message)
      onSaved?.()
    } catch (e) {
      const err = formatWaSurveyError(e, 'Could not save template').message
      setCardErrors((prev) => ({ ...prev, [item.index]: err }))
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
          instruction,
          purpose: item.template?.purpose || purpose,
          slot_hint: item.template?.purpose || '',
          current_template: item.template || null,
          sibling_summaries: siblingContext(item.index),
          seen_names: seenNames(item.index),
        }),
      })
      mergeItem(data.item)
      setEditing((prev) => {
        const next = new Set(prev)
        next.delete(item.index)
        return next
      })
      setSavedIndices((prev) => {
        const next = new Set(prev)
        next.delete(item.index)
        return next
      })
      setMsg(formatActionSuccess(data, `Regenerated template ${item.index + 1} only — other templates unchanged`).message)
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
      const templates = items.filter((i) => i.template && i.valid).map((i) => i.template)
      const data = await apiFetch(`/admin/wa-survey/types/${encodeURIComponent(surveyTypeId)}/templates/save-pack`, {
        method: 'POST',
        body: JSON.stringify({ templates }),
      })
      setSavedIndices(new Set(items.filter((i) => i.template && i.valid).map((i) => i.index)))
      setMsg(formatActionSuccess(data, `Saved ${data.saved_count} draft template(s)`).message)
      onSaved?.()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not save templates').message)
    } finally {
      setWorking('')
    }
  }

  if (!open) return null

  return (
    <div className="waSurveyPackBackdrop" role="dialog" aria-modal="true">
      <div className="waSurveyPackShell">
        <header className="waSurveyPackTopBar">
          <div className="waSurveyPackTopBarMain">
            <h2>Generate 10 Templates with OpenAI</h2>
            <p className="muted">{surveyTypeName} — full-width template gallery · 2 per page · save or regenerate individually</p>
          </div>
          <div className="waSurveyPackTopBarActions">
            {items.length ? (
              <div className="waSurveyPackPager">
                <button type="button" className="btn sm ghost" disabled={page <= 0} onClick={() => setPage((p) => p - 1)}>
                  Previous
                </button>
                <span className="waSurveyPackPagerLabel">{page + 1} / {totalPages}</span>
                <button type="button" className="btn sm ghost" disabled={page >= totalPages - 1} onClick={() => setPage((p) => p + 1)}>
                  Next
                </button>
              </div>
            ) : null}
            <button type="button" className="btn ghost" onClick={onClose}>Close</button>
          </div>
        </header>

        {error ? <div className="alert error waSurveyPackGlobalAlert"><strong>{error}</strong></div> : null}
        {msg ? <div className="alert ok waSurveyPackGlobalAlert"><strong>{msg}</strong></div> : null}

        <div className="waSurveyPackToolbar">
          <label className="waSurveyPackToolbarField">
            <span className="label">Purpose</span>
            <input className="input" value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder="Post-visit feedback, reminders…" />
          </label>
          <label className="waSurveyPackToolbarField waSurveyPackToolbarFieldGrow">
            <span className="label">Admin instruction</span>
            <input className="input" value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder="Tone, emoji level, CTA style…" />
          </label>
          <div className="waSurveyPackToolbarButtons">
            <button type="button" className="btn primary" onClick={generatePack} disabled={working === 'generate'}>
              {working === 'generate' ? 'Generating pack…' : 'Generate 10 templates'}
            </button>
            {pack ? (
              <button type="button" className="btn" onClick={saveAllValid} disabled={working === 'save-all'}>
                {working === 'save-all' ? 'Saving all…' : 'Save all valid'}
              </button>
            ) : null}
          </div>
          {pack?.openai ? (
            <span className="fieldHint waSurveyPackModelHint">Model: {pack.openai.model}</span>
          ) : null}
        </div>

        <div className="waSurveyPackScroll">
          {items.length ? (
            <>
              <div className="waSurveyPackGalleryHeader">
                <h3>Template gallery</h3>
                <span className="muted">{pack.valid_count} valid · {pack.generated_count} generated</span>
              </div>
              <div className="waSurveyPackGallery">
                {pageItems.map((item) => (
                  <PackTemplateGalleryCard
                    key={item.index}
                    item={item}
                    editing={editing.has(item.index)}
                    saved={savedIndices.has(item.index)}
                    workingKey={working}
                    cardError={cardErrors[item.index]}
                    onToggleEdit={toggleEdit}
                    onEdit={editTemplate}
                    onSave={saveOne}
                    onRegenerate={regenerateOne}
                  />
                ))}
              </div>
            </>
          ) : (
            <div className="waSurveyPackEmpty">
              <p>Generate a 10-template pack to open the gallery. Each template gets its own WhatsApp preview, Save, and Regenerate controls.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
