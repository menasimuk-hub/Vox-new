import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatWaSurveyError } from '../lib/waSurveyFeedback'
import { resolveTelnyxSyncLabel, telnyxSyncPillClass, validateCategoryBeforeSync } from '../lib/waSurveyTelnyxSync'
import WaSurveyTemplateModal from '../components/WaSurveyTemplateModal'

const KIND_OPTIONS = [
  { value: 'welcome', label: 'Welcome' },
  { value: 'thank_you', label: 'Thank you' },
  { value: 'tell_us_more', label: 'Tell us more' },
]

function kindLabel(kind) {
  return KIND_OPTIONS.find((k) => k.value === kind)?.label || kind
}

export default function WaSurveySystemTemplates() {
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [errorDetail, setErrorDetail] = useState('')
  const [msg, setMsg] = useState('')
  const [kinds, setKinds] = useState([])
  const [modalTemplateId, setModalTemplateId] = useState(null)
  const [modalTemplate, setModalTemplate] = useState(null)
  const [genKind, setGenKind] = useState('welcome')
  const [genInstruction, setGenInstruction] = useState('')
  const [genCount, setGenCount] = useState(2)
  const [genResult, setGenResult] = useState(null)
  const [selectedGen, setSelectedGen] = useState({})

  const clearFeedback = () => {
    setError('')
    setErrorDetail('')
    setMsg('')
  }

  const showError = (err, fallback = 'Request failed') => {
    const formatted = formatWaSurveyError(err, fallback)
    setError(formatted.message)
    setErrorDetail(formatted.detailText !== formatted.message ? formatted.detailText : '')
    setMsg('')
  }

  const showOk = (result, fallback = 'Done') => {
    const formatted = formatActionSuccess(result, fallback)
    setError('')
    setErrorDetail('')
    setMsg(formatted.message)
  }

  const load = useCallback(async () => {
    setLoading(true)
    clearFeedback()
    try {
      const data = await apiFetch('/admin/wa-survey/system-templates')
      setKinds(Array.isArray(data?.kinds) ? data.kinds : [])
    } catch (e) {
      showError(e, 'Could not load global system templates')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const surveyTypeIdForKind = useMemo(() => {
    const map = {}
    for (const k of kinds) {
      if (k.kind && k.survey_type_id) map[k.kind] = k.survey_type_id
    }
    return map
  }, [kinds])

  const createDraft = async (kind) => {
    setWorking(`create-${kind}`)
    clearFeedback()
    try {
      await apiFetch('/admin/wa-survey/system-templates', {
        method: 'POST',
        body: JSON.stringify({ system_template_kind: kind }),
      })
      showOk(null, `Created new ${kindLabel(kind)} draft.`)
      await load()
    } catch (e) {
      showError(e, `Could not create ${kindLabel(kind)} template`)
    } finally {
      setWorking('')
    }
  }

  const deleteTemplate = async (tpl, kind) => {
    if (!window.confirm(`Delete “${tpl.display_name || tpl.name}”? This removes it from Telnyx when synced.`)) return
    setWorking(`delete-${tpl.id}`)
    clearFeedback()
    try {
      await apiFetch(`/admin/wa-survey/system-templates/${encodeURIComponent(tpl.id)}`, { method: 'DELETE' })
      showOk(null, 'Template deleted.')
      await load()
    } catch (e) {
      showError(e, 'Could not delete template')
    } finally {
      setWorking('')
    }
  }

  const pushOne = async (tpl) => {
    const catErr = validateCategoryBeforeSync(tpl)
    if (catErr) {
      showError({ message: catErr }, 'Fix category before sync')
      return
    }
    setWorking(`push-${tpl.id}`)
    clearFeedback()
    try {
      const result = await apiFetch(`/admin/wa-survey/templates/${encodeURIComponent(tpl.id)}/push`, {
        method: 'POST',
        body: '{}',
      })
      showOk(result, 'Pushed to Telnyx.')
      await load()
    } catch (e) {
      showError(e, 'Telnyx sync failed')
    } finally {
      setWorking('')
    }
  }

  const runGenerate = async () => {
    setWorking('generate')
    clearFeedback()
    setGenResult(null)
    setSelectedGen({})
    try {
      const data = await apiFetch('/admin/wa-survey/system-templates/generate', {
        method: 'POST',
        body: JSON.stringify({
          system_template_kind: genKind,
          instruction: genInstruction,
          count: Number(genCount) || 1,
        }),
      })
      setGenResult(data)
      const next = {}
      ;(data?.templates || []).forEach((row, idx) => {
        if (row.valid && row.template) next[idx] = true
      })
      setSelectedGen(next)
      showOk(data, `Generated ${data.valid_count || 0} valid template(s).`)
    } catch (e) {
      showError(e, 'OpenAI generation failed')
    } finally {
      setWorking('')
    }
  }

  const saveGenerated = async () => {
    if (!genResult) return
    const picked = (genResult.templates || []).filter((row, idx) => selectedGen[idx] && row.valid && row.template)
    if (!picked.length) {
      showError({ message: 'Select at least one valid generated template.' }, 'Nothing selected')
      return
    }
    setWorking('save-gen')
    clearFeedback()
    try {
      const result = await apiFetch('/admin/wa-survey/system-templates/save-generated', {
        method: 'POST',
        body: JSON.stringify({
          system_template_kind: genResult.system_template_kind || genKind,
          instruction: genInstruction,
          templates: picked.map((row) => row.template),
        }),
      })
      showOk(result, 'Saved generated templates.')
      setGenResult(null)
      setSelectedGen({})
      await load()
    } catch (e) {
      showError(e, 'Could not save generated templates')
    } finally {
      setWorking('')
    }
  }

  return (
    <div className="content">
      <div className="breadcrumb">
        <Link to="/settings/wa-survey">WA Survey</Link>
        <span> / Global System Templates</span>
      </div>

      <div className="pageHead">
        <div>
          <h1>Global System Templates</h1>
          <p className="muted">
            Shared welcome, thank-you, and tell-us-more WhatsApp templates used across all industries.
            Customers pick welcome and thank-you templates when creating a survey.
          </p>
        </div>
      </div>

      {error ? (
        <div className="note" style={{ borderColor: 'var(--red)', color: 'var(--red)' }}>
          {error}
          {errorDetail ? <div className="fieldHint">{errorDetail}</div> : null}
        </div>
      ) : null}
      {msg ? <div className="note">{msg}</div> : null}

      <section className="card">
        <div className="cardHead">
          <h2>Generate with OpenAI</h2>
        </div>
        <div className="cardBody orgProfileGrid2">
          <div className="formField">
            <label className="label" htmlFor="sys-kind">Template type</label>
            <select id="sys-kind" className="select" value={genKind} onChange={(e) => setGenKind(e.target.value)}>
              {KIND_OPTIONS.map((k) => (
                <option key={k.value} value={k.value}>{k.label}</option>
              ))}
            </select>
          </div>
          <div className="formField">
            <label className="label" htmlFor="sys-count">Variants to generate</label>
            <input
              id="sys-count"
              className="input"
              type="number"
              min={1}
              max={6}
              value={genCount}
              onChange={(e) => setGenCount(e.target.value)}
            />
            <p className="fieldHint">Typically 2 per type — not limited to 2.</p>
          </div>
          <div className="formField span-12" style={{ gridColumn: '1 / -1' }}>
            <label className="label" htmlFor="sys-instruction">Optional instructions</label>
            <textarea
              id="sys-instruction"
              className="input"
              rows={3}
              value={genInstruction}
              onChange={(e) => setGenInstruction(e.target.value)}
              placeholder="e.g. Warm UK tone, mention it only takes a minute…"
            />
          </div>
          <div className="actions">
            <button type="button" className="btn primary" disabled={working === 'generate'} onClick={() => void runGenerate()}>
              {working === 'generate' ? 'Generating…' : 'Generate drafts'}
            </button>
            {genResult ? (
              <button type="button" className="btn soft" disabled={working === 'save-gen'} onClick={() => void saveGenerated()}>
                {working === 'save-gen' ? 'Saving…' : 'Save selected'}
              </button>
            ) : null}
          </div>
        </div>
        {genResult?.templates?.length ? (
          <div className="cardBody" style={{ borderTop: '1px solid var(--line)' }}>
            <p className="formSectionTitle">Generated previews</p>
            <div className="tableWrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Use</th>
                    <th>Name</th>
                    <th>Body preview</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {genResult.templates.map((row, idx) => {
                    const tpl = row.template || {}
                    const valid = Boolean(row.valid)
                    return (
                      <tr key={idx}>
                        <td>
                          <input
                            type="checkbox"
                            disabled={!valid}
                            checked={Boolean(selectedGen[idx])}
                            onChange={(e) => setSelectedGen((prev) => ({ ...prev, [idx]: e.target.checked }))}
                          />
                        </td>
                        <td>{tpl.title || tpl.template_name || '—'}</td>
                        <td>{String(tpl.body || '').slice(0, 120)}{String(tpl.body || '').length > 120 ? '…' : ''}</td>
                        <td>{valid ? 'Valid' : (row.errors || []).join('; ') || 'Invalid'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </section>

      {loading ? (
        <div className="card"><div className="cardBody muted">Loading…</div></div>
      ) : (
        kinds.map((section) => (
          <section className="card" key={section.kind}>
            <div className="cardHead">
              <h2>
                {section.label || kindLabel(section.kind)}
                <span className="muted" style={{ fontWeight: 500, marginLeft: 8 }}>
                  ({section.count ?? (section.templates || []).length} template{(section.count ?? (section.templates || []).length) === 1 ? '' : 's'})
                </span>
              </h2>
              <div className="actions">
                <button
                  type="button"
                  className="btn sm primary"
                  disabled={working === `create-${section.kind}`}
                  onClick={() => void createDraft(section.kind)}
                >
                  {working === `create-${section.kind}` ? 'Creating…' : 'New template'}
                </button>
              </div>
            </div>
            <div className="cardBody">
              <p className="fieldHint" style={{ marginBottom: 12 }}>
                {section.kind === 'welcome' && 'Opening message — customers choose one when creating a survey.'}
                {section.kind === 'thank_you' && 'Closing message — customers choose one when creating a survey.'}
                {section.kind === 'tell_us_more' && 'Low-rating follow-up — applied automatically (not shown in customer picker).'}
              </p>
              {(section.templates || []).length ? (
                <div className="waSurveySystemTemplateList">
                  {section.templates.map((tpl) => (
                    <article key={tpl.id} className="waSurveySystemTemplateCard">
                      <div className="waSurveySystemTemplateMain">
                        <p className="waSurveySystemTemplateTitle">{tpl.display_name || tpl.name || 'Untitled template'}</p>
                        <div className="waSurveySystemTemplateMeta">
                          <span>{tpl.language || '—'}</span>
                          <span className={`pill ${telnyxSyncPillClass(resolveTelnyxSyncLabel(tpl))}`}>
                            {resolveTelnyxSyncLabel(tpl)}
                          </span>
                          <span>{tpl.active_for_survey ? 'Active' : 'Inactive'}</span>
                        </div>
                      </div>
                      <div className="waSurveySystemTemplateActions">
                        <button
                          type="button"
                          className="btn sm"
                          onClick={() => {
                            setModalTemplate({
                              ...tpl,
                              system_template_kind: tpl.system_template_kind || section.kind,
                            })
                            setModalTemplateId(tpl.id)
                          }}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          className="btn sm soft"
                          disabled={working === `push-${tpl.id}`}
                          onClick={() => void pushOne(tpl)}
                        >
                          {working === `push-${tpl.id}` ? 'Syncing…' : 'Sync to Telnyx'}
                        </button>
                        <button
                          type="button"
                          className="btn sm soft danger"
                          disabled={working === `delete-${tpl.id}`}
                          onClick={() => void deleteTemplate(tpl, section.kind)}
                        >
                          {working === `delete-${tpl.id}` ? 'Deleting…' : 'Delete'}
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="muted">No templates yet — create one or generate with OpenAI.</p>
              )}
            </div>
          </section>
        ))
      )}

      <WaSurveyTemplateModal
        templateId={modalTemplateId}
        initialTemplate={modalTemplate}
        surveyTypeId={
          surveyTypeIdForKind[modalTemplate?.system_template_kind]
          || modalTemplate?.survey_type_id
          || kinds.find((k) => k.kind === modalTemplate?.system_template_kind)?.survey_type_id
        }
        open={Boolean(modalTemplateId)}
        onClose={() => {
          setModalTemplateId(null)
          setModalTemplate(null)
        }}
        onSaved={() => void load()}
      />
    </div>
  )
}
