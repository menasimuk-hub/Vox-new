import React, { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatWaSurveyError } from '../lib/waSurveyFeedback'
import WaSurveyPhonePreview from './WaSurveyPhonePreview'

const PAGE_SIZE = 2

function formatButtons(tpl) {
  const preview = tpl?.preview || {}
  const raw = preview.buttons || tpl?.buttons_preview || []
  if (Array.isArray(raw) && raw.length) {
    return raw.map((b, i) => ({
      key: `${b.label || b.text || i}`,
      label: b.label || b.text || 'Button',
      url: b.url || '',
      phone: b.phone_number || '',
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
  }))
}

function PackTemplateReviewCard({
  item,
  editing,
  saved,
  workingKey,
  onToggleEdit,
  onEdit,
  onSave,
  onRegenerate,
}) {
  const tpl = item.template
  const preview = tpl?.preview || {}
  const buttons = formatButtons(tpl)
  const cardWorking = workingKey === `save-${item.index}` || workingKey === `regen-${item.index}`

  if (!tpl) {
    return (
      <article className="waSurveyPackReviewCard waSurveyPackReviewCardInvalid">
        <header className="waSurveyPackReviewHead">
          <strong>Template #{item.index + 1} — invalid</strong>
        </header>
        <ul className="waSurveyPackErrorList">
          {(item.errors || []).map((e) => <li key={e}>{e}</li>)}
        </ul>
        <div className="waSurveyPackReviewActions">
          <button type="button" className="btn sm" disabled={cardWorking} onClick={() => onRegenerate(item)}>
            {workingKey === `regen-${item.index}` ? 'Regenerating…' : 'Regenerate'}
          </button>
        </div>
      </article>
    )
  }

  return (
    <article className={`waSurveyPackReviewCard${saved ? ' is-saved' : ''}`}>
      <header className="waSurveyPackReviewHead">
        <div>
          <strong>{tpl.title || tpl.template_name}</strong>
          <p className="muted waSurveyPackReviewMetaLine">
            {tpl.purpose} · {tpl.variant_type} · {tpl.button_type}
          </p>
        </div>
        {saved ? <span className="waSurveyPackSavedBadge">Saved</span> : null}
      </header>

      <div className="waSurveyPackReviewLayout">
        <div className="waSurveyPackReviewPreview">
          <WaSurveyPhonePreview
            businessName={tpl.example_values?.[1] || 'Northgate Dental'}
            renderedBody={preview.rendered_body || tpl.body}
            footer={preview.footer || tpl.footer}
            buttons={preview.buttons || tpl.buttons_preview || []}
            templateName={tpl.telnyx_name}
            approvalStatus="LOCAL_DRAFT"
          />
        </div>

        <div className="waSurveyPackReviewDetails">
          {item.errors?.length ? (
            <ul className="waSurveyPackErrorList">
              {item.errors.map((e) => <li key={e}>{e}</li>)}
            </ul>
          ) : null}

          <dl className="waSurveyPackDetailList">
            <div>
              <dt>Variables</dt>
              <dd>
                {(tpl.example_values || []).map((val, i) => (
                  <span key={i} className="waSurveyPackVarChip">{`{{${i + 1}}} = ${val}`}</span>
                ))}
              </dd>
            </div>
            <div>
              <dt>Buttons</dt>
              <dd>
                {buttons.length ? buttons.map((b) => (
                  <span key={b.key} className="waSurveyPackBtnChip">{b.label}</span>
                )) : <span className="muted">None (plain text)</span>}
              </dd>
            </div>
            <div>
              <dt>Telnyx name</dt>
              <dd className="fieldHint">{tpl.telnyx_name}</dd>
            </div>
          </dl>

          {editing ? (
            <>
              <label className="msgFieldBlock">
                <span className="label">Body</span>
                <textarea className="input msgFieldEditorBox" rows={5} value={tpl.body} onChange={(e) => onEdit(item.index, { body: e.target.value })} />
              </label>
              <label className="msgFieldBlock">
                <span className="label">Footer</span>
                <input className="input" value={tpl.footer} onChange={(e) => onEdit(item.index, { footer: e.target.value })} />
              </label>
            </>
          ) : (
            <>
              <div className="waSurveyPackTextBlock">
                <span className="label">Body</span>
                <p>{tpl.body}</p>
              </div>
              <div className="waSurveyPackTextBlock">
                <span className="label">Footer</span>
                <p>{tpl.footer}</p>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="waSurveyPackReviewActions">
        <button type="button" className="btn primary sm" disabled={cardWorking || !item.valid} onClick={() => onSave(item)}>
          {workingKey === `save-${item.index}` ? 'Saving…' : 'Save'}
        </button>
        <button type="button" className="btn sm" disabled={cardWorking} onClick={() => onRegenerate(item)}>
          {workingKey === `regen-${item.index}` ? 'Regenerating…' : 'Regenerate'}
        </button>
        <button type="button" className="btn ghost sm" onClick={() => onToggleEdit(item.index)}>
          {editing ? 'Done editing' : 'Edit'}
        </button>
      </div>
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

  const reset = () => {
    setInstruction('')
    setPurpose('')
    setError('')
    setMsg('')
    setPack(null)
    setPage(0)
    setEditing(new Set())
    setSavedIndices(new Set())
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
    setError('')
    try {
      const data = await apiFetch(`/admin/wa-survey/types/${encodeURIComponent(surveyTypeId)}/templates/save-pack`, {
        method: 'POST',
        body: JSON.stringify({ templates: [item.template] }),
      })
      setSavedIndices((prev) => new Set(prev).add(item.index))
      setMsg(formatActionSuccess(data, `Saved “${item.template.title || item.template.template_name}” as draft`).message)
      onSaved?.()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not save template').message)
    } finally {
      setWorking('')
    }
  }

  const regenerateOne = async (item) => {
    setWorking(`regen-${item.index}`)
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
      setMsg(formatActionSuccess(data, `Regenerated template #${item.index + 1}`).message)
    } catch (e) {
      setError(formatWaSurveyError(e, 'Regenerate failed').message)
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
    <div className="waSurveyModalBackdrop" role="dialog" aria-modal="true">
      <div className="waSurveyModal waSurveyPackModal">
        <div className="waSurveyModalHead">
          <div>
            <h2>Generate 10 Templates with OpenAI</h2>
            <p className="muted">{surveyTypeName} — review 2 at a time, save or regenerate individually</p>
          </div>
          <button type="button" className="btn ghost" onClick={onClose}>Close</button>
        </div>

        {error ? <div className="alert error"><strong>{error}</strong></div> : null}
        {msg ? <div className="alert ok"><strong>{msg}</strong></div> : null}

        <div className="waSurveyModalBody waSurveyPackBody">
          <section className="card waSurveyPackSettings">
            <div className="cardHead"><h3>Generation settings</h3></div>
            <div className="cardBody grid2">
              <label className="msgFieldBlock span2">
                <span className="label">Template purpose (optional)</span>
                <input className="input" value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder="e.g. post-visit feedback, reminders" />
              </label>
              <label className="msgFieldBlock span2">
                <span className="label">Admin instruction (optional)</span>
                <textarea className="input" rows={3} value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder="Tone, emoji level, industry, CTA style…" />
              </label>
              <div className="span2 btnRow">
                <button type="button" className="btn primary" onClick={generatePack} disabled={working === 'generate'}>
                  {working === 'generate' ? 'Generating…' : 'Generate 10 Templates with OpenAI'}
                </button>
                {pack ? (
                  <button type="button" className="btn" onClick={saveAllValid} disabled={working === 'save-all'}>
                    {working === 'save-all' ? 'Saving all…' : 'Save all valid drafts'}
                  </button>
                ) : null}
              </div>
              {pack?.openai ? (
                <p className="fieldHint span2">Model: {pack.openai.model} · API: {pack.openai.api_style}</p>
              ) : null}
            </div>
          </section>

          {items.length ? (
            <section className="card waSurveyPackReviewSection">
              <div className="cardHead waSurveyPackReviewToolbar">
                <h3>Preview pack ({pack.valid_count}/{pack.generated_count} valid)</h3>
                <div className="waSurveyPackPager">
                  <button type="button" className="btn sm ghost" disabled={page <= 0} onClick={() => setPage((p) => p - 1)}>
                    Previous
                  </button>
                  <span className="waSurveyPackPagerLabel">Page {page + 1} of {totalPages}</span>
                  <button type="button" className="btn sm ghost" disabled={page >= totalPages - 1} onClick={() => setPage((p) => p + 1)}>
                    Next
                  </button>
                </div>
              </div>
              <div className="cardBody waSurveyPackReviewGrid">
                {pageItems.map((item) => (
                  <PackTemplateReviewCard
                    key={item.index}
                    item={item}
                    editing={editing.has(item.index)}
                    saved={savedIndices.has(item.index)}
                    workingKey={working}
                    onToggleEdit={toggleEdit}
                    onEdit={editTemplate}
                    onSave={saveOne}
                    onRegenerate={regenerateOne}
                  />
                ))}
              </div>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  )
}
