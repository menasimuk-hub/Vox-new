import React, { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatWaSurveyError } from '../lib/waSurveyFeedback'
import WaSurveyPhonePreview from './WaSurveyPhonePreview'

function PackTemplateCard({ item, selected, onToggle, onEdit }) {
  const tpl = item.template
  if (!tpl) {
    return (
      <div className="waSurveyPackCard waSurveyPackCardInvalid">
        <strong>Invalid template #{item.index + 1}</strong>
        <ul>{(item.errors || []).map((e) => <li key={e}>{e}</li>)}</ul>
      </div>
    )
  }
  const preview = tpl.preview || {}
  return (
    <div className={`waSurveyPackCard ${selected ? 'is-selected' : ''}`}>
      <label className="checkRow waSurveyPackSelect">
        <input type="checkbox" checked={selected} onChange={() => onToggle(item.index)} />
        <strong>{tpl.title || tpl.template_name}</strong>
      </label>
      <p className="muted">{tpl.purpose} · {tpl.variant_type} · {tpl.button_type}</p>
      <p className="fieldHint">Telnyx name: {tpl.telnyx_name}</p>
      <label className="msgFieldBlock">
        <span className="label">Body</span>
        <textarea className="input msgFieldEditorBox" rows={4} value={tpl.body} onChange={(e) => onEdit(item.index, { body: e.target.value })} />
      </label>
      <label className="msgFieldBlock">
        <span className="label">Footer</span>
        <input className="input" value={tpl.footer} onChange={(e) => onEdit(item.index, { footer: e.target.value })} />
      </label>
      <WaSurveyPhonePreview
        businessName={tpl.example_values?.[1] || 'Northgate Dental'}
        renderedBody={preview.rendered_body || tpl.body}
        footer={preview.footer || tpl.footer}
        buttons={preview.buttons || tpl.buttons_preview || []}
        templateName={tpl.telnyx_name}
        approvalStatus="LOCAL_DRAFT"
      />
    </div>
  )
}

export default function WaSurveyTemplatePackModal({ surveyTypeId, surveyTypeName, open, onClose, onSaved }) {
  const [instruction, setInstruction] = useState('')
  const [purpose, setPurpose] = useState('')
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [pack, setPack] = useState(null)
  const [selected, setSelected] = useState(() => new Set())

  const reset = () => {
    setInstruction('')
    setPurpose('')
    setError('')
    setMsg('')
    setPack(null)
    setSelected(new Set())
  }

  useEffect(() => {
    if (!open) reset()
  }, [open])

  const items = useMemo(() => (Array.isArray(pack?.templates) ? pack.templates : []), [pack])

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
      setSelected(new Set((data.templates || []).filter((i) => i.template).map((i) => i.index)))
      setMsg(formatActionSuccess(data, `Generated ${data.valid_count || 0} valid template(s) with OpenAI`).message)
    } catch (e) {
      setError(formatWaSurveyError(e, 'OpenAI template generation failed').message)
    } finally {
      setWorking('')
    }
  }

  const showOk = (result, fallback) => {
    setMsg(formatActionSuccess(result, fallback).message)
  }

  const toggle = (index) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
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

  const saveSelected = async () => {
    setWorking('save')
    setError('')
    try {
      const templates = items.filter((i) => selected.has(i.index) && i.template).map((i) => i.template)
      const data = await apiFetch(`/admin/wa-survey/types/${encodeURIComponent(surveyTypeId)}/templates/save-pack`, {
        method: 'POST',
        body: JSON.stringify({ templates }),
      })
      showOk(data, `Saved ${data.saved_count} draft template(s)`)
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
            <p className="muted">{surveyTypeName} — drafts only until you push to Telnyx</p>
          </div>
          <button type="button" className="btn ghost" onClick={onClose}>Close</button>
        </div>

        {error ? <div className="alert error"><strong>{error}</strong></div> : null}
        {msg ? <div className="alert ok"><strong>{msg}</strong></div> : null}

        <div className="waSurveyModalBody waSurveyPackBody">
          <section className="card">
            <div className="cardHead"><h3>Generation settings</h3></div>
            <div className="cardBody grid2">
              <label className="msgFieldBlock span2">
                <span className="label">Template purpose (optional)</span>
                <input className="input" value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder="e.g. post-visit feedback, reminders" />
              </label>
              <label className="msgFieldBlock span2">
                <span className="label">Admin instruction (optional)</span>
                <textarea className="input" rows={3} value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder="Tone, industry, or mix preferences" />
              </label>
              <div className="span2 btnRow">
                <button type="button" className="btn primary" onClick={generatePack} disabled={working === 'generate'}>
                  {working === 'generate' ? 'Generating…' : 'Generate 10 Templates with OpenAI'}
                </button>
                {pack ? (
                  <button type="button" className="btn" onClick={saveSelected} disabled={working === 'save' || selected.size === 0}>
                    {working === 'save' ? 'Saving…' : `Save ${selected.size} selected as drafts`}
                  </button>
                ) : null}
              </div>
              {pack?.openai ? (
                <p className="fieldHint span2">Model: {pack.openai.model} · API: {pack.openai.api_style}</p>
              ) : null}
            </div>
          </section>

          {items.length ? (
            <section className="card">
              <div className="cardHead"><h3>Generated pack ({pack.valid_count}/{pack.generated_count} valid)</h3></div>
              <div className="cardBody waSurveyPackGrid">
                {items.map((item) => (
                  <PackTemplateCard
                    key={item.index}
                    item={item}
                    selected={selected.has(item.index)}
                    onToggle={toggle}
                    onEdit={editTemplate}
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
