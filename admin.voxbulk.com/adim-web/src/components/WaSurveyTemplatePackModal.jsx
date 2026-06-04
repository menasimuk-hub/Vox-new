import React, { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatWaSurveyError } from '../lib/waSurveyFeedback'
import {
  VAR_LABELS,
  ensureExampleValues,
  previewButtonsFromTemplate,
  substituteTemplateVars,
} from '../lib/waSurveyTemplateVars'
import WaSurveyPhonePreview from './WaSurveyPhonePreview'

const PAGE_SIZE = 1

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
  return previewButtonsFromTemplate(tpl).map((b, i) => ({
    key: `${b.label}-${i}`,
    label: b.label,
    url: b.url,
    phone: b.phone_number,
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
  onEditVariable,
  onSave,
  onRegenerate,
}) {
  const tpl = item.template
  const buttons = formatButtons(tpl)
  const isSaving = workingKey === `save-${item.index}`
  const isRegenerating = workingKey === `regen-${item.index}`
  const cardBusy = isSaving || isRegenerating
  const exampleValues = ensureExampleValues(tpl?.body, tpl?.header, tpl?.example_values)
  const liveBody = substituteTemplateVars(tpl?.body, exampleValues)
  const liveBusiness = exampleValues[1] || 'Northgate Dental'

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
            {isRegenerating ? 'Regenerating…' : 'Regenerate this template'}
          </button>
        </footer>
      </article>
    )
  }

  return (
    <article className={`waSurveyPackGalleryCard waSurveyPackGalleryCardFull${saved ? ' is-saved' : ''}${cardBusy ? ' is-busy' : ''}`}>
      {cardBusy ? <div className="waSurveyPackGalleryBusy">{isRegenerating ? 'Regenerating…' : 'Saving…'}</div> : null}

      <header className="waSurveyPackGalleryHead">
        <div>
          <span className="waSurveyPackSlotLabel">Template {item.index + 1} of 10</span>
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

      <div className="waSurveyPackGalleryBody waSurveyPackGalleryBodyFull">
        <div className="waSurveyPackGalleryPhone waSurveyPackGalleryPhoneFull">
          <WaSurveyPhonePreview
            businessName={liveBusiness}
            renderedBody={liveBody}
            footer={tpl.footer}
            buttons={previewButtonsFromTemplate(tpl)}
            templateName={tpl.telnyx_name}
            approvalStatus="LOCAL_DRAFT"
          />
        </div>

        <div className="waSurveyPackGalleryMeta waSurveyPackGalleryMetaFull">
          <div className="waSurveyPackMetaGrid">
            <div className="waSurveyPackMetaBlock">
              <span className="label">Body</span>
              {editing ? (
                <textarea className="input msgFieldEditorBox" rows={5} value={tpl.body} onChange={(e) => onEdit(item.index, { body: e.target.value })} />
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

            <div className="waSurveyPackMetaBlock waSurveyPackMetaBlockVars">
              <span className="label">Variables (example values)</span>
              {editing ? (
                <div className="waSurveyPackVarEditGrid">
                  {exampleValues.map((val, i) => (
                    <label key={i} className="waSurveyPackVarEditRow">
                      <span className="waSurveyPackVarEditLabel">{`{{${i + 1}}} — ${VAR_LABELS[i] || 'Variable'}`}</span>
                      <input
                        className="input"
                        value={val}
                        onChange={(e) => onEditVariable(item.index, i, e.target.value)}
                      />
                    </label>
                  ))}
                </div>
              ) : (
                <div className="waSurveyPackChipRow">
                  {exampleValues.map((val, i) => (
                    <span key={i} className="waSurveyPackVarChip">{`{{${i + 1}}} → ${val}`}</span>
                  ))}
                </div>
              )}
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
          {editing ? 'Done editing' : 'Edit template'}
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

  useEffect(() => {
    if (!open) return undefined
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
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
          const next = { ...row.template, ...patch }
          if (patch.body !== undefined) {
            next.example_values = ensureExampleValues(next.body, next.header, next.example_values)
          }
          return { ...row, template: next }
        }),
      }
    })
  }

  const editVariable = (index, varIndex, value) => {
    setPack((prev) => {
      if (!prev?.templates) return prev
      return {
        ...prev,
        templates: prev.templates.map((row) => {
          if (row.index !== index || !row.template) return row
          const values = ensureExampleValues(row.template.body, row.template.header, row.template.example_values)
          values[varIndex] = value
          return { ...row, template: { ...row.template, example_values: values } }
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
    const payload = {
      ...item.template,
      example_values: ensureExampleValues(item.template.body, item.template.header, item.template.example_values),
    }
    setWorking(`save-${item.index}`)
    setCardErrors((prev) => ({ ...prev, [item.index]: '' }))
    setError('')
    try {
      const data = await apiFetch(`/admin/wa-survey/types/${encodeURIComponent(surveyTypeId)}/templates/save-pack`, {
        method: 'POST',
        body: JSON.stringify({ templates: [payload] }),
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
      const templates = items.filter((i) => i.template && i.valid).map((i) => ({
        ...i.template,
        example_values: ensureExampleValues(i.template.body, i.template.header, i.template.example_values),
      }))
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
      <div className="waSurveyPackShell waSurveyPackShellNoScroll">
        <header className="waSurveyPackTopBar waSurveyPackTopBarCompact">
          <div className="waSurveyPackTopBarMain">
            <h2>Generate 10 Templates with OpenAI</h2>
            <p className="muted">{surveyTypeName} · one template per screen · edit variables and save individually</p>
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

        <div className="waSurveyPackToolbar waSurveyPackToolbarCompact">
          <label className="waSurveyPackToolbarField">
            <span className="label">Purpose</span>
            <input className="input" value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder="Post-visit feedback…" />
          </label>
          <label className="waSurveyPackToolbarField waSurveyPackToolbarFieldGrow">
            <span className="label">Admin instruction</span>
            <input className="input" value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder="Tone, emoji, CTA…" />
          </label>
          <div className="waSurveyPackToolbarButtons">
            <button type="button" className="btn primary" onClick={generatePack} disabled={working === 'generate'}>
              {working === 'generate' ? 'Generating…' : 'Generate 10'}
            </button>
            {pack ? (
              <button type="button" className="btn" onClick={saveAllValid} disabled={working === 'save-all'}>
                Save all valid
              </button>
            ) : null}
          </div>
        </div>

        <div className="waSurveyPackScroll waSurveyPackScrollFit">
          {items.length ? (
            <div className="waSurveyPackGallery waSurveyPackGallerySingle">
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
                  onEditVariable={editVariable}
                  onSave={saveOne}
                  onRegenerate={regenerateOne}
                />
              ))}
            </div>
          ) : (
            <div className="waSurveyPackEmpty">
              <p>Generate a 10-template pack. Each template fills the screen with live WhatsApp preview — edit body, footer, and variables, then save.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
